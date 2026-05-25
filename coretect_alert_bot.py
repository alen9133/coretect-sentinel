#!/usr/bin/env python3
"""
CoreTect Telegram Alert Bot v2.0
=================================
修复版：加入冷却时间，同一告警2小时内不重复推送
推送链接改为品牌云监控平台

作者: CoreTect Global Technology
"""

import requests
import time
from datetime import datetime

# ═══════════════════════════════════════════
# ⚙️ 配置区 — 只需修改这里
# ═══════════════════════════════════════════

TB_HOST  = "https://monitor.coretect-microgrid.com"
TB_USER  = "tenant@thingsboard.org"
TB_PASS  = "YOUR_PASSWORD_HERE"

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

CHAT_IDS = [
    "YOUR_CHAT_ID_HERE",
]

# 客户看到的品牌云监控地址（Telegram消息里的链接）
CLIENT_URL = "https://coretect-microgrid.com/intake.html?mode=client"

# 告警阈值
THRESHOLDS = {
    "temp_high":      45.0,
    "temp_critical":  55.0,
    "delta_v_warn":   0.050,
    "delta_v_alarm":  0.100,
    "soc_low":        20.0,
    "soc_critical":   10.0,
    "cycle_maintain": 3000,
    "cycle_warn":     4500,
}

CHECK_INTERVAL  = 60    # 每60秒检查一次
ALERT_COOLDOWN  = 7200  # 同一告警2小时（7200秒）内不重复推送
DAILY_REPORT_HOUR = 8   # 每天8:00发日报

ELEC_RATE = 12.0
ELEC_SYM  = "₱"

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════

# alert_last_sent: 记录每个告警最后一次推送的时间戳
# 格式: {"ESS-PH-001_high_temp": 1716123456.0, ...}
alert_last_sent = {}

# alert_active: 记录告警是否处于激活状态（用于恢复通知）
# 格式: {"ESS-PH-001_high_temp": True/False}
alert_active = {}

last_daily_report = None
jwt_token = ""

# ═══════════════════════════════════════════
# ThingsBoard API
# ═══════════════════════════════════════════

def tb_login():
    global jwt_token
    try:
        r = requests.post(
            f"{TB_HOST}/api/auth/login",
            json={"username": TB_USER, "password": TB_PASS},
            timeout=10
        )
        if r.status_code == 200:
            jwt_token = r.json()["token"]
            print(f"  ✅ ThingsBoard 登录成功")
            return True
        print(f"  ❌ 登录失败: {r.status_code}")
        return False
    except Exception as e:
        print(f"  ❌ 登录异常: {e}")
        return False

def tb_get(path):
    global jwt_token
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    r = requests.get(f"{TB_HOST}{path}", headers=headers, timeout=10)
    if r.status_code == 401:
        tb_login()
        r = requests.get(f"{TB_HOST}{path}", headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def get_all_devices():
    data = tb_get("/api/tenant/devices?pageSize=50&page=0")
    return data.get("data", [])

KEYS = (
    "soc,soh,status,pack_voltage,pack_current,power_kw,"
    "delta_v,temperature,temperature_avg,temperature_max,temperature_min,"
    "energy_stored_kwh,capacity_kwh,cycle_count,total_discharge_kwh,"
    "total_co2_saved_kg,alarm_high_temp,alarm_delta_v,alarm_low_soc,"
    "alarm_overtemp,alarm_grid_abnormal,grid_frequency_hz,fault_code"
)

def get_telemetry(device_id):
    data = tb_get(f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys={KEYS}")
    tel = {}
    for k, v in data.items():
        if v and v[0]:
            val = v[0]["value"]
            try:
                tel[k] = float(val)
            except (ValueError, TypeError):
                tel[k] = val
    return tel

# ═══════════════════════════════════════════
# Telegram 推送
# ═══════════════════════════════════════════

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if r.status_code == 200:
                print(f"  📱 推送成功 → {chat_id}")
            else:
                print(f"  ❌ 推送失败: {r.text[:80]}")
        except Exception as e:
            print(f"  ❌ 推送异常: {e}")

def msg_alert_l1(device, key_desc, detail, temp_val=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"🚨 <b>CORETECT ALERT — Level 1</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Site: <b>{device}</b>\n"
        f"🔔 Alert: <b>{key_desc}</b>\n"
        f"📊 Detail: {detail}\n"
        f"⏰ Time: {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Please check your device immediately!</b>\n"
        f"🌐 <a href='{CLIENT_URL}'>Open CoreTect Monitor</a>"
    )

def msg_alert_l2(device, key_desc, detail):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"⚠️ <b>CORETECT WARNING — Level 2</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Site: <b>{device}</b>\n"
        f"🔔 Warning: <b>{key_desc}</b>\n"
        f"📊 Detail: {detail}\n"
        f"⏰ Time: {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Action recommended within 24 hours.\n"
        f"🌐 <a href='{CLIENT_URL}'>Open CoreTect Monitor</a>"
    )

def msg_recovery(device, key_desc, detail):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"✅ <b>CORETECT RECOVERY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Site: <b>{device}</b>\n"
        f"✓ Recovered: <b>{key_desc}</b>\n"
        f"📊 {detail}\n"
        f"⏰ Time: {now}\n"
        f"🌐 <a href='{CLIENT_URL}'>Open CoreTect Monitor</a>"
    )

def msg_daily(devices_data):
    now = datetime.now().strftime("%Y-%m-%d")
    online  = sum(1 for d in devices_data if d["tel"])
    tot_kwh = sum(float(d["tel"].get("total_discharge_kwh") or 0) for d in devices_data)
    tot_co2 = sum(float(d["tel"].get("total_co2_saved_kg") or 0) for d in devices_data)
    tot_nrg = sum(float(d["tel"].get("energy_stored_kwh") or 0) for d in devices_data)
    socs    = [float(d["tel"].get("soc") or 0) for d in devices_data if d["tel"].get("soc")]
    avg_soc = sum(socs)/len(socs) if socs else 0
    savings = tot_kwh * ELEC_RATE

    lines = [
        f"📊 <b>CoreTect Daily Report — {now}</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🟢 Online: {online}/{len(devices_data)}",
        f"⚡ Avg SOC: {avg_soc:.1f}%",
        f"🔋 Total Stored: {tot_nrg:.1f} kWh",
        f"💰 Cost Savings: {ELEC_SYM}{savings:,.0f}",
        f"🌿 CO₂ Saved: {tot_co2:,.0f} kg",
        f"━━━━━━━━━━━━━━━━━━━━",
        "<b>Device Status:</b>",
    ]
    for d in devices_data:
        t   = d["tel"]
        soc = float(t.get("soc") or 0)
        st  = t.get("status", "UNKNOWN")
        ico = "🟢" if soc >= 60 else "🟡" if soc >= 20 else "🔴"
        lines.append(f"{ico} {d['name']}: SOC {soc:.0f}% | {st}")

    active_alarms = sum(
        1 for d in devices_data
        for k in ["alarm_high_temp","alarm_delta_v","alarm_low_soc","alarm_overtemp"]
        if float(d["tel"].get(k) or 0) == 1
    )
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🔔 Active Alarms: {active_alarms}",
        f"🌐 <a href='{CLIENT_URL}'>Open CoreTect Monitor</a>",
    ]
    return "\n".join(lines)

# ═══════════════════════════════════════════
# 核心：带冷却时间的告警触发
# ═══════════════════════════════════════════

def trigger(device, key, desc, detail, level=1):
    """
    触发告警，带冷却时间控制：
    - 同一设备同一告警，ALERT_COOLDOWN 秒内不重复推送
    - 告警从未激活→激活才推送
    """
    ck  = f"{device}__{key}"   # 唯一键
    now = time.time()
    last_time = alert_last_sent.get(ck, 0)
    elapsed   = now - last_time

    if elapsed < ALERT_COOLDOWN:
        remaining = int((ALERT_COOLDOWN - elapsed) / 60)
        print(f"  ⏱  [{device}:{key}] 冷却中，剩余 {remaining} 分钟")
        return

    # 推送告警
    alert_last_sent[ck]  = now
    alert_active[ck]     = True

    if level == 1:
        send_telegram(msg_alert_l1(device, desc, detail))
    else:
        send_telegram(msg_alert_l2(device, desc, detail))

    print(f"  🔔 [L{level}告警] {device}: {desc} | {detail}")

def recover(device, key, desc, detail):
    """告警恢复通知（只在之前激活过的情况下推送）"""
    ck = f"{device}__{key}"
    if alert_active.get(ck):
        alert_active[ck] = False
        alert_last_sent[ck] = 0   # 重置冷却，下次可以立即告警
        send_telegram(msg_recovery(device, desc, detail))
        print(f"  ✅ [恢复] {device}: {desc}")

# ═══════════════════════════════════════════
# 告警检查逻辑
# ═══════════════════════════════════════════

def check_device(name, tel):
    t    = tel
    temp = t.get("temperature_avg") or t.get("temperature") or t.get("temperature_max")
    soc  = t.get("soc")
    dv   = t.get("delta_v")
    freq = t.get("grid_frequency_hz")
    cyc  = t.get("cycle_count")

    # ── 一级告警 ─────────────────────────
    # 危急高温
    if temp and temp >= THRESHOLDS["temp_critical"]:
        trigger(name, "critical_temp", "Battery Critical Temperature",
                f"Temp: {temp:.1f}°C 🔥🔥", level=1)
    else:
        recover(name, "critical_temp", "Critical Temperature",
                f"Temp returned to: {temp:.1f}°C" if temp else "Normal")

    # 高温
    if temp and THRESHOLDS["temp_high"] <= temp < THRESHOLDS["temp_critical"]:
        trigger(name, "high_temp", "Battery High Temperature",
                f"Temp: {temp:.1f}°C (limit: {THRESHOLDS['temp_high']}°C)", level=1)
    else:
        recover(name, "high_temp", "High Temperature",
                f"Temp normal: {temp:.1f}°C" if temp else "Normal")

    # BMS过温保护
    if float(t.get("alarm_overtemp") or 0) == 1:
        trigger(name, "overtemp", "BMS Over Temperature Protection Triggered",
                "BMS has activated protection", level=1)
    else:
        recover(name, "overtemp", "BMS Over Temperature", "BMS protection cleared")

    # 压差危急（一级）
    if dv and dv >= THRESHOLDS["delta_v_alarm"]:
        trigger(name, "dv_alarm", "Cell Severe Imbalance",
                f"ΔV = {dv*1000:.1f}mV (limit: {THRESHOLDS['delta_v_alarm']*1000:.0f}mV)", level=1)
    else:
        recover(name, "dv_alarm", "Cell Severe Imbalance",
                f"ΔV normal: {dv*1000:.1f}mV" if dv else "Normal")

    # 危急低电量（一级）
    if soc is not None and soc <= THRESHOLDS["soc_critical"]:
        trigger(name, "soc_critical", "Battery Critical Low",
                f"SOC: {soc:.1f}% (critical limit: {THRESHOLDS['soc_critical']}%)", level=1)
    else:
        recover(name, "soc_critical", "Critical Low Battery",
                f"SOC recovered: {soc:.1f}%" if soc else "Normal")

    # ── 二级告警 ─────────────────────────
    # 压差预警（二级）
    if dv and THRESHOLDS["delta_v_warn"] <= dv < THRESHOLDS["delta_v_alarm"]:
        trigger(name, "dv_warn", "Cell Imbalance Warning",
                f"ΔV = {dv*1000:.1f}mV (warn limit: {THRESHOLDS['delta_v_warn']*1000:.0f}mV)", level=2)
    else:
        recover(name, "dv_warn", "Cell Imbalance",
                f"ΔV OK: {dv*1000:.1f}mV" if dv else "Normal")

    # 低电量预警（二级）
    if soc is not None and THRESHOLDS["soc_critical"] < soc <= THRESHOLDS["soc_low"]:
        trigger(name, "low_soc", "Low Battery Warning",
                f"SOC: {soc:.1f}% (warn limit: {THRESHOLDS['soc_low']}%)", level=2)
    else:
        recover(name, "low_soc", "Low Battery",
                f"SOC OK: {soc:.1f}%" if soc else "Normal")

    # 电网频率异常（二级）
    if freq and (freq < 59.5 or freq > 60.5):
        trigger(name, "grid_freq", "Grid Frequency Abnormal",
                f"Freq: {freq:.2f}Hz (normal: 60Hz)", level=2)
    else:
        recover(name, "grid_freq", "Grid Frequency",
                f"Freq normal: {freq:.2f}Hz" if freq else "Normal")

    # 循环次数维护提醒（二级，只推送一次）
    if cyc and cyc >= THRESHOLDS["cycle_maintain"]:
        trigger(name, "cycle_maintain", "Maintenance Reminder",
                f"Cycle Count: {int(cyc)} (recommend check at {THRESHOLDS['cycle_maintain']})", level=2)

    # 接近寿命警告（一级）
    if cyc and cyc >= THRESHOLDS["cycle_warn"]:
        trigger(name, "cycle_eol", "Battery Aging Warning",
                f"Cycle Count: {int(cyc)} — Near end of life", level=1)

# ═══════════════════════════════════════════
# 日报
# ═══════════════════════════════════════════

def check_daily_report(devices_data):
    global last_daily_report
    now   = datetime.now()
    today = now.date()
    if now.hour == DAILY_REPORT_HOUR and now.minute < 2 and last_daily_report != today:
        last_daily_report = today
        print(f"\n  📊 发送日报...")
        send_telegram(msg_daily(devices_data))

# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

def main():
    print("=" * 60)
    print("  CoreTect Telegram Alert Bot  v2.0")
    print(f"  ThingsBoard : {TB_HOST}")
    print(f"  品牌平台   : {CLIENT_URL}")
    print(f"  检查间隔   : {CHECK_INTERVAL} 秒")
    print(f"  告警冷却   : {ALERT_COOLDOWN//3600} 小时")
    print(f"  日报时间   : 每天 {DAILY_REPORT_HOUR}:00")
    print("=" * 60)

    print("\n正在连接ThingsBoard...")
    if not tb_login():
        print("❌ 无法连接ThingsBoard，请检查账号密码")
        return

    print("正在获取设备列表...")
    raw_devices = get_all_devices()
    print(f"  发现 {len(raw_devices)} 台设备\n")

    # 启动通知
    send_telegram(
        f"🚀 <b>CoreTect Monitor Started v2.0</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ {len(raw_devices)} devices online\n"
        f"🔍 Checking every {CHECK_INTERVAL}s\n"
        f"⏱ Alert cooldown: {ALERT_COOLDOWN//3600}h\n"
        f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🌐 <a href='{CLIENT_URL}'>Open CoreTect Monitor</a>"
    )

    round_num = 0
    while True:
        round_num += 1
        print(f"\n[Round {round_num:04d}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)

        devices_data = []
        for dev in raw_devices:
            dev_id   = dev["id"]["id"]
            dev_name = dev["name"]
            try:
                tel = get_telemetry(dev_id)
                devices_data.append({"name": dev_name, "id": dev_id, "tel": tel})
                check_device(dev_name, tel)

                soc  = tel.get("soc", "--")
                tmp  = tel.get("temperature_avg") or tel.get("temperature") or "--"
                st   = tel.get("status", "--")
                print(f"  ✓ {dev_name:15s} | SOC:{float(soc) if soc != '--' else '--':>5}% | {str(st):12s} | {tmp}°C")
            except Exception as e:
                print(f"  ⚠️  {dev_name:15s} | Error: {e}")
                devices_data.append({"name": dev_name, "id": dev_id, "tel": {}})

        check_daily_report(devices_data)
        print(f"\n  ⏱  {CHECK_INTERVAL}秒后继续...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n告警机器人已停止。")
