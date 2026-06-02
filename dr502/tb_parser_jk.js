/**
 * CORETECT Sentinel — 极空(JK) BMS 解析器
 * 用途：ThingsBoard 规则链 Transformation 节点
 * 协议：RS485 Modbus RTU，115200 8N1
 * 输入：DR502 上传的原始 HEX 字符串（FC-03 响应帧）
 *       msg.bms_raw = "0103...CRCL CRCH"
 * 输出：统一 JSON 遥测数据
 *
 * 极空寄存器基地址：
 *   0x1200 = 实时数据（从 DR502 轮询起始地址）
 *   DR502 配置：从机地址1，起始寄存器0x1200，数量96
 */

function parseJK(hexStr) {
    // ── 1. HEX字符串转字节数组 ──────────────────────────────────────────────
    var clean = hexStr.replace(/\s+/g, '').toUpperCase();
    var bytes = [];
    for (var i = 0; i < clean.length; i += 2) {
        bytes.push(parseInt(clean.substr(i, 2), 16));
    }

    // ── 2. 基本校验 ─────────────────────────────────────────────────────────
    // DR502返回的是完整Modbus响应帧：[addr, FC, byteCount, data..., CRCL, CRCH]
    if (bytes.length < 7) return null;
    if (bytes[1] & 0x80) return null;  // 从机返回错误
    if (bytes[1] !== 0x03) return null;

    var dataLen = bytes[2];
    if (bytes.length < dataLen + 5) return null;

    // 数据区从 bytes[3] 开始
    var d = bytes.slice(3, 3 + dataLen);

    // ── 3. 工具函数 ─────────────────────────────────────────────────────────
    function u16(off) {
        return (d[off] << 8) | d[off + 1];
    }
    function i16(off) {
        var v = u16(off);
        return v >= 0x8000 ? v - 0x10000 : v;
    }
    function u32(off) {
        return ((d[off] << 24) | (d[off+1] << 16) | (d[off+2] << 8) | d[off+3]) >>> 0;
    }
    function i32(off) {
        var v = u32(off);
        return v >= 0x80000000 ? v - 0x100000000 : v;
    }

    /**
     * DR502 轮询配置：起始寄存器 0x1200，数量 96
     * 数据区偏移 = (目标寄存器地址 - 0x1200) * 2
     * 0x1200对应d[0], 每个寄存器2字节
     *
     * 实时数据寄存器（相对0x1200的字节偏移）：
     * 0x0000(d[0])   : 单体电压0~31 (32×UINT16, 每个2字节)
     * 0x0040(d[64])  : 电池状态 UINT32
     * 0x0044(d[68])  : 平均电压 UINT16
     * 0x0046(d[70])  : 最大压差 UINT16
     * 0x0048(d[72])  : 最高/最低单体编号 UINT8×2
     * 0x008A(d[138]) : MOS温度 INT16
     * 0x0090(d[144]) : 总电压 UINT32
     * 0x0094(d[148]) : 功率 UINT32
     * 0x0098(d[152]) : 电流 INT32
     * 0x009C(d[156]) : 温度1 INT16
     * 0x009E(d[158]) : 温度2 INT16
     * 0x00A0(d[160]) : 告警标志 UINT32
     * 0x00A4(d[164]) : 均衡电流 INT16
     * 0x00A6(d[166]) : 均衡状态UINT8 + SOC UINT8
     * 0x00A8(d[168]) : 剩余容量 INT32
     * 0x00AC(d[172]) : 满充容量 UINT32
     * 0x00B0(d[176]) : 循环次数 UINT32
     * 0x00B8(d[184]) : SOH UINT8 + 预充状态 UINT8
     * 0x00BC(d[188]) : 运行时间 UINT32
     * 0x00C0(d[192]) : 充电状态 UINT8 + 放电状态 UINT8
     */

    // ── 4. 解析单体电压（最多32节，取有效非零值）────────────────────────────
    var cells = {};
    var cellCount = 0;
    for (var i = 0; i < 32; i++) {
        var off = i * 2;
        if (off + 1 >= d.length) break;
        var mv = u16(off);
        if (mv > 500) {  // >500mV 视为有效电芯
            cellCount++;
            cells['cell_v_' + (cellCount < 10 ? '0' : '') + cellCount] =
                Math.round(mv) / 1000.0;
        }
    }

    // ── 5. 检查数据长度够不够读后续字段 ──────────────────────────────────────
    if (d.length < 196) return null;

    // ── 6. 解析主要字段 ──────────────────────────────────────────────────────
    var alarmRaw  = u32(160);
    var packMv    = u32(144);
    var packMw    = u32(148);
    var packMa    = i32(152);
    var temp1Raw  = i16(156);
    var temp2Raw  = i16(158);
    var mosTemp   = i16(138);
    var deltaVMv  = u16(70);
    var avgVMv    = u16(68);
    var soc       = d[167];
    var soh       = d[184];
    var remainMah = i32(168);
    var fullMah   = u32(172);
    var cycles    = u32(176);
    var chgState  = d[192];
    var dchState  = d[193];
    var balState  = d[166];

    var temp1 = Math.round(temp1Raw) / 10.0;
    var temp2 = Math.round(temp2Raw) / 10.0;
    var tempAvg = Math.round((temp1 + temp2) * 5) / 10.0;
    var tempMax = Math.max(temp1, temp2);

    var powerW = Math.round(packMw) / 1000.0;
    if (packMa < 0) powerW = -Math.abs(powerW);

    // ── 7. 告警位解析 ────────────────────────────────────────────────────────
    var result = {
        brand:            'JK',
        soc:              soc,
        soh:              soh,
        pack_voltage:     Math.round(packMv) / 1000.0,
        pack_current:     Math.round(packMa) / 1000.0,
        power_w:          powerW,
        temperature_avg:  tempAvg,
        temperature_max:  tempMax,
        mos_temperature:  Math.round(mosTemp) / 10.0,
        delta_v:          Math.round(deltaVMv) / 1000.0,
        avg_cell_v:       Math.round(avgVMv) / 1000.0,
        cell_count:       cellCount,
        remain_ah:        Math.round(remainMah) / 1000.0,
        full_capacity_ah: Math.round(fullMah) / 1000.0,
        cycle_count:      cycles,
        charge_state:     chgState,
        discharge_state:  dchState,
        balance_state:    balState,
        // 告警（任意=1触发）
        alarm_cell_ovp:       (alarmRaw >> 4) & 1,
        alarm_cell_uvp:       (alarmRaw >> 11) & 1,
        alarm_bat_ovp:        (alarmRaw >> 5) & 1,
        alarm_bat_uvp:        (alarmRaw >> 12) & 1,
        alarm_over_current:   ((alarmRaw >> 6) | (alarmRaw >> 13)) & 1,
        alarm_short_circuit:  ((alarmRaw >> 7) | (alarmRaw >> 14)) & 1,
        alarm_over_temp:      ((alarmRaw >> 8) | (alarmRaw >> 15) | (alarmRaw >> 1)) & 1,
        alarm_cell_imbalance: (deltaVMv > 50) ? 1 : 0
    };

    // 合并单体电压
    for (var k in cells) result[k] = cells[k];

    return result;
}
