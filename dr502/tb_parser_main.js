/**
 * CORETECT Sentinel — ThingsBoard 规则链主解析脚本
 * ═══════════════════════════════════════════════════════════════════
 * 【使用方法】将本文件全部内容粘贴到 ThingsBoard 规则链的
 *   Transformation → Script 节点中
 *
 * 【DR502 MQTT Payload 格式】
 * DR502 每次上报两个字段（JSON格式）：
 * {
 *   "bms_raw":  "01 03 ... CRC",  ← BMS Modbus响应帧HEX
 *   "bms_raw2": "DD 04 ... 77",   ← JBD旧协议单体电压帧（可选）
 *   "inv_raw":  "02 03 ... CRC"   ← 逆变器Modbus响应帧HEX（如有）
 * }
 *
 * 【设备属性配置】在ThingsBoard每台设备的 Server Attributes 里设置：
 * {
 *   "bms_brand":  "JK",       ← JK / JBD / DY
 *   "inv_brand":  "GOODWE",   ← GOODWE / DEYE / SOLIS / GROWATT / SOFAR / NONE
 *   "has_inverter": true,
 *   "device_id":  "ESS-PH-001",
 *   "location":   "Palawan Island"
 * }
 * ═══════════════════════════════════════════════════════════════════
 */

// ════════ 通用工具 ════════════════════════════════════════════════════════════

function hexToBytes(hexStr) {
    var clean = (hexStr || '').replace(/\s+/g, '').toUpperCase();
    var bytes = [];
    for (var i = 0; i < clean.length; i += 2) {
        bytes.push(parseInt(clean.substr(i, 2), 16));
    }
    return bytes;
}

function u16be(d, off) { return (d[off] << 8) | d[off + 1]; }
function i16be(d, off) { var v = u16be(d, off); return v >= 0x8000 ? v - 0x10000 : v; }
function u32be(d, off) { return (((d[off] << 24) | (d[off+1] << 16) | (d[off+2] << 8) | d[off+3]) >>> 0); }
function i32be(d, off) { var v = u32be(d, off); return v >= 0x80000000 ? v - 0x100000000 : v; }

// ════════ CRC-16 Modbus 验证 ══════════════════════════════════════════════════

function crc16(bytes) {
    var crc = 0xFFFF;
    for (var i = 0; i < bytes.length - 2; i++) {
        crc ^= bytes[i];
        for (var b = 0; b < 8; b++) {
            crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
        }
    }
    return crc;
}

function verifyCRC(bytes) {
    if (bytes.length < 4) return false;
    var calc = crc16(bytes);
    var recv = bytes[bytes.length-2] | (bytes[bytes.length-1] << 8);
    return calc === recv;
}

// ════════ JK 极空 BMS 解析 ════════════════════════════════════════════════════

function parseJK(bytes) {
    if (!bytes || bytes.length < 7) return null;
    if (bytes[1] & 0x80) return null;
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    if (bytes.length < dataLen + 5) return null;
    var d = bytes.slice(3, 3 + dataLen);
    if (d.length < 196) return null;

    var cells = {}, cellCount = 0;
    for (var i = 0; i < 32; i++) {
        var mv = u16be(d, i * 2);
        if (mv > 500) {
            cellCount++;
            var idx = cellCount < 10 ? '0' + cellCount : '' + cellCount;
            cells['cell_v_' + idx] = Math.round(mv) / 1000.0;
        }
    }

    var alarmRaw = u32be(d, 160);
    var packMv   = u32be(d, 144);
    var packMw   = u32be(d, 148);
    var packMa   = i32be(d, 152);
    var temp1    = i16be(d, 156) / 10.0;
    var temp2    = i16be(d, 158) / 10.0;
    var mosTemp  = i16be(d, 138) / 10.0;
    var deltaV   = u16be(d, 70);
    var soc      = d[167];
    var soh      = d[184];
    var powerW   = u32be(d, 148) / 1000.0;
    if (packMa < 0) powerW = -Math.abs(powerW);

    var res = {
        brand:'JK', soc:soc, soh:soh,
        pack_voltage:   Math.round(packMv)/1000.0,
        pack_current:   Math.round(packMa)/1000.0,
        power_w:        Math.round(powerW*10)/10,
        temperature_avg:Math.round((temp1+temp2)*5)/10,
        temperature_max:Math.max(temp1,temp2),
        mos_temperature:Math.round(mosTemp*10)/10,
        delta_v:        Math.round(deltaV)/1000.0,
        avg_cell_v:     Math.round(u16be(d,68))/1000.0,
        cell_count:     cellCount,
        remain_ah:      Math.round(i32be(d,168))/1000.0,
        full_capacity_ah: Math.round(u32be(d,172))/1000.0,
        cycle_count:    u32be(d,176),
        charge_state:   d[192],
        discharge_state:d[193],
        balance_state:  d[166],
        alarm_cell_ovp:      (alarmRaw>>4)&1,
        alarm_cell_uvp:      (alarmRaw>>11)&1,
        alarm_bat_ovp:       (alarmRaw>>5)&1,
        alarm_bat_uvp:       (alarmRaw>>12)&1,
        alarm_over_current:  ((alarmRaw>>6)|(alarmRaw>>13))&1,
        alarm_short_circuit: ((alarmRaw>>7)|(alarmRaw>>14))&1,
        alarm_over_temp:     ((alarmRaw>>8)|(alarmRaw>>15)|(alarmRaw>>1))&1,
        alarm_cell_imbalance: deltaV > 50 ? 1 : 0
    };
    for (var k in cells) res[k] = cells[k];
    return res;
}

// ════════ JBD 嘉佰达 BMS 解析（自动识别新旧协议）═══════════════════════════

function parseJBD(bytes, bytes2) {
    if (!bytes || bytes.length < 4) return null;

    // 新协议 Modbus A12（地址0x10, FC-04）
    if (bytes[0] === 0x10 && bytes[1] === 0x04) {
        var dataLen = bytes[2];
        var d = bytes.slice(3, 3 + dataLen);
        function r(reg) {
            var off=(reg-0x1000)*2;
            return (off<0||off+1>=d.length)?0:((d[off]<<8)|d[off+1]);
        }
        function ri(reg){var v=r(reg);return v>=0x8000?v-0x10000:v;}

        var sysState = r(0x100E);
        var capUnit  = (sysState>>15)&1;
        var capMult  = capUnit?0.1:0.01;
        var curMult  = ((r(0x1002)>>15)&1)?0.1:0.01;
        var packV    = r(0x1000)*0.01;
        var packA    = ri(0x1001)*curMult;
        var soc      = r(0x1002)&0x7FFF;
        var maxMv    = r(0x1005), minMv = r(0x1007);
        var cellCnt  = r(0x1029);
        var cells2   = {};
        for(var i=0;i<Math.min(cellCnt,32);i++){
            var mv=r(0x102A+i);
            var idx=(i+1)<10?'0'+(i+1):''+(i+1);
            cells2['cell_v_'+idx]=Math.round(mv)/1000.0;
        }
        var prot0=r(0x1011),prot1=r(0x1012),alm0=r(0x1013);
        var res2 = {
            brand:'JBD', protocol:'MODBUS_A12',
            soc:soc, soh:r(0x1003),
            pack_voltage:Math.round(packV*100)/100,
            pack_current:Math.round(packA*100)/100,
            power_w:Math.round(packV*packA*10)/10,
            temperature_avg:Math.round((r(0x1009)*0.1-50+r(0x100B)*0.1-50)*5)/10,
            temperature_max:r(0x1009)*0.1-50,
            mos_temperature:r(0x100D)*0.1-50,
            env_temperature:r(0x100C)*0.1-50,
            delta_v:Math.round(maxMv-minMv)/1000.0,
            cell_count:cellCnt,
            remain_ah:Math.round(r(0x1010)*capMult*100)/100,
            full_capacity_ah:Math.round(r(0x100F)*capMult*100)/100,
            cycle_count:r(0x1027),
            charge_state:(sysState>>2)&1, discharge_state:(sysState>>3)&1,
            charge_mos:(sysState>>1)&1, discharge_mos:(sysState>>0)&1,
            alarm_cell_ovp:((prot0>>0)|(alm0>>0))&1,
            alarm_cell_uvp:((prot0>>1)|(alm0>>1))&1,
            alarm_bat_ovp:((prot0>>2)|(alm0>>2))&1,
            alarm_bat_uvp:((prot0>>3)|(alm0>>3))&1,
            alarm_over_current:((prot0>>4)|(prot0>>5)|(alm0>>8)|(alm0>>9))&1,
            alarm_short_circuit:(prot1>>18)&1,
            alarm_over_temp:((prot0>>6)|(prot0>>8)|(alm0>>6)|(alm0>>8))&1,
            alarm_cell_imbalance:((prot1>>15)|(alm0>>10))&1
        };
        for(var k2 in cells2) res2[k2]=cells2[k2];
        return res2;
    }

    // 旧协议 V12 DD...77
    if (bytes[0] === 0xDD && bytes[1] === 0x03 && bytes[2] === 0x00) {
        var dLen = bytes[3];
        var d3   = bytes.slice(4, 4 + dLen);
        var fetSt= d3[20];
        var bigU = (fetSt>>7)&1;
        var cMult= bigU?100:10;
        var packV3 = ((d3[0]<<8)|d3[1])*10/1000.0;
        var rawCur3 = (d3[2]<<8)|d3[3];
        if(rawCur3>=0x8000) rawCur3-=0x10000;
        var packA3 = rawCur3*cMult/1000.0;
        var ntcCnt = d3[22];
        var temps3 = [];
        for(var t=0;t<ntcCnt&&t<8;t++){
            var tk=((d3[23+t*2]<<8)|d3[24+t*2]);
            temps3.push(Math.round(tk-2731)/10.0);
        }
        var tAvg3=temps3.length?Math.round(temps3.reduce(function(a,b){return a+b;},0)/temps3.length*10)/10:0;
        var tMax3=temps3.length?Math.max.apply(null,temps3):0;
        var prot3=(d3[16]<<8)|d3[17];
        var base3 = {
            brand:'JBD', protocol:'V12_DD77',
            soc:d3[19], soh:0,
            pack_voltage:Math.round(packV3*100)/100,
            pack_current:Math.round(packA3*100)/100,
            power_w:Math.round(packV3*packA3*10)/10,
            temperature_avg:tAvg3, temperature_max:tMax3,
            cell_count:d3[21],
            remain_ah:Math.round(((d3[4]<<8)|d3[5])*cMult)/1000.0,
            full_capacity_ah:Math.round(((d3[6]<<8)|d3[7])*cMult)/1000.0,
            cycle_count:(d3[8]<<8)|d3[9],
            charge_state:(prot3>>2)&1, discharge_state:(prot3>>3)&1,
            charge_mos:(fetSt>>0)&1, discharge_mos:(fetSt>>1)&1,
            delta_v:0, alarm_cell_imbalance:0,
            alarm_cell_ovp:(prot3>>0)&1, alarm_cell_uvp:(prot3>>1)&1,
            alarm_bat_ovp:(prot3>>2)&1, alarm_bat_uvp:(prot3>>3)&1,
            alarm_over_current:((prot3>>8)|(prot3>>9))&1,
            alarm_short_circuit:(prot3>>10)&1,
            alarm_over_temp:((prot3>>4)|(prot3>>6))&1
        };
        // 合并单体电压帧
        if(bytes2 && bytes2[0]===0xDD && bytes2[1]===0x04 && bytes2[2]===0x00){
            var cLen=bytes2[3], maxMv4=0, minMv4=9999;
            for(var ci=0;ci<cLen/2;ci++){
                var cmv=(bytes2[4+ci*2]<<8)|bytes2[5+ci*2];
                if(cmv>500){
                    var cidx=(ci+1)<10?'0'+(ci+1):''+(ci+1);
                    base3['cell_v_'+cidx]=Math.round(cmv)/1000.0;
                    if(cmv>maxMv4)maxMv4=cmv;
                    if(cmv<minMv4)minMv4=cmv;
                }
            }
            base3.delta_v=Math.round(maxMv4-minMv4)/1000.0;
            base3.alarm_cell_imbalance=(maxMv4-minMv4)>50?1:0;
        }
        return base3;
    }
    return null;
}

// ════════ DY 达锂 BMS 解析 ════════════════════════════════════════════════════

function parseDY(bytes) {
    if (!bytes || bytes.length < 7) return null;
    if (bytes[0] !== 0x51) return null;
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);
    function r(reg){var off=reg*2;return(off+1>=d.length)?0:((d[off]<<8)|d[off+1]);}
    function ri(reg){var v=r(reg);return v>=0x8000?v-0x10000:v;}

    var cellCnt = Math.min(r(0x3C), 48);
    var tmpCnt  = Math.min(r(0x3D), 8);
    var cells   = {}, maxMv=0, minMv=9999;
    for(var i=0;i<cellCnt;i++){
        var mv=r(i);
        if(mv>500){
            var idx=(i+1)<10?'0'+(i+1):''+(i+1);
            cells['cell_v_'+idx]=Math.round(mv)/1000.0;
            if(mv>maxMv)maxMv=mv; if(mv<minMv)minMv=mv;
        }
    }
    var temps=[];
    for(var j=0;j<tmpCnt;j++){var rw=r(0x30+j);if(rw)temps.push(rw-40);}
    var tAvg=temps.length?Math.round(temps.reduce(function(a,b){return a+b;},0)/temps.length*10)/10:0;
    var tMax=temps.length?Math.max.apply(null,temps):0;
    var packA=Math.round(r(0x39)-30000)/10.0;
    var packV=Math.round(r(0x38))/10.0;
    var soc=Math.round(r(0x3A))/10.0;
    var dV=maxMv-minMv;
    var f01=r(0x6D),f45=r(0x6F);
    var res={
        brand:'DY', soc:soc, soh:0,
        pack_voltage:packV, pack_current:packA,
        power_w:Math.round(packV*packA*10)/10,
        temperature_avg:tAvg, temperature_max:tMax,
        mos_temperature:r(0x5A)-40, env_temperature:r(0x5B)-40,
        delta_v:Math.round(dV)/1000.0,
        cell_count:cellCnt, remain_ah:Math.round(r(0x4B))/10.0,
        full_capacity_ah:0, cycle_count:r(0x4C),
        charge_state:r(0x48)===1?1:0, discharge_state:r(0x48)===2?1:0,
        balance_state:r(0x4D), charger_plugged:r(0x49),
        charge_mos:r(0x52), discharge_mos:r(0x53),
        alarm_cell_ovp:(f01&7)>0?1:0, alarm_cell_uvp:((f01>>3)&7)>0?1:0,
        alarm_bat_ovp:(f45>>7)&1, alarm_bat_uvp:(f45>>14)&1,
        alarm_over_current:((f45>>8)&7)>0||((f45>>11)&7)>0?1:0,
        alarm_short_circuit:(f45>>6)&1,
        alarm_over_temp:((f01>>11)&7)>0||((r(0x6E)>>3)&7)>0?1:0,
        alarm_cell_imbalance:(((f01>>8)&7)>0||dV>50)?1:0
    };
    for(var k in cells) res[k]=cells[k];
    return res;
}

// ════════ 逆变器解析（统一接口）══════════════════════════════════════════════

function parseInverter(bytes, brand) {
    if (!bytes || bytes.length < 7) return null;
    if (bytes[1] & 0x80) return null;
    if (bytes[1] !== 0x03) return null;
    var dataLen = bytes[2];
    var d = bytes.slice(3, 3 + dataLen);

    function r(off){return(off+1>=d.length)?0:((d[off]<<8)|d[off+1]);}
    function ri(off){var v=r(off);return v>=0x8000?v-0x10000:v;}
    function r32(off){return((r(off)<<16)|r(off+2))>>>0;}
    function rReg(reg,base){return r((reg-(base||0))*2);}
    function riReg(reg,base){return ri((reg-(base||0))*2);}

    var inv = {inv_brand: brand};

    if (brand === 'GOODWE') {
        inv.inv_status        = rReg(0x0008);
        inv.inv_pv1_voltage   = rReg(0x000A)*0.1;
        inv.inv_pv2_voltage   = rReg(0x000C)*0.1;
        inv.inv_pv_power      = rReg(0x0011)*rReg(0x0013)*0.01;
        inv.inv_grid_voltage  = rReg(0x0011)*0.1;
        inv.inv_grid_freq     = rReg(0x0016)*0.01;
        inv.inv_grid_power    = riReg(0x001E)*1;
        inv.inv_load_power    = rReg(0x0027)*1;
        inv.inv_bat_voltage   = rReg(0x0034)*0.1;
        inv.inv_bat_current   = riReg(0x0035)*0.1;
        inv.inv_bat_soc       = rReg(0x0037);
        inv.inv_bat_power     = Math.round(inv.inv_bat_voltage*inv.inv_bat_current*10)/10;
        inv.inv_today_gen_kwh = rReg(0x0044)*0.1;
        inv.inv_total_gen_kwh = r32(0x0045*2)*0.1;
        inv.inv_temperature   = riReg(0x0058)*0.1;
    }
    else if (brand === 'DEYE') {
        var B=3;
        inv.inv_status        = riReg(0x003B,B);
        inv.inv_pv1_voltage   = rReg(0x006D,B)*0.1;
        inv.inv_pv2_voltage   = rReg(0x006F,B)*0.1;
        inv.inv_pv_power      = rReg(0x00DC,B)+rReg(0x00DD,B);
        inv.inv_grid_voltage  = rReg(0x0049,B)*0.1;
        inv.inv_grid_freq     = rReg(0x004C,B)*0.01;
        inv.inv_grid_power    = riReg(0x0046,B)*10;
        inv.inv_load_power    = rReg(0x004B,B)*10;
        inv.inv_bat_voltage   = rReg(0x00B5,B)*0.01;
        inv.inv_bat_current   = riReg(0x00B6,B)*0.01;
        inv.inv_bat_soc       = rReg(0x00B8,B);
        inv.inv_bat_temperature = riReg(0x00B7,B)*0.1;
        inv.inv_bat_power     = Math.round(inv.inv_bat_voltage*inv.inv_bat_current*10)/10;
        inv.inv_today_gen_kwh = rReg(0x0041,B)*0.1;
        inv.inv_total_gen_kwh = ((rReg(0x0042,B)<<16)|rReg(0x0043,B))*0.1;
        inv.inv_temperature   = riReg(0x005A,B)*0.1;
    }
    else if (brand === 'SOLIS') {
        var B2=3;
        inv.inv_status       = rReg(0x0AB0,B2);
        inv.inv_pv1_voltage  = rReg(0x0AE7,B2)*0.1;
        inv.inv_pv_power     = r32((0x0AE9-B2)*2);
        inv.inv_grid_voltage = rReg(0x0AEF,B2)*0.1;
        inv.inv_grid_freq    = rReg(0x0AEC,B2)*0.01;
        inv.inv_grid_power   = riReg(0x0AEE,B2);
        inv.inv_load_power   = rReg(0x0AB6,B2);
        inv.inv_bat_voltage  = rReg(0x0AFF,B2)*0.1;
        inv.inv_bat_current  = riReg(0x0B00,B2)*0.1;
        inv.inv_bat_soc      = rReg(0x0BF3,B2);
        inv.inv_bat_power    = Math.round(inv.inv_bat_voltage*inv.inv_bat_current*10)/10;
        inv.inv_today_gen_kwh= rReg(0x0AB1,B2)*0.1;
        inv.inv_total_gen_kwh= r32((0x0AB3-B2)*2)*0.1;
        inv.inv_temperature  = riReg(0x0B03,B2)*0.1;
    }
    else if (brand === 'GROWATT') {
        inv.inv_status       = r(0);
        inv.inv_pv1_voltage  = r(2)*0.1;
        inv.inv_pv_power     = r32(10);
        inv.inv_grid_voltage = r(40)*0.1;
        inv.inv_grid_freq    = r(44)*0.01;
        inv.inv_grid_power   = r32(48);
        inv.inv_load_power   = r32(74);
        inv.inv_bat_voltage  = r(166)*0.1;
        inv.inv_bat_current  = ri(174)*0.1;
        inv.inv_bat_soc      = r(176);
        inv.inv_bat_power    = Math.round(inv.inv_bat_voltage*inv.inv_bat_current*10)/10;
        inv.inv_today_gen_kwh= r(130)*0.1;
        inv.inv_total_gen_kwh= r32(132)*0.1;
        inv.inv_temperature  = ri(93)*0.1;
    }
    else if (brand === 'SOFAR') {
        var B3=0x200;
        inv.inv_status       = rReg(0x0200,B3);
        inv.inv_pv1_voltage  = rReg(0x0206,B3)*0.1;
        inv.inv_pv_power     = rReg(0x0215,B3)*10;
        inv.inv_grid_voltage = rReg(0x020A,B3)*0.1;
        inv.inv_grid_freq    = rReg(0x020C,B3)*0.01;
        inv.inv_grid_power   = riReg(0x0212,B3)*10;
        inv.inv_load_power   = rReg(0x0213,B3)*10;
        inv.inv_bat_voltage  = rReg(0x0218,B3)*0.1;
        inv.inv_bat_current  = riReg(0x0219,B3)*0.01;
        inv.inv_bat_soc      = rReg(0x0210,B3);
        inv.inv_bat_power    = rReg(0x020D,B3)*10;
        inv.inv_today_gen_kwh= rReg(0x021F,B3)*0.1;
        inv.inv_total_gen_kwh= ((rReg(0x0220,B3)<<16)|rReg(0x0221,B3))*0.1;
        inv.inv_temperature  = riReg(0x0238,B3)*0.1;
    }

    return inv;
}


// ════════════════════════════════════════════════════════════════════════════
// ★ ThingsBoard Transformation 主函数 ★
// 将此整个文件内容粘贴到规则链 Script Transformation 节点
// ════════════════════════════════════════════════════════════════════════════

function Transform(msg, metadata, msgType) {
    var result = {};

    try {
        // ── 读取设备属性 ──────────────────────────────────────────────────────
        var bmsBrand  = (metadata.bms_brand  || 'JK').toUpperCase();
        var invBrand  = (metadata.inv_brand  || 'NONE').toUpperCase();
        var hasInv    = metadata.has_inverter === true || metadata.has_inverter === 'true';

        // ── 解析 BMS ─────────────────────────────────────────────────────────
        var bmsBytes  = msg.bms_raw  ? hexToBytes(msg.bms_raw)  : null;
        var bmsBytes2 = msg.bms_raw2 ? hexToBytes(msg.bms_raw2) : null;
        var bmsData   = null;

        if (bmsBrand === 'JK') {
            bmsData = parseJK(bmsBytes);
        } else if (bmsBrand === 'JBD') {
            bmsData = parseJBD(bmsBytes, bmsBytes2);
        } else if (bmsBrand === 'DY') {
            bmsData = parseDY(bmsBytes);
        }

        if (bmsData) {
            for (var k in bmsData) result[k] = bmsData[k];
        } else {
            result.bms_parse_error = 1;
        }

        // ── 解析逆变器（如有）──────────────────────────────────────────────
        if (hasInv && invBrand !== 'NONE' && msg.inv_raw) {
            var invBytes = hexToBytes(msg.inv_raw);
            var invData  = parseInverter(invBytes, invBrand);
            if (invData) {
                for (var k2 in invData) result[k2] = invData[k2];
            } else {
                result.inv_parse_error = 1;
            }
        }

        // ── 计算电网频率异常告警（菲律宾60Hz）──────────────────────────────
        if (result.inv_grid_freq) {
            var freq = result.inv_grid_freq;
            result.alarm_grid_freq = (freq < 59.5 || freq > 60.5) ? 1 : 0;
        }

        // ── 元数据 ────────────────────────────────────────────────────────
        result.ts = new Date().getTime();

    } catch (e) {
        result.parse_exception = e.message || String(e);
    }

    return { msg: result, metadata: metadata, msgType: msgType };
}
