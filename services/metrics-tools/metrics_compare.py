#!/usr/bin/env python3
import os, argparse, sqlite3, requests, json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load env
load_dotenv()
API_URL = os.getenv("CHIRPSTACK_API_URL")
API_KEY = os.getenv("CHIRPSTACK_API_KEY")
GATEWAY_ID = os.getenv("GATEWAY_ID")
APPLICATION_ID = os.getenv("APPLICATION_ID")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH")

headers = {"Grpc-Metadata-Authorization": f"Bearer {API_KEY}"}

# ------------------------------
# 1. 게이트웨이 메트릭 조회
# ------------------------------
def get_gateway_metrics(gateway_id):
    url = f"{API_BASE}/gateways/{gateway_id}/metrics"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

# ------------------------------
# 2. 디바이스 리스트 + 메트릭 조회
# ------------------------------
def get_devices():
    url = f"{API_BASE}/devices"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json().get("result", [])

def get_device_metrics(dev_eui):
    url = f"{API_BASE}/devices/{dev_eui}/metrics"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

# ------------------------------
# 3. SQLite DB row count
# ------------------------------
def get_db_count():
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM uplink")   # uplink 테이블명 맞게 수정
    count = cur.fetchone()[0]
    conn.close()
    return count

# ------------------------------
# 실행
# ------------------------------
if __name__ == "__main__":
    print("=== Gateway Metrics ===")
    gw_metrics = get_gateway_metrics(GATEWAY_ID)
    print(gw_metrics)

    print("\n=== Devices ===")
    devices = get_devices()
    for d in devices:
        dev_eui = d["devEui"]
        print(f"\nDevice {dev_eui} metrics:")
        dev_metrics = get_device_metrics(dev_eui)
        print(dev_metrics)

    print("\n=== DB Row Count ===")
    print("Rows in SQLite:", get_db_count())