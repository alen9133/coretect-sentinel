"""
CORETECT Sentinel — 极空（JK）BMS 驱动
协议：RS485 Modbus RTU，115200 8N1
寄存器基地址：0x1200（实时数据）/ 0x1000（配置参数）
文档版本：极空BMS RS485 Modbus通用协议V1.1

硬件：HaaS506-ED1 RS485 口 (uart2)
"""

import time
from machine import UART
from bms_common import (
    build_read_req, parse_fc03_response,
    u16be, i16be, u32be, i32be
)

# ─── 寄存器基地址 ──────────────────────────────────────────────────────────────
# 注意：表中的"偏移 offset"是字节偏移，Modbus 寄存器地址 = 基地址 + offset/2
_BASE_RT   = 0x1200   # 实时数据 Real-Time
_BASE_CFG  = 0x1000   # 配置参数 Config

# ─── 实时数据寄存器偏移（字节）→ 转成 Modbus 寄存器偏移时 /2 ─────────────────
_OFF_CELL_V0   = 0x0000   # UINT16 x 32，单体电压 (mV)
_OFF_CELL_STA  = 0x0040   # UINT32，电池状态位
_OFF_AVG_V     = 0x0044   # UINT16，平均电压 (mV)
_OFF_DELTA_V   = 0x0046   # UINT16，最大压差 (mV)
_OFF_CELL_NBR  = 0x0048   # UINT8(max) + UINT8(min)，最高/最低编号
_OFF_MOS_TEMP  = 0x008A   # INT16，功率板温度 (0.1°C)
_OFF_BAT_VOL   = 0x0090   # UINT32，总电压 (mV)
_OFF_BAT_WATT  = 0x0094   # UINT32，功率 (mW)
_OFF_BAT_CUR   = 0x0098   # INT32，电流 (mA)，正=充，负=放
_OFF_TEMP1     = 0x009C   # INT16，电池温度1 (0.1°C)
_OFF_TEMP2     = 0x009E   # INT16，电池温度2 (0.1°C)
_OFF_ALARM     = 0x00A0   # UINT32，告警标志位
_OFF_BAL_CUR   = 0x00A4   # INT16，均衡电流 (mA)
_OFF_BAL_SOC   = 0x00A6   # UINT8(均衡状态) + UINT8(SOC %)
_OFF_REMAIN    = 0x00A8   # INT32，剩余容量 (mAh)
_OFF_FULL_CAP  = 0x00AC   # UINT32，实际满容量 (mAh)
_OFF_CYCLES    = 0x00B0   # UINT32，循环次数
_OFF_SOH_PRE   = 0x00B8   # UINT8(SOH%) + UINT8(预充状态)
_OFF_RUN_TIME  = 0x00BC   # UINT32，运行时间 (s)
_OFF_CHG_DCG   = 0x00C0   # UINT8(充电状态) + UINT8(放电状态)

# ─── 告警位定义 (0x00A0 ALARM UINT32) ─────────────────────────────────────────
ALARM_WIRE_RES      = 1 << 0
ALARM_MOS_OTP       = 1 << 1
ALARM_CELL_QTY      = 1 << 2
ALARM_CUR_SENSOR    = 1 << 3
ALARM_CELL_OVP      = 1 << 4
ALARM_BAT_OVP       = 1 << 5
ALARM_CH_OCP        = 1 << 6
ALARM_CH_SCP        = 1 << 7
ALARM_CH_OTP        = 1 << 8
ALARM_CH_UTP        = 1 << 9
ALARM_CPU_COMM      = 1 << 10
ALARM_CELL_UVP      = 1 << 11
ALARM_BAT_UVP       = 1 << 12
ALARM_DCH_OCP       = 1 << 13
ALARM_DCH_SCP       = 1 << 14
ALARM_DCH_OTP       = 1 << 15


class JKBMS:
    """
    极空 JK BMS RS485 Modbus 驱动
    用法：
        bms = JKBMS(uart_id=2, slave_addr=1)
        data = bms.read_all()
        if data:
            print(data['soc'], data['pack_voltage'])
    """

    def __init__(self, uart_id: int = 2, slave_addr: int = 1,
                 tx_pin: int = 17, rx_pin: int = 18,
                 timeout_ms: int = 500):
        self.addr = slave_addr
        self.timeout = timeout_ms
        self.uart = UART(uart_id, baudrate=115200, bits=8, parity=None, stop=1,
                         tx=tx_pin, rx=rx_pin,
                         timeout=timeout_ms, timeout_char=50)
        time.sleep_ms(100)

    # ─── 内部：发送请求并接收响应 ───────────────────────────────────────────────

    def _query(self, reg_start: int, reg_count: int) -> bytes | None:
        """发 FC-03 读请求，返回数据字节（不含帧头/CRC），失败返回 None"""
        req = build_read_req(self.addr, reg_start, reg_count)
        self.uart.read()          # 清空接收缓冲区
        self.uart.write(req)
        time.sleep_ms(self.timeout)
        raw = self.uart.read()
        if not raw:
            return None
        return parse_fc03_response(raw, self.addr)

    # ─── 内部：读实时数据某段 ──────────────────────────────────────────────────

    def _read_rt(self, byte_offset: int, byte_count: int) -> bytes | None:
        """读实时数据区，byte_offset 是字节偏移，byte_count 必须是 2 的倍数"""
        reg_start = _BASE_RT + byte_offset // 2
        reg_count = byte_count // 2
        return self._query(reg_start, reg_count)

    # ─── 读取所有重要数据 ──────────────────────────────────────────────────────

    def read_all(self) -> dict | None:
        """
        读取极空 BMS 全部关键数据，返回统一 JSON 字典。
        失败返回 None。
        """
        # ── 第1段：单体电压（32节，每节 2 字节，offset 0x00 ~ 0x3F）
        seg1 = self._read_rt(0x0000, 64)   # 32 个 UINT16
        if seg1 is None:
            return None

        # ── 第2段：状态 + 电流 + 告警 + SOC 等（offset 0x0040 ~ 0x00C3）
        seg2 = self._read_rt(0x0040, 132)  # 0xC4 - 0x40 = 0x84 = 132 bytes
        if seg2 is None:
            return None

        return self._parse(seg1, seg2)

    # ─── 解析 ─────────────────────────────────────────────────────────────────

    def _parse(self, seg1: bytes, seg2: bytes) -> dict:
        """
        seg1: offset 0x0000 开始的 64 字节（32 个单体电压）
        seg2: offset 0x0040 开始的 132 字节（状态数据）
        """
        # 单体电压（mV → V）
        cells = []
        for i in range(32):
            mv = u16be(seg1, i * 2)
            cells.append(round(mv / 1000.0, 3))

        # seg2 偏移量 = 字段字节偏移 - 0x0040
        def s2(byte_off):
            return byte_off - 0x0040

        alarm_raw   = u32be(seg2, s2(0x00A0))
        chg_dcg     = seg2[s2(0x00C0)]      # UINT8 充电状态
        dcg_state   = seg2[s2(0x00C1)]      # UINT8 放电状态
        bal_soc_b   = seg2[s2(0x00A6)]
        soc_b       = seg2[s2(0x00A7)]
        soh_b       = seg2[s2(0x00B8)]

        pack_mv     = u32be(seg2, s2(0x0090))
        pack_ma     = i32be(seg2, s2(0x0098))
        pack_mw     = u32be(seg2, s2(0x0094))  # 注意极空功率为 UINT32，放电时值可能仍为正
        temp1_raw   = i16be(seg2, s2(0x009C))
        temp2_raw   = i16be(seg2, s2(0x009E))
        mos_temp_r  = i16be(seg2, s2(0x008A))
        delta_v     = u16be(seg2, s2(0x0046))
        avg_v       = u16be(seg2, s2(0x0044))
        max_nbr     = seg2[s2(0x0048)]
        min_nbr     = seg2[s2(0x0049)]
        remain_mah  = i32be(seg2, s2(0x00A8))
        full_mah    = u32be(seg2, s2(0x00AC))
        cycles      = u32be(seg2, s2(0x00B0))

        # 实际使用的单体数量（非零电压的数量）
        active_cells = [v for v in cells if v > 0.5]
        cell_count   = len(active_cells)

        # 温度换算（0.1°C 单位 → °C）
        temp1 = round(temp1_raw / 10.0, 1)
        temp2 = round(temp2_raw / 10.0, 1)
        mos_temp = round(mos_temp_r / 10.0, 1)
        temp_avg = round((temp1 + temp2) / 2.0, 1)
        temp_max = max(temp1, temp2)

        # 功率方向修正（按电流正负判断）
        power_w = round(pack_mw / 1000.0, 1)
        if pack_ma < 0:
            power_w = -abs(power_w)

        # 构建统一输出 JSON
        result = {
            "brand":           "JK",
            "soc":             soc_b,
            "soh":             soh_b,
            "pack_voltage":    round(pack_mv / 1000.0, 3),
            "pack_current":    round(pack_ma / 1000.0, 2),
            "power_w":         power_w,
            "temperature_avg": temp_avg,
            "temperature_max": temp_max,
            "mos_temperature": mos_temp,
            "delta_v":         round(delta_v / 1000.0, 3),
            "cell_count":      cell_count,
            "remain_ah":       round(remain_mah / 1000.0, 1),
            "full_capacity_ah":round(full_mah / 1000.0, 1),
            "cycle_count":     cycles,
            "charge_state":    chg_dcg,
            "discharge_state": dcg_state,
            "balance_state":   bal_soc_b,
            # ── 告警位 ───────────────────────────────────────────────────────
            "alarm_cell_ovp":        int(bool(alarm_raw & ALARM_CELL_OVP)),
            "alarm_cell_uvp":        int(bool(alarm_raw & ALARM_CELL_UVP)),
            "alarm_bat_ovp":         int(bool(alarm_raw & ALARM_BAT_OVP)),
            "alarm_bat_uvp":         int(bool(alarm_raw & ALARM_BAT_UVP)),
            "alarm_over_current":    int(bool(alarm_raw & (ALARM_CH_OCP | ALARM_DCH_OCP))),
            "alarm_short_circuit":   int(bool(alarm_raw & (ALARM_CH_SCP | ALARM_DCH_SCP))),
            "alarm_over_temp":       int(bool(alarm_raw & (ALARM_CH_OTP | ALARM_DCH_OTP | ALARM_MOS_OTP))),
            "alarm_cell_imbalance":  int(delta_v > 50),   # >50mV 视为不均衡
            # ── 单体电压 ─────────────────────────────────────────────────────
        }

        # 只输出实际有电压的单体
        for i, v in enumerate(cells[:cell_count], start=1):
            result[f"cell_v_{i:02d}"] = v

        return result

    # ─── 控制指令 ──────────────────────────────────────────────────────────────

    def _write_cfg(self, byte_offset: int, value_32bit: int) -> bool:
        """写配置寄存器（UINT32），byte_offset 是 0x1000 段的字节偏移"""
        reg = _BASE_CFG + byte_offset // 2
        # UINT32 写两个连续寄存器
        vals = [(value_32bit >> 16) & 0xFFFF, value_32bit & 0xFFFF]
        from bms_common import build_write_multi_req
        frame = build_write_multi_req(self.addr, reg, vals)
        self.uart.read()
        self.uart.write(frame)
        time.sleep_ms(200)
        resp = self.uart.read()
        return resp is not None and len(resp) >= 8

    def set_charge_enable(self, enable: bool) -> bool:
        """远程开/关充电 MOS（寄存器 0x1000 偏移 0x0070）"""
        return self._write_cfg(0x0070, 1 if enable else 0)

    def set_discharge_enable(self, enable: bool) -> bool:
        """远程开/关放电 MOS（寄存器 0x1000 偏移 0x0074）"""
        return self._write_cfg(0x0074, 1 if enable else 0)

    def set_balance_enable(self, enable: bool) -> bool:
        """远程开/关均衡（寄存器 0x1000 偏移 0x0078）"""
        return self._write_cfg(0x0078, 1 if enable else 0)
