import sqlite3, base64, csv
from datetime import datetime

DB_PATH = "raw_logs.db"
DEVICE_EUI = "a840412db25da383"

def decode_battery(base64_str):
    data = base64.b64decode(base64_str)
    bat_raw = int.from_bytes(data[:2], 'big')
    status_code = (bat_raw >> 14) & 0x03
    voltage_mv = bat_raw & 0x3FFF
    status = {0: "Ultra-Low", 1: "Low", 2: "OK", 3: "Good"}[status_code]
    return f"0x{bat_raw:04X}", voltage_mv, status

def fetch_payloads():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        WITH daily_ranked AS (
          SELECT
            strftime('%Y-%m-%d', received_at) AS day,
            received_at,
            json_extract(payload, '$.data') AS data,
            ROW_NUMBER() OVER (
              PARTITION BY strftime('%Y-%m-%d', received_at)
              ORDER BY received_at DESC
            ) AS rn
          FROM raw_logs
          WHERE topic LIKE '%/event/up'
            AND json_extract(payload, '$.deviceInfo.devEui') = ?
        )
        SELECT day, received_at, data
        FROM daily_ranked
        WHERE rn = 1
        ORDER BY day DESC;
    """, (DEVICE_EUI,))
    return cur.fetchall()

def main():
    rows = fetch_payloads()
    output = []
    for day, ts, payload in rows:
        hex_bat, voltage, status = decode_battery(payload)
        output.append((day, payload, hex_bat, voltage, status))
        print(f"{day} | {payload} | {hex_bat} | {voltage} mV | {status}")

    # CSV 저장
    with open("battery_monitor.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "payload", "hex_bat", "voltage_mV", "status"])
        writer.writerows(output)

if __name__ == "__main__":
    main()
