"""
CORETECT Sentinel — 主程序
HaaS506-ED1 (ESP32-S3 MicroPython)

功能：
  1. 4G 联网
  2. 自动识别 BMS 品牌（JK 极空 / DY 达锂）
  3. 每 30 秒轮询 BMS，解析数据
  4. 通过 MQTT 上传统一 JSON 到 ThingsBoard
  5. 掉线自动重连，WDT 防止死机

接线（HaaS506-ED1）：
  RS485 A/B 端子 → BMS RS485 A/B
  12~24V DC 供电

配置说明：
  修改下方 CONFIG 区域填入实际参数即可，不需要改其他代码。
"""

import time
import json
import network
from machine import UART, WDT
from umqtt.simple import MQTTClient

from jk_bms import JKBMS
from dy_bms import DYBMS

# ═══════════════════════════════════════════════════════════════════════════════
#  ★ 配置区 — 只需修改这里 ★
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # ── ThingsBoard ──────────────────────────────────────────────────────────
    "tb_host":    "206.189.93.135",          # ThingsBoard 服务器 IP 或域名
    "tb_port":    1883,
    "tb_token":   "YOUR_DEVICE_TOKEN_HERE",  # 替换为设备的 Access Token

    # ── BMS 设置 ─────────────────────────────────────────────────────────────
    "bms_brand":  "AUTO",   # "AUTO"=自动检测, "JK"=极空, "DY"=达锂
    "jk_slave_addr": 1,     # 极空 BMS 从机地址（出厂默认1）
    # 达锂 BMS 地址固定 0x81/0x51，无需配置

    # ── UART 硬件引脚（HaaS506-ED1 RS485 = uart2）────────────────────────────
    "rs485_uart": 2,
    "rs485_tx":   17,        # 请对照板子丝印确认
    "rs485_rx":   18,

    # ── 上报间隔 ──────────────────────────────────────────────────────────────
    "upload_interval_s": 30,

    # ── 设备标识（显示在 ThingsBoard 属性里）────────────────────────────────
    "device_id":  "ESS-PH-001",
    "location":   "Palawan Island",
}

# ═══════════════════════════════════════════════════════════════════════════════

MQTT_TOPIC = b"v1/devices/me/telemetry"


# ─── 日志 ─────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = time.localtime()
    print(f"[{ts[3]:02d}:{ts[4]:02d}:{ts[5]:02d}] {msg}")


# ─── 4G 联网 ──────────────────────────────────────────────────────────────────

def connect_4g(timeout_s: int = 60) -> bool:
    """等待 4G 模块联网，成功返回 True"""
    log("正在等待 4G 联网...")
    try:
        lte = network.LTE()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if lte.isconnected():
                log(f"4G 已连接，IP: {lte.ifconfig()[0]}")
                return True
            time.sleep(2)
        log("4G 联网超时！")
        return False
    except Exception as e:
        log(f"4G 初始化失败: {e}")
        return False


# ─── MQTT 连接 ────────────────────────────────────────────────────────────────

def connect_mqtt() -> MQTTClient | None:
    """连接 ThingsBoard MQTT，返回 client 对象，失败返回 None"""
    try:
        client_id = CONFIG["device_id"].encode()
        client = MQTTClient(
            client_id=client_id,
            server=CONFIG["tb_host"],
            port=CONFIG["tb_port"],
            user=CONFIG["tb_token"].encode(),
            password=b"",
            keepalive=60,
        )
        client.connect()
        log(f"MQTT 已连接: {CONFIG['tb_host']}")
        return client
    except Exception as e:
        log(f"MQTT 连接失败: {e}")
        return None


# ─── BMS 自动识别 ─────────────────────────────────────────────────────────────

def detect_bms() -> object | None:
    """
    尝试自动识别 BMS 品牌。
    先试 JK（115200），失败再试 DY（9600）。
    返回已初始化的 BMS 驱动对象，失败返回 None。
    """
    uart_id = CONFIG["rs485_uart"]
    tx      = CONFIG["rs485_tx"]
    rx      = CONFIG["rs485_rx"]
    brand   = CONFIG["bms_brand"].upper()

    if brand == "JK":
        log("使用 JK 极空 BMS 驱动")
        return JKBMS(uart_id=uart_id, slave_addr=CONFIG["jk_slave_addr"],
                     tx_pin=tx, rx_pin=rx)

    if brand == "DY":
        log("使用 DY 达锂 BMS 驱动")
        return DYBMS(uart_id=uart_id, tx_pin=tx, rx_pin=rx)

    # AUTO 模式：先试 JK
    log("AUTO 模式：尝试 JK 极空 BMS...")
    bms = JKBMS(uart_id=uart_id, slave_addr=CONFIG["jk_slave_addr"],
                tx_pin=tx, rx_pin=rx)
    data = bms.read_all()
    if data:
        log(f"✅ 检测到 JK 极空 BMS，SOC={data['soc']}%")
        return bms

    # 再试 DY
    log("AUTO 模式：尝试 DY 达锂 BMS...")
    bms = DYBMS(uart_id=uart_id, tx_pin=tx, rx_pin=rx)
    data = bms.read_all()
    if data:
        log(f"✅ 检测到 DY 达锂 BMS，SOC={data['soc']}%")
        return bms

    log("❌ 未能识别 BMS 品牌，请检查接线和地址配置")
    return None


# ─── 数据上传 ─────────────────────────────────────────────────────────────────

def upload(client: MQTTClient, data: dict) -> bool:
    """发布 JSON 到 ThingsBoard，成功返回True"""
    try:
        # 追加设备元数据
        data["device_id"] = CONFIG["device_id"]
        data["location"]  = CONFIG["location"]
        payload = json.dumps(data).encode()
        client.publish(MQTT_TOPIC, payload)
        return True
    except Exception as e:
        log(f"MQTT 发布失败: {e}")
        return False


# ─── 主循环 ───────────────────────────────────────────────────────────────────

def main():
    log("=" * 50)
    log("CORETECT Sentinel 固件启动")
    log(f"设备ID: {CONFIG['device_id']}")
    log("=" * 50)

    # WDT：120秒超时（正常循环会在30s内喂狗）
    wdt = WDT(timeout=120000)

    # 4G 联网（失败则重启）
    if not connect_4g(timeout_s=90):
        log("4G 联网失败，30秒后重启...")
        time.sleep(30)
        import machine
        machine.reset()

    wdt.feed()

    # 识别 BMS
    bms = detect_bms()
    if bms is None:
        log("BMS 识别失败，60秒后重启...")
        time.sleep(60)
        import machine
        machine.reset()

    wdt.feed()

    # MQTT 连接
    mqtt = connect_mqtt()
    mqtt_fail_count = 0

    # ── 主轮询循环 ────────────────────────────────────────────────────────────
    bms_fail_count = 0
    interval = CONFIG["upload_interval_s"]

    while True:
        loop_start = time.time()
        wdt.feed()

        # 读 BMS
        try:
            data = bms.read_all()
        except Exception as e:
            log(f"BMS 读取异常: {e}")
            data = None

        if data:
            bms_fail_count = 0
            log(f"BMS 数据 | SOC:{data['soc']}% V:{data['pack_voltage']}V "
                f"I:{data['pack_current']}A ΔV:{data['delta_v']*1000:.0f}mV")

            # 打印告警（任何告警位为1时）
            alarms = {k: v for k, v in data.items()
                      if k.startswith("alarm_") and v == 1}
            if alarms:
                log(f"⚠️  告警: {list(alarms.keys())}")

            # 上传
            if mqtt:
                ok = upload(mqtt, data)
                if not ok:
                    mqtt_fail_count += 1
                    log(f"MQTT 失败次数: {mqtt_fail_count}")
                    if mqtt_fail_count >= 3:
                        log("重连 MQTT...")
                        try:
                            mqtt.disconnect()
                        except:
                            pass
                        mqtt = connect_mqtt()
                        mqtt_fail_count = 0
                else:
                    mqtt_fail_count = 0
                    log("✅ 数据已上传 ThingsBoard")
            else:
                log("MQTT 未连接，尝试重连...")
                mqtt = connect_mqtt()

        else:
            bms_fail_count += 1
            log(f"BMS 无响应（连续{bms_fail_count}次）")
            if bms_fail_count >= 10:
                log("BMS 持续无响应，60秒后重启...")
                time.sleep(60)
                import machine
                machine.reset()

        # 等到下一个周期
        elapsed = time.time() - loop_start
        sleep_s = max(1, interval - elapsed)
        time.sleep(sleep_s)


# ─── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
