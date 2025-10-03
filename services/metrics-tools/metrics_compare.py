#!/usr/bin/env python3
import os
import argparse
import sqlite3
import requests
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# -----------------------------
# 환경 변수 로드
# -----------------------------
load_dotenv(os.getenv("ONLOG_ENV_PATH", ".env"))

API_BASE = os.getenv("CHIRPSTACK_API_URL", "http://localhost:8090/api")
API_KEY = os.getenv("CHIRPSTACK_API_KEY")
GATEWAY_ID = os.getenv("GATEWAY_ID")
SQLITE_DB = os.getenv("SQLITE_DB_PATH", "/mnt/nvme/infra/sqlite/sensor_logs.db")

HEADERS = {"Grpc-Metadata-Authorization": f"Bearer {API_KEY}"}

# -----------------------------
# devices.json 로드
# -----------------------------
def load_devices(path="devices.json"):
    with open(path, "r") as f:
        return json.load(f)

DEVICES = load_devices()

# -----------------------------
# ChirpStack REST API
# -----------------------------
def get_gateway_rx(start, end):
    """게이트웨이 전체 수신 패킷 수"""
    url = f"{API_BASE}/gateways/{GATEWAY_ID}/metrics"
    params = {"start": start, "end": end, "aggregation": "HOUR"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    return sum(data["rxPackets"]["datasets"][0]["data"])

def get_device_rx(dev_eui, start, end):
    """디바이스별 수신 패킷 수"""
    url = f"{API_BASE}/devices/{dev_eui}/link-metrics"
    params = {"start": start, "end": end, "aggregation": "HOUR"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    datasets = r.json().get("rxPackets", {}).get("datasets", [])
    return sum(datasets[0]["data"]) if datasets else 0

# -----------------------------
# SQLite
# -----------------------------
def get_db_counts(start, end):
    """SQLite raw_logs에서 devEUI별 패킷 카운트"""
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    query = """
        SELECT substr(topic, instr(topic, 'device/')+7, 16) AS devEUI,
               COUNT(*) AS packet_count
        FROM raw_logs
        WHERE received_at BETWEEN ? AND ?
        GROUP BY devEUI
    """
    cur.execute(query, (start, end))
    results = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return results

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare ChirpStack metrics vs DB logs")
    parser.add_argument("--start", help="Start time (UTC, ISO8601, e.g. 2025-10-02T00:00:00Z)")
    parser.add_argument("--end", help="End time (UTC, ISO8601, e.g. 2025-10-02T23:59:59Z)")
    args = parser.parse_args()

    # 시간 범위 기본값 (최근 6시간)
    if args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=6)
        start_str = start.isoformat().replace("+00:00", "Z")
        end_str = end.isoformat().replace("+00:00", "Z")

    # SQLite 포맷 변환
    def to_sqlite_fmt(s: str):
        return s.replace("T", " ").replace("Z", "")

    db_start, db_end = to_sqlite_fmt(start_str), to_sqlite_fmt(end_str)

    # Interval
    print(f"\n=== Interval ===")
    print(f"UTC: {start_str} ~ {end_str}")
    print(f"KST: {(datetime.fromisoformat(start_str.replace('Z',''))+timedelta(hours=9))} ~ "
          f"{(datetime.fromisoformat(end_str.replace('Z',''))+timedelta(hours=9))}")

    # Gateway total
    gw_total = get_gateway_rx(start_str, end_str)
    print(f"\n=== Gateway total uplinks: {gw_total}")

    # Device totals (API)
    device_total = 0
    api_counts = {}
    print(f"\n=== Device uplinks (link-metrics API) ===")
    for d in DEVICES:
        dev_eui, name = d["devEui"], d["name"]
        count = get_device_rx(dev_eui, start_str, end_str)
        api_counts[dev_eui] = count
        device_total += count
        print(f"{name:12s} ({dev_eui}): {count}")
    print(f"\nDevices total uplinks: {device_total}")
    print(f"Difference (Gateway - Devices) = {gw_total - device_total}")

    # DB totals
    db_counts = get_db_counts(db_start, db_end)
    db_total = sum(db_counts.values())
    print(f"\n=== Device uplinks (SQLite raw_logs) ===")
    for d in DEVICES:
        dev_eui, name = d["devEui"], d["name"]
        print(f"{name:12s} ({dev_eui}): {db_counts.get(dev_eui, 0)}")
    print(f"\nDB total uplinks: {db_total}")
    print(f"Difference (Gateway - DB) = {gw_total - db_total}")
    print(f"Difference (Devices API - DB) = {device_total - db_total}")
