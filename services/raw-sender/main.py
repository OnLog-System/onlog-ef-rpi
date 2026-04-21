from fastapi import FastAPI, Header, HTTPException, Request
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values
import os
import logging

# =================================================
# Config
# =================================================
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

# =================================================
# Logging
# =================================================
os.makedirs("/logs", exist_ok=True)

logging.basicConfig(
    filename="/logs/api.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# =================================================
# FastAPI
# =================================================
app = FastAPI()


def get_conn():
    return psycopg2.connect(DATABASE_URL)


@app.get("/health")
def health():
    return {"status": "ok"}


# =================================================
# Bulk SQL
# =================================================
ENV_COLUMNS = [
    "event_time", "network_time", "gateway_time", "edge_ingest_time",
    "deduplication_id", "tenant_id", "tenant_name",
    "application_id", "application_name",
    "device_profile_id", "device_profile_name",
    "device_name", "dev_eui", "dev_addr", "device_class",
    "temperature", "humidity", "battery_mv", "battery_status",
    "f_cnt", "f_port", "adr", "dr", "confirmed",
    "gateway_id", "uplink_id", "rssi", "snr", "crc_status",
    "frequency", "bandwidth", "spreading_factor", "code_rate", "region_config_id"
]

SCALE_COLUMNS = [
    "event_time", "network_time", "gateway_time", "edge_ingest_time",
    "deduplication_id", "tenant_id", "tenant_name",
    "application_id", "application_name",
    "device_profile_id", "device_profile_name",
    "device_name", "dev_eui", "dev_addr", "device_class",
    "weight",
    "f_cnt", "f_port", "adr", "dr", "confirmed",
    "gateway_id", "uplink_id", "rssi", "snr", "crc_status",
    "frequency", "bandwidth", "spreading_factor", "code_rate", "region_config_id"
]

EVENT_COLUMNS = [
    "event_time", "edge_ingest_time", "event_type", "topic",
    "tenant_id", "tenant_name",
    "application_id", "application_name",
    "device_name", "dev_eui", "payload"
]


def tuple_from_payload(payload, columns):
    row = []
    for col in columns:
        val = payload.get(col)
        if col == "payload" and val is not None:
            val = psycopg2.extras.Json(val)
        row.append(val)
    return tuple(row)


def bulk_insert_env(cur, payloads):
    values = [tuple_from_payload(p, ENV_COLUMNS) for p in payloads]
    sql = f"""
    INSERT INTO raw.sensor_env ({", ".join(ENV_COLUMNS)})
    VALUES %s
    ON CONFLICT (deduplication_id, event_time) DO NOTHING
    """
    execute_values(cur, sql, values, page_size=1000)


def bulk_insert_scale(cur, payloads):
    values = [tuple_from_payload(p, SCALE_COLUMNS) for p in payloads]
    sql = f"""
    INSERT INTO raw.sensor_scale ({", ".join(SCALE_COLUMNS)})
    VALUES %s
    ON CONFLICT (deduplication_id, event_time) DO NOTHING
    """
    execute_values(cur, sql, values, page_size=1000)


def bulk_insert_event(cur, payloads):
    values = [tuple_from_payload(p, EVENT_COLUMNS) for p in payloads]
    sql = f"""
    INSERT INTO raw.device_events ({", ".join(EVENT_COLUMNS)})
    VALUES %s
    """
    execute_values(cur, sql, values, page_size=1000)


# =================================================
# Ingest API
# =================================================
@app.post("/api/ingest/normalized")
async def ingest_raw(
    request: Request,
    x_api_key: str = Header(None),
):
    if x_api_key != API_KEY:
        logging.warning("Unauthorized request from %s", request.client.host)
        raise HTTPException(status_code=401, detail="invalid api key")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    if isinstance(body, dict):
        payloads = [body]
    elif isinstance(body, list):
        payloads = body
    else:
        raise HTTPException(status_code=400, detail="json must be object or array")

    if not payloads:
        return {"status": "stored", "count": 0}

    env_payloads = []
    scale_payloads = []
    event_payloads = []

    for payload in payloads:
        event_type = payload.get("type")

        if event_type == "env":
            env_payloads.append(payload)
        elif event_type == "scale":
            scale_payloads.append(payload)
        elif event_type == "event":
            event_payloads.append(payload)
        else:
            raise HTTPException(status_code=400, detail=f"unknown event type: {event_type}")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if env_payloads:
            bulk_insert_env(cur, env_payloads)

        if scale_payloads:
            bulk_insert_scale(cur, scale_payloads)

        if event_payloads:
            bulk_insert_event(cur, event_payloads)

        conn.commit()
        cur.close()
        conn.close()

        logging.info(
            "Ingested batch | env=%d scale=%d event=%d total=%d",
            len(env_payloads),
            len(scale_payloads),
            len(event_payloads),
            len(payloads),
        )

        return {
            "status": "stored",
            "env": len(env_payloads),
            "scale": len(scale_payloads),
            "event": len(event_payloads),
            "total": len(payloads),
        }

    except Exception as e:
        logging.exception("DB insert failed")
        print("ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))