import sqlite3
import requests
import time
import json
import base64
import os
from datetime import datetime, timezone

# ===============================
# Config
# ===============================
SENSOR_DB_PATH = "/mnt/nvme/infra/sqlite/sensor_logs.db"
SCALE_DB_PATH  = "/mnt/nvme/infra/sqlite/scale_logs.db"

API_URL = "http://43.201.233.103/api/ingest/normalized"
API_KEY = "changeme"

BATCH_SIZE = 50
SLEEP_SEC = 3
REQUEST_TIMEOUT = 5


# ===============================
# Helpers
# ===============================
def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_ts(ts):
    if ts is None:
        return None
    return ts.replace("Z", "+00:00")


# ===============================
# LHT65N Decoder
# ===============================
def decode_lht65n(data_b64: str):
    raw = base64.b64decode(data_b64)

    # LHT65N payload (confirmed from your samples)
    temp = ((raw[0] << 8) | raw[1]) / 100
    hum  = ((raw[2] << 8) | raw[3]) / 100
    bat  = (raw[4] << 8) | raw[5]

    if bat >= 3000:
        status = "GOOD"
    elif bat >= 2700:
        status = "OK"
    elif bat >= 2400:
        status = "LOW"
    else:
        status = "ULTRA_LOW"

    return temp, hum, bat, status


def decode_scale(data_b64: str):
    raw = base64.b64decode(data_b64)
    # scale payload: single signed byte / example "ViI="
    return raw[0]


# ===============================
# Normalize Builders
# ===============================
def build_env_event(row):
    payload = json.loads(row["payload"])
    rx = payload["rxInfo"][0]

    temp, hum, bat, bat_status = decode_lht65n(payload["data"])

    return {
        "type": "env",
        "event_time": payload["time"],
        "edge_ingest_time": row["received_at"],

        "deduplication_id": payload["deduplicationId"],

        "tenant_id": payload["deviceInfo"]["tenantId"],
        "tenant_name": payload["deviceInfo"]["tenantName"],

        "application_id": payload["deviceInfo"]["applicationId"],
        "application_name": payload["deviceInfo"]["applicationName"],

        "device_profile_id": payload["deviceInfo"]["deviceProfileId"],
        "device_profile_name": payload["deviceInfo"]["deviceProfileName"],

        "device_name": payload["deviceInfo"]["deviceName"],
        "dev_eui": payload["deviceInfo"]["devEui"],
        "dev_addr": payload.get("devAddr"),
        "device_class": payload["deviceInfo"]["deviceClassEnabled"],

        "temperature": temp,
        "humidity": hum,
        "battery_mv": bat,
        "battery_status": bat_status,

        "f_cnt": payload.get("fCnt"),
        "f_port": payload.get("fPort"),
        "adr": payload.get("adr"),
        "dr": payload.get("dr"),
        "confirmed": payload.get("confirmed"),

        "gateway_id": rx.get("gatewayId"),
        "uplink_id": rx.get("uplinkId"),
        "rssi": rx.get("rssi"),
        "snr": rx.get("snr"),
        "crc_status": rx.get("crcStatus"),

        "network_time": rx.get("nsTime"),
        "gateway_time": rx.get("gwTime"),

        "frequency": payload["txInfo"]["frequency"],
        "bandwidth": payload["txInfo"]["modulation"]["lora"]["bandwidth"],
        "spreading_factor": payload["txInfo"]["modulation"]["lora"]["spreadingFactor"],
        "code_rate": payload["txInfo"]["modulation"]["lora"]["codeRate"],
        "region_config_id": payload.get("regionConfigId"),
    }


def build_scale_event(row):
    payload = json.loads(row["payload"])
    rx = payload["rxInfo"][0]

    weight = decode_scale(payload["data"])

    return {
        "type": "scale",
        "event_time": payload["time"],
        "edge_ingest_time": row["received_at"],

        "deduplication_id": payload["deduplicationId"],

        "tenant_id": payload["deviceInfo"]["tenantId"],
        "tenant_name": payload["deviceInfo"]["tenantName"],

        "application_id": payload["deviceInfo"]["applicationId"],
        "application_name": payload["deviceInfo"]["applicationName"],

        "device_profile_id": payload["deviceInfo"]["deviceProfileId"],
        "device_profile_name": payload["deviceInfo"]["deviceProfileName"],

        "device_name": payload["deviceInfo"]["deviceName"],
        "dev_eui": payload["deviceInfo"]["devEui"],
        "dev_addr": payload.get("devAddr"),
        "device_class": payload["deviceInfo"]["deviceClassEnabled"],

        "weight": weight,

        "f_cnt": payload.get("fCnt"),
        "f_port": payload.get("fPort"),
        "adr": payload.get("adr"),
        "dr": payload.get("dr"),
        "confirmed": payload.get("confirmed"),

        "gateway_id": rx.get("gatewayId"),
        "uplink_id": rx.get("uplinkId"),
        "rssi": rx.get("rssi"),
        "snr": rx.get("snr"),
        "crc_status": rx.get("crcStatus"),

        "network_time": rx.get("nsTime"),
        "gateway_time": rx.get("gwTime"),

        "frequency": payload["txInfo"]["frequency"],
        "bandwidth": payload["txInfo"]["modulation"]["lora"]["bandwidth"],
        "spreading_factor": payload["txInfo"]["modulation"]["lora"]["spreadingFactor"],
        "code_rate": payload["txInfo"]["modulation"]["lora"]["codeRate"],
        "region_config_id": payload.get("regionConfigId"),
    }


# ===============================
# Sender Core
# ===============================
def process_db(db_path, builder):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, received_at, payload
        FROM raw_logs
        WHERE uploaded = 0
        ORDER BY received_at
        LIMIT ?
        """,
        (BATCH_SIZE,)
    ).fetchall()

    for row in rows:
        event = builder(row)

        r = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            data=json.dumps(event),
            timeout=REQUEST_TIMEOUT,
        )

        if r.status_code == 200:
            cur.execute(
                "UPDATE raw_logs SET uploaded = 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
        else:
            print("Upload failed:", r.status_code, r.text)
            break

    conn.close()


# ===============================
# Main Loop
# ===============================
def main():
    while True:
        try:
            process_db(SENSOR_DB_PATH, build_env_event)
            process_db(SCALE_DB_PATH, build_scale_event)
        except Exception as e:
            print("Sender error:", e)

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
