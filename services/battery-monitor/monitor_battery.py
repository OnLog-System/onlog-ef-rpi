import sqlite3
import base64
import sys
import json
from datetime import datetime
from pathlib import Path

# ===============================
# 1️⃣ DB & DEVICE 설정
# ===============================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = "/mnt/nvme/infra/sqlite/sensor_logs.db"
DEVICES_FILE = BASE_DIR / "devices.json"

V_MIN = 2500  # 2.5 V
V_MAX = 3000  # 3.0 V


def load_devices():
    """devices.json 로드"""
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            devices = json.load(f)
        return {f"{i+1:02d}": d["devEui"] for i, d in enumerate(devices)}
    except Exception as e:
        print(f"[에러] devices.json 로드 실패: {e}")
        sys.exit(1)


# ===============================
# 2️⃣ 배터리 디코딩 함수
# ===============================
def decode_battery(base64_str):
    data = base64.b64decode(base64_str)
    bat_raw = int.from_bytes(data[:2], "big")
    status_code = (bat_raw >> 14) & 0x03
    voltage_mv = bat_raw & 0x3FFF

    status = {
        0b00: "Ultra-Low",
        0b01: "Low",
        0b10: "OK",
        0b11: "Good",
    }.get(status_code, "Unknown")

    percent = max(0, min(100, int((voltage_mv - V_MIN) / (V_MAX - V_MIN) * 100)))
    return f"0x{bat_raw:04X}", voltage_mv, percent, status


# ===============================
# 3️⃣ SQLite 쿼리 함수
# ===============================
def fetch_payloads(dev_eui):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
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
        """,
        (dev_eui,),
    )
    return cur.fetchall()


# ===============================
# 4️⃣ 실행부
# ===============================
def main():
    devices = load_devices()

    if len(sys.argv) < 2:
        print("사용법: python3 monitor_battery.py <센서번호>")
        print("예시:   python3 monitor_battery.py 05")
        return

    sensor_id = sys.argv[1].zfill(2)
    if sensor_id not in devices:
        print(f"[에러] 존재하지 않는 센서 번호: {sensor_id}")
        print("가능한 센서:", ", ".join(devices.keys()))
        return

    dev_eui = devices[sensor_id]
    print(f"\n📡 센서 {sensor_id} | DevEUI: {dev_eui}\n")

    rows = fetch_payloads(dev_eui)
    if not rows:
        print("❌ 데이터가 없습니다.")
        return

    print(f"{'일자':<12} {'Payload(Base64)':<24} {'Hex(BAT)':<10} {'전압(mV)':<10} {'배터리(%)':<10} {'상태'}")
    print("-" * 80)

    for day, ts, payload in rows:
        hex_bat, voltage, percent, status = decode_battery(payload)
        print(f"{day:<12} {payload:<24} {hex_bat:<10} {voltage:<10} {percent:<10} {status}")


if __name__ == "__main__":
    main()
