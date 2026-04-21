from fastapi import FastAPI, Header, HTTPException, Request
import psycopg2
import psycopg2.extras
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
# SQL
# =================================================
SQL_INSERT_ENV = """
INSERT INTO raw.sensor_env (
  event_time,
  network_time,
  gateway_time,
  edge_ingest_time,
  deduplication_id,
  tenant_id,
  tenant_name,
  application_id,
  application_name,
  device_profile_id,
  device_profile_name,
  device_name,
  dev_eui,
  dev_addr,
  device_class,
  temperature,
  humidity,
  battery_mv,
  battery_status,
  f_cnt,
  f_port,
  adr,
  dr,
  confirmed,
  gateway_id,
  uplink_id,
  rssi,
  snr,
  crc_status,
  frequency,
  bandwidth,
  spreading_factor,
  code_rate,
  region_config_id
)
VALUES (
  %(event_time)s,
  %(network_time)s,
  %(gateway_time)s,
  %(edge_ingest_time)s,
  %(deduplication_id)s,
  %(tenant_id)s,
  %(tenant_name)s,
  %(application_id)s,
  %(application_name)s,
  %(device_profile_id)s,
  %(device_profile_name)s,
  %(device_name)s,
  %(dev_eui)s,
  %(dev_addr)s,
  %(device_class)s,
  %(temperature)s,
  %(humidity)s,
  %(battery_mv)s,
  %(battery_status)s,
  %(f_cnt)s,
  %(f_port)s,
  %(adr)s,
  %(dr)s,
  %(confirmed)s,
  %(gateway_id)s,
  %(uplink_id)s,
  %(rssi)s,
  %(snr)s,
  %(crc_status)s,
  %(frequency)s,
  %(bandwidth)s,
  %(spreading_factor)s,
  %(code_rate)s,
  %(region_config_id)s
)
ON CONFLICT (deduplication_id, event_time) DO NOTHING
"""

SQL_INSERT_SCALE = """
INSERT INTO raw.sensor_scale (
  event_time,
  network_time,
  gateway_time,
  edge_ingest_time,
  deduplication_id,
  tenant_id,
  tenant_name,
  application_id,
  application_name,
  device_profile_id,
  device_profile_name,
  device_name,
  dev_eui,
  dev_addr,
  device_class,
  weight,
  f_cnt,
  f_port,
  adr,
  dr,
  confirmed,
  gateway_id,
  uplink_id,
  rssi,
  snr,
  crc_status,
  frequency,
  bandwidth,
  spreading_factor,
  code_rate,
  region_config_id
)
VALUES (
  %(event_time)s,
  %(network_time)s,
  %(gateway_time)s,
  %(edge_ingest_time)s,
  %(deduplication_id)s,
  %(tenant_id)s,
  %(tenant_name)s,
  %(application_id)s,
  %(application_name)s,
  %(device_profile_id)s,
  %(device_profile_name)s,
  %(device_name)s,
  %(dev_eui)s,
  %(dev_addr)s,
  %(device_class)s,
  %(weight)s,
  %(f_cnt)s,
  %(f_port)s,
  %(adr)s,
  %(dr)s,
  %(confirmed)s,
  %(gateway_id)s,
  %(uplink_id)s,
  %(rssi)s,
  %(snr)s,
  %(crc_status)s,
  %(frequency)s,
  %(bandwidth)s,
  %(spreading_factor)s,
  %(code_rate)s,
  %(region_config_id)s
)
ON CONFLICT (deduplication_id, event_time) DO NOTHING
"""

SQL_INSERT_EVENT = """
INSERT INTO raw.device_events (
  event_time,
  edge_ingest_time,
  event_type,
  topic,
  tenant_id,
  tenant_name,
  application_id,
  application_name,
  device_name,
  dev_eui,
  payload
)
VALUES (
  %(event_time)s,
  %(edge_ingest_time)s,
  %(event_type)s,
  %(topic)s,
  %(tenant_id)s,
  %(tenant_name)s,
  %(application_id)s,
  %(application_name)s,
  %(device_name)s,
  %(dev_eui)s,
  %(payload)s
);
"""


# =================================================
# Ingest API
# =================================================
@app.post("/api/ingest/normalized")
async def ingest_raw(
    request: Request,
    x_api_key: str = Header(None),
):
    # --- API Key ---
    if x_api_key != API_KEY:
        logging.warning("Unauthorized request from %s", request.client.host)
        raise HTTPException(status_code=401, detail="invalid api key")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    event_type = payload.get("type")
    if event_type not in ("env", "scale", "event"):
        raise HTTPException(status_code=400, detail="unknown event type")

    try:
        conn = get_conn()
        cur = conn.cursor()

        if event_type == "env":
            cur.execute(SQL_INSERT_ENV, payload)
        elif event_type == "scale":
            cur.execute(SQL_INSERT_SCALE, payload)
        elif event_type == "event":
            payload["payload"] = psycopg2.extras.Json(payload["payload"])
            cur.execute(SQL_INSERT_EVENT, payload)

        conn.commit()
        cur.close()
        conn.close()

        logging.info(
            "Ingested %s | dev_eui=%s | event_time=%s",
            event_type,
            payload.get("dev_eui"),
            payload.get("event_time"),
        )

        return {"status": "stored"}

    except Exception as e:
        logging.exception(f"DB insert failed | payload={payload}")
        print("ERROR PAYLOAD:", payload)
        print("ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))