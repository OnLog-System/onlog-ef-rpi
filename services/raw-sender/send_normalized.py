import sqlite3
import requests
import time
import json
import base64
import os

# ===============================
# Env / Config
# ===============================
SENSOR_DB_PATH = os.getenv("SENSOR_DB_PATH", "/data/sensor_logs.db")
SCALE_DB_PATH  = os.getenv("SCALE_DB_PATH", "/data/scale_logs.db")

API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")

CURSOR_ENV_PATH   = "/data/cursor_env.txt"
CURSOR_SCALE_PATH = "/data/cursor_scale.txt"

TIMEOUT = 5
IDLE_SLEEP = 1


# ===============================
# Cursor
# ===============================
def load_cursor(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r") as f:
        return int(f.read().strip())


def save_cursor(path, value):
    with open(path, "w") as f:
        f.write(str(value))


# ===============================
# Decoder
# ===============================
def decode_lht65n(data_b64):
    if not data_b64:
        return None
    try:
        data = base64.b64decode(data_b64)
    except:
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


def decode_scale(data_b64):
    try:
        data = base64.b64decode(data_b64)
        return data[0]
    except:
        return None


# ===============================
# Normalize
# ===============================
def normalize_env(row):
    try:
        payload = json.loads(row["payload"])

        rx_list = payload.get("rxInfo")
        if not rx_list:
            return None

        rx = rx_list[0]

        decoded = decode_lht65n(payload.get("data"))
        if decoded is None:
            return None

        temperature, humidity, battery_mv, battery_status = decoded

        return {
            "type": "env",
            "event_time": payload.get("time"),
            "edge_ingest_time": row["received_at"],
            "network_time": rx.get("nsTime"),
            "gateway_time": rx.get("gwTime"),
            "deduplication_id": payload.get("deduplicationId"),
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

    except Exception as e:
        print("normalize_env error:", e)
        return None


def normalize_scale(row):
    try:
        payload = json.loads(row["payload"])

        rx_list = payload.get("rxInfo")
        if not rx_list:
            return None

        rx = rx_list[0]

        weight = decode_scale(payload.get("data"))
        if weight is None:
            return None

        return {
            "type": "scale",
            "event_time": payload.get("time"),
            "edge_ingest_time": row["received_at"],
            "network_time": rx.get("nsTime"),
            "gateway_time": rx.get("gwTime"),
            "deduplication_id": payload.get("deduplicationId"),
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

    except Exception as e:
        print("normalize_scale error:", e)
        return None


def normalize_event(row):
    try:
        payload = json.loads(row["payload"])
        device_info = payload.get("deviceInfo", {})

        return {
            "type": "event",
            "event_type": row["topic"].split("/")[-1],
            "topic": row["topic"],
            "event_time": payload.get("time"),
            "edge_ingest_time": row["received_at"],
            "tenant_id": device_info.get("tenantId"),
            "tenant_name": device_info.get("tenantName"),
            "application_id": device_info.get("applicationId"),
            "application_name": device_info.get("applicationName"),
            "device_name": device_info.get("deviceName"),
            "dev_eui": device_info.get("devEui"),
            "payload": payload
        }

    except Exception as e:
        print("normalize_event error:", e)
        return None


# ===============================
# Core loop
# ===============================
def process_one(db_path, cursor_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cursor = load_cursor(cursor_path)

    rows = cur.execute(
        """
        SELECT id, received_at, payload, topic
        FROM raw_logs
        WHERE id > ?
        ORDER BY id
        LIMIT 100
        """,
        (cursor,),
    ).fetchall()

    if not rows:
        conn.close()
        return False

    last_success_id = cursor

    for row in rows:
        topic = row["topic"]

        if topic.endswith("/event/up"):
            event = normalize_env(row)
        else:
            event = normalize_event(row)

        if event is None:
            last_success_id = row["id"]
            continue

        try:
            r = requests.post(
                API_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY,
                },
                json=event,
                timeout=TIMEOUT,
            )
        except Exception as e:
            print("request error:", e)
            break

        if r.status_code == 200:
            last_success_id = row["id"]
        else:
            print("upload failed:", r.status_code)
            break

    save_cursor(cursor_path, last_success_id)
    conn.close()
    return True


def main():
    print("sender started")

    while True:
        progressed = False

        if process_one(SENSOR_DB_PATH, CURSOR_ENV_PATH):
            progressed = True

        if process_one(SCALE_DB_PATH, CURSOR_SCALE_PATH):
            progressed = True

        if not progressed:
            time.sleep(IDLE_SLEEP)


if __name__ == "__main__":
    main()