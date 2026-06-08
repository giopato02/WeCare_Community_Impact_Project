import os
import sys
import time
import threading
import cv2
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory
from flask_cors import CORS
from gpiozero import MotionSensor, DigitalInputDevice
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import smbus

# --- I2C sensor libraries (guarded so a missing lib never kills the server) ---
try:
    from mlx90614 import MLX90614
except Exception as _e:
    MLX90614 = None
    print(f"⚠️  MLX90614 library unavailable: {_e}")

try:
    sys.path.insert(0, "/home/pi/DFRobot_BloodOxygen_S/python/raspberry")
    from DFRobot_BloodOxygen_S import DFRobot_BloodOxygen_S_i2c
except Exception as _e:
    DFRobot_BloodOxygen_S_i2c = None
    print(f"⚠️  DFRobot BloodOxygen library unavailable: {_e}")

# ==========================================
# 🛑 CORE INTEGRATED SYSTEM CONFIGURATION 🛑
# ==========================================
URL = "https://eu-central-1-1.aws.cloud2.influxdata.com"
ORG = "javrishvili.atuna@gmail.com"
BUCKET = "pi_sensors" 
TOKEN = "78O-Qx7oc_wV9sXFGpY8KMDDzqcxS_bEHfNypax0xhZhNqdLhedADhLfJaVHjiU1dLLdt6Uh-zBHkqbJdzWBZw=="
DEVICE = "my-raspberry-pi"

MOTION_PIN = 26
NOISE_PIN = 17
PHOTO_DIR = "/home/pi"

# I2C sensors
I2C_BUS = 1            # standard Pi I2C bus (GPIO2 = SDA, GPIO3 = SCL)
MLX_ADDR = 0x5A        # Joy-IT SEN-IR-TEMP (MLX90614)
OXIMETER_ADDR = 0x57   # DFRobot Heartrate & Oximeter (SEN0344)
# ==========================================

os.makedirs("templates", exist_ok=True)

# ------------------------------------------
# 🎨 WRITING DYNAMIC HTML DASHBOARD TEMPLATE
# ------------------------------------------
html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Sensor Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8fafc; --card-bg: #ffffff; --text-main: #1e293b;
            --text-muted: #64748b; --accent: #3b82f6;
            --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
        }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 40px 20px; display: flex; flex-direction: column; align-items: center; }
        header { margin-bottom: 40px; text-align: center; }
        h1 { font-size: 2.25rem; font-weight: 700; color: #334155; display: flex; align-items: center; gap: 15px; margin: 0; }
        #status-indicator { font-size: 0.8rem; margin-top: 20px; color: var(--text-muted); }
        .dot { height: 8px; width: 8px; background-color: #22c55e; border-radius: 50%; display: inline-block; margin-right: 5px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; width: 100%; max-width: 1200px; }
        .card { background: var(--card-bg); border-radius: 16px; padding: 24px; box-shadow: var(--shadow); border: 1px solid #e2e8f0; }
        .card-title { font-size: 0.875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
        .live-value { font-size: 3rem; font-weight: 700; color: var(--accent); margin: 8px 0; }
        .timestamp { font-size: 0.75rem; color: var(--text-muted); }
        .stats-tray { margin-top: 15px; padding-top: 15px; border-top: 1px solid #f1f5f9; }
        .stat-label { font-size: 0.7rem; color: var(--text-muted); }
        .stat-value { font-weight: 600; font-size: 1rem; }
        .btn-capture { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .btn-capture:disabled { background: #cbd5e1; }
    </style>
</head>
<body>
    <header>
        <h1>🛰️ Live Sensor Dashboard</h1>
        <div id="status-indicator"><span class="dot"></span> System Live</div>
    </header>
    
    <div class="dashboard-grid">
        <div id="dashboard-container" style="display: contents;">
            <p style="text-align:center; width:100%;">Waiting for sensor data...</p>
        </div>
        
        <div class="card" style="grid-column: span 1;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span class="card-title">Patient Vision feed</span>
                <button onclick="takePhoto()" id="snap-btn" class="btn-capture">📸 Capture</button>
            </div>
            <div style="width:100%; height:200px; background:#000; border-radius:12px; overflow:hidden; display:flex; align-items:center; justify-content:center;">
                <img id="patient-img" src="/api/latest_photo" style="width:100%; height:100%; object-fit:cover;" onerror="this.style.display='none'" onload="this.style.display='block'">
            </div>
        </div>
    </div>

    <script>
        async function updateDashboard() {
            try {
                const [latestRes, statsRes] = await Promise.all([fetch('/api/latest'), fetch('/api/stats')]);
                const latestData = await latestRes.json();
                const statsData = await statsRes.json();
                const container = document.getElementById('dashboard-container');
                
                if (Object.keys(latestData).length === 0) return;
                container.innerHTML = '';

                for (const [name, data] of Object.entries(latestData)) {
                    if (name === 'camera_status') continue; 
                    const stats = statsData[name] || { avg: 0 };
                    let displayValue = data.value;
                    let unit = "";

                    if (name.includes('temp')) { unit = "°C"; displayValue = data.value.toFixed(1); }
                    else if (name === 'heart_rate') { unit = "BPM"; displayValue = data.value.toFixed(0); }
                    else if (name === 'spo2') { unit = "%"; displayValue = data.value.toFixed(0); }
                    else if (name === 'motion_detected') { displayValue = data.value > 0 ? "ALERT" : "CLEAR"; }
                    else if (name === 'noise_level') { displayValue = data.value > 0 ? "LOUD" : "QUIET"; }
                    else if (typeof data.value === 'number') { displayValue = data.value.toFixed(0); }

                    let avgDisplay = (name === 'motion_detected' || name === 'noise_level') ? 
                                     (stats.avg * 100).toFixed(0) + '%' : stats.avg.toFixed(1) + unit;

                    container.innerHTML += `
                        <div class="card">
                            <div class="card-title">${name.replace(/_/g, ' ')}</div>
                            <div class="live-value">${displayValue}<span style="font-size:1.5rem">${unit}</span></div>
                            <div class="timestamp">Last record: ${data.time}</div>
                            <div class="stats-tray">
                                <span class="stat-label">24H BURDEN / AVG: </span>
                                <span class="stat-value">${avgDisplay}</span>
                            </div>
                        </div>`;
                }
            } catch (e) { console.error(e); }
        }

        async function takePhoto() {
            const btn = document.getElementById('snap-btn');
            const img = document.getElementById('patient-img');
            btn.innerText = "⌛..."; btn.disabled = true;
            try {
                const response = await fetch('/api/capture', { method: 'POST' });
                if (response.ok) { img.src = "/api/latest_photo?t=" + new Date().getTime(); }
                else { alert("Camera capture failed. Check hardware connection."); }
            } catch (e) { console.error(e); }
            finally { btn.innerText = "📸 Capture"; btn.disabled = false; }
        }

        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""

with open("templates/dashboard.html", "w") as f:
    f.write(html_content)

# ------------------------------------------
# 💾 BACKGROUND DATA INGESTION ENGINE
# ------------------------------------------
noise_memory = [False]

def noise_polling_thread():
    """Aggressively checks the noise sensor 100 times per second"""
    # pull_up=None prevents the Pi from forcing a voltage, letting the sensor speak for itself
    noise_sensor = DigitalInputDevice(NOISE_PIN, pull_up=None)
    
    # Wait 1 second on startup, then record whatever voltage the sensor is resting at
    time.sleep(1)
    baseline_quiet = noise_sensor.value
    
    while True:
        # If the voltage changes from the quiet baseline, we have a noise spike!
        if noise_sensor.value != baseline_quiet:
            if not noise_memory[0]: # Print to terminal for instant debugging
                print("🎤 [DEBUG] Instant Noise Micro-Pulse Detected!")
            noise_memory[0] = True
        time.sleep(0.01)

def data_bridge_loop():
    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    pir = MotionSensor(MOTION_PIN)

    # --- I2C sensor setup (each guarded; a bus hiccup must not kill the thread) ---
    i2c_bus = None
    mlx = None
    oximeter = None
    oximeter_ready = False
    try:
        i2c_bus = smbus.SMBus(I2C_BUS)
    except Exception as e:
        print(f"⚠️  Could not open I2C bus {I2C_BUS}: {e}")

    if i2c_bus is not None and MLX90614 is not None:
        try:
            mlx = MLX90614(i2c_bus, address=MLX_ADDR)
        except Exception as e:
            print(f"⚠️  MLX90614 init failed: {e}")

    print("📡 Background Ingestion Running seamlessly...")

    # Start the ultra-fast noise watcher in the background
    threading.Thread(target=noise_polling_thread, daemon=True).start()

    while True:
        try:
            res = os.popen('vcgencmd measure_temp').readline()
            cpu_temp = float(res.replace("temp=","").replace("'C\n",""))
            motion = 1.0 if pir.motion_detected else 0.0
            
            # Check if noise happened anytime in the last 2 seconds
            noise = 1.0 if noise_memory[0] else 0.0
            noise_memory[0] = False # Reset memory to False for the next 2-second window
            
            photos = float(len([f for f in os.listdir(PHOTO_DIR) if f.startswith('patient_') and f.endswith('.jpg')]))

            data_points = [
                Point("cpu_temperature").tag("device", DEVICE).field("value", cpu_temp),
                Point("motion_detected").tag("device", DEVICE).field("value", motion),
                Point("noise_level").tag("device", DEVICE).field("value", noise),
                Point("photos_captured").tag("device", DEVICE).field("value", photos)
            ]

            # --- MLX90614 infrared temperatures (ambient + patient/object) ---
            if mlx is not None:
                try:
                    ambient_temp = mlx.get_amb_temp()
                    patient_temp = mlx.get_obj_temp()
                    data_points.append(Point("ambient_temp").tag("device", DEVICE).field("value", ambient_temp))
                    data_points.append(Point("patient_temp").tag("device", DEVICE).field("value", patient_temp))
                except Exception as e:
                    print(f"MLX90614 read skip: {e}")

            # --- DFRobot heart rate & SpO2 ---
            # Lazy-init: begin() is safe (returns False if the sensor is absent);
            # only start collection once it actually answers, so we never trip the
            # library's blocking write-retry loop on a missing sensor.
            if DFRobot_BloodOxygen_S_i2c is not None and not oximeter_ready:
                try:
                    if oximeter is None:
                        oximeter = DFRobot_BloodOxygen_S_i2c(I2C_BUS, OXIMETER_ADDR)
                    if oximeter.begin():
                        oximeter.sensor_start_collect()
                        oximeter_ready = True
                        print("❤️  DFRobot oximeter online.")
                except Exception as e:
                    print(f"Oximeter init skip: {e}")

            if oximeter_ready:
                try:
                    oximeter.get_heartbeat_SPO2()
                    bpm = oximeter.heartbeat
                    spo2 = oximeter.SPO2
                    # Library returns -1 when no finger is present; skip those.
                    if bpm and bpm > 0:
                        data_points.append(Point("heart_rate").tag("device", DEVICE).field("value", float(bpm)))
                    if spo2 and spo2 > 0:
                        data_points.append(Point("spo2").tag("device", DEVICE).field("value", float(spo2)))
                except Exception as e:
                    print(f"Oximeter read skip: {e}")

            write_api.write(bucket=BUCKET, org=ORG, record=data_points)
        except Exception as e:
            print(f"Ingestion engine skip: {e}")
        time.sleep(2)

# Start main bridge loop
threading.Thread(target=data_bridge_loop, daemon=True).start()

# ------------------------------------------
# 🚀 FLASK WEB CONTROLLER SERVICES
# ------------------------------------------
app = Flask(__name__)
CORS(app)
client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/latest')
def get_latest():
    query_api = client.query_api()
    query = f'from(bucket: "{BUCKET}") |> range(start: -10m) |> filter(fn: (r) => r["device"] == "{DEVICE}") |> last()'
    try:
        tables = query_api.query(query)
        result = {record.get_measurement(): {'value': record.get_value(), 'time': record.get_time().strftime('%H:%M:%S')} 
                  for table in tables for record in table.records}
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def get_stats():
    query_api = client.query_api()
    query = f'from(bucket: "{BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r["device"] == "{DEVICE}") |> mean()'
    try:
        tables = query_api.query(query)
        return jsonify({record.get_measurement(): {'avg': record.get_value()} for table in tables for record in table.records})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/capture', methods=['POST'])
def capture_photo():
    filename = f"patient_{int(time.time())}.jpg"
    filepath = os.path.join(PHOTO_DIR, filename)
    
    if os.system(f"rpicam-jpeg -o {filepath} -t 1000 --width 800 --height 600 > /dev/null 2>&1") == 0:
        return jsonify({"status": "success", "filename": filename})
    if os.system(f"libcamera-jpeg -o {filepath} -t 1000 --width 800 --height 600 > /dev/null 2>&1") == 0:
        return jsonify({"status": "success", "filename": filename})

    try:
        cap = cv2.VideoCapture(0)
        for _ in range(5): cap.read() 
        ret, frame = cap.read()
        cap.release()
        if ret:
            cv2.imwrite(filepath, frame)
            return jsonify({"status": "success", "filename": filename})
    except:
        pass

    return jsonify({"status": "error"}), 500

@app.route('/api/latest_photo')
def get_latest_photo():
    files = [f for f in os.listdir(PHOTO_DIR) if f.startswith('patient_') and f.endswith('.jpg')]
    if not files: return "No image", 404
    return send_from_directory(PHOTO_DIR, max(files, key=lambda x: os.path.getctime(os.path.join(PHOTO_DIR, x))))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
