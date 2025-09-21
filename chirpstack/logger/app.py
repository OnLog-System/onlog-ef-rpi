import os, sqlite3, json, time
from datetime import datetime, timedelta
from collections import defaultdict, deque
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "application/#")
DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")
SYNC_CHECK_INTERVAL = int(os.getenv("SYNC_CHECK_INTERVAL", "300"))  # 5분마다 동기화 체크
MESSAGE_BALANCE_THRESHOLD = float(os.getenv("MESSAGE_BALANCE_THRESHOLD", "0.1"))  # 10% 임계값

# 메시지 동기화 모니터링을 위한 전역 변수
device_message_counts = defaultdict(int)
device_last_seen = defaultdict(float)
device_intervals = defaultdict(lambda: deque(maxlen=10))  # 최근 10개 간격만 저장
last_sync_check = time.time()

# SQLite 초기화
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# 기존 raw_logs 테이블
c.execute("""
CREATE TABLE IF NOT EXISTS raw_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  topic TEXT,
  payload TEXT
)
""")

# 새로운 동기화 모니터링 테이블
c.execute("""
CREATE TABLE IF NOT EXISTS sync_monitoring (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  device_id TEXT,
  message_count INTEGER,
  avg_interval REAL,
  last_message_time TIMESTAMP,
  sync_status TEXT,
  notes TEXT
)
""")

# 동기화 이벤트 로그 테이블
c.execute("""
CREATE TABLE IF NOT EXISTS sync_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type TEXT,
  device_id TEXT,
  message TEXT,
  severity TEXT
)
""")

conn.commit()

def extract_device_id(topic):
    """MQTT 토픽에서 디바이스 ID 추출"""
    parts = topic.split('/')
    if len(parts) >= 3 and parts[0] == 'application':
        return parts[2]  # application/{app_id}/{device_id}/...
    return None

def analyze_message_balance():
    """메시지 균형 분석 및 불균형 감지"""
    if not device_message_counts:
        return
    
    total_devices = len(device_message_counts)
    if total_devices < 2:
        return
    
    counts = list(device_message_counts.values())
    avg_count = sum(counts) / len(counts)
    max_count = max(counts)
    min_count = min(counts)
    
    # 불균형 계산 (최대값과 최소값의 차이가 평균의 임계값 이상인지 확인)
    if avg_count > 0:
        imbalance_ratio = (max_count - min_count) / avg_count
        
        if imbalance_ratio > MESSAGE_BALANCE_THRESHOLD:
            # 불균형 감지 - 이벤트 로그 기록
            max_device = [dev for dev, count in device_message_counts.items() if count == max_count][0]
            min_device = [dev for dev, count in device_message_counts.items() if count == min_count][0]
            
            event_msg = f"Message imbalance detected: {max_device}({max_count}) vs {min_device}({min_count}), ratio: {imbalance_ratio:.2f}"
            log_sync_event("IMBALANCE", None, event_msg, "WARNING")
            print(f"⚠️  {event_msg}")

def log_sync_event(event_type, device_id, message, severity="INFO"):
    """동기화 이벤트 로깅"""
    c.execute("""
        INSERT INTO sync_events (event_type, device_id, message, severity) 
        VALUES (?, ?, ?, ?)
    """, (event_type, device_id, message, severity))
    conn.commit()

def check_device_synchronization():
    """주기적 디바이스 동기화 상태 체크"""
    current_time = time.time()
    
    for device_id, message_count in device_message_counts.items():
        last_seen = device_last_seen.get(device_id, 0)
        intervals = device_intervals.get(device_id, deque())
        
        # 평균 메시지 간격 계산
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        
        # 동기화 상태 판단
        time_since_last = current_time - last_seen
        sync_status = "ACTIVE"
        notes = ""
        
        if time_since_last > 600:  # 10분 이상 메시지 없음
            sync_status = "INACTIVE"
            notes = f"No messages for {int(time_since_last/60)} minutes"
        elif avg_interval > 0 and time_since_last > avg_interval * 2:
            sync_status = "DELAYED"
            notes = f"Message delayed, expected interval: {avg_interval:.1f}s"
        
        # 모니터링 데이터 저장
        c.execute("""
            INSERT INTO sync_monitoring 
            (device_id, message_count, avg_interval, last_message_time, sync_status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (device_id, message_count, avg_interval, 
              datetime.fromtimestamp(last_seen).isoformat(), sync_status, notes))
    
    conn.commit()
    analyze_message_balance()

# MQTT 콜백
def on_message(client, userdata, msg):
    global last_sync_check
    
    payload = msg.payload.decode("utf-8")
    current_time = time.time()
    
    # 기존 로깅
    c.execute("INSERT INTO raw_logs (topic, payload) VALUES (?, ?)", (msg.topic, payload))
    
    # 디바이스 추적 및 동기화 모니터링
    device_id = extract_device_id(msg.topic)
    if device_id:
        # 메시지 카운트 업데이트
        device_message_counts[device_id] += 1
        
        # 이전 메시지와의 간격 계산
        last_seen = device_last_seen.get(device_id, 0)
        if last_seen > 0:
            interval = current_time - last_seen
            device_intervals[device_id].append(interval)
        
        device_last_seen[device_id] = current_time
        
        print(f"✅ Saved: {msg.topic} (Device: {device_id}, Count: {device_message_counts[device_id]})")
    else:
        print(f"✅ Saved: {msg.topic}")
    
    conn.commit()
    
    # 주기적 동기화 체크
    if current_time - last_sync_check > SYNC_CHECK_INTERVAL:
        print("🔍 Performing synchronization check...")
        check_device_synchronization()
        last_sync_check = current_time

def print_sync_summary():
    """동기화 상태 요약 출력"""
    if not device_message_counts:
        print("📊 No devices detected yet")
        return
    
    print("📊 Device Synchronization Summary:")
    print("-" * 60)
    
    for device_id in sorted(device_message_counts.keys()):
        count = device_message_counts[device_id]
        last_seen = device_last_seen.get(device_id, 0)
        intervals = device_intervals.get(device_id, deque())
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        
        time_since = time.time() - last_seen if last_seen > 0 else 0
        status = "🟢" if time_since < 300 else "🟡" if time_since < 600 else "🔴"
        
        print(f"{status} {device_id}: {count} msgs, avg interval: {avg_interval:.1f}s, last seen: {int(time_since)}s ago")

def on_connect(client, userdata, flags, rc):
    """MQTT 연결 시 콜백"""
    if rc == 0:
        print(f"📡 Connected to {MQTT_HOST}:{MQTT_PORT}")
        log_sync_event("SYSTEM", None, "MQTT Logger started", "INFO")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_disconnect(client, userdata, rc):
    """MQTT 연결 해제 시 콜백"""
    print(f"📡 Disconnected from MQTT broker (code: {rc})")
    log_sync_event("SYSTEM", None, "MQTT Logger disconnected", "WARNING")

# 시작 시 초기 동기화 체크 수행
print("🚀 Starting MQTT Logger with Synchronization Monitoring")
print(f"📊 Sync check interval: {SYNC_CHECK_INTERVAL}s")
print(f"⚖️  Message balance threshold: {MESSAGE_BALANCE_THRESHOLD*100}%")

client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect  
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC, qos=1)  # QoS 1로 변경하여 메시지 유실 방지
print(f"📡 Subscribed to {MQTT_TOPIC} at {MQTT_HOST}:{MQTT_PORT} (QoS=1)")

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\n🛑 Shutting down MQTT Logger...")
    log_sync_event("SYSTEM", None, "MQTT Logger shutdown", "INFO")
    print_sync_summary()
    client.disconnect()
    conn.close()
