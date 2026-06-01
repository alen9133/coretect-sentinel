# CORETECT Sentinel — ESP32 固件使用说明
## 硬件：HaaS506-ED1（ESP32-S3 MicroPython）

---

## 文件清单

| 文件 | 说明 |
|---|---|
| `bms_common.py` | CRC16 + Modbus 帧工具（两个驱动都依赖） |
| `jk_bms.py` | 极空（JK）BMS 驱动，115200 Modbus RTU |
| `dy_bms.py` | 达锂（DY/KVMS）BMS 驱动，9600 Modbus RTU |
| `main.py` | 主程序（4G联网 → BMS轮询 → MQTT上传） |

---

## 快速上手（5步）

### 第1步：安装开发工具
```bash
pip install mpremote
```

### 第2步：修改 main.py 配置
打开 `main.py`，找到 `CONFIG` 字典，填入：
```python
CONFIG = {
    "tb_token": "你的ThingsBoard设备Access Token",
    "bms_brand": "AUTO",   # 自动识别，或填 "JK" / "DY"
    "device_id": "ESS-PH-001",
    "location":  "Palawan Island",
    # 其他保持默认即可
}
```

### 第3步：确认 RS485 引脚
ED1 的 RS485 是 uart2，TX/RX 引脚号对照板子丝印填入 CONFIG：
```python
"rs485_uart": 2,
"rs485_tx":   17,   # 对照丝印修改
"rs485_rx":   18,   # 对照丝印修改
```

### 第4步：上传文件到设备
用 TypeC 线连接 ED1，然后：
```bash
# 上传全部固件文件
mpremote connect auto cp bms_common.py :bms_common.py
mpremote connect auto cp jk_bms.py :jk_bms.py
mpremote connect auto cp dy_bms.py :dy_bms.py
mpremote connect auto cp main.py :main.py
```

### 第5步：运行并查看日志
```bash
mpremote connect auto run main.py
```
正常输出示例：
```
[08:30:01] CORETECT Sentinel 固件启动
[08:30:01] 设备ID: ESS-PH-001
[08:30:03] 正在等待 4G 联网...
[08:30:18] 4G 已连接，IP: 10.x.x.x
[08:30:19] AUTO 模式：尝试 JK 极空 BMS...
[08:30:20] ✅ 检测到 JK 极空 BMS，SOC=85%
[08:30:21] MQTT 已连接: 206.189.93.135
[08:30:21] BMS 数据 | SOC:85% V:51.2V I:-32.1A ΔV:8mV
[08:30:21] ✅ 数据已上传 ThingsBoard
```

---

## ThingsBoard 上的 JSON 字段说明

| 字段 | 单位 | 说明 |
|---|---|---|
| `brand` | - | "JK" 或 "DY" |
| `soc` | % | 剩余电量 |
| `soh` | % | 电池健康度（DY暂无） |
| `pack_voltage` | V | 总电压 |
| `pack_current` | A | 电流（正=充电，负=放电） |
| `power_w` | W | 功率（正=充电，负=放电） |
| `temperature_avg` | °C | 平均温度 |
| `temperature_max` | °C | 最高温度 |
| `mos_temperature` | °C | MOS管温度 |
| `delta_v` | V | 最大压差 |
| `cell_count` | - | 电芯数量 |
| `remain_ah` | Ah | 剩余容量 |
| `cycle_count` | - | 循环次数 |
| `charge_state` | 0/1 | 是否在充电 |
| `discharge_state` | 0/1 | 是否在放电 |
| `alarm_cell_ovp` | 0/1 | 单体过压告警 |
| `alarm_cell_uvp` | 0/1 | 单体欠压告警 |
| `alarm_over_current` | 0/1 | 过流告警 |
| `alarm_over_temp` | 0/1 | 过温告警 |
| `alarm_cell_imbalance` | 0/1 | 压差过大告警 |
| `alarm_short_circuit` | 0/1 | 短路告警 |
| `cell_v_01` ~ `cell_v_32` | V | 各单体电压 |

---

## 常见问题

**Q：BMS 没有响应怎么办？**
1. 检查 A/B 接线是否接反（极空是 A+、B-）
2. 用万用表量 A-B 间电压，正常约 200-400mV
3. 确认 BMS 从机地址（极空出厂默认1）
4. 如果是 DY 达锂，地址固定是 0x81，不用配置

**Q：MQTT 连接失败？**
1. 确认 ThingsBoard 服务器的 1883 端口已开放
2. 确认 Access Token 复制正确（在 ThingsBoard 设备详情里查看）
3. 宝塔面板检查 Docker ThingsBoard 容器是否在运行

**Q：4G 一直连不上？**
1. 确认 SIM 卡已激活，插卡方向正确
2. Globe/Smart SIM 卡均支持 B1/B3/B5/B8，ED1 完全兼容
3. 检查天线是否拧紧

---

## 扩展：同时接逆变器

ED1 有 RS232（uart1）和 RS485（uart2）两个串口：
- uart2 (RS485) → BMS
- uart1 (RS232) → 固德威/德业等逆变器（如果逆变器支持 RS232）

或者通过 RS485 分路器把 uart2 分给两个设备（BMS 和逆变器用不同从机地址）。
