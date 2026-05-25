#!/usr/bin/env python3
"""
CoreTect ThingsBoard Device Simulator
=====================================
模拟三类设备向ThingsBoard持续发送遥测数据：
  - ESS储能柜 × 3台 (菲律宾离岛)
  - 高尔夫球车电池 × 5辆
  - 工商业储能 × 1套

用法:
  1. pip install requests
  2. python3 coretect_simulator.py

作者: CoreTect Global Technology
"""

import requests
import time
import random
from datetime import datetime

# ============================================================
# ⚙️  配置区
# ============================================================

TB_HOST = "https://monitor.coretect-microgrid.com"

DEVICE_TOKENS = {
    "ESS-PH-001":   "JKCwYZWhfFQvz4PmEVTW",
    "ESS-PH-002":   "T2arPCbTV4o3d963bVLm",
    "ESS-PH-003":   "r0X097dVVn0pqvqimGU3",
    "GOLF-001":     "zk88HuEwrfQgALfbVRcu",
    "GOLF-002":     "Z49W65CzVL8znPWyk4Ba",
    "GOLF-003":     "nO2FSvvXzc9ro0GYV7FG",
    "GOLF-004":     "n1kRAF0AInDTZ6HSkfZ0",
    "GOLF-005":     "KBQ6QLzmMnsXThqBwERR",
    "BESS-COM-001": "CTn7avFT1u4llj3IJ1hY",
}

SEND_INTERVAL = 30  # 秒，演示时可改成10

# ============================================================
# 📍 设备静态信息
# ============================================================

DEVICE_PROFILES = {
    "ESS-PH-001":   {"type":"ess",        "location":"Palawan Island",          "latitude":9.8349,  "longitude":118.7384, "capacity_kwh":64.0,  "nominal_voltage":51.2, "cell_count":16},
    "ESS-PH-002":   {"type":"ess",        "location":"Cebu Island",             "latitude":10.3157, "longitude":123.8854, "capacity_kwh":30.0,  "nominal_voltage":51.2, "cell_count":16},
    "ESS-PH-003":   {"type":"ess",        "location":"Quezon Province",         "latitude":14.0313, "longitude":122.1116, "capacity_kwh":48.0,  "nominal_voltage":51.2, "cell_count":16},
    "GOLF-001":     {"type":"golf",       "location":"Cebu Golf & Country Club","latitude":10.3312, "longitude":123.9071, "capacity_kwh":10.0,  "nominal_voltage":48.0, "cell_count":15},
    "GOLF-002":     {"type":"golf",       "location":"Cebu Golf & Country Club","latitude":10.3315, "longitude":123.9075, "capacity_kwh":10.0,  "nominal_voltage":48.0, "cell_count":15},
    "GOLF-003":     {"type":"golf",       "location":"Cebu Golf & Country Club","latitude":10.3308, "longitude":123.9068, "capacity_kwh":10.0,  "nominal_voltage":48.0, "cell_count":15},
    "GOLF-004":     {"type":"golf",       "location":"Manila Golf & Country Club","latitude":14.5547,"longitude":121.0244,"capacity_kwh":10.0,  "nominal_voltage":48.0, "cell_count":15},
    "GOLF-005":     {"type":"golf",       "location":"Manila Golf & Country Club","latitude":14.5549,"longitude":121.0247,"capacity_kwh":10.0,  "nominal_voltage":48.0, "cell_count":15},
    "BESS-COM-001": {"type":"commercial", "location":"Makati Commercial District","latitude":14.5547,"longitude":121.0244,"capacity_kwh":200.0, "nominal_voltage":768.0,"cell_count":240},
}

# ============================================================
# 🔄 设备状态追踪
# ============================================================

device_states = {}

def init_device_state(device_id):
    profile = DEVICE_PROFILES[device_id]
    t = profile["type"]
    device_states[device_id] = {
        "soc":         random.uniform(40, 90),
        "mode":        random.choice(["charging","discharging","standby"]),
        "cycle_count": random.randint(50, 500),
        "soh":         random.uniform(88, 99),
        "tick":        random.randint(0, 100),
    }

def gentle_fluctuate(value, max_delta, min_val, max_val):
    return round(max(min_val, min(max_val, value + random.uniform(-max_delta, max_delta))), 2)

# ============================================================
# 📊 ESS 储能柜数据
# ============================================================

def generate_ess_telemetry(device_id):
    state  = device_states[device_id]
    profile = DEVICE_PROFILES[device_id]

    # SOC 趋势
    if state["mode"] == "charging":
        state["soc"] = min(98, state["soc"] + random.uniform(0.1, 0.4))
        if state["soc"] >= 98: state["mode"] = "discharging"
    elif state["mode"] == "discharging":
        state["soc"] = max(15, state["soc"] - random.uniform(0.05, 0.3))
        if state["soc"] <= 15: state["mode"] = "charging"
    else:
        state["soc"] = gentle_fluctuate(state["soc"], 0.1, 20, 95)

    soc     = round(state["soc"], 1)
    voltage = round(profile["nominal_voltage"] * (0.85 + soc/100*0.2) + random.uniform(-0.5, 0.5), 2)

    if state["mode"] == "charging":
        current = round(random.uniform(20, 80), 1)
    elif state["mode"] == "discharging":
        current = round(-random.uniform(10, 60), 1)
    else:
        current = round(random.uniform(-2, 2), 1)

    power_kw    = round(voltage * current / 1000, 2)
    temperature = round(28 + abs(current)*0.05 + random.uniform(-1, 1), 1)

    # 16节电芯电压
    cell_voltages = {}
    base_v = voltage / profile["cell_count"]
    for i in range(1, profile["cell_count"]+1):
        offset = -random.uniform(0.02, 0.08) if (i==14 and random.random()<0.3) else random.uniform(-0.005, 0.005)
        cell_voltages[f"cell_v_{i:02d}"] = round(base_v + offset, 3)

    delta_v      = round(max(cell_voltages.values()) - min(cell_voltages.values()), 4)
    state["soh"] = gentle_fluctuate(state["soh"], 0.01, 75, 100)
    state["tick"] += 1
    energy_stored       = round(profile["capacity_kwh"] * soc / 100, 2)
    total_discharge_kwh = round(state["cycle_count"] * profile["capacity_kwh"] * 0.9 + state["tick"]*0.01, 1)

    return {
        # 核心
        "soc": soc, "soh": round(state["soh"],1),
        "status": state["mode"].upper(), "fault_code": 0,
        # 电气
        "pack_voltage": voltage, "pack_current": current,
        "power_kw": power_kw,   "delta_v": delta_v,
        "energy_stored_kwh": energy_stored, "capacity_kwh": profile["capacity_kwh"],
        # 温度
        "temperature_max": round(temperature+random.uniform(0,2),1),
        "temperature_avg": temperature,
        "temperature_min": round(temperature-random.uniform(0,1.5),1),
        # 统计
        "cycle_count": state["cycle_count"],
        "total_discharge_kwh": total_discharge_kwh,
        # 告警
        "alarm_high_temp": int(temperature > 45),
        "alarm_delta_v":   int(delta_v > 0.05),
        # 位置
        "latitude": profile["latitude"], "longitude": profile["longitude"],
        # 电芯
        **cell_voltages,
    }

# ============================================================
# 📊 高尔夫球车数据
# ============================================================

def generate_golf_telemetry(device_id):
    state   = device_states[device_id]
    profile = DEVICE_PROFILES[device_id]

    if state["mode"] == "discharging":
        state["soc"] = max(10, state["soc"] - random.uniform(0.1, 0.5))
        if state["soc"] <= 10: state["mode"] = "charging"
    elif state["mode"] == "charging":
        state["soc"] = min(100, state["soc"] + random.uniform(0.3, 0.8))
        if state["soc"] >= 100: state["mode"] = "standby"
    else:
        state["soc"] = gentle_fluctuate(state["soc"], 0.1, 10, 100)

    soc     = round(state["soc"], 1)
    voltage = round(profile["nominal_voltage"] * (0.88 + soc/100*0.15) + random.uniform(-0.3,0.3), 2)

    if state["mode"] == "discharging":
        current   = round(-random.uniform(15, 45), 1)
        speed_kmh = round(random.uniform(5, 18), 1)
    elif state["mode"] == "charging":
        current   = round(random.uniform(10, 20), 1)
        speed_kmh = 0.0
    else:
        current   = round(random.uniform(-1, 1), 1)
        speed_kmh = 0.0

    temperature = round(30 + abs(current)*0.08 + random.uniform(-1,1), 1)

    cell_voltages = {}
    base_v = voltage / profile["cell_count"]
    for i in range(1, profile["cell_count"]+1):
        cell_voltages[f"cell_v_{i:02d}"] = round(base_v + random.uniform(-0.008, 0.008), 3)

    delta_v      = round(max(cell_voltages.values()) - min(cell_voltages.values()), 4)
    state["soh"] = gentle_fluctuate(state["soh"], 0.02, 70, 100)

    return {
        "soc": soc, "soh": round(state["soh"],1),
        "status": state["mode"].upper(),
        "pack_voltage": voltage, "pack_current": current,
        "power_w": round(voltage * abs(current), 1),
        "delta_v": delta_v, "temperature": temperature,
        "speed_kmh": speed_kmh, "cycle_count": state["cycle_count"],
        "alarm_low_soc":   int(soc < 15),
        "alarm_high_temp": int(temperature > 50),
        "latitude":  profile["latitude"]  + random.uniform(-0.001, 0.001),
        "longitude": profile["longitude"] + random.uniform(-0.001, 0.001),
        **cell_voltages,
    }

# ============================================================
# 📊 工商业储能数据
# ============================================================

def generate_commercial_telemetry(device_id):
    state   = device_states[device_id]
    profile = DEVICE_PROFILES[device_id]

    hour = datetime.now().hour
    target = "discharging" if 8 <= hour <= 22 else "charging"
    if   state["soc"] >= 95: state["mode"] = "discharging"
    elif state["soc"] <= 10: state["mode"] = "charging"
    else:                     state["mode"] = target

    if state["mode"] == "charging":
        state["soc"] = min(95, state["soc"] + random.uniform(0.05, 0.2))
        current  = round(random.uniform(50, 150), 1)
    else:
        state["soc"] = max(10, state["soc"] - random.uniform(0.05, 0.25))
        current  = round(-random.uniform(30, 120), 1)

    soc           = round(state["soc"], 1)
    voltage       = round(profile["nominal_voltage"]*(0.9+soc/100*0.12)+random.uniform(-2,2), 1)
    power_kw      = round(voltage * current / 1000, 1)
    temperature   = round(32 + abs(current)*0.02 + random.uniform(-1,2), 1)
    energy_stored = round(profile["capacity_kwh"] * soc / 100, 1)
    state["soh"]  = gentle_fluctuate(state["soh"], 0.005, 80, 100)

    grid_voltage   = round(220 + random.uniform(-5, 5), 1)
    grid_frequency = round(60  + random.uniform(-0.1, 0.1), 2)
    total_co2      = round(state["cycle_count"] * profile["capacity_kwh"] * 0.7 * 0.5, 1)

    return {
        "soc": soc, "soh": round(state["soh"],1),
        "status": state["mode"].upper(),
        "pack_voltage": voltage, "pack_current": current,
        "power_kw": power_kw,
        "energy_stored_kwh": energy_stored, "capacity_kwh": profile["capacity_kwh"],
        "temperature_max": round(temperature+2,1), "temperature_avg": temperature,
        "grid_voltage_v": grid_voltage, "grid_frequency_hz": grid_frequency,
        "cycle_count": state["cycle_count"], "total_co2_saved_kg": total_co2,
        "alarm_overtemp":       int(temperature > 50),
        "alarm_grid_abnormal":  int(abs(grid_frequency-60) > 0.5),
        "latitude":  profile["latitude"], "longitude": profile["longitude"],
    }

# ============================================================
# 📡 发送到 ThingsBoard
# ============================================================

def send_telemetry(device_id, token, data):
    url = f"{TB_HOST}/api/v1/{token}/telemetry"
    try:
        r = requests.post(url, json=data, headers={"Content-Type":"application/json"}, timeout=10)
        soc   = data.get("soc","-")
        st    = data.get("status","-")
        temp  = data.get("temperature_avg", data.get("temperature","-"))
        if r.status_code == 200:
            print(f"  ✅ {device_id:15s} | SOC:{soc:5.1f}% | {st:12s} | Temp:{temp}°C")
        else:
            print(f"  ❌ {device_id:15s} | HTTP {r.status_code}")
    except Exception as e:
        print(f"  ⚠️  {device_id:15s} | {e}")

def generate_telemetry(device_id):
    t = DEVICE_PROFILES[device_id]["type"]
    if   t == "ess":        return generate_ess_telemetry(device_id)
    elif t == "golf":       return generate_golf_telemetry(device_id)
    elif t == "commercial": return generate_commercial_telemetry(device_id)

# ============================================================
# 🚀 主循环
# ============================================================

def main():
    print("=" * 60)
    print("  CoreTect ThingsBoard Simulator  v1.0")
    print(f"  服务器: {TB_HOST}")
    print(f"  设备数: {len(DEVICE_TOKENS)} 台")
    print(f"  间隔:   {SEND_INTERVAL} 秒")
    print("=" * 60)

    print("\n初始化设备状态...")
    for d in DEVICE_TOKENS:
        init_device_state(d)
        print(f"  ✓ {d}  ({DEVICE_PROFILES[d]['location']})")

    print(f"\n▶  开始运行，按 Ctrl+C 停止\n")

    n = 0
    while True:
        n += 1
        print(f"\n[Round {n:04d}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        for device_id, token in DEVICE_TOKENS.items():
            send_telemetry(device_id, token, generate_telemetry(device_id))
        print(f"\n  {SEND_INTERVAL}秒后继续...")
        time.sleep(SEND_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n模拟器已停止。")
