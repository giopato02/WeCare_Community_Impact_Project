# WeCare: Health, Equality & Technology

**Community Impact Project**
**Authors:** Giorgi Pataridze & Avtandili Javrishvili  
**Supervisors:** Danial Eyvazi & Roshanak Davallou  

## Overview
WeCare is a community impact initiative that transitioned from a mobile app concept ("Bridge for Balance") into a fully functional, physical health-monitoring kiosk. Built to address severe inequalities in global health access, the kiosk provides fast, free, and anonymous vital-sign checks. 

By removing the human barrier of a traditional waiting room, WeCare helps bypass the stigmas that prevent men from seeking care, while providing critical, accessible health infrastructure for underserved women in peri-urban and rural communities.

## UN Sustainable Development Goals (SDGs)
This project directly targets three global goals:
* **SDG 3 (Good Health & Well-being):** Providing instant, free access to preventative health monitoring (Heart Rate, SpO2, Temperature).
* **SDG 5 (Gender Equality):** Bypassing gender-based stigmas and cultural taboos that prevent men and women from accessing basic health awareness.
* **SDG 9 (Industry, Innovation & Infrastructure):** Proving that highly accurate, scalable medical infrastructure can be engineered for under $150 per unit.

## Hardware Architecture
The kiosk runs on a pure Raspberry Pi 5 (Bookworm OS) architecture, requiring no external microcontrollers. 
* **MAX30102 / DFRobot (I2C):** Measures Heart Rate and Blood Oxygen (SpO2) via red/infrared LEDs.
* **MLX90614 (I2C):** Non-contact infrared body temperature sensor.
* **PIR Motion Sensor:** Tracks visitor footfall and clinic usage.
* **Sound Sensor (Digital):** Monitors ambient noise to detect crowded or distressed waiting room environments.
* **Pi Camera Module 3:** Provides an on-demand, live patient vision feed.

## Software Stack
* **Core Logic:** Python 3
* **Live Dashboard:** Flask (Web server delivering a real-time, responsive UI)
* **Data Storage:** InfluxDB (Time-series database storing live metrics, historical trends, and 24-hour rolling averages)
* **Hardware Interfacing:** smbus for I2C, gpiozero for digital pins.

## Quick Start & Deployment

**1. Hardware Setup:**
Ensure I2C is enabled on the Raspberry Pi:
```bash
sudo raspi-config  # Navigate to Interface Options -> I2C -> Enable
sudo reboot
```

**2. Install Dependencies:**
```bash
sudo apt install i2c-tools -y
sudo pip3 install PyMLX90614 Flask Flask-Cors influxdb-client gpiozero --break-system-packages
git clone https://github.com/DFRobot/DFRobot_BloodOxygen_S.git /home/atunapato/DFRobot_BloodOxygen_S
```

**3. Run the Kiosk Engine:**
```bash
sudo python3 deploy_system.py
```

**4. Access the Dashboard:**
Open a web browser on any device connected to the local network and navigate to:
`http://<YOUR_PI_IP_ADDRESS>:5000`

## Testing & Validation
The prototype underwent rigorous validation across three layers:
1. **Accuracy:** Sensor outputs were cross-referenced with commercial pulse oximeters and medical thermometers.
2. **Stability:** The Python/Flask ingestion engine and I2C bus were hardened to run continuously without memory leaks or [Errno 121] crashes.
3. **Environmental Tuning:** The sound sensor and camera were calibrated under real-world lighting and ambient noise conditions.

---
*Designed and engineered with care by the WeCare Team*
