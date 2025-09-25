import os, sqlite3, json, time
from datetime import datetime, timedelta
from collections import defaultdict
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "application/#")
DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")
QOS_LEVEL = int(os.getenv("QOS_LEVEL", "1"))  # Use QoS 1 for reliability
BALANCE_CHECK_INTERVAL = int(os.getenv("BALANCE_CHECK_INTERVAL", "300"))  # 5 minutes

# Device message tracking
device_message_counts = defaultdict(int)
device_last_seen = defaultdict(lambda: datetime.now())
device_expected_interval = defaultdict(lambda: 60)  # Default 60 seconds

# SQLite 초기화
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# Create enhanced tables
c.execute("""
CREATE TABLE IF NOT EXISTS raw_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  topic TEXT,
  payload TEXT,
  device_id TEXT,
  message_type TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS device_stats (
  device_id TEXT PRIMARY KEY,
  message_count INTEGER DEFAULT 0,
  last_seen TIMESTAMP,
  expected_interval INTEGER DEFAULT 60,
  actual_avg_interval REAL,
  status TEXT DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS message_balance_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  total_devices INTEGER,
  balanced BOOLEAN,
  min_messages INTEGER,
  max_messages INTEGER,
  avg_messages REAL,
  details TEXT
)
""")

conn.commit()

def extract_device_id(topic):
    """Extract device ID from MQTT topic"""
    # Topic format: application/{application_id}/device/{device_eui}/event/up
    parts = topic.split('/')
    if len(parts) >= 4 and parts[2] == 'device':
        return parts[3]  # device_eui
    return 'unknown'

def extract_message_type(topic):
    """Extract message type from MQTT topic"""
    parts = topic.split('/')
    if len(parts) >= 6:
        return parts[5]  # event type (up, join, etc.)
    return 'unknown'

def update_device_stats(device_id, current_time):
    """Update device statistics in database"""
    device_message_counts[device_id] += 1
    
    # Calculate interval if we have previous timestamp
    if device_id in device_last_seen:
        interval = (current_time - device_last_seen[device_id]).total_seconds()
        # Update running average (simple exponential smoothing)
        c.execute("SELECT actual_avg_interval FROM device_stats WHERE device_id = ?", (device_id,))
        result = c.fetchone()
        if result and result[0]:
            avg_interval = 0.8 * result[0] + 0.2 * interval
        else:
            avg_interval = interval
    else:
        avg_interval = None
    
    device_last_seen[device_id] = current_time
    
    # Upsert device statistics
    c.execute("""
        INSERT OR REPLACE INTO device_stats 
        (device_id, message_count, last_seen, actual_avg_interval, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (device_id, device_message_counts[device_id], current_time, avg_interval, current_time))

def check_message_balance():
    """Check if devices are sending messages at balanced rates"""
    print("🔍 Checking message balance...")
    
    # Get current stats for all devices
    c.execute("""
        SELECT device_id, message_count, actual_avg_interval, 
               (strftime('%s','now') - strftime('%s',last_seen)) as seconds_since_last
        FROM device_stats 
        WHERE last_seen > datetime('now', '-1 hour')
    """)
    
    devices = c.fetchall()
    if not devices:
        print("⚠️ No active devices found")
        return
    
    message_counts = [d[1] for d in devices]
    min_messages = min(message_counts)
    max_messages = max(message_counts)
    avg_messages = sum(message_counts) / len(message_counts)
    
    # Check if balanced (within 10% tolerance)
    balance_threshold = 0.1 * avg_messages
    balanced = (max_messages - min_messages) <= balance_threshold
    
    # Log balance check
    details = json.dumps({
        'devices': [
            {
                'device_id': d[0], 
                'message_count': d[1], 
                'avg_interval': d[2],
                'seconds_since_last': d[3]
            } for d in devices
        ]
    })
    
    c.execute("""
        INSERT INTO message_balance_log 
        (total_devices, balanced, min_messages, max_messages, avg_messages, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (len(devices), balanced, min_messages, max_messages, avg_messages, details))
    
    conn.commit()
    
    # Print summary
    status = "✅ BALANCED" if balanced else "⚠️ IMBALANCED"
    print(f"{status} - Devices: {len(devices)}, Messages: {min_messages}-{max_messages} (avg: {avg_messages:.1f})")
    
    if not balanced:
        print("📊 Device details:")
        for device in devices:
            print(f"  - {device[0]}: {device[1]} messages, avg interval: {device[2]:.1f}s")

# MQTT 콜백
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"📡 Connected to MQTT broker with QoS {QOS_LEVEL}")
    else:
        print(f"❌ Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    current_time = datetime.now()
    payload = msg.payload.decode("utf-8")
    device_id = extract_device_id(msg.topic)
    message_type = extract_message_type(msg.topic)
    
    # Store raw message
    c.execute("""
        INSERT INTO raw_logs (topic, payload, device_id, message_type) 
        VALUES (?, ?, ?, ?)
    """, (msg.topic, payload, device_id, message_type))
    
    # Update device statistics
    update_device_stats(device_id, current_time)
    
    conn.commit()
    print(f"✅ Saved: {device_id} ({message_type}) - Total: {device_message_counts[device_id]}")

def on_disconnect(client, userdata, rc):
    print(f"📡 Disconnected from MQTT broker, return code {rc}")

# Setup MQTT client with enhanced reliability
client = mqtt.Client(client_id="sensor-monitor-logger", clean_session=False)
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Connect with retry logic
connected = False
retry_count = 0
max_retries = 5

while not connected and retry_count < max_retries:
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        connected = True
    except Exception as e:
        retry_count += 1
        print(f"❌ Connection attempt {retry_count} failed: {e}")
        if retry_count < max_retries:
            time.sleep(5)

if not connected:
    print("❌ Failed to connect after maximum retries")
    exit(1)

client.subscribe(MQTT_TOPIC, qos=QOS_LEVEL)
print(f"📡 Subscribed to {MQTT_TOPIC} at {MQTT_HOST}:{MQTT_PORT} with QoS {QOS_LEVEL}")

# Start balance checking in background
import threading

def balance_checker():
    while True:
        time.sleep(BALANCE_CHECK_INTERVAL)
        check_message_balance()

balance_thread = threading.Thread(target=balance_checker, daemon=True)
balance_thread.start()

print(f"🔍 Message balance checking every {BALANCE_CHECK_INTERVAL} seconds")
print("🚀 Sensor message synchronization monitor started")

# Start MQTT loop
try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\n👋 Shutting down gracefully...")
    client.disconnect()
    conn.close()
