/**
 * CORETECT Sentinel — 达锂(DY/KVMS) BMS 解析器
 * 用途：ThingsBoard 规则链 Transformation 节点
 * 协议：RS485 Modbus RTU，9600 8N1
 * 特殊：请求地址0x81，响应地址0x51（厂家固定设计）
 *
 * DR502 轮询配置：
 *   从机地址：0x81(129)，FC-03，起始寄存器0x0000，数量96
 *   注意：DR502 配置从机地址填 81H（十六进制），不是十进制129
 */

function parseDY(hexStr) {
    var clean = hexStr.replace(/\s+/g, '').toUpperCase();
    var bytes = [];
    for (var i = 0; i < clean.length; i += 2) {
        bytes.push(parseInt(clean.substr(i, 2), 16));
    }

    if (bytes.length < 7) return null;
    // 达锂响应地址是 0x51
    if (bytes[0] !== 0x51) return null;
    if (bytes[1] & 0x80) return null;
    if (bytes[1] !== 0x03) return null;

    var dataLen = bytes[2];
    if (bytes.length < dataLen + 5) return null;
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        var off = reg * 2;
        if (off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) {
        var v = r(reg);
        return v >= 0x8000 ? v - 0x10000 : v;
    }

    var cellCount = Math.min(r(0x3C), 48);
    var tempCount = Math.min(r(0x3D), 8);

    // 单体电压（寄存器0x00~，值×0.001=V）
    var cells = {};
    var maxMv = 0, minMv = 9999;
    for (var i = 0; i < cellCount; i++) {
        var mv = r(i);
        if (mv > 500) {
            var idx = (i+1) < 10 ? '0'+(i+1) : ''+(i+1);
            cells['cell_v_' + idx] = Math.round(mv) / 1000.0;
            if (mv > maxMv) maxMv = mv;
            if (mv < minMv) minMv = mv;
        }
    }

    // 温度（寄存器0x30~，值-40=℃）
    var temps = [];
    for (var j = 0; j < tempCount; j++) {
        var raw = r(0x30 + j);
        if (raw !== 0) temps.push(raw - 40);
    }
    var tempAvg = temps.length ? Math.round(temps.reduce(function(a,b){return a+b;},0) / temps.length * 10) / 10 : 0;
    var tempMax = temps.length ? Math.max.apply(null, temps) : 0;

    // 电流（偏移30000，0.1A，>30000=充电正，<30000=放电负）
    var curRaw  = r(0x39);
    var packA   = Math.round((curRaw - 30000)) / 10.0;

    // 总电压（0.1V）
    var packV   = Math.round(r(0x38)) / 10.0;

    // SOC（×0.1%）
    var soc     = Math.round(r(0x3A)) / 10.0;

    // 功率
    var powerW  = Math.round(packV * packA * 10) / 10;

    // 压差
    var deltaVMv = maxMv - minMv;

    // MOS和环境温度
    var mosTemp = r(0x5A) - 40;
    var envTemp = r(0x5B) - 40;

    // 剩余容量（0.1AH）
    var remainAh = Math.round(r(0x4B)) / 10.0;

    // 故障码（寄存器0x6D~0x73）
    var f01 = r(0x6D);
    var f23 = r(0x6E);
    var f45 = r(0x6F);
    var f67 = r(0x70);

    // 故障等级解析（0=无故障，1=警告，2=保护）
    var cellOvpLevel  = f01 & 0x0007;
    var cellUvpLevel  = (f01 >> 3) & 0x0007;
    var deltaAlarm    = (f01 >> 8) & 0x0007;
    var chOtpLevel    = (f01 >> 11) & 0x0007;
    var dchOtpLevel   = (f23 >> 3) & 0x0007;
    var chOcpLevel    = (f45 >> 8) & 0x0007;
    var dchOcpLevel   = (f45 >> 11) & 0x0007;
    var shortCircuit  = (f45 >> 6) & 0x0001;

    var chargeState   = r(0x48);  // 0静止 1充电 2放电
    var chargeMos     = r(0x52);
    var dischargeMos  = r(0x53);
    var balState      = r(0x4D);
    var cycles        = r(0x4C);
    var chargerPlug   = r(0x49);

    var result = {
        brand:            'DY',
        soc:              soc,
        soh:              0,
        pack_voltage:     packV,
        pack_current:     packA,
        power_w:          powerW,
        temperature_avg:  tempAvg,
        temperature_max:  tempMax,
        mos_temperature:  mosTemp,
        env_temperature:  envTemp,
        delta_v:          Math.round(deltaVMv) / 1000.0,
        cell_count:       cellCount,
        remain_ah:        remainAh,
        full_capacity_ah: 0,
        cycle_count:      cycles,
        charge_state:     chargeState === 1 ? 1 : 0,
        discharge_state:  chargeState === 2 ? 1 : 0,
        balance_state:    balState,
        charger_plugged:  chargerPlug,
        charge_mos:       chargeMos,
        discharge_mos:    dischargeMos,
        alarm_cell_ovp:       cellOvpLevel > 0 ? 1 : 0,
        alarm_cell_uvp:       cellUvpLevel > 0 ? 1 : 0,
        alarm_bat_ovp:        (f45 >> 7) & 1,
        alarm_bat_uvp:        (f45 >> 14) & 1,
        alarm_over_current:   (chOcpLevel > 0 || dchOcpLevel > 0) ? 1 : 0,
        alarm_short_circuit:  shortCircuit,
        alarm_over_temp:      (chOtpLevel > 0 || dchOtpLevel > 0) ? 1 : 0,
        alarm_cell_imbalance: (deltaAlarm > 0 || deltaVMv > 50) ? 1 : 0
    };

    for (var k in cells) result[k] = cells[k];
    return result;
}
