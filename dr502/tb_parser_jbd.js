/**
 * CORETECT Sentinel — 嘉佰达(JBD) BMS 解析器
 * 用途：ThingsBoard 规则链 Transformation 节点
 *
 * 自动识别两种协议：
 *   【新协议 Modbus A12】  帧头：01 04 ...（标准Modbus，地址0x10，FC-04）
 *   【旧协议 V12】         帧头：DD 03/04 ...（私有协议，DD...77）
 *
 * DR502 轮询配置：
 *   新协议：从机地址0x10(16)，FC-04，起始0x1000，数量64
 *   旧协议：直接发 DD A5 03 00 FF FD 77 和 DD A5 04 00 FF FC 77
 */

// ════════════════════════════════════════════════════════════════════════════
// 新协议解析：JBD Modbus A12（地址0x10, FC-04, 寄存器从0x1000开始）
// ════════════════════════════════════════════════════════════════════════════

function parseJBD_Modbus(bytes) {
    // bytes[0]=从机地址(0x10), bytes[1]=FC(0x04), bytes[2]=数据长度
    if (bytes[0] !== 0x10) return null;
    if (bytes[1] !== 0x04) return null;

    var dataLen = bytes[2];
    if (bytes.length < dataLen + 5) return null;
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        // reg是相对0x1000的偏移（寄存器号），每个寄存器2字节
        var off = (reg - 0x1000) * 2;
        if (off < 0 || off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) {
        var v = r(reg);
        return v >= 0x8000 ? v - 0x10000 : v;
    }

    // 电流精度判断（0x1002 BIT15）
    var curPrecision = (r(0x1002) >> 15) & 1;
    var curMult = curPrecision ? 0.1 : 0.01;

    // 总电压（0.01V）和电流
    var packV   = r(0x1000) * 0.01;
    var rawCur  = ri(0x1001);
    var packA   = rawCur * curMult;

    var soc     = r(0x1002) & 0x7FFF;  // 去掉精度标志位
    var soh     = r(0x1003);

    // 温度（0.1℃偏移-50）
    var maxTemp = r(0x1009) * 0.1 - 50;
    var minTemp = r(0x100B) * 0.1 - 50;
    var envTemp = r(0x100C) * 0.1 - 50;
    var mosTemp = r(0x100D) * 0.1 - 50;
    var tempAvg = Math.round((maxTemp + minTemp) * 5) / 10.0;

    // 系统状态（0x100E）
    var sysState   = r(0x100E);
    var dchMos     = (sysState >> 0) & 1;
    var chgMos     = (sysState >> 1) & 1;
    var chgState   = (sysState >> 2) & 1;
    var dchState   = (sysState >> 3) & 1;
    var capUnit    = (sysState >> 15) & 1;  // 容量单位标志

    var capMult    = capUnit ? 0.1 : 0.01;
    var fullAh     = r(0x100F) * capMult;
    var remainAh   = r(0x1010) * capMult;

    // 保护/告警信息（0x1011~0x1014 各2字节）
    var prot0 = r(0x1011);
    var prot1 = r(0x1012);
    var alm0  = r(0x1013);
    var alm1  = r(0x1014);

    var cycles  = r(0x1027);
    var cellCnt = r(0x1029);

    // 单体电压（0x102A开始，最多16节）
    var cells = {};
    for (var i = 0; i < Math.min(cellCnt, 32); i++) {
        var mv = r(0x102A + i);
        var idx = (i + 1) < 10 ? '0' + (i + 1) : '' + (i + 1);
        cells['cell_v_' + idx] = Math.round(mv) / 1000.0;
    }

    // 最大/最小单体电压
    var maxCellMv = r(0x1005);
    var minCellMv = r(0x1007);
    var deltaVMv  = maxCellMv - minCellMv;

    var powerW = Math.round(packV * packA * 10) / 10;

    var result = {
        brand:            'JBD',
        protocol:         'MODBUS_A12',
        soc:              soc,
        soh:              soh,
        pack_voltage:     Math.round(packV * 100) / 100,
        pack_current:     Math.round(packA * 100) / 100,
        power_w:          powerW,
        temperature_avg:  tempAvg,
        temperature_max:  maxTemp,
        mos_temperature:  mosTemp,
        env_temperature:  envTemp,
        delta_v:          Math.round(deltaVMv) / 1000.0,
        cell_count:       cellCnt,
        remain_ah:        Math.round(remainAh * 100) / 100,
        full_capacity_ah: Math.round(fullAh * 100) / 100,
        cycle_count:      cycles,
        charge_state:     chgState,
        discharge_state:  dchState,
        charge_mos:       chgMos,
        discharge_mos:    dchMos,
        // 告警（保护位 OR 告警位，任意触发=1）
        alarm_cell_ovp:       ((prot0 >> 0) | (alm0 >> 0)) & 1,
        alarm_cell_uvp:       ((prot0 >> 1) | (alm0 >> 1)) & 1,
        alarm_bat_ovp:        ((prot0 >> 2) | (alm0 >> 2)) & 1,
        alarm_bat_uvp:        ((prot0 >> 3) | (alm0 >> 3)) & 1,
        alarm_over_current:   ((prot0 >> 4) | (prot0 >> 5) | (alm0 >> 8) | (alm0 >> 9)) & 1,
        alarm_short_circuit:  (prot1 >> 18) & 1,
        alarm_over_temp:      ((prot0 >> 6) | (prot0 >> 8) | (alm0 >> 6) | (alm0 >> 8)) & 1,
        alarm_cell_imbalance: ((prot1 >> 15) | (alm0 >> 10)) & 1,
        alarm_mos_ovt:        (prot1 >> 12) & 1,
        alarm_mos_fault:      ((prot1 >> 21) | (prot1 >> 22)) & 1
    };

    for (var k in cells) result[k] = cells[k];
    return result;
}


// ════════════════════════════════════════════════════════════════════════════
// 旧协议解析：JBD V12 私有协议（DD...77 帧格式）
// DR502 需配置为透传模式，将完整帧上传
// ════════════════════════════════════════════════════════════════════════════

function jbdChecksum(bytes, start, end) {
    // checksum = ~(sum of bytes[start..end]) + 1，取低16位
    var sum = 0;
    for (var i = start; i <= end; i++) sum += bytes[i];
    return ((~sum + 1) & 0xFFFF);
}

function parseJBD_V12_basic(bytes) {
    // 基本信息 0x03 响应：DD 03 00 LEN data... CSUM_H CSUM_L 77
    if (bytes[0] !== 0xDD || bytes[1] !== 0x03) return null;
    if (bytes[2] !== 0x00) return null;  // 状态码非0=错误

    var dataLen = bytes[3];
    if (bytes.length < dataLen + 7) return null;

    var d = bytes.slice(4, 4 + dataLen);

    function u16(off) { return (d[off] << 8) | d[off + 1]; }
    function i16(off) {
        var v = u16(off);
        return v >= 0x8000 ? v - 0x10000 : v;
    }

    // FET状态（d[20]），BIT7=容量电流单位标志
    var fetState = d[20];
    var bigUnit  = (fetState >> 7) & 1;
    var capMult  = bigUnit ? 100 : 10;    // 10mAh 或 100mAh
    var curMult  = bigUnit ? 100 : 10;    // 10mA 或 100mA

    var packMv   = u16(0) * 10;           // 10mV→mV
    var rawCur   = i16(2);
    var packMa   = rawCur * curMult;      // mA
    var packV    = packMv / 1000.0;
    var packA    = packMa / 1000.0;

    var remainMah = u16(4) * capMult;
    var fullMah   = u16(6) * capMult;
    var cycles    = u16(8);
    // u16(10) = 生产日期
    // u16(12) = 均衡低, u16(14) = 均衡高
    var protState = u16(16);
    var softVer   = d[18];
    var soc       = d[19];
    // fetState = d[20]
    var cellCount = d[21];
    var ntcCount  = d[22];

    // 温度（开尔文×0.1，偏移-2731）
    var temps = [];
    for (var i = 0; i < ntcCount && i < 8; i++) {
        var tk = u16(23 + i * 2);
        temps.push(Math.round((tk - 2731)) / 10.0);
    }
    var tempAvg = temps.length ? Math.round(temps.reduce(function(a,b){return a+b;},0) / temps.length * 10) / 10 : 0;
    var tempMax = temps.length ? Math.max.apply(null, temps) : 0;

    // 满充/剩余容量（V12后续字节，如果长度够）
    var afterNTC = 23 + ntcCount * 2;
    // humidity (1byte), alarmState (2byte), fullCap (2byte), remCap (2byte), balCur (2byte)

    // 保护状态位解析
    var chgMos  = (fetState >> 0) & 1;
    var dchMos  = (fetState >> 1) & 1;
    var powerW  = Math.round(packV * packA * 10) / 10;

    // 压差从单体电压计算（如有），此处先设0，等0x04指令数据合并
    var result = {
        brand:            'JBD',
        protocol:         'V12_DD77',
        soc:              soc,
        soh:              0,
        pack_voltage:     Math.round(packV * 100) / 100,
        pack_current:     Math.round(packA * 100) / 100,
        power_w:          powerW,
        temperature_avg:  tempAvg,
        temperature_max:  tempMax,
        cell_count:       cellCount,
        remain_ah:        Math.round(remainMah) / 1000.0,
        full_capacity_ah: Math.round(fullMah) / 1000.0,
        cycle_count:      cycles,
        charge_state:     (protState >> 2) & 1,
        discharge_state:  (protState >> 3) & 1,
        charge_mos:       chgMos,
        discharge_mos:    dchMos,
        alarm_cell_ovp:       (protState >> 0) & 1,
        alarm_cell_uvp:       (protState >> 1) & 1,
        alarm_bat_ovp:        (protState >> 2) & 1,
        alarm_bat_uvp:        (protState >> 3) & 1,
        alarm_over_current:   ((protState >> 8) | (protState >> 9)) & 1,
        alarm_short_circuit:  (protState >> 10) & 1,
        alarm_over_temp:      ((protState >> 4) | (protState >> 6)) & 1,
        alarm_cell_imbalance: 0,  // 需要单体电压数据才能计算
        delta_v:          0,
        mos_temperature:  0
    };
    return result;
}

function parseJBD_V12_cells(bytes, baseResult) {
    // 单体电压 0x04 响应：DD 04 00 LEN data... CSUM_H CSUM_L 77
    if (!bytes || bytes[0] !== 0xDD || bytes[1] !== 0x04) return baseResult;
    if (bytes[2] !== 0x00) return baseResult;

    var dataLen = bytes[3];
    var cellCount = dataLen / 2;
    var cells = {};
    var maxMv = 0, minMv = 9999;

    for (var i = 0; i < cellCount; i++) {
        var mv = (bytes[4 + i*2] << 8) | bytes[5 + i*2];
        if (mv > 500) {
            var idx = (i+1) < 10 ? '0'+(i+1) : ''+(i+1);
            cells['cell_v_' + idx] = Math.round(mv) / 1000.0;
            if (mv > maxMv) maxMv = mv;
            if (mv < minMv) minMv = mv;
        }
    }

    var deltaVMv = maxMv - minMv;
    baseResult.delta_v = Math.round(deltaVMv) / 1000.0;
    baseResult.alarm_cell_imbalance = deltaVMv > 50 ? 1 : 0;
    for (var k in cells) baseResult[k] = cells[k];
    return baseResult;
}


// ════════════════════════════════════════════════════════════════════════════
// 主入口：自动识别协议版本
// ════════════════════════════════════════════════════════════════════════════

function parseJBD(hexStr_basic, hexStr_cells) {
    var clean = hexStr_basic.replace(/\s+/g, '').toUpperCase();
    var bytes = [];
    for (var i = 0; i < clean.length; i += 2) {
        bytes.push(parseInt(clean.substr(i, 2), 16));
    }
    if (bytes.length < 4) return null;

    // 判断协议版本
    if (bytes[0] === 0x10 && bytes[1] === 0x04) {
        // 新协议 Modbus A12
        return parseJBD_Modbus(bytes);
    }
    else if (bytes[0] === 0xDD) {
        // 旧协议 V12 DD...77
        var base = parseJBD_V12_basic(bytes);
        if (!base) return null;

        // 如果有单体电压帧，一并解析
        if (hexStr_cells) {
            var cleanC = hexStr_cells.replace(/\s+/g, '').toUpperCase();
            var bytesC = [];
            for (var j = 0; j < cleanC.length; j += 2) {
                bytesC.push(parseInt(cleanC.substr(j, 2), 16));
            }
            return parseJBD_V12_cells(bytesC, base);
        }
        return base;
    }
    return null;
}
