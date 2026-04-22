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

TIMEOUT = 10
IDLE_SLEEP = 0.2
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))


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


def decode_scale(data_b64):
    try:
        data = base64.b64decode(data_b64)
        return data[0]
    except Exception:
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
        device_info = payload.get("deviceInfo", {})
        tx_info = payload.get("txInfo", {})
        lora = tx_info.get("modulation", {}).get("lora", {})

        return {
            "type": "env",
            "event_time": payload.get("time"),
            "edge_ingest_time": row["received_at"],
            "network_time": rx.get("nsTime"),
            "gateway_time": rx.get("gwTime"),
            "deduplication_id": payload.get("deduplicationId"),
            "tenant_id": device_info.get("tenantId"),
            "tenant_name": device_info.get("tenantName"),
            "application_id": device_info.get("applicationId"),
            "application_name": device_info.get("applicationName"),
            "device_profile_id": device_info.get("deviceProfileId"),
            "device_profile_name": device_info.get("deviceProfileName"),
            "device_name": device_info.get("deviceName"),
            "dev_eui": device_info.get("devEui"),
            "dev_addr": payload.get("devAddr"),
            "device_class": device_info.get("deviceClassEnabled"),
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
            "frequency": tx_info.get("frequency"),
            "bandwidth": lora.get("bandwidth"),
            "spreading_factor": lora.get("spreadingFactor"),
            "code_rate": lora.get("codeRate"),
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

        device_info = payload.get("deviceInfo", {})
        tx_info = payload.get("txInfo", {})
        lora = tx_info.get("modulation", {}).get("lora", {})

        return {
            "type": "scale",
            "event_time": payload.get("time"),
            "edge_ingest_time": row["received_at"],
            "network_time": rx.get("nsTime"),
            "gateway_time": rx.get("gwTime"),
            "deduplication_id": payload.get("deduplicationId"),
            "tenant_id": device_info.get("tenantId"),
            "tenant_name": device_info.get("tenantName"),
            "application_id": device_info.get("applicationId"),
            "application_name": device_info.get("applicationName"),
            "device_profile_id": device_info.get("deviceProfileId"),
            "device_profile_name": device_info.get("deviceProfileName"),
            "device_name": device_info.get("deviceName"),
            "dev_eui": device_info.get("devEui"),
            "dev_addr": payload.get("devAddr"),
            "device_class": device_info.get("deviceClassEnabled"),
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
            "frequency": tx_info.get("frequency"),
            "bandwidth": lora.get("bandwidth"),
            "spreading_factor": lora.get("spreadingFactor"),
            "code_rate": lora.get("codeRate"),
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
            "payload": payload,
        }

    except Exception as e:
        print("normalize_event error:", e)
        return None


# ===============================
# Batch sender
# ===============================
def process_batch(db_path, cursor_path):
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
        LIMIT ?
        """,
        (cursor, BATCH_SIZE),
    ).fetchall()

    if not rows:
        conn.close()
        return False

    events = []
    last_row_id = cursor

    for row in rows:
        topic = row["topic"]

        if topic.endswith("/event/up"):
            # scale DB도 /event/up일 수 있으므로 payload 특성으로 구분
            payload = json.loads(row["payload"])
            app_name = payload.get("deviceInfo", {}).get("applicationName", "")
            if "scale" in app_name.lower():
                event = normalize_scale(row)
            else:
                event = normalize_env(row)
        else:
            event = normalize_event(row)

        last_row_id = row["id"]

        if event is None:
            continue

        events.append(event)

    # 유효 이벤트가 하나도 없어도 cursor는 전진
    if not events:
        save_cursor(cursor_path, last_row_id)
        conn.close()
        return True

    try:
        r = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            json=events,
            timeout=TIMEOUT,
        )
    except Exception as e:
        print("request error:", e)
        conn.close()
        return False

    if r.status_code == 200:
        save_cursor(cursor_path, last_row_id)
        conn.close()
        return True

    print("upload failed:", r.status_code, r.text)
    conn.close()
    return False


def main():
    print("sender started")

    while True:
        progressed = False

        if process_batch(SENSOR_DB_PATH, CURSOR_ENV_PATH):
            progressed = True

        if process_batch(SCALE_DB_PATH, CURSOR_SCALE_PATH):
            progressed = True

        if not progressed:
            time.sleep(IDLE_SLEEP)


if __name__ == "__main__":
    main()