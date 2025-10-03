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
# API 함수
# ------------------------------
def get_gateway_metrics(start, end):
    url = f"{API_BASE}/gateways/{GATEWAY_ID}/metrics?start={start}&end={end}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_devices(limit=50, offset=0):
    url = f"{API_BASE}/devices?applicationId={APPLICATION_ID}&limit={limit}&offset={offset}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json().get("result", [])

def get_device_metrics(dev_eui, start, end):
    url = f"{API_BASE}/devices/{dev_eui}/metrics?start={start}&end={end}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

# ------------------------------
# DB 함수
# ------------------------------
def get_db_count():
    try:
        conn = sqlite3.connect(SQLITE_DB)
        cur = conn.cursor()
        # ✅ 테이블 이름 확인 후 수정 필요
        cur.execute("SELECT COUNT(*) FROM uplink;")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print("SQLite 조회 실패:", e)
        return None

# ------------------------------
# 실행
# ------------------------------
if __name__ == "__main__":
    # 시간 범위 (오늘 6시간 기준 예시)
    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=6)
    start_str = start.isoformat() + "Z"
    end_str = end.isoformat() + "Z"

    print("=== Gateway Metrics ===")
    try:
        gw = get_gateway_metrics(start_str, end_str)
        print(gw)
    except Exception as e:
        print("Gateway metrics 조회 실패:", e)

    print("\n=== Device Metrics ===")
    try:
        devices = get_devices()
        if not devices:
            print("등록된 디바이스가 없습니다.")
        for d in devices:
            dev_eui = d.get("devEui")
            name = d.get("name")
            print(f"\nDevice {name} ({dev_eui}):")
            try:
                metrics = get_device_metrics(dev_eui, start_str, end_str)
                print(metrics)
            except Exception as e:
                print(f"Device {dev_eui} metrics 조회 실패:", e)
    except Exception as e:
        print("Device 리스트 조회 실패:", e)

    print("\n=== SQLite Row Count ===")
    db_count = get_db_count()
    if db_count is not None:
        print(f"DB 저장 row 수: {db_count}")