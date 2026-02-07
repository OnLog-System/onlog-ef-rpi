import sqlite3
import requests
import time
import json
import base64
import os
from datetime import datetime, timezone

# ===============================
# Env / Config
# ===============================
SENSOR_DB_PATH = os.getenv("SENSOR_DB_PATH", "/data/sensor_logs.db")
SCALE_DB_PATH  = os.getenv("SCALE_DB_PATH", "/data/scale_logs.db")

API_URL = os.getenv("API_URL", "http://43.201.233.103/api/ingest/normalized")
API_KEY = os.getenv("API_KEY", "changeme")

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
SLEEP_SEC  = int(os.getenv("SLEEP_SEC", "5"))
TIMEOUT    = 5


# ===============================
# Decoder (Java parity)
# ===============================
def decode_lht65n(data_b64: str):
    if not data_b64:
        return None

    try:
        data = base64.b64decode(data_b64)
    except Exception:
        return None

    if len(data) < 6:
        return None

    bat_raw = ((data[0] & 0xFF) << 8) | (data[1] & 0xFF)
    status_bits = (bat_raw >> 14) & 0b11
    battery_mv = bat_raw & 0x3FFF

    battery_status = {
        0b00: "ULTRA_LOW",
        0b01: "LOW",
        0b10: "OK",
        0b11: "GOOD",
    }.get(status_bits, "UNKNOWN")

    temp_raw = (data[2] << 8) | data[3]
    if temp_raw & 0x8000:
        temp_raw -= 0x10000
    temperature = temp_raw / 100.0

    hum_raw = ((data[4] & 0xFF) << 8) | (data[5] & 0xFF)
    humidity = hum_raw / 10.0

    return temperature, humidity, battery_mv, battery_status


def decode_scale(data_b64: str):
    try:
        data = base64.b64decode(data_b64)
        return data[0]
    except Exception:
        return None


# ===============================
# Normalizers
# ===============================
def normalize_env(row):
    payload = json.loads(row["payload"])
    rx = payload["rxInfo"][0]

    decoded = decode_lht65n(payload.get("data"))
    if decoded is None:
        return None

    temperature, humidity, battery_mv, battery_status = decoded

    return {
        "type": "env",

        "event_time": payload["time"],
        "edge_ingest_time": row["received_at"],

        "network_time": rx.get("nsTime"),
        "gateway_time": rx.get("gwTime"),

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

        "temperature": temperature,
        "humidity": humidity,
        "battery_mv": battery_mv,
        "battery_status": battery_status,

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

        "frequency": payload["txInfo"]["frequency"],
        "bandwidth": payload["txInfo"]["modulation"]["lora"]["bandwidth"],
        "spreading_factor": payload["txInfo"]["modulation"]["lora"]["spreadingFactor"],
        "code_rate": payload["txInfo"]["modulation"]["lora"]["codeRate"],
        "region_config_id": payload.get("regionConfigId"),
    }


def normalize_scale(row):
    payload = json.loads(row["payload"])
    rx = payload["rxInfo"][0]

    weight = decode_scale(payload.get("data"))
    if weight is None:
        return None

    return {
        "type": "scale",

        "event_time": payload["time"],
        "edge_ingest_time": row["received_at"],

        "network_time": rx.get("nsTime"),
        "gateway_time": rx.get("gwTime"),

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

        "frequency": payload["txInfo"]["frequency"],
        "bandwidth": payload["txInfo"]["modulation"]["lora"]["bandwidth"],
        "spreading_factor": payload["txInfo"]["modulation"]["lora"]["spreadingFactor"],
        "code_rate": payload["txInfo"]["modulation"]["lora"]["codeRate"],
        "region_config_id": payload.get("regionConfigId"),
    }


# ===============================
# Sender Core
# ===============================
def process_db(db_path, normalizer):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, received_at, payload
        FROM raw_logs
        WHERE uploaded = 0
          AND received_at >= datetime('now', '-5 minutes')
        ORDER BY received_at
        LIMIT ?
        """,
        (BATCH_SIZE,),
    ).fetchall()

    for row in rows:
        event = normalizer(row)
        if event is None:
            cur.execute(
                "UPDATE raw_logs SET uploaded = 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            continue

        r = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            json=event,
            timeout=TIMEOUT,
        )

        if r.status_code == 200:
            cur.execute(
                "UPDATE raw_logs SET uploaded = 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
        else:
            print("upload failed:", r.status_code, r.text)
            continue

    conn.close()


# ===============================
# Main Loop
# ===============================
def main():
    while True:
        try:
            process_db(SENSOR_DB_PATH, normalize_env)
            process_db(SCALE_DB_PATH, normalize_scale)
        except Exception as e:
            print("sender error:", e)

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
