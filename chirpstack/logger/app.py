import os, sqlite3
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "application/#")
DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")

# SQLite 초기화
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS raw_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  topic TEXT,
  payload TEXT
)
""")
conn.commit()

# MQTT 콜백
def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    c.execute("INSERT INTO raw_logs (topic, payload) VALUES (?, ?)", (msg.topic, payload))
    conn.commit()
    print("✅ Saved:", msg.topic)

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC, qos=1)
print(f"📡 Subscribed to {MQTT_TOPIC} at {MQTT_HOST}:{MQTT_PORT}")
client.loop_forever()
