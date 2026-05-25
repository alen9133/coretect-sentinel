# CoreTect Sentinel — Global Energy Control Platform

> **Remote asset monitoring & early warning system for ESS, microgrid, and EV battery fleets in Southeast Asia**

---

## Overview

CoreTect Sentinel is a full-stack IoT monitoring platform built for the Philippine and Southeast Asian energy storage market. It connects battery assets (ESS cabinets, golf cart batteries, commercial BESS) to a branded cloud dashboard with real-time telemetry, automated Telegram alerts, and cost-savings analytics.

**Live Platform:** [coretect-microgrid.com](https://coretect-microgrid.com)  
**Cloud Monitor:** [monitor.coretect-microgrid.com](https://monitor.coretect-microgrid.com)

---

## Architecture

```
Hardware (ESS / Golf Cart / BESS)
        ↓  4G DTU Module (HTTP POST)
ThingsBoard CE  ·  Singapore VPS (DigitalOcean)
        ↓  JWT REST API
┌───────────────────────────────────────┐
│  intake.html  (Branded Dashboard)    │
│  index.html   (Official Website)     │
│  coretect_alert_bot.py  (Telegram)   │
└───────────────────────────────────────┘
        ↓
Telegram Alerts  ·  Client Dashboard  ·  Public Website
```

---

## File Structure

```
coretect-sentinel/
├── web/
│   ├── index.html              # Official website (bilingual EN/CN)
│   └── intake.html             # Branded cloud dashboard (guest + client mode)
├── server/
│   ├── coretect_simulator.py   # Device data simulator (pre-DTU testing)
│   └── coretect_alert_bot.py   # Telegram alert bot (v2.0 with cooldown)
├── assets/
│   ├── qr_website.html         # QR code — official website
│   └── qr_repair.html          # QR code — repair service
└── README.md
```

---

## Monitored Device Types

| Device | Model | Location | Capacity |
|--------|-------|----------|----------|
| ESS-PH-001 | Solid-state LFP (QingTao) | Palawan Island | 64 kWh |
| ESS-PH-002 | Solid-state LFP (QingTao) | Cebu Island | 30 kWh |
| ESS-PH-003 | Solid-state LFP (QingTao) | Quezon Province | 48 kWh |
| GOLF-001~005 | Golf cart battery pack | Cebu / Manila Golf Club | 10 kWh each |
| BESS-COM-001 | Commercial BESS | Makati, Manila | 200 kWh |

---

## Key Features

### Client Dashboard (`intake.html`)
- **Guest mode** — public overview, no login required
- **Client mode** — JWT-authenticated, real-time device data
- SOC / SOH / Power / Temperature — live 30s refresh
- **Cost savings calculator** — per-country electricity rate (PHP / SGD / VND / MYR)
- **Technical details panel** — collapsible cell voltages (C1–C16), temp sensors, BMS protection status
- Alarm history, SOC trend chart, fleet KPI panel
- Bilingual EN / 中文 toggle

### Telegram Alert Bot (`coretect_alert_bot.py`)
- Polls ThingsBoard every 60 seconds
- **Level 1 alerts** (immediate): high temp, critical low SOC, severe cell imbalance, BMS protection triggered
- **Level 2 alerts** (recommended): cell imbalance warning, low SOC, grid frequency abnormal, maintenance reminder
- **2-hour cooldown** per alert — no repeated spam
- Recovery notifications when alert clears
- Daily 8:00 AM fleet summary report
- All alert links route to branded dashboard (not ThingsBoard)

### Data Simulator (`coretect_simulator.py`)
- Simulates 9 devices × 28 telemetry fields each
- Realistic SOC drift, cell voltage variance, temperature modelling
- Sends data every 30 seconds via ThingsBoard HTTP API
- Runs as background process (`nohup`) on VPS

---

## Infrastructure

| Component | Details |
|-----------|---------|
| VPS | DigitalOcean Singapore · 1GB RAM · Ubuntu 24.04 |
| IoT Platform | ThingsBoard Community Edition (Docker) |
| Database | PostgreSQL + Cassandra (inside Docker) |
| Web Server | Nginx + BaoTa Panel |
| Domain | coretect-microgrid.com (SSL) |
| Alerts | Telegram Bot API |

---

## API Reference

### ThingsBoard Telemetry Ingestion
```
POST https://monitor.coretect-microgrid.com/api/v1/{ACCESS_TOKEN}/telemetry
Content-Type: application/json

{
  "soc": 78.3,
  "soh": 94.2,
  "pack_voltage": 51.4,
  "pack_current": -32.1,
  "temperature_avg": 29.5,
  "delta_v": 0.012,
  "cell_v_01": 3.210,
  ...
}
```

### ThingsBoard REST API (used by intake.html)
```
POST /api/auth/login          → JWT token
GET  /api/tenant/devices      → device list
GET  /api/plugins/telemetry/DEVICE/{id}/values/timeseries?keys=soc,soh,...
```

---

## Alert Thresholds

| Parameter | Warning (L2) | Critical (L1) |
|-----------|-------------|---------------|
| Temperature | > 45°C | > 55°C |
| Cell Delta-V | > 50mV | > 100mV |
| SOC | < 20% | < 10% |
| Cycle count | ≥ 3,000 | ≥ 4,500 |
| Grid frequency | — | < 59.5 or > 60.5 Hz |

---

## Setup Guide

### 1. Server requirements
```bash
# Ubuntu 24.04 · Docker · Python 3 · Nginx
pip install requests
```

### 2. Run device simulator
```bash
# Edit DEVICE_TOKENS in coretect_simulator.py first
nohup python3 /root/coretect/coretect_simulator.py > /root/coretect/simulator.log 2>&1 &
```

### 3. Run alert bot
```bash
# Edit BOT_TOKEN, TB_PASS, CHAT_IDS in coretect_alert_bot.py first
nohup python3 /root/coretect/coretect_alert_bot.py > /root/coretect/bot.log 2>&1 &
```

### 4. Deploy web files
```
Upload index.html and intake.html to:
/www/wwwroot/coretect-microgrid.com/
```

---

## Business Context

CoreTect targets the Philippine off-grid and microgrid market:
- 7,000+ islands, 400万+ households without reliable power
- RA 11646 (Microgrid Systems Act) provides 20-year UCME subsidies
- DOE 3rd-round CSP auction covers 167 unserved/underserved areas
- Registered DTI business in Philippines (authorized technical distributor for QingTao solid-state batteries)

**Revenue streams:**
1. ESS hardware sales (QingTao solid-state LFP batteries)
2. SaaS cloud monitoring (₱/month per device)
3. Battery pack repair & BMS calibration services
4. 4G DTU module sales & cloud integration

---

## Roadmap

- [ ] 4G DTU hardware arrival & first real device connection
- [ ] SEC corporation registration (Philippines, 60/40 structure)
- [ ] WhatsApp Business API integration
- [ ] Monthly PDF report generation
- [ ] AI predictive maintenance module (Phase 2)
- [ ] DOE CSP bidding participation (as technical subcontractor)

---

## Contact

**CoreTect Global Technology**  
Singapore Node | Philippines Operations  
[coretect-microgrid.com](https://coretect-microgrid.com)

---

*Built with ThingsBoard CE · Deployed on DigitalOcean Singapore*
