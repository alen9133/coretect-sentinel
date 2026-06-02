"""
CORETECT Sentinel — 达锂（DY / KVMS）BMS 驱动
协议：RS485 Modbus RTU，9600 8N1，无校验
请求地址：0x81，响应地址：0x51（这是该设备的固定设计）
支持功能码：FC-03（读）/ FC-06（写单个）/ FC-10（写多个）
文档版本：KVMS内网通信UART协议_客户版

硬件：HaaS506-ED1 RS485 口 (uart2)
"""

import time
from machine import UART
from bms_common import (
    build_read_req, build_write_single_req,
    verify_crc, u16be, i16be
)

# 达锂 BMS 固定地址（不可修改）
_SLAVE_ADDR_REQ  = 0x81   # 发送请求时使用的从机地址
_SLAVE_ADDR_RESP = 0x51   # 从机响应时返回的地址

# ─── 寄存器地址定义 ────────────────────────────────────────────────────────────
# 全部寄存器为 16-bit，大端（高位在前）
REG_CELL_V_START  = 0x0000   # 0x00~0x2F：单体电压（每格 2 字节 = 0.001V）
REG_TEMP_START    = 0x0030   # 0x30~0x37：温度（偏移40，即0→-40℃）
REG_PACK_VOL      = 0x0038   # 总电压（0.1V）
REG_CURRENT       = 0x0039   # 电流（offset 30000，0.1A，>30000=充电）
REG_SOC           = 0x003A   # SOC（×0.001，即 800→80.0%）
REG_LIFE          = 0x003B   # 心跳包
REG_CELL_COUNT    = 0x003C   # 电池数量
REG_TEMP_COUNT    = 0x003D   # 温度传感器数量
REG_MAX_CELL_V    = 0x003E   # 最高单体电压 (mV)
REG_MAX_CELL_IDX  = 0x003F   # 最高单体编号
REG_MIN_CELL_V    = 0x0040   # 最低单体电压 (mV)
REG_MIN_CELL_IDX  = 0x0041   # 最低单体编号
REG_DELTA_V       = 0x0042   # 压差 (mV)
REG_MAX_TEMP      = 0x0043   # 最高温度（偏移40）
REG_MIN_TEMP      = 0x0045   # 最低温度（偏移40）
REG_CHARGE_STATE  = 0x0048   # 充放电状态（0静止 1充电 2放电）
REG_CHARGER_STA   = 0x0049   # 充电器状态
REG_LOAD_STA      = 0x004A   # 负载状态
REG_REMAIN_CAP    = 0x004B   # 剩余容量（0.1AH）
REG_CYCLES        = 0x004C   # 循环次数
REG_BAL_STATE     = 0x004D   # 均衡状态（0关 1被动 2主动）
REG_CHG_MOS       = 0x0052   # 充电MOS（0关 1开）
REG_DCH_MOS       = 0x0053   # 放电MOS（0关 1开）
REG_PRE_MOS       = 0x0054   # 预充MOS
REG_HEAT_MOS      = 0x0055   # 加热MOS
REG_AVG_V         = 0x0057   # 平均电压 (mV)
REG_POWER         = 0x0058   # 功率 (W)
REG_ENERGY        = 0x0059   # 能量 (Wh)
REG_MOS_TEMP      = 0x005A   # MOS温度（偏移40）
REG_ENV_TEMP      = 0x005B   # 环境温度（偏移40）
REG_FAULT_0_1     = 0x006D   # 新故障码 0-1
REG_FAULT_2_3     = 0x006E   # 新故障码 2-3
REG_FAULT_4_5     = 0x006F   # 新故障码 4-5
REG_FAULT_6_7     = 0x0070   # 新故障码 6-7
REG_FAULT_10_11   = 0x0072   # 新故障码 10-11（硬件故障）
REG_FAULT_12_13   = 0x0073   # 新故障码 12-13（MOS故障）

# ─── 一次性读取范围（分两段）─────────────────────────────────────────────────
# 段1：0x0000 ~ 0x005F（96个寄存器）——单体电压+温度+主要状态
# 段2：0x006D ~ 0x007E（18个寄存器）——故障码
_SEG1_START = 0x0000
_SEG1_COUNT = 0x0060   # 96
_SEG2_START = 0x006D
_SEG2_COUNT = 0x0012   # 18


class DYBMS:
    """
    达锂 DY / KVMS BMS RS485 Modbus 驱动

    注意：该 BMS 固定使用 0x81 作为请求地址，0x51 作为响应地址，
    这是厂家设计，不可更改。

    用法：
        bms = DYBMS(uart_id=2)
        data = bms.read_all()
        if data:
            print(data['soc'], data['pack_voltage'])
    """

    def __init__(self, uart_id: int = 2,
                 tx_pin: int = 17, rx_pin: int = 18,
                 timeout_ms: int = 500):
        self.timeout = timeout_ms
        self.uart = UART(uart_id, baudrate=9600, bits=8, parity=None, stop=1,
                         tx=tx_pin, rx=rx_pin,
                         timeout=timeout_ms, timeout_char=80)
        time.sleep_ms(100)

    # ─── 内部：发送并接收 ──────────────────────────────────────────────────────

    def _query(self, reg_start: int, reg_count: int) -> bytes | None:
        """
        发 FC-03 请求（地址 0x81），等待地址 0x51 的响应
        返回数据字节，失败返回 None
        """
        req = build_read_req(_SLAVE_ADDR_REQ, reg_start, reg_count)
        self.uart.read()          # 清空
        self.uart.write(req)
        time.sleep_ms(self.timeout)
        raw = self.uart.read()
        if not raw or len(raw) < 5:
            return None

        # 达锂响应地址是 0x51（不是 0x81）
        if not verify_crc(raw):
            return None
        if raw[0] != _SLAVE_ADDR_RESP:
            return None
        if raw[1] & 0x80:         # 从机错误响应
            return None
        if raw[1] != 0x03:
            return None

        data_len = raw[2]
        if len(raw) != data_len + 5:
            return None
        return raw[3: 3 + data_len]

    # ─── 读取全部关键数据 ─────────────────────────────────────────────────────

    def read_all(self) -> dict | None:
        """读取达锂 BMS 全部关键数据，返回统一 JSON 字典。失败返回 None。"""
        seg1 = self._query(_SEG1_START, _SEG1_COUNT)
        if seg1 is None:
            return None

        seg2 = self._query(_SEG2_START, _SEG2_COUNT)
        if seg2 is None:
            return None

        return self._parse(seg1, seg2)

    # ─── 解析 ─────────────────────────────────────────────────────────────────

    def _parse(self, seg1: bytes, seg2: bytes) -> dict:
        """
        seg1: 寄存器 0x0000 开始的数据（192字节 = 96寄存器×2）
        seg2: 寄存器 0x006D 开始的数据（36字节 = 18寄存器×2）
        """

        def r1(reg: int) -> int:
            """从 seg1 读寄存器（相对 0x0000）"""
            off = reg * 2
            return u16be(seg1, off)

        def r1s(reg: int) -> int:
            """从 seg1 读有符号寄存器"""
            off = reg * 2
            return i16be(seg1, off)

        def r2(reg: int) -> int:
            """从 seg2 读寄存器（相对 0x006D）"""
            off = (reg - 0x006D) * 2
            return u16be(seg2, off)

        # ── 基本信息 ──────────────────────────────────────────────────────────
        cell_count  = r1(REG_CELL_COUNT)
        temp_count  = r1(REG_TEMP_COUNT)
        cell_count  = min(cell_count, 48)   # 最多支持 48 节

        # ── 单体电压（寄存器 0x00~0x2F，值×0.001=V）─────────────────────────
        cells = []
        for i in range(cell_count):
            mv = r1(i)
            cells.append(round(mv / 1000.0, 3))

        # ── 温度（寄存器 0x30~0x37，值-40=℃）────────────────────────────────
        temps = []
        for i in range(min(temp_count, 8)):
            raw_t = r1(REG_TEMP_START + i)
            if raw_t != 0:
                temps.append(raw_t - 40)

        # ── 电流（偏移 30000，0.1A，充正放负）────────────────────────────────
        cur_raw  = r1(REG_CURRENT)
        current_a = round((cur_raw - 30000) / 10.0, 1)

        # ── 电压（0.1V）──────────────────────────────────────────────────────
        pack_v = round(r1(REG_PACK_VOL) / 10.0, 2)

        # ── SOC（×0.001）─────────────────────────────────────────────────────
        soc = round(r1(REG_SOC) / 10.0, 1)   # 800 → 80.0%

        # ── 功率（W，用电压电流计算，符号跟随电流）───────────────────────────
        power_w = round(pack_v * current_a, 1)

        # ── 温度统计 ──────────────────────────────────────────────────────────
        if temps:
            temp_avg = round(sum(temps) / len(temps), 1)
            temp_max = max(temps)
        else:
            temp_avg = temp_max = 0.0

        mos_temp = r1(REG_MOS_TEMP) - 40
        env_temp = r1(REG_ENV_TEMP) - 40

        # ── 压差 ─────────────────────────────────────────────────────────────
        delta_v_mv = r1(REG_DELTA_V)

        # ── 剩余容量（0.1AH）────────────────────────────────────────────────
        remain_ah = round(r1(REG_REMAIN_CAP) / 10.0, 1)

        # ── 故障码解析 ────────────────────────────────────────────────────────
        f01 = r2(REG_FAULT_0_1)
        f23 = r2(REG_FAULT_2_3)
        f45 = r2(REG_FAULT_4_5)
        f67 = r2(REG_FAULT_6_7)

        # f01 低字节：bit[2:0]=单体过压等级, bit[5:3]=单体欠压等级
        # f01 高字节：bit[2:0]=压差过大等级, bit[5:3]=充电高温等级
        # f45 低字节：bit6=短路保护
        # f45 高字节：bit6=低压禁止充电, bit7=高压禁止放电
        cell_ovp_level  = f01 & 0x0007
        cell_uvp_level  = (f01 >> 3) & 0x0007
        delta_alarm     = (f01 >> 8) & 0x0007
        ch_otp_level    = (f01 >> 11) & 0x0007
        dch_otp_level   = (f23 >> 3) & 0x0007
        ch_ocp_level    = (f45 >> 8) & 0x0007
        dch_ocp_level   = (f45 >> 11) & 0x0007
        short_circuit   = (f45 >> 6) & 0x0001

        # 任意等级 > 0 视为告警
        result = {
            "brand":           "DY",
            "soc":             soc,
            "soh":             0,            # DY 协议无 SOH 字段
            "pack_voltage":    pack_v,
            "pack_current":    current_a,
            "power_w":         power_w,
            "temperature_avg": temp_avg,
            "temperature_max": temp_max,
            "mos_temperature": float(mos_temp),
            "env_temperature": float(env_temp),
            "delta_v":         round(delta_v_mv / 1000.0, 3),
            "cell_count":      cell_count,
            "remain_ah":       remain_ah,
            "full_capacity_ah": 0.0,         # 需另外读配置寄存器
            "cycle_count":     r1(REG_CYCLES),
            "charge_state":    r1(REG_CHARGE_STATE),
            "discharge_state": 1 if r1(REG_CHARGE_STATE) == 2 else 0,
            "balance_state":   r1(REG_BAL_STATE),
            "charger_plugged": r1(REG_CHARGER_STA),
            "charge_mos":      r1(REG_CHG_MOS),
            "discharge_mos":   r1(REG_DCH_MOS),
            # ── 告警位 ───────────────────────────────────────────────────────
            "alarm_cell_ovp":       int(cell_ovp_level > 0),
            "alarm_cell_uvp":       int(cell_uvp_level > 0),
            "alarm_bat_ovp":        int((f45 >> 7) & 1),
            "alarm_bat_uvp":        int((f45 >> 14) & 1),
            "alarm_over_current":   int(ch_ocp_level > 0 or dch_ocp_level > 0),
            "alarm_short_circuit":  int(short_circuit),
            "alarm_over_temp":      int(ch_otp_level > 0 or dch_otp_level > 0),
            "alarm_cell_imbalance": int(delta_alarm > 0 or delta_v_mv > 50),
        }

        # 单体电压
        for i, v in enumerate(cells, start=1):
            result[f"cell_v_{i:02d}"] = v

        return result

    # ─── 控制指令 ──────────────────────────────────────────────────────────────

    def _write_reg(self, reg: int, value: int) -> bool:
        """写单个寄存器（FC-06），使用 0x81 发送"""
        frame = build_write_single_req(_SLAVE_ADDR_REQ, reg, value)
        self.uart.read()
        self.uart.write(frame)
        time.sleep_ms(200)
        resp = self.uart.read()
        # 响应地址应为 0x51
        return resp is not None and len(resp) >= 8 and resp[0] == _SLAVE_ADDR_RESP

    # 达锂控制寄存器地址（需向厂家确认写入控制寄存器地址）
    # 以下为常见实现，可能因固件版本不同而异
    def set_charge_enable(self, enable: bool) -> bool:
        """远程开/关充电 MOS"""
        return self._write_reg(0x010C, 1 if enable else 0)

    def set_discharge_enable(self, enable: bool) -> bool:
        """远程开/关放电 MOS"""
        return self._write_reg(0x010D, 1 if enable else 0)
