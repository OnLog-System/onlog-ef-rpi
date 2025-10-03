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

DEVICES = [
    ("a84041f3275da38b", "EF-LHT65N-01"),
    ("a840419f755da38c", "EF-LHT65N-02"),
    ("a84041949e5da381", "EF-LHT65N-03"),
    ("a8404166815da382", "EF-LHT65N-04"),
    ("a840412db25da383", "EF-LHT65N-05"),
    ("a84041f6e55da385", "EF-LHT65N-06"),
    ("a84041f65a5da384", "EF-LHT65N-07"),
    ("a8404133545da38a", "EF-LHT65N-08"),
    ("a84041bb5f5da389", "EF-LHT65N-09"),
    ("a8404166bf5da388", "EF-LHT65N-10"),
    ("a840419f4f5da386", "EF-LHT65N-11"),
    ("a84041e0055da387", "EF-LHT65N-12"),
]

# -----------------------------
# REST API
# -----------------------------
def get_gateway_rx(start, end):
    url = f"{API_BASE}/gateways/{GATEWAY_ID}/metrics?start={start}&end={end}&aggregation=HOUR"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    return sum(r.json()["rxPackets"]["datasets"][0]["data"])

def get_device_rx(dev_eui, start, end):
    url = f"{API_BASE}/devices/{dev_eui}/link-metrics?start={start}&end={end}&aggregation=HOUR"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    datasets = r.json()["rxPackets"]["datasets"]
    return sum(datasets[0]["data"]) if datasets else 0

# -----------------------------
# SQLite
# -----------------------------
def get_db_counts(start, end):
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT substr(topic, instr(topic, 'device/')+7, 16) AS devEUI,
               COUNT(*) AS packet_count
        FROM raw_logs
        WHERE received_at BETWEEN ? AND ?
        GROUP BY devEUI
    """, (start, end))
    results = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return results

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="Start time (ISO8601, e.g. 2025-10-02T00:00:00Z)")
    parser.add_argument("--end", help="End time (ISO8601, e.g. 2025-10-02T23:59:59Z)")
    args = parser.parse_args()

    if args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=6)
        start_str, end_str = start.isoformat().replace("+00:00","Z"), end.isoformat().replace("+00:00","Z")

    # SQLite용 포맷 변환
    def to_sqlite_fmt(s: str):
        return s.replace("T", " ").replace("Z", "")

    db_start, db_end = to_sqlite_fmt(start_str), to_sqlite_fmt(end_str)

    print(f"\n=== Interval ===")
    print(f"UTC: {start_str} ~ {end_str}")
    print(f"KST: {(datetime.fromisoformat(start_str.replace('Z',''))+timedelta(hours=9)).isoformat()} ~ "
          f"{(datetime.fromisoformat(end_str.replace('Z',''))+timedelta(hours=9)).isoformat()}")

    # Gateway total
    gw_total = get_gateway_rx(start_str, end_str)
    print(f"\n=== Gateway total uplinks: {gw_total}")

    # Device totals (API)
    device_total = 0
    print(f"\n=== Device uplinks (link-metrics API) ===")
    api_counts = {}
    for dev_eui, name in DEVICES:
        count = get_device_rx(dev_eui, start_str, end_str)
        api_counts[dev_eui] = count
        device_total += count
        print(f"{name:12s} ({dev_eui}): {count}")
    print(f"\nDevices total uplinks: {device_total}")
    print(f"Difference (gateway - devices) = {gw_total - device_total}")

    # DB totals
    db_counts = get_db_counts(db_start, db_end)
    db_total = sum(db_counts.values())
    print(f"\n=== Device uplinks (SQLite raw_logs) ===")
    for dev_eui, name in DEVICES:
        count = db_counts.get(dev_eui, 0)
        print(f"{name:12s} ({dev_eui}): {count}")
    print(f"\nDB total uplinks: {db_total}")
    print(f"Difference (gateway - DB) = {gw_total - db_total}")
    print(f"Difference (devices API - DB) = {device_total - db_total}")