import os, sqlite3
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "application/#")

DATA_DIR = "/data"

# application_id → DB 매핑
APP_DB_MAP = {
    # 온습도 (EF-SmartFactory)
    "a0cc862c-126b-4d6a-9f0a-d5438c432d48": "sensor_logs.db",

    # 저울용 application (예시)
    "9f43161d-1f4b-482a-be74-2797c516c2c5": "scale_logs.db",
}

# --- DB connection cache ---
db_conns = {}

def get_db(app_id):
    """
    application_id에 대응하는 DB 커넥션 반환
    """
    if app_id not in APP_DB_MAP:
        return None

    if app_id not in db_conns:
        db_path = os.path.join(DATA_DIR, APP_DB_MAP[app_id])
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cur = conn.cursor()

        # 공통 raw 테이블
        cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          topic TEXT,
          payload TEXT
        )
        """)
        conn.commit()

        db_conns[app_id] = (conn, cur)

    return db_conns[app_id]


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore")
    topic = msg.topic

    # topic 예: application/2/device/xxxx/event/up
    parts = topic.split("/")
    if len(parts) < 2:
        return

    app_id = parts[1]

    db = get_db(app_id)
    if not db:
        print(f"ℹ️ Unknown application_id: {app_id}")
        return

    conn, cur = db

    cur.execute(
        "INSERT INTO raw_logs (topic, payload) VALUES (?, ?)",
        (topic, payload)
    )
    conn.commit()

    print(f"✅ Saved app={app_id} topic={topic}")


client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC, qos=0)

print(f"📡 Subscribed to {MQTT_TOPIC} at {MQTT_HOST}:{MQTT_PORT}")
client.loop_forever()
