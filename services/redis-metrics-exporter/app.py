import redis
import sqlite3
import json
from datetime import datetime
import os

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
SQLITE_PATH = os.getenv("DB_PATH", "/data/redis_metrics.db")

def init_db():
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        ts TEXT,
        obj_type TEXT,
        obj_id TEXT,
        granularity TEXT,
        data TEXT
    )
    """)
    conn.commit()
    return conn

def export_metrics(r, conn):
    cur = conn.cursor()
    for key in r.scan_iter("metrics:*"):
        parts = key.split(":")
        obj_type = "gateway" if "gw" in parts[1] else "device"
        obj_id = parts[1].split("{")[1].strip("}")
        granularity = parts[2]
        ts = parts[3]

        values = r.hgetall(key)

        record = {
            "ts": ts,
            "type": obj_type,
            "id": obj_id,
            "granularity": granularity,
            "metrics": values
        }

        cur.execute(
            "INSERT INTO metrics (ts, obj_type, obj_id, granularity, data) VALUES (?, ?, ?, ?, ?)",
            (record["ts"], record["type"], record["id"], record["granularity"], json.dumps(record["metrics"]))
        )
    conn.commit()

if __name__ == "__main__":
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    conn = init_db()
    export_metrics(r, conn)
    print("✅ Redis metrics exported to SQLite")
