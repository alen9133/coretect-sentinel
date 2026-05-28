# CoreTect Project Handover Document
> 把这个文档发给Claude新窗口，说"继续CoreTect项目"，Claude会立刻了解所有背景

---

## 项目概况
- **公司**：CoreTect Global Technology
- **定位**：菲律宾储能全生命周期服务商（硬件销售+云监控SaaS+电池修复）
- **合作品牌**：清陶（QingTao）固态电池 授权经销商
- **注册形式**：菲律宾DTI小店（同事名义），实际资金由老板出
- **官网**：coretect-microgrid.com
- **云监控**：monitor.coretect-microgrid.com（ThingsBoard CE，新加坡DigitalOcean VPS）
- **GitHub**：https://github.com/alen9133/coretect-sentinel

---

## 服务器信息
- **VPS**：DigitalOcean 新加坡 1GB RAM Ubuntu 24.04
- **IP**：206.189.93.135
- **面板**：宝塔面板
- **ThingsBoard**：Docker部署，域名 monitor.coretect-microgrid.com
- **网站文件路径**：/www/wwwroot/coretect-microgrid.com/

---

## 已完成的工作

### 硬件
- USR-DR502 4G DTU模块（已到货，待配置）
- 等待接入真实BMS和逆变器

### 云平台（ThingsBoard）
- 已建9台模拟设备：ESS-PH-001/002/003，GOLF-001~005，BESS-COM-001
- 模拟数据脚本 coretect_simulator.py 在服务器后台运行（nohup，PID需重启后确认）
- 脚本路径：/root/coretect/coretect_simulator.py
- 日志路径：/root/coretect/simulator.log

### Telegram告警机器人
- 脚本路径：/root/coretect/coretect_alert_bot.py（v2.0）
- 功能：每60秒轮询ThingsBoard，L1/L2分级告警，2小时冷却，每日8:00日报
- 告警链接指向品牌云监控页（非ThingsBoard原生）
- Bot Token和Chat ID已配置在脚本中（GitHub版本已脱敏）

### 网页文件
- index.html：官网主页（中英双语，国家分页，SaaS定价）
- intake.html：云监控平台（guest免登录/client登录，多客户视图，电芯折叠展示，费用节省计算）
- qr_website.html：官网二维码
- qr_repair.html：维修服务二维码

---

## 下一步待完成的工作（优先级排序）

### 🔴 最高优先级
1. **JK BMS / JBD BMS / 达锂DY BMS 三种品牌的ThingsBoard解析规则链代码**
   - 要求：即插即用，不固定型号，云端自动识别品牌并解析
   - 思路：DR502上传原始Modbus十六进制数据到ThingsBoard，规则链根据设备标签（brand=JK/JBD/DY）调用对应JavaScript解析脚本，输出统一JSON格式
   - 统一输出字段：soc, soh, pack_voltage, pack_current, temperature, cell_v_01~cell_v_16, alarm_xxx

2. **USR-DR502配置步骤文档**
   - 配置MQTT上传到ThingsBoard
   - 配置Modbus轮询规则
   - 针对JK/JBD/DY各品牌的寄存器地址配置

### 🟡 中优先级
3. **逆变器API对接**
   - 固德威GoodWe SEMS API（已有官方文档，需申请Key）
   - 德业Deye SolarmanPV API（已有开放文档）
   - 有RS485接口的逆变器：改地址和波特率后用DR502直接接

4. **intake.html功能完善**
   - 当前版本已有：多客户视图、设备列表、费用节省、电芯折叠、告警历史
   - 待完善：月度报告PDF导出、多站点切换

5. **index.html手机APP区域联动真实数据**

### 🟢 后期
6. SSL证书安装（certbot）
7. VPS自动备份开启
8. Facebook Messenger推送

---

## 核心技术架构

```
现场设备（BMS/逆变器）
    ↓ RS485
USR-DR502（4G DTU）
    ↓ MQTT / HTTP（4G）
ThingsBoard（新加坡VPS）
    ↓ 规则链解析
CoreTect Cloud统一数据格式
    ↓
intake.html监控大屏 + Telegram告警
```

---

## BMS协议解析方案（核心设计）

**设计思路：**
DR502上传原始数据 → ThingsBoard规则链 → 根据设备标签brand值 → 调用对应JS解析脚本 → 统一格式存储

**支持的BMS品牌（第一批）：**
- JK BMS（极空）：有官方RS485 Modbus V1.1协议文档
- JBD BMS（嘉佰达）：私有UART协议包在RS485上，需专用解析库
- 达锂DY BMS：需联系厂家要协议文档（已有话术）

**向厂家要协议文档话术：**
"你好，我们在海外做微电网项目，需要做二次开发，把你们的BMS接上我们的4G DTU上传到我们自己的云平台。请把RS485 Modbus底层通信协议说明书（完整版寄存器地址表）发我一份。需要包含：单体电芯电压和多路温度读取地址、故障报警码对应解释、控制指令（远程开关充放电MOS管）。请发PDF或Excel。"

---

## 逆变器接入方案

| 情况 | 方案 |
|---|---|
| 逆变器有第2RS485接口 | DR502直接接，BMS地址1逆变器地址2 |
| 逆变器只有1个接口（已接BMS） | 有源RS485分路器（约100元）分出一路给DR502 |
| 固德威/德业等主流品牌 | 调用官方云API，不需要硬件接线 |
| 大型工商储能 | 树莓派+Solar Assistant |

---

## 菲律宾市场信息
- 主要目标：离岛微电网、高尔夫球场、工商业储能
- 相关法规：RA 11646（微电网系统法），DOE第三轮CSP招标
- 电价：菲律宾₱12/kWh（Meralco平均）
- 主流BMS品牌：JK（极空）、JBD（嘉佰达）、DY（达锂）、派能Pylontech
- 主流逆变器品牌：固德威、德业、SMA

---

## 文件清单（GitHub仓库）
```
coretect-sentinel/
├── coretect_simulator.py    # 9台设备模拟数据脚本（tokens已脱敏）
├── coretect_alert_bot.py    # Telegram告警机器人v2.0（tokens已脱敏）
├── index.html               # 官网主页
├── intake.html              # 云监控平台v3.1（多客户视图）
├── qr_website.html          # 官网二维码
├── qr_repair.html           # 维修二维码
└── README.md                # 项目说明
```

---

*最后更新：2026-05-28*
*下次对话请说：继续CoreTect项目，并附上此文档链接*
*GitHub: https://github.com/alen9133/coretect-sentinel*
