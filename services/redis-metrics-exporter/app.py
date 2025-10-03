import redis
import sqlite3
import json
import os
import re
import time
from datetime import datetime

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
SQLITE_PATH = os.getenv("DB_PATH", "/data/redis_metrics.db")
EXPORT_INTERVAL = int(os.getenv("EXPORT_INTERVAL", 3600))  # 기본 1시간(3600초)

def init_db():
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        ts TEXT,
        obj_type TEXT,
        obj_id TEXT,
        granularity TEXT,
        data TEXT,
        PRIMARY KEY (ts, obj_type, obj_id, granularity)
    )
    """)
    conn.commit()
    return conn

def parse_key(key):
    m = re.match(r"metrics:{(gw|device):([^}]+)}:(HOUR|DAY|MONTH):(\d+)", key)
    if not m:
        return None
    obj_type = "gateway" if m.group(1) == "gw" else "device"
    obj_id = m.group(2)
    granularity = m.group(3)
    ts_raw = m.group(4)

    try:
        ts = datetime.strptime(ts_raw, "%Y%m%d%H%M").isoformat()
    except ValueError:
        return None
    return obj_type, obj_id, granularity, ts

def export_metrics(r, conn):
    cur = conn.cursor()
    new_rows = 0
    for key in r.scan_iter("metrics:*"):
        parsed = parse_key(key)
        if not parsed:
            continue
        obj_type, obj_id, granularity, ts = parsed
        values = r.hgetall(key)

        try:
            cur.execute("""
            INSERT OR IGNORE INTO metrics (ts, obj_type, obj_id, granularity, data)
            VALUES (?, ?, ?, ?, ?)
            """, (ts, obj_type, obj_id, granularity, json.dumps(values)))
            if cur.rowcount > 0:
                new_rows += 1
        except sqlite3.Error as e:
            print(f"⚠️ SQLite insert error: {e}")
    conn.commit()
    return new_rows

if __name__ == "__main__":
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    conn = init_db()

    while True:
        inserted = export_metrics(r, conn)
        print(f"✅ Export 완료: {inserted} rows inserted")
        print(f"⏳ 다음 실행까지 {EXPORT_INTERVAL}초 대기")
        time.sleep(EXPORT_INTERVAL)
