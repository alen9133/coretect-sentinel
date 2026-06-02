# CORETECT Sentinel — ThingsBoard 规则链配置说明
## 第一代产品（DR502）数据解析

---

## 一、文件说明

| 文件 | 用途 |
|---|---|
| `tb_parser_main.js` | ★ **粘贴到TB规则链的唯一文件**，包含全部解析逻辑 |
| `tb_parser_jk.js` | 极空JK解析器（独立版，供参考/调试） |
| `tb_parser_jbd.js` | 嘉佰达JBD解析器（独立版，供参考/调试） |
| `tb_parser_dy.js` | 达锂DY解析器（独立版，供参考/调试） |
| `tb_parser_inverter.js` | 逆变器解析器合集（独立版，供参考/调试） |

**实际操作只需要 `tb_parser_main.js` 一个文件。**

---

## 二、DR502 配置参数

### BMS 轮询配置

| BMS品牌 | 从机地址 | 功能码 | 起始寄存器 | 寄存器数量 | 波特率 |
|---|---|---|---|---|---|
| 极空 JK | 01 (0x01) | FC-03 | 0x1200 | 96 | 115200 |
| 嘉佰达 JBD（新协议A12） | 16 (0x10) | FC-04 | 0x1000 | 64 | 9600 |
| 嘉佰达 JBD（旧协议V12） | 直接发DD帧 | — | — | — | 9600 |
| 达锂 DY | 129 (0x81) | FC-03 | 0x0000 | 96 | 9600 |

### 逆变器轮询配置（双485/CAN+485场景，从机地址2）

| 品牌 | 从机地址 | 功能码 | 起始寄存器 | 寄存器数量 | 波特率 |
|---|---|---|---|---|---|
| 固德威 Goodwe | 02 | FC-03 | 0x0000 | 80 | 9600 |
| 德业 Deye | 02 | FC-03 | 0x0003 | 80 | 9600 |
| 锦浪 Solis | 02 | FC-03 | 0x0003 | 80 | 9600 |
| 古瑞瓦特 Growatt | 02 | FC-03 | 0x0000 | 80 | 9600 |
| 索福 Sofar | 02 | FC-03 | 0x0200 | 80 | 9600 |

### DR502 MQTT 上传格式配置
```
上行Topic：  v1/devices/me/telemetry
Payload格式：JSON
BMS字段名：  bms_raw
逆变器字段名：inv_raw
嘉佰达旧协议单体电压帧字段名：bms_raw2
```

---

## 三、ThingsBoard 规则链配置步骤

### 步骤1：创建规则链
```
Rule Chains → 右上角"+" → 新建
名称：CORETECT BMS Parser
```

### 步骤2：添加 Transformation 节点
```
拖入 "Script" 节点（Transformation类型）
节点名称：Parse BMS Data
```
将 `tb_parser_main.js` **全部内容** 粘贴进去，点保存。

### 步骤3：连接节点
```
Message Type Switch
    → POST_TELEMETRY_REQUEST → Parse BMS Data
                                    → Save Timeseries
```

### 步骤4：应用到设备Profile
```
Device Profiles → 找到你的储能设备Profile
→ Device rule chain → 选择 "CORETECT BMS Parser"
```

---

## 四、设备属性配置

每台设备在 ThingsBoard 设备详情 → **Server Attributes** 里添加：

| 属性名 | 类型 | 示例值 | 说明 |
|---|---|---|---|
| `bms_brand` | String | `JK` | BMS品牌：JK / JBD / DY |
| `inv_brand` | String | `GOODWE` | 逆变器品牌，无逆变器填NONE |
| `has_inverter` | Boolean | `true` | 是否有逆变器数据 |
| `device_id` | String | `ESS-PH-001` | 设备编号 |
| `location` | String | `Palawan Island` | 安装位置 |

---

## 五、输出 JSON 字段说明

### BMS 通用字段（三个品牌输出一致）

| 字段 | 说明 | 单位 |
|---|---|---|
| `brand` | BMS品牌 | JK/JBD/DY |
| `soc` | 剩余电量 | % |
| `soh` | 健康度 | % |
| `pack_voltage` | 总电压 | V |
| `pack_current` | 电流（正=充，负=放） | A |
| `power_w` | 功率（正=充，负=放） | W |
| `temperature_avg` | 平均温度 | ℃ |
| `temperature_max` | 最高温度 | ℃ |
| `mos_temperature` | MOS管温度 | ℃ |
| `delta_v` | 最大压差 | V |
| `cell_count` | 电芯数量 | 个 |
| `remain_ah` | 剩余容量 | Ah |
| `full_capacity_ah` | 满充容量 | Ah |
| `cycle_count` | 循环次数 | 次 |
| `cell_v_01`~`cell_v_32` | 各单体电压 | V |
| `alarm_cell_ovp` | 单体过压 | 0/1 |
| `alarm_cell_uvp` | 单体欠压 | 0/1 |
| `alarm_over_current` | 过流 | 0/1 |
| `alarm_over_temp` | 过温 | 0/1 |
| `alarm_short_circuit` | 短路 | 0/1 |
| `alarm_cell_imbalance` | 压差过大(>50mV) | 0/1 |

### 逆变器字段（inv_前缀）

| 字段 | 说明 | 单位 |
|---|---|---|
| `inv_brand` | 逆变器品牌 | - |
| `inv_status` | 运行状态码 | - |
| `inv_pv_power` | 光伏功率 | W |
| `inv_pv1_voltage` | PV1电压 | V |
| `inv_grid_voltage` | 电网电压 | V |
| `inv_grid_freq` | 电网频率 | Hz |
| `inv_grid_power` | 并网功率（正=馈网，负=购电） | W |
| `inv_load_power` | 负载功率 | W |
| `inv_bat_voltage` | 电池端电压 | V |
| `inv_bat_current` | 电池电流 | A |
| `inv_bat_power` | 电池功率 | W |
| `inv_bat_soc` | 逆变器显示SOC | % |
| `inv_today_gen_kwh` | 今日发电量 | kWh |
| `inv_total_gen_kwh` | 累计发电量 | kWh |
| `inv_temperature` | 逆变器温度 | ℃ |
| `alarm_grid_freq` | 频率异常(菲律宾60Hz±0.5) | 0/1 |

---

## 六、嘉佰达 JBD 协议选择说明

嘉佰达有两种协议，自动识别：

| 协议 | 识别方式 | 适用产品 |
|---|---|---|
| 新协议 Modbus A12 | 响应帧第1字节=0x10 | 2024年后家储产品 |
| 旧协议 V12 DD77 | 响应帧第1字节=0xDD | 早期产品、软件版 |

旧协议需要DR502发两次请求：
1. `DD A5 03 00 FF FD 77`（基本信息）→ 上传为 `bms_raw`
2. `DD A5 04 00 FF FC 77`（单体电压）→ 上传为 `bms_raw2`

---

## 七、单485口场景（只显示BMS）

如果客户只有单个RS485口（BMS和逆变器共用），DR502只连BMS：
- `has_inverter` 设为 `false`
- `inv_brand` 设为 `NONE`
- intake.html 不显示逆变器卡片
- 告知客户升级第二代产品（ESP32网关）才能同时监控逆变器
