/**
 * CORETECT Sentinel — 逆变器解析器合集
 * 用途：ThingsBoard 规则链 Transformation 节点
 * 支持品牌：固德威Goodwe / 德业Deye / 锦浪Solis / 古瑞瓦特Growatt / 索福Sofar
 *
 * DR502 轮询配置（逆变器，从机地址2）：
 *   波特率：9600（所有品牌默认）
 *   功能码：FC-03
 *   起始寄存器和数量见各品牌说明
 *
 * 输出统一字段（inv_前缀区分BMS数据）：
 *   inv_brand, inv_status, inv_pv_power, inv_grid_power,
 *   inv_bat_power, inv_load_power, inv_grid_freq,
 *   inv_today_gen_kwh, inv_total_gen_kwh, inv_temperature
 */


// ════════════════════════════════════════════════════════════════════════════
// 固德威 Goodwe — 储能逆变器（ET/BT系列为主）
// DR502配置：FC-03，起始0x0000，数量80
// 参考：GoodWe Modbus RTU Communication Protocol V1.4
// ════════════════════════════════════════════════════════════════════════════

function parseGoodwe(bytes) {
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(off) { return (d[off] << 8) | d[off + 1]; }
    function ri(off) { var v = r(off); return v >= 0x8000 ? v - 0x10000 : v; }
    function r32(off) { return ((r(off) << 16) | r(off+2)) >>> 0; }

    // Goodwe ET系列主要寄存器（相对起始地址的偏移，单位字节）
    // 0x0000=机型, 0x0008=运行状态, 0x000A=Vpv1, ...
    // 以下偏移基于寄存器0x0000起始
    var status   = r(0x0008 * 2);   // 运行状态 0:待机 1:发电 8:故障
    var pv1V     = r(0x000A * 2) * 0.1;
    var pv1A     = r(0x000B * 2) * 0.1;
    var pv2V     = r(0x000C * 2) * 0.1;
    var pv2A     = r(0x000D * 2) * 0.1;
    var pvPowerW = Math.round((pv1V * pv1A + pv2V * pv2A) * 10) / 10;

    var gridV    = r(0x0011 * 2) * 0.1;
    var gridA    = ri(0x0013 * 2) * 0.1;
    var gridFreq = r(0x0016 * 2) * 0.01;
    var gridPowerW = Math.round(gridV * gridA * 10) / 10;

    var loadPowerW = r(0x0027 * 2);   // W

    var batV     = r(0x0034 * 2) * 0.1;
    var batA     = ri(0x0035 * 2) * 0.1;  // 正=充电，负=放电
    var batSoc   = r(0x0037 * 2);
    var batPowerW = Math.round(batV * batA * 10) / 10;

    var todayKwh = r(0x0044 * 2) * 0.1;
    var totalKwh = r32(0x0045 * 2) * 0.1;
    var temp     = ri(0x0058 * 2) * 0.1;

    return {
        inv_brand:         'GOODWE',
        inv_status:        status,
        inv_pv_power:      pvPowerW,
        inv_pv1_voltage:   pv1V,
        inv_pv2_voltage:   pv2V,
        inv_grid_voltage:  gridV,
        inv_grid_freq:     gridFreq,
        inv_grid_power:    gridPowerW,
        inv_load_power:    loadPowerW,
        inv_bat_voltage:   batV,
        inv_bat_current:   batA,
        inv_bat_power:     batPowerW,
        inv_bat_soc:       batSoc,
        inv_today_gen_kwh: todayKwh,
        inv_total_gen_kwh: Math.round(totalKwh * 10) / 10,
        inv_temperature:   temp
    };
}


// ════════════════════════════════════════════════════════════════════════════
// 德业 Deye — 储能逆变器（SUN系列）
// DR502配置：FC-03，起始0x0003，数量80
// ════════════════════════════════════════════════════════════════════════════

function parseDeye(bytes) {
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        // reg是绝对寄存器地址，起始0x0003，偏移=(reg-3)*2
        var off = (reg - 3) * 2;
        if (off < 0 || off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) { var v = r(reg); return v >= 0x8000 ? v - 0x10000 : v; }

    // Deye SUN系列关键寄存器
    var status     = r(0x003B);    // 机器状态
    var pv1V       = r(0x006D) * 0.1;
    var pv1A       = r(0x006E) * 0.1;
    var pv2V       = r(0x006F) * 0.1;
    var pv2A       = r(0x0070) * 0.1;
    var pvPowerW   = r(0x00DC) + r(0x00DD);  // PV1功率+PV2功率

    var gridV      = r(0x0049) * 0.1;
    var gridFreq   = r(0x004C) * 0.01;
    var gridPowerW = ri(0x0046) * 10;   // 有符号，正=送出，负=购入

    var loadPowerW = r(0x004B) * 10;

    var batV       = r(0x00B5) * 0.01;
    var batA       = ri(0x00B6) * 0.01;
    var batSoc     = r(0x00B8);
    var batTemp    = ri(0x00B7) * 0.1;
    var batPowerW  = Math.round(batV * batA * 10) / 10;

    var todayKwh   = r(0x0041) * 0.1;
    var totalKwh   = ((r(0x0042) << 16) | r(0x0043)) * 0.1;
    var temp       = ri(0x005A) * 0.1;

    return {
        inv_brand:         'DEYE',
        inv_status:        status,
        inv_pv_power:      pvPowerW,
        inv_pv1_voltage:   pv1V,
        inv_pv2_voltage:   pv2V,
        inv_grid_voltage:  gridV,
        inv_grid_freq:     gridFreq,
        inv_grid_power:    gridPowerW,
        inv_load_power:    loadPowerW,
        inv_bat_voltage:   batV,
        inv_bat_current:   batA,
        inv_bat_power:     batPowerW,
        inv_bat_soc:       batSoc,
        inv_bat_temperature: batTemp,
        inv_today_gen_kwh: todayKwh,
        inv_total_gen_kwh: Math.round(totalKwh * 10) / 10,
        inv_temperature:   temp
    };
}


// ════════════════════════════════════════════════════════════════════════════
// 锦浪 Solis — 储能逆变器（RAI/RHI系列）
// DR502配置：FC-03，起始0x0003，数量80
// ════════════════════════════════════════════════════════════════════════════

function parseSolis(bytes) {
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        var off = (reg - 3) * 2;
        if (off < 0 || off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) { var v = r(reg); return v >= 0x8000 ? v - 0x10000 : v; }
    function r32(reg) { return ((r(reg) << 16) | r(reg+1)) >>> 0; }

    // Solis RAI/RHI 关键寄存器（Modbus地址）
    var status     = r(0x0AB0);   // 工作状态
    var pv1V       = r(0x0AE7) * 0.1;
    var pv1A       = r(0x0AE8) * 0.1;
    var pvPowerW   = r32(0x0AE9) * 1;

    var gridV      = r(0x0AEF) * 0.1;
    var gridFreq   = r(0x0AEC) * 0.01;
    var gridPowerW = ri(0x0AEE) * 1;  // 正=送出，负=购入

    var loadPowerW = r(0x0AB6) * 1;

    var batV       = r(0x0AFF) * 0.1;
    var batA       = ri(0x0B00) * 0.1;
    var batSoc     = r(0x0BF3);
    var batPowerW  = Math.round(batV * batA * 10) / 10;

    var todayKwh   = r(0x0AB1) * 0.1;
    var totalKwh   = r32(0x0AB3) * 0.1;
    var temp       = ri(0x0B03) * 0.1;

    return {
        inv_brand:         'SOLIS',
        inv_status:        status,
        inv_pv_power:      pvPowerW,
        inv_pv1_voltage:   pv1V,
        inv_grid_voltage:  gridV,
        inv_grid_freq:     gridFreq,
        inv_grid_power:    gridPowerW,
        inv_load_power:    loadPowerW,
        inv_bat_voltage:   batV,
        inv_bat_current:   batA,
        inv_bat_power:     batPowerW,
        inv_bat_soc:       batSoc,
        inv_today_gen_kwh: todayKwh,
        inv_total_gen_kwh: Math.round(totalKwh * 10) / 10,
        inv_temperature:   temp
    };
}


// ════════════════════════════════════════════════════════════════════════════
// 古瑞瓦特 Growatt — 储能逆变器（SPF/SPA系列）
// DR502配置：FC-03，起始0x0000，数量80
// ════════════════════════════════════════════════════════════════════════════

function parseGrowatt(bytes) {
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        var off = reg * 2;
        if (off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) { var v = r(reg); return v >= 0x8000 ? v - 0x10000 : v; }
    function r32(reg) { return ((r(reg) << 16) | r(reg+1)) >>> 0; }

    // Growatt SPF/SPA 关键寄存器
    var status     = r(0x0000);
    var pvV        = r(0x0001) * 0.1;
    var pvA        = r(0x0002) * 0.1;
    var pvPowerW   = r32(0x0005);

    var gridV      = r(0x0014) * 0.1;
    var gridFreq   = r(0x0016) * 0.01;
    var gridPowerW = r32(0x0018);

    var outV       = r(0x0022) * 0.1;
    var loadPowerW = r32(0x0025);

    var batV       = r(0x0053) * 0.1;
    var batA       = ri(0x0056) * 0.1;
    var batSoc     = r(0x0058);
    var batPowerW  = Math.round(batV * batA * 10) / 10;

    var todayKwh   = r(0x0041) * 0.1;
    var totalKwh   = r32(0x0043) * 0.1;
    var temp       = ri(0x005B) * 0.1;

    return {
        inv_brand:         'GROWATT',
        inv_status:        status,
        inv_pv_power:      pvPowerW,
        inv_pv1_voltage:   pvV,
        inv_grid_voltage:  gridV,
        inv_grid_freq:     gridFreq,
        inv_grid_power:    gridPowerW,
        inv_load_power:    loadPowerW,
        inv_bat_voltage:   batV,
        inv_bat_current:   batA,
        inv_bat_power:     batPowerW,
        inv_bat_soc:       batSoc,
        inv_today_gen_kwh: todayKwh,
        inv_total_gen_kwh: Math.round(totalKwh * 10) / 10,
        inv_temperature:   temp
    };
}


// ════════════════════════════════════════════════════════════════════════════
// 索福 Sofar — 储能逆变器（HYD系列）
// DR502配置：FC-03，起始0x0200，数量80
// ════════════════════════════════════════════════════════════════════════════

function parseSofar(bytes) {
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(reg) {
        var off = (reg - 0x0200) * 2;
        if (off < 0 || off + 1 >= d.length) return 0;
        return (d[off] << 8) | d[off + 1];
    }
    function ri(reg) { var v = r(reg); return v >= 0x8000 ? v - 0x10000 : v; }

    var status     = r(0x0200);
    var pvV        = r(0x0206) * 0.1;
    var pvA        = r(0x0207) * 0.01;
    var pvPowerW   = r(0x0215) * 10;

    var gridV      = r(0x020A) * 0.1;
    var gridFreq   = r(0x020C) * 0.01;
    var gridPowerW = ri(0x0212) * 10;

    var loadPowerW = r(0x0213) * 10;

    var batV       = r(0x0218) * 0.1;
    var batA       = ri(0x0219) * 0.01;
    var batSoc     = r(0x0210);
    var batPowerW  = r(0x020D) * 10;

    var todayKwh   = r(0x0219) * 0.01;
    var totalKwh   = ((r(0x021A) << 16) | r(0x021B)) * 0.1;
    var temp       = ri(0x0238) * 0.1;

    return {
        inv_brand:         'SOFAR',
        inv_status:        status,
        inv_pv_power:      pvPowerW,
        inv_pv1_voltage:   pvV,
        inv_grid_voltage:  gridV,
        inv_grid_freq:     gridFreq,
        inv_grid_power:    gridPowerW,
        inv_load_power:    loadPowerW,
        inv_bat_voltage:   batV,
        inv_bat_current:   batA,
        inv_bat_power:     batPowerW,
        inv_bat_soc:       batSoc,
        inv_today_gen_kwh: todayKwh,
        inv_total_gen_kwh: Math.round(totalKwh * 10) / 10,
        inv_temperature:   temp
    };
}


// ════════════════════════════════════════════════════════════════════════════
// 主入口：根据品牌路由
// ════════════════════════════════════════════════════════════════════════════

function parseInverter(hexStr, brand) {
    var clean = hexStr.replace(/\s+/g, '').toUpperCase();
    var bytes = [];
    for (var i = 0; i < clean.length; i += 2) {
        bytes.push(parseInt(clean.substr(i, 2), 16));
    }
    if (bytes.length < 7) return null;
    if (bytes[1] & 0x80) return null;

    switch ((brand || '').toUpperCase()) {
        case 'GOODWE': return parseGoodwe(bytes);
        case 'DEYE':   return parseDeye(bytes);
        case 'SOLIS':  return parseSolis(bytes);
        case 'GROWATT':return parseGrowatt(bytes);
        case 'SOFAR':  return parseSofar(bytes);
        default:       return null;
    }
}
