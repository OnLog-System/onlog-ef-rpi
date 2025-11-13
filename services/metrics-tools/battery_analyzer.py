#!/usr/bin/env python3
"""
Battery Analyzer for LHT65N Devices
====================================
모든 센서의 배터리 상태를 시간대별로 분석하고 터미널에 시각화합니다.

사용법:
    python3 battery_analyzer.py
    (대화형으로 일수와 주기를 입력)

    python3 battery_analyzer.py --days 30 --interval 1
    (명령줄 인자로 지정)

    python3 battery_analyzer.py --days 7 --interval 6 --export-json battery.json
    python3 battery_analyzer.py --days 7 --interval 6 --export-csv battery.csv
    (JSON/CSV로 내보내기)

파일 전송:
    scp로 결과 파일을 로컬로 전송할 수 있습니다:
    scp ubuntu@your-server:/path/to/battery.json ./
"""

import sqlite3
import base64
import json
import csv
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# -----------------------------
# 설정
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = "/mnt/nvme/infra/sqlite/sensor_logs.db"
DEVICES_FILE = BASE_DIR / "devices.json"

V_MIN = 2500  # 2.5V
V_MAX = 3300  # 3.3V
KST = timezone(timedelta(hours=9))

# -----------------------------
# devices.json 로드
# -----------------------------
def load_devices(path=None):
    """devices.json 로드"""
    if path is None:
        path = DEVICES_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[에러] devices.json 로드 실패: {e}")
        return []


# -----------------------------
# 배터리 디코딩
# -----------------------------
# -----------------------------
# 배터리 디코딩
# -----------------------------
def decode_battery(base64_str):
    """Base64 페이로드에서 배터리 정보 추출"""
    try:
        data = base64.b64decode(base64_str)
        bat_raw = int.from_bytes(data[:2], "big")
        voltage_mv = bat_raw & 0x3FFF
        percent = max(0, min(100, int((voltage_mv - V_MIN) / (V_MAX - V_MIN) * 100)))
        return voltage_mv, percent
    except Exception:
        return None, None


# -----------------------------
# SQLite 데이터 수집
# -----------------------------
# -----------------------------
# SQLite 데이터 수집
# -----------------------------
def fetch_battery_data(dev_eui, days, interval_hours):
    """
    지정된 기간 동안 특정 간격으로 배터리 데이터 수집
    
    Args:
        dev_eui: 디바이스 EUI
        days: 최근 며칠
        interval_hours: 샘플링 간격 (시간)
    
    Returns:
        List of (timestamp, voltage_mv, percent)
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 시간 범위 계산
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    # 간격별로 데이터 수집
    query = """
        WITH hourly_data AS (
            SELECT 
                datetime(
                    strftime('%s', received_at) / (? * 3600) * (? * 3600),
                    'unixepoch'
                ) AS time_bucket,
                received_at,
                json_extract(payload, '$.data') AS data,
                ROW_NUMBER() OVER (
                    PARTITION BY datetime(
                        strftime('%s', received_at) / (? * 3600) * (? * 3600),
                        'unixepoch'
                    )
                    ORDER BY received_at DESC
                ) AS rn
            FROM raw_logs
            WHERE topic LIKE '%/event/up'
              AND json_extract(payload, '$.deviceInfo.devEui') = ?
              AND received_at >= ?
              AND received_at <= ?
        )
        SELECT time_bucket, data
        FROM hourly_data
        WHERE rn = 1
        ORDER BY time_bucket ASC;
    """
    
    start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    
    cur.execute(query, (
        interval_hours, interval_hours,
        interval_hours, interval_hours,
        dev_eui, start_str, end_str
    ))
    
    rows = cur.fetchall()
    conn.close()
    
    # 데이터 파싱
    results = []
    for time_bucket, payload in rows:
        if not payload:
            continue
        voltage_mv, percent = decode_battery(payload)
        if voltage_mv is not None:
            ts = datetime.strptime(time_bucket, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            results.append((ts, voltage_mv, percent))
    
    return results


# -----------------------------
# 분석 함수
# -----------------------------
def calculate_battery_stats(data_points):
    """배터리 데이터 통계 계산"""
    if not data_points:
        return None
    
    voltages = [v for _, v, _ in data_points]
    percents = [p for _, _, p in data_points]
    
    # 감소율 계산 (일일)
    if len(data_points) >= 2:
        first_ts, first_v, first_p = data_points[0]
        last_ts, last_v, last_p = data_points[-1]
        
        days_elapsed = (last_ts - first_ts).total_seconds() / 86400
        if days_elapsed > 0:
            voltage_drop_per_day = (first_v - last_v) / days_elapsed
            percent_drop_per_day = (first_p - last_p) / days_elapsed
        else:
            voltage_drop_per_day = 0
            percent_drop_per_day = 0
    else:
        voltage_drop_per_day = 0
        percent_drop_per_day = 0
    
    return {
        "count": len(data_points),
        "first_voltage": voltages[0],
        "last_voltage": voltages[-1],
        "first_percent": percents[0],
        "last_percent": percents[-1],
        "min_voltage": min(voltages),
        "max_voltage": max(voltages),
        "avg_voltage": sum(voltages) / len(voltages),
        "voltage_drop": voltages[0] - voltages[-1],
        "percent_drop": percents[0] - percents[-1],
        "voltage_drop_per_day": voltage_drop_per_day,
        "percent_drop_per_day": percent_drop_per_day,
    }


# -----------------------------
# 터미널 출력
# -----------------------------
def print_summary_table(all_stats):
    """모든 센서의 통계 요약 출력"""
    print(f"\n{'='*120}")
    print(f"{'센서':<15} {'샘플':<7} {'시작전압':<10} {'종료전압':<10} {'전압감소':<10} {'시작(%)':<9} {'종료(%)':<9} {'감소(%)':<10} {'일일감소':<12}")
    print(f"{'-'*120}")
    
    for name, stats in sorted(all_stats.items()):
        if stats is None:
            print(f"{name:<15} {'N/A':<7} {'-':<10} {'-':<10} {'-':<10} {'-':<9} {'-':<9} {'-':<10} {'-':<12}")
        else:
            print(f"{name:<15} "
                  f"{stats['count']:<7} "
                  f"{stats['first_voltage']:<10.0f} "
                  f"{stats['last_voltage']:<10.0f} "
                  f"{stats['voltage_drop']:<10.0f} "
                  f"{stats['first_percent']:<9} "
                  f"{stats['last_percent']:<9} "
                  f"{stats['percent_drop']:<10.1f} "
                  f"{stats['percent_drop_per_day']:<12.2f}")
    
    print(f"{'='*120}")


def percent_to_spark(pct):
    SPARKS = '▁▂▃▄▅▆▇█'
    if pct is None:
        return '.'
    try:
        pct = float(pct)
    except Exception:
        return '?'
    if pct <= 0:
        return SPARKS[0]
    idx = int(pct / 100 * (len(SPARKS) - 1))
    idx = max(0, min(len(SPARKS) - 1, idx))
    return SPARKS[idx]


def print_ascii_charts(all_data, days, interval_hours):
    """Print per-day ASCII charts for all devices.

    One line per day. Each character represents one interval (interval_hours).
    """
    now = datetime.now(timezone.utc)
    start_dt = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = now.replace(minute=0, second=0, microsecond=0)
    interval = timedelta(hours=interval_hours)

    for name, data_points in sorted(all_data.items()):
        print(f"\nDevice: {name}  samples: {len(data_points)}")
        # build dictionary mapping bucket start -> percent
        bucket_map = {}
        for ts, v, p in data_points:
            # floor ts to interval
            offset = int((ts - start_dt).total_seconds())
            if offset < 0:
                continue
            idx = offset // int(interval_hours * 3600)
            bucket_start = start_dt + timedelta(seconds=idx * int(interval_hours * 3600))
            # keep latest per bucket (data_points assumed sorted asc)
            bucket_map[bucket_start] = p

        # print per day
        day_cursor = start_dt
        total_days = (end_dt.date() - start_dt.date()).days + 1
        for d in range(total_days):
            day_start = day_cursor + timedelta(days=d)
            line_chars = []
            cur = day_start
            while cur < day_start + timedelta(days=1) and cur < end_dt:
                pct = bucket_map.get(cur)
                line_chars.append(percent_to_spark(pct))
                cur += interval
            label = day_start.strftime('%Y-%m-%d')
            # summary: avg if any
            pcts = [v for v in [bucket_map.get(day_start + timedelta(seconds=i * int(interval_hours * 3600))) for i in range(len(line_chars))] if v is not None]
            avg = int(sum(pcts) / len(pcts)) if pcts else None
            summary = f"avg={avg}%" if avg is not None else "no-data"
            print(f"{label} {''.join(line_chars):<60} {summary}")


# -----------------------------
# Export 함수
# -----------------------------
def export_to_json(data, output_path):
    """JSON 파일로 저장"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ JSON exported to {output_path}")


def export_to_csv(data, output_path):
    """CSV 파일로 저장"""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # 헤더
        writer.writerow([
            "Timestamp", "DevEUI", "Name", "Voltage_mV", "Percent", "Status"
        ])
        
        # 데이터
        for dev_eui, dev_data in data["devices"].items():
            name = dev_data["name"]
            samples = dev_data.get("samples", [])
            
            for sample in samples:
                ts_str = sample["timestamp"]
                voltage = sample["voltage_mv"]
                percent = sample["percent"]
                
                # 상태 판단
                if percent >= 80:
                    status = "Good"
                elif percent >= 50:
                    status = "OK"
                elif percent >= 20:
                    status = "Low"
                else:
                    status = "Critical"
                
                writer.writerow([
                    ts_str, dev_eui, name, voltage, percent, status
                ])
    
    print(f"✅ CSV exported to {output_path}")


# -----------------------------
# 실행부
# -----------------------------
# -----------------------------
# 실행부
# -----------------------------
def main():
    parser = argparse.ArgumentParser(
        description='배터리 상태를 시간대별로 분석하고 시각화합니다.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python3 battery_analyzer.py
  python3 battery_analyzer.py --days 30 --interval 1
  python3 battery_analyzer.py --days 7 --interval 6 --export-json battery.json
  python3 battery_analyzer.py --days 7 --interval 6 --export-csv battery.csv
  
파일 전송 (scp):
  scp ubuntu@your-server:/path/to/battery.json ./
        """
    )
    
    parser.add_argument('--days', type=int, help='최근 며칠 데이터를 분석할지 (예: 30)')
    parser.add_argument('--interval', type=int, help='샘플링 간격 (시간 단위, 예: 1)')
    parser.add_argument('--export-json', metavar='PATH', help='JSON 파일로 내보내기')
    parser.add_argument('--export-csv', metavar='PATH', help='CSV 파일로 내보내기')
    parser.add_argument('--no-plot', action='store_true', help='시각화 건너뛰기 (통계만 출력)')
    
    args = parser.parse_args()
    
    # 대화형 입력
    if args.days is None:
        try:
            days_input = input("\n📅 최근 며칠 데이터를 분석하시겠습니까? (예: 30): ").strip()
            days = int(days_input) if days_input else 30
        except (ValueError, KeyboardInterrupt):
            print("\n기본값 30일을 사용합니다.")
            days = 30
    else:
        days = args.days
    
    if args.interval is None:
        try:
            interval_input = input("⏱️  샘플링 간격은? (시간 단위, 예: 1): ").strip()
            interval_hours = int(interval_input) if interval_input else 1
        except (ValueError, KeyboardInterrupt):
            print("\n기본값 1시간을 사용합니다.")
            interval_hours = 1
    else:
        interval_hours = args.interval
    
    # 유효성 검증
    if days <= 0 or days > 365:
        print("❌ 일수는 1~365 사이여야 합니다.")
        return
    
    if interval_hours <= 0 or interval_hours > 24:
        print("❌ 간격은 1~24시간 사이여야 합니다.")
        return
    
    print(f"\n{'='*80}")
    print(f"🔋 배터리 분석 시작")
    print(f"{'='*80}")
    print(f"📊 분석 기간: 최근 {days}일")
    print(f"⏱️  샘플링 간격: {interval_hours}시간")
    print(f"{'='*80}\n")
    
    # 디바이스 로드
    devices = load_devices()
    if not devices:
        print("❌ 디바이스를 찾을 수 없습니다.")
        return
    
    print(f"📡 총 {len(devices)}개 센서 데이터 수집 중...\n")
    
    # 모든 디바이스 데이터 수집
    all_data = {}
    all_stats = {}
    
    for device in devices:
        dev_eui = device['devEui']
        name = device['name']
        
        print(f"  └─ {name} ... ", end='', flush=True)
        
        data_points = fetch_battery_data(dev_eui, days, interval_hours)
        
        if data_points:
            all_data[name] = data_points
            all_stats[name] = calculate_battery_stats(data_points)
            print(f"✅ {len(data_points)}개 샘플")
        else:
            all_data[name] = []
            all_stats[name] = None
            print("❌ 데이터 없음")
    
    # 통계 출력
    print_summary_table(all_stats)
    
    # 경고 메시지
    print(f"\n{'='*80}")
    print("⚠️  경고 센서:")
    print(f"{'-'*80}")
    
    warnings_found = False
    for name, stats in sorted(all_stats.items()):
        if stats is None:
            continue
        
        # 일일 감소율이 1% 이상인 경우
        if stats['percent_drop_per_day'] > 1.0:
            warnings_found = True
            print(f"  🔴 {name}: 일일 {stats['percent_drop_per_day']:.2f}% 감소 (빠른 배터리 소모)")
        
        # 현재 배터리가 20% 이하인 경우
        if stats['last_percent'] <= 20:
            warnings_found = True
            print(f"  🟡 {name}: 현재 배터리 {stats['last_percent']}% (교체 권장)")
    
    if not warnings_found:
        print("  ✅ 모든 센서가 정상 범위 내에 있습니다.")
    
    print(f"{'='*80}\n")
    
    # 시각화 (터미널 출력)
    if not args.no_plot:
        print("\n📊 ASCII 차트 (터미널 출력)")
        print_ascii_charts(all_data, days, interval_hours)
    
    # Export 데이터 준비
    if args.export_json or args.export_csv:
        export_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interval": {
                "days": days,
                "interval_hours": interval_hours,
                "start": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
                "end": datetime.now(timezone.utc).isoformat()
            },
            "devices": {}
        }
        
        for device in devices:
            dev_eui = device['devEui']
            name = device['name']
            data_points = all_data.get(name, [])
            stats = all_stats.get(name)
            
            export_data["devices"][dev_eui] = {
                "name": name,
                "stats": stats,
                "samples": [
                    {
                        "timestamp": ts.isoformat(),
                        "voltage_mv": v,
                        "percent": p
                    }
                    for ts, v, p in data_points
                ]
            }
        
        # Export
        if args.export_json:
            export_to_json(export_data, args.export_json)
        
        if args.export_csv:
            export_to_csv(export_data, args.export_csv)
    
    print("\n✅ 분석 완료!")


if __name__ == "__main__":
    main()
