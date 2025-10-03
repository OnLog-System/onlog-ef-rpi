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

def get_gateway_rx(start, end):
    url = f"{API_BASE}/gateways/{GATEWAY_ID}/metrics?start={start}&end={end}&aggregation=HOUR"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    data = r.json()["rxPackets"]["datasets"][0]["data"]
    return sum(data)

def get_device_rx(dev_eui, start, end):
    url = f"{API_BASE}/devices/{dev_eui}/link-metrics?start={start}&end={end}&aggregation=HOUR"
    r = requests.get(url, headers=HEADERS); r.raise_for_status()
    datasets = r.json()["rxPackets"]["datasets"]
    if datasets:
        return sum(datasets[0]["data"])
    return 0

if __name__ == "__main__":
    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=6)
    start_str, end_str = start.isoformat()+"Z", end.isoformat()+"Z"

    gw_total = get_gateway_rx(start_str, end_str)
    print(f"\n=== Gateway total uplinks: {gw_total}")

    device_total = 0
    for dev_eui, name in DEVICES:
        count = get_device_rx(dev_eui, start_str, end_str)
        device_total += count
        print(f"{name} ({dev_eui}): {count}")

    print(f"\n=== Devices total uplinks: {device_total}")
    diff = gw_total - device_total
    print(f"Difference (gateway - devices) = {diff}")