# CoreTect 项目完整交接文档 v2.0
> 新对话开始时发给Claude说：**"继续CoreTect项目，这是完整交接文档"**
> GitHub: https://github.com/alen9133/coretect-sentinel

---

## 一、项目基本信息

| 项目 | 内容 |
|---|---|
| 公司名 | CoreTect Global Technology |
| 定位 | 菲律宾/东南亚储能全生命周期服务商 |
| 三条业务线 | 硬件销售（清陶固态电池）+ 云监控SaaS + 电池修复 |
| 菲律宾公司 | DTI小店（同事名义注册），实际资金老板出 |
| 清陶电池 | 已签约授权技术经销商 |

---

## 二、服务器和平台信息

| 项目 | 内容 |
|---|---|
| VPS | DigitalOcean 新加坡 1GB RAM Ubuntu 24.04 |
| IP | 206.189.93.135 |
| 面板 | 宝塔面板 |
| ThingsBoard | Docker部署，CE社区版 |
| 云监控域名 | monitor.coretect-microgrid.com |
| 官网域名 | coretect-microgrid.com |
| 网站文件路径 | /www/wwwroot/coretect-microgrid.com/ |
| ThingsBoard账号 | tenant@thingsboard.org |

---

## 三、已完成的工作

### 3.1 服务器脚本（均在 /root/coretect/ 目录）

**coretect_simulator.py** — 9台模拟设备数据脚本
```
后台运行命令：
nohup python3 /root/coretect/coretect_simulator.py > /root/coretect/simulator.log 2>&1 &

模拟设备列表：
ESS-PH-001 (Palawan Island, 64kWh)
ESS-PH-002 (Cebu Island, 30kWh)
ESS-PH-003 (Quezon Province, 48kWh)
GOLF-001~005 (高尔夫球车, 10kWh each)
BESS-COM-001 (Makati Commercial, 200kWh)

发送间隔：30秒
每台设备发送字段：28个（含cell_v_01~cell_v_16）
```

**coretect_alert_bot.py v2.0** — Telegram告警机器人
```
后台运行命令：
nohup python3 /root/coretect/coretect_alert_bot.py > /root/coretect/bot.log 2>&1 &

功能：
- 每60秒轮询ThingsBoard
- L1告警（立即推送）：高温/危急低电量/严重压差/BMS保护
- L2告警（建议处理）：低电量/压差偏大/电网频率异常/维护提醒
- 2小时冷却时间（同一告警不重复推送）
- 每天8:00发日报
- 告警链接指向品牌云监控页（非ThingsBoard原生）

告警链接：https://coretect-microgrid.com/intake.html?mode=client
```

### 3.2 网页文件（均在宝塔面板网站目录）

| 文件 | 功能 | 状态 |
|---|---|---|
| index.html | 官网主页（中英双语，国家分页） | ✅已加SEO meta标签 |
| intake.html | 云监控平台v3.1 | ✅多客户视图，电芯折叠 |
| sitemap.xml | Google网站地图 | ✅已提交Search Console |
| robots.txt | 搜索引擎爬虫配置 | ✅已上传 |
| qr_website.html | 官网二维码页面 | ✅ |
| qr_repair.html | 维修服务二维码页面 | ✅ |

### 3.3 SEO状态
- Google Search Console已验证：coretect-microgrid.com
- sitemap.xml已提交，状态"正在处理"（正常，等24-48小时）
- 已请求编入索引

### 3.4 ThingsBoard配置
- 9台模拟设备已建立并活跃
- 各设备Access Token已配置在simulator.py中
- 目前无客户账号（等第一个真实客户）

---

## 四、硬件清单

| 设备 | 状态 | 用途 |
|---|---|---|
| USR-DR502 4G DTU | ✅已到货，待配置 | 现阶段连接BMS |
| ESP32工业4G网关 | 🔄待采购 | 第二代产品，同时接BMS+逆变器 |
| 清陶BMS+逆变器 | 🔄待接入 | 第一个真实测试设备 |

---

## 五、下一步最重要的工作（按优先级）

### 🔴 第一优先：BMS解析代码（正在进行）

**背景：**
已拿到三个品牌的RS485底层协议文档：
- 极空（JK）BMS — 1份文档
- 嘉佰达（JBD）BMS — 3份文档（三代协议版本）
- 达锂（DY）BMS — 1份文档

**架构设计（已确认）：**
```
DR502方案（当前阶段）：
BMS → RS485 → DR502 → 原始十六进制数据 → ThingsBoard
ThingsBoard规则链（JavaScript）根据设备标签brand值解析
输出统一JSON格式 → 显示在intake.html

ESP32方案（第二阶段）：
BMS → RS485 → ESP32（本地C++解析）→ 干净JSON → ThingsBoard
ThingsBoard直接显示，不需要二次解析
DR502阶段的JS逻辑直接翻译成C++烧录进ESP32
```

**待完成：**
- [ ] JK BMS的ThingsBoard规则链JS解析代码
- [ ] JBD BMS解析代码（需自动识别三个版本）
- [ ] DY BMS解析代码
- [ ] USR-DR502配置文档（MQTT+Modbus轮询设置）
- [ ] ESP32 C++固件代码

**统一输出JSON格式：**
```json
{
  "brand": "JK",
  "soc": 85.2,
  "soh": 94.1,
  "pack_voltage": 51.4,
  "pack_current": -32.1,
  "power_w": -1649,
  "temperature_avg": 29.5,
  "temperature_max": 31.2,
  "delta_v": 0.012,
  "cell_count": 16,
  "cell_v_01": 3.210,
  "cell_v_02": 3.208,
  "...": "...",
  "cell_v_16": 3.211,
  "alarm_over_voltage": 0,
  "alarm_under_voltage": 0,
  "alarm_over_current": 0,
  "alarm_over_temp": 0,
  "alarm_cell_imbalance": 0,
  "cycle_count": 156
}
```

### 🔴 第二优先：ESP32工业网关采购

**确认规格：**
```
发给淘宝商家的采购要求：
- 主控：ESP32-S3或ESP32-WROOM-32
- 4G模块：LTE Cat-1或Cat-4，支持B1/B3/B5/B8/B28频段（菲律宾Globe/Smart）
- RS485：独立2路，隔离防雷击
- 数字输入DI：4路以上（接门磁/烟感）
- I2C接口：2个（接SHT30温湿度）
- 供电：DC 9-36V宽压
- 工作温度：-20°C~70°C
- 安装：35mm导轨
- 支持OTA远程升级
- 支持Arduino IDE开发
- 预算：200-400元
```

**ESP32工作模式（自动切换）：**
```
有CAN口场景：
  UART1读BMS（独立总线）
  UART2读逆变器（独立总线）

无CAN只有RS485场景：
  Serial Bridge透明桥接模式
  ESP32插在BMS和逆变器中间
  完全透明转发双方通讯
  空闲时主动查询单体电芯数据
```

### 🟡 第三优先：逆变器数据接入

**分层方案：**
```
有第2接口的逆变器：
  DR502/ESP32直接接，改地址2，波特率统一

没有第2接口（RS485被BMS占用）：
  有源RS485分路器（约100元）→ 分出一路给DTU

主流品牌（有API）：
  固德威GoodWe → SEMS OpenAPI
  德业Deye → SolarmanPV API
  锦浪Solis → SolisCloud API
  阳光电源SMA → 官方API
  注意：API有5-15分钟延迟，不如直连实时

杂牌无API无第2接口：
  放弃逆变器数据，只显示BMS数据
```

### 🟡 第四优先：ThingsBoard多租户配置
```
目标：
  客户A登录 → 只看自己的设备
  客户B登录 → 只看自己的设备
  互相看不到

实现：
  ThingsBoard创建Customer账号
  把设备分配给对应客户
  intake.html已支持多客户视图（已完成）
```

---

## 六、关键技术决策记录

### RS485多设备总线规则
```
同一RS485总线只能有一个MASTER
BMS-逆变器通讯：逆变器是MASTER，BMS是SLAVE
加入DR502/ESP32：会产生MASTER冲突

解决方案优先级：
1. BMS用CAN接逆变器 + RS485接ESP32（最干净）
2. BMS有双RS485口，各接一个设备（干净）
3. 有源RS485分路器（BMS数据能读，逆变器数据走API）
4. ESP32 Serial Bridge透明桥接（最复杂但最完整）
```

### 告警冷却时间
```
同一设备同一告警：2小时（7200秒）内不重复推送
告警恢复后：冷却重置，下次可立即推送
脚本变量：ALERT_COOLDOWN = 7200
```

### 电价节省计算
```
菲律宾：₱12/kWh（Meralco平均）
越南：₫4,500/kWh
马来西亚：RM 0.57/kWh
新加坡：S$0.32/kWh
计算公式：total_discharge_kwh × 当地电价
```

---

## 七、菲律宾市场信息

| 项目 | 内容 |
|---|---|
| 相关法规 | RA 11646（微电网系统法） |
| DOE招标 | 第三轮CSP招标，167个未通电区域 |
| 主要目标客户 | 离岛微电网、高尔夫球场、工商业储能 |
| 主流BMS | JK极空、JBD嘉佰达、DY达锂、Pylontech派能 |
| 主流逆变器 | 固德威、德业、锦浪、SMA |
| 菲律宾电网频率 | 60Hz |
| Telegram普及率 | 高，推荐用于告警推送 |

---

## 八、向BMS厂家要协议文档的话术
```
"你好，我们在海外做微电网项目，需要做二次开发，
把你们的BMS接上我们的4G DTU上传到我们自己的云平台。
请把RS485 Modbus底层通信协议说明书（完整版寄存器地址表）
发我一份。需要包含：
- 单体电芯电压和多路温度读取地址
- 故障报警码对应解释
- 控制指令（远程开关充放电MOS管）
请发PDF或Excel。"
```

---

## 九、文件清单（GitHub仓库）

```
coretect-sentinel/
├── index.html                    # 官网主页（已加SEO）
├── intake.html                   # 云监控平台v3.1
├── coretect_simulator.py         # 9台设备模拟脚本
├── coretect_alert_bot.py         # Telegram告警机器人v2.0
├── sitemap.xml                   # Google网站地图
├── robots.txt                    # 爬虫配置
├── qr_website.html               # 官网二维码
├── qr_repair.html                # 维修二维码
├── CORETECT_PROJECT_HANDOVER.md  # 原版交接文档
└── CORETECT_FULL_HANDOVER.md     # 本文档（完整版）
```

---

## 十、对话恢复指令

新对话开始时发送：
```
继续CoreTect项目。

项目GitHub：https://github.com/alen9133/coretect-sentinel
完整交接文档：https://github.com/alen9133/coretect-sentinel/blob/main/CORETECT_FULL_HANDOVER.md

当前最紧迫的任务：
写JK BMS的ThingsBoard规则链JavaScript解析代码
（JK协议文档我会一起上传）
```

---
*最后更新：2026-05-31*
*本文档涵盖从项目启动到当前的所有技术决策和待办事项*
