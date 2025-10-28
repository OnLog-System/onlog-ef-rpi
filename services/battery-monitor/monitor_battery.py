import sqlite3
import base64
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===============================
# 1️⃣ DB & DEVICE 설정
# ===============================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = "/mnt/nvme/infra/sqlite/sensor_logs.db"
DEVICES_FILE = BASE_DIR / "devices.json"

V_MIN = 2500  # 2.5 V
V_MAX = 3000  # 3.0 V
KST = timezone(timedelta(hours=9))  # 한국 시간대


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
    try:
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
    except Exception:
        return "-", 0, 0, "DecodeError"


# ===============================
# 3️⃣ SQLite 쿼리 함수
# ===============================
def fetch_payloads(dev_eui, recent_limit=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if recent_limit:
        # 🔹 최근 n개 레코드 조회
        query = """
            SELECT 
                strftime('%Y-%m-%d', received_at) AS day,
                received_at,
                json_extract(payload, '$.data') AS data
            FROM raw_logs
            WHERE topic LIKE '%/event/up'
              AND json_extract(payload, '$.deviceInfo.devEui') = ?
            ORDER BY received_at DESC
            LIMIT ?;
        """
        cur.execute(query, (dev_eui, recent_limit))
    else:
        # 🔹 일별 최신 1건씩 조회
        query = """
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
        """
        cur.execute(query, (dev_eui,))
    rows = cur.fetchall()
    conn.close()
    return rows


def fetch_latest_for_all(devices):
    """모든 센서의 최신 1건"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    results = []
    for sid, dev_eui in devices.items():
        cur.execute(
            """
            SELECT 
                received_at, json_extract(payload, '$.data') AS data
            FROM raw_logs
            WHERE topic LIKE '%/event/up'
              AND json_extract(payload, '$.deviceInfo.devEui') = ?
            ORDER BY received_at DESC
            LIMIT 1;
            """,
            (dev_eui,),
        )
        row = cur.fetchone()
        if row:
            results.append((sid, dev_eui, *row))
    conn.close()
    return results


# ===============================
# 4️⃣ 실행부
# ===============================
def main():
    devices = load_devices()

    if len(sys.argv) < 2:
        print("사용법:")
        print("  python3 monitor_battery.py <센서번호>")
        print("  python3 monitor_battery.py <센서번호> recent <개수>")
        print("  python3 monitor_battery.py all")
        print("예시:")
        print("  python3 monitor_battery.py 05")
        print("  python3 monitor_battery.py 05 recent 20")
        print("  python3 monitor_battery.py all")
        return

    mode = sys.argv[1].lower()

    # 🔸 all 모드
    if mode == "all":
        print("\n📡 모든 센서의 최신 배터리 상태\n")
        print(f"{'센서':<6} {'일자':<12} {'시간':<10} {'전압(mV)':<10} {'배터리(%)':<10} {'상태':<10} {'Payload(Base64)'}")
        print("-" * 100)

        all_rows = fetch_latest_for_all(devices)
        if not all_rows:
            print("❌ 데이터가 없습니다.")
            return

        for sid, dev_eui, ts, payload in all_rows:
            try:
                t_kst = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(KST)
                day, time_str = t_kst.strftime("%Y-%m-%d"), t_kst.strftime("%H:%M:%S")
            except Exception:
                day, time_str = "?", "?"

            hex_bat, voltage, percent, status = decode_battery(payload)
            print(f"{sid:<6} {day:<12} {time_str:<10} {voltage:<10} {percent:<10} {status:<10} {payload}")
        return

    # 🔸 단일 센서 모드
    sensor_id = sys.argv[1].zfill(2)
    if sensor_id not in devices:
        print(f"[에러] 존재하지 않는 센서 번호: {sensor_id}")
        print("가능한 센서:", ", ".join(devices.keys()))
        return

    dev_eui = devices[sensor_id]
    print(f"\n📡 센서 {sensor_id} | DevEUI: {dev_eui}\n")

    # recent 모드 처리
    recent_limit = None
    if len(sys.argv) >= 4 and sys.argv[2].lower() == "recent":
        try:
            recent_limit = int(sys.argv[3])
        except ValueError:
            print("[에러] recent 개수는 숫자여야 합니다.")
            return

    rows = fetch_payloads(dev_eui, recent_limit)
    if not rows:
        print("❌ 데이터가 없습니다.")
        return

    print(f"{'일자':<12} {'시간':<10} {'Payload(Base64)':<24} {'Hex(BAT)':<10} {'전압(mV)':<10} {'배터리(%)':<10} {'상태'}")
    print("-" * 100)

    for day, ts, payload in rows:
        try:
            t_kst = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(KST)
            time_str = t_kst.strftime("%H:%M:%S")
        except Exception:
            time_str = "?"
        hex_bat, voltage, percent, status = decode_battery(payload)
        print(f"{day:<12} {time_str:<10} {payload:<24} {hex_bat:<10} {voltage:<10} {percent:<10} {status}")


if __name__ == "__main__":
    main()
