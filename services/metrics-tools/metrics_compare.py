#!/usr/bin/env python3
import os
import argparse
import sqlite3
import requests
import json
import csv
import redis
import statistics
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from collections import defaultdict

# -----------------------------
# 환경 변수 로드
# -----------------------------
load_dotenv("/home/ubuntu/.envs/onlog-ef-rpi.env")

API_BASE = os.getenv("CHIRPSTACK_API_URL", "http://localhost:8090/api")
API_KEY = os.getenv("CHIRPSTACK_API_KEY")
GATEWAY_ID = os.getenv("GATEWAY_ID")
SQLITE_DB = os.getenv("SQLITE_DB_PATH", "/mnt/nvme/infra/sqlite/sensor_logs.db")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

HEADERS = {"Grpc-Metadata-Authorization": f"Bearer {API_KEY}"}

# KR920 주파수 정의 (Hz)
KR920_FREQUENCIES = [
    922100000, 922300000, 922500000,  # 기본 3채널
    922700000, 922900000, 923100000, 923300000, 921700000  # 추가 5채널
]

# -----------------------------
# devices.json 로드
# -----------------------------
def load_devices(path="devices.json"):
    with open(path, "r") as f:
        return json.load(f)

DEVICES = load_devices()

# -----------------------------
# ChirpStack REST API
# -----------------------------
def get_gateway_rx(start, end):
    """게이트웨이 전체 수신 패킷 수"""
    url = f"{API_BASE}/gateways/{GATEWAY_ID}/metrics"
    params = {"start": start, "end": end, "aggregation": "HOUR"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    return sum(data["rxPackets"]["datasets"][0]["data"])

def get_device_rx(dev_eui, start, end):
    """디바이스별 수신 패킷 수"""
    url = f"{API_BASE}/devices/{dev_eui}/link-metrics"
    params = {"start": start, "end": end, "aggregation": "HOUR"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    datasets = r.json().get("rxPackets", {}).get("datasets", [])
    return sum(datasets[0]["data"]) if datasets else 0

# -----------------------------
# SQLite
# -----------------------------
def get_db_counts(start, end):
    """SQLite raw_logs에서 devEUI별 패킷 카운트"""
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()
    query = """
        SELECT substr(topic, instr(topic, 'device/')+7, 16) AS devEUI,
               COUNT(*) AS packet_count
        FROM raw_logs
        WHERE received_at BETWEEN ? AND ?
        GROUP BY devEUI
    """
    cur.execute(query, (start, end))
    results = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return results

# -----------------------------
# Redis 연결 및 메트릭 수집
# -----------------------------
def connect_redis():
    """Redis 연결"""
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def generate_hour_keys(dev_eui, start_dt, end_dt):
    """시간 범위 내 모든 HOUR 키 생성"""
    keys = []
    current = start_dt.replace(minute=0, second=0, microsecond=0)

    while current <= end_dt:
        timestamp_str = current.strftime("%Y%m%d%H%M")
        key = f"metrics:{{device:{dev_eui}}}:HOUR:{timestamp_str}"
        keys.append(key)
        current += timedelta(hours=1)

    return keys

def get_device_metrics_from_redis(r, dev_eui, start_dt, end_dt):
    """Redis에서 디바이스 메트릭 수집 및 집계"""
    keys = generate_hour_keys(dev_eui, start_dt, end_dt)

    aggregated = {
        "rx_count": 0,
        "tx_count": 0,
        "gw_rssi_sum": 0.0,
        "gw_snr_sum": 0.0,
        "gw_count": 0,
        "frequency": defaultdict(int),
        "dr": defaultdict(int),
        "errors": defaultdict(int)
    }

    for key in keys:
        if not r.exists(key):
            continue

        data = r.hgetall(key)

        # 기본 카운트
        aggregated["rx_count"] += int(data.get("rx_count", 0))
        aggregated["tx_count"] += int(data.get("tx_count", 0))

        # 신호 품질
        aggregated["gw_rssi_sum"] += float(data.get("gw_rssi_sum", 0))
        aggregated["gw_snr_sum"] += float(data.get("gw_snr_sum", 0))
        aggregated["gw_count"] += int(data.get("gw_count", 0))

        # 주파수별 집계
        for freq in KR920_FREQUENCIES:
            key_name = f"rx_freq_{freq}"
            if key_name in data:
                aggregated["frequency"][freq] += int(data[key_name])

        # DR별 집계
        for dr in range(6):  # DR0~DR5
            key_name = f"rx_dr_{dr}"
            if key_name in data:
                aggregated["dr"][dr] += int(data[key_name])

        # 에러 집계
        for error_type in ["CRC", "COLLISION_PACKET", "MIC"]:
            key_name = f"error_{error_type}"
            if key_name in data:
                aggregated["errors"][error_type] += int(data[key_name])

    return aggregated

# -----------------------------
# 분석 함수
# -----------------------------
def analyze_frequency_distribution(metrics):
    """주파수별 분포 분석"""
    freq_data = metrics["frequency"]
    total = sum(freq_data.values())

    if total == 0:
        return None

    result = {
        "total_packets": total,
        "distribution": {},
        "active_channels": 0,
        "channel_balance": 0
    }

    for freq in KR920_FREQUENCIES:
        count = freq_data.get(freq, 0)
        percentage = (count / total * 100) if total > 0 else 0
        freq_mhz = freq / 1_000_000
        result["distribution"][freq_mhz] = {
            "count": count,
            "percentage": percentage
        }
        if count > 0:
            result["active_channels"] += 1

    # 채널 균등성 (표준편차)
    if len([v for v in freq_data.values() if v > 0]) > 1:
        active_values = [v for v in freq_data.values() if v > 0]
        std_dev = statistics.stdev(active_values)
        mean = statistics.mean(active_values)
        result["channel_balance"] = (std_dev / mean * 100) if mean > 0 else 0

    return result

def analyze_dr_distribution(metrics):
    """DR별 분포 분석"""
    dr_data = metrics["dr"]
    total = sum(dr_data.values())

    if total == 0:
        return None

    result = {
        "total_packets": total,
        "distribution": {}
    }

    dr_names = {
        0: "DR0 (SF12)",
        1: "DR1 (SF11)",
        2: "DR2 (SF10)",
        3: "DR3 (SF9)",
        4: "DR4 (SF8)",
        5: "DR5 (SF7)"
    }

    for dr in range(6):
        count = dr_data.get(dr, 0)
        percentage = (count / total * 100) if total > 0 else 0
        result["distribution"][dr] = {
            "name": dr_names[dr],
            "count": count,
            "percentage": percentage
        }

    return result

def analyze_signal_quality(metrics):
    """신호 품질 분석"""
    rx_count = metrics["rx_count"]

    if rx_count == 0:
        return None

    avg_rssi = metrics["gw_rssi_sum"] / rx_count
    avg_snr = metrics["gw_snr_sum"] / rx_count

    # 상태 판단
    if avg_rssi > -100:
        status = "Good"
        emoji = "🟢"
    elif avg_rssi > -110:
        status = "Fair"
        emoji = "🟡"
    else:
        status = "Poor"
        emoji = "🔴"

    return {
        "avg_rssi": round(avg_rssi, 2),
        "avg_snr": round(avg_snr, 2),
        "status": status,
        "emoji": emoji,
        "total_packets": rx_count
    }

def analyze_error_rate(metrics):
    """에러율 분석"""
    rx_count = metrics["rx_count"]

    if rx_count == 0:
        return None

    result = {
        "total_packets": rx_count,
        "errors": {}
    }

    for error_type, count in metrics["errors"].items():
        percentage = (count / rx_count * 100) if rx_count > 0 else 0
        result["errors"][error_type] = {
            "count": count,
            "percentage": round(percentage, 2)
        }

    return result

# -----------------------------
# 터미널 출력
# -----------------------------
def print_frequency_report(dev_name, dev_eui, freq_analysis):
    """주파수 분포 출력"""
    if not freq_analysis:
        print(f"{dev_name} ({dev_eui}): 데이터 없음")
        return

    print(f"\n{dev_name} ({dev_eui}): 총 {freq_analysis['total_packets']}개")

    for freq_mhz in sorted(freq_analysis['distribution'].keys()):
        data = freq_analysis['distribution'][freq_mhz]
        count = data['count']
        pct = data['percentage']
        bar = "█" * int(pct / 2)
        print(f"  {freq_mhz:6.1f} MHz: {count:5d} ({pct:5.1f}%) {bar}")

    # 채널 사용 평가
    active = freq_analysis['active_channels']
    balance = freq_analysis['channel_balance']

    if active <= 3:
        print(f"  ❌ 기본 3개 채널만 사용 중 (재Join 필요)")
    elif active >= 8 and balance < 15:
        print(f"  ✅ 8개 채널 균등 사용 중 (편차: {balance:.1f}%)")
    elif active >= 8:
        print(f"  ⚠️  8개 채널 사용하나 불균등 (편차: {balance:.1f}%)")
    else:
        print(f"  ⚠️  {active}개 채널 사용 중")

def print_dr_report(dr_analysis):
    """DR 분포 출력"""
    if not dr_analysis:
        return

    for dr in range(6):
        data = dr_analysis['distribution'][dr]
        name = data['name']
        count = data['count']
        pct = data['percentage']
        bar = "█" * int(pct / 5)
        print(f"  {name:12s}: {count:5d} ({pct:5.1f}%) {bar}")

def print_signal_quality_report(signal_analysis):
    """신호 품질 출력"""
    if not signal_analysis:
        return

    emoji = signal_analysis['emoji']
    status = signal_analysis['status']
    rssi = signal_analysis['avg_rssi']
    snr = signal_analysis['avg_snr']

    print(f"  평균 RSSI: {rssi:7.2f} dBm")
    print(f"  평균 SNR:  {snr:7.2f} dB")
    print(f"  상태: {emoji} {status}")

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
            "DevEUI", "Name", "Total_Packets",
            "Freq_922.1", "Freq_922.3", "Freq_922.5", "Freq_922.7", "Freq_922.9",
            "Freq_923.1", "Freq_923.3", "Freq_921.7",
            "DR0", "DR1", "DR2", "DR3", "DR4", "DR5",
            "Avg_RSSI", "Avg_SNR", "Status"
        ])

        # 데이터
        for dev_eui, dev_data in data["devices"].items():
            name = dev_data["name"]
            freq_dist = dev_data.get("frequency_distribution", {}).get("distribution", {})
            dr_dist = dev_data.get("dr_distribution", {}).get("distribution", {})
            signal = dev_data.get("signal_quality", {})

            row = [
                dev_eui, name, dev_data.get("total_packets", 0)
            ]

            # 주파수
            for freq in [922.1, 922.3, 922.5, 922.7, 922.9, 923.1, 923.3, 921.7]:
                row.append(freq_dist.get(freq, {}).get("count", 0))

            # DR
            for dr in range(6):
                row.append(dr_dist.get(dr, {}).get("count", 0))

            # 신호
            row.extend([
                signal.get("avg_rssi", 0),
                signal.get("avg_snr", 0),
                signal.get("status", "Unknown")
            ])

            writer.writerow(row)

    print(f"✅ CSV exported to {output_path}")

def compare_experiments(before_path, after_path):
    """두 실험 결과 비교"""
    with open(before_path, 'r') as f:
        before = json.load(f)
    with open(after_path, 'r') as f:
        after = json.load(f)

    print(f"\n{'='*80}")
    print(f"=== 실험 결과 비교 ===")
    print(f"{'='*80}")
    print(f"Before: {before['timestamp']}")
    print(f"After:  {after['timestamp']}")

    print(f"\n{'센서':<20} {'지표':<20} {'Before':<15} {'After':<15} {'변화':<15}")
    print(f"{'-'*90}")

    for dev_eui in before["devices"].keys():
        if dev_eui not in after["devices"]:
            continue

        b_dev = before["devices"][dev_eui]
        a_dev = after["devices"][dev_eui]
        name = b_dev["name"]

        # 총 패킷 수
        b_total = b_dev.get("total_packets", 0)
        a_total = a_dev.get("total_packets", 0)
        diff_total = a_total - b_total
        print(f"{name:<20} {'Total Packets':<20} {b_total:<15} {a_total:<15} {diff_total:+d}")

        # 활성 채널 수
        b_active = b_dev.get("frequency_distribution", {}).get("active_channels", 0)
        a_active = a_dev.get("frequency_distribution", {}).get("active_channels", 0)
        diff_active = a_active - b_active
        print(f"{'':<20} {'Active Channels':<20} {b_active:<15} {a_active:<15} {diff_active:+d}")

        # 평균 RSSI
        b_rssi = b_dev.get("signal_quality", {}).get("avg_rssi", 0)
        a_rssi = a_dev.get("signal_quality", {}).get("avg_rssi", 0)
        diff_rssi = a_rssi - b_rssi
        print(f"{'':<20} {'Avg RSSI':<20} {b_rssi:<15.2f} {a_rssi:<15.2f} {diff_rssi:+.2f}")

        print()

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare ChirpStack metrics vs DB logs with detailed analysis")
    parser.add_argument("--start", help="Start time (UTC, ISO8601, e.g. 2025-10-02T00:00:00Z)")
    parser.add_argument("--end", help="End time (UTC, ISO8601, e.g. 2025-10-02T23:59:59Z)")
    parser.add_argument("--detailed", action="store_true", help="Show detailed analysis (frequency, DR, signal)")
    parser.add_argument("--export-json", metavar="PATH", help="Export results to JSON file")
    parser.add_argument("--export-csv", metavar="PATH", help="Export results to CSV file")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="Compare two JSON experiment results")
    args = parser.parse_args()

    # 비교 모드
    if args.compare:
        compare_experiments(args.compare[0], args.compare[1])
        exit(0)

    # 시간 범위 기본값 (최근 6시간)
    if args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=6)
        start_str = start.isoformat().replace("+00:00", "Z")
        end_str = end.isoformat().replace("+00:00", "Z")

    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

    # SQLite 포맷 변환
    def to_sqlite_fmt(s: str):
        return s.replace("T", " ").replace("Z", "")

    db_start, db_end = to_sqlite_fmt(start_str), to_sqlite_fmt(end_str)

    # Interval
    print(f"\n=== Interval ===")
    print(f"UTC: {start_str} ~ {end_str}")
    print(f"KST: {(datetime.fromisoformat(start_str.replace('Z',''))+timedelta(hours=9))} ~ "
          f"{(datetime.fromisoformat(end_str.replace('Z',''))+timedelta(hours=9))}")

    # Gateway total
    gw_total = get_gateway_rx(start_str, end_str)
    print(f"\n=== Gateway total uplinks: {gw_total}")

    # Device totals (API)
    device_total = 0
    api_counts = {}
    print(f"\n=== Device uplinks (link-metrics API) ===")
    for d in DEVICES:
        dev_eui, name = d["devEui"], d["name"]
        count = get_device_rx(dev_eui, start_str, end_str)
        api_counts[dev_eui] = count
        device_total += count
        print(f"{name:12s} ({dev_eui}): {count}")
    print(f"\nDevices total uplinks: {device_total}")
    print(f"Difference (Gateway - Devices) = {gw_total - device_total}")

    # DB totals
    db_counts = get_db_counts(db_start, db_end)
    db_total = sum(db_counts.values())
    print(f"\n=== Device uplinks (SQLite raw_logs) ===")
    for d in DEVICES:
        dev_eui, name = d["devEui"], d["name"]
        print(f"{name:12s} ({dev_eui}): {db_counts.get(dev_eui, 0)}")
    print(f"\nDB total uplinks: {db_total}")
    print(f"Difference (Gateway - DB) = {gw_total - db_total}")
    print(f"Difference (Devices API - DB) = {device_total - db_total}")

    # 상세 분석 (Redis)
    if args.detailed:
        print(f"\n{'='*80}")
        print(f"=== 상세 분석 (Redis metrics) ===")
        print(f"{'='*80}")

        r = connect_redis()

        # 결과 저장용 딕셔너리
        export_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interval": {
                "start": start_str,
                "end": end_str
            },
            "devices": {}
        }

        for d in DEVICES:
            dev_eui, name = d["devEui"], d["name"]

            print(f"\n{'-'*80}")
            print(f"📡 {name} ({dev_eui})")
            print(f"{'-'*80}")

            # Redis에서 메트릭 수집
            metrics = get_device_metrics_from_redis(r, dev_eui, start_dt, end_dt)

            # 분석
            freq_analysis = analyze_frequency_distribution(metrics)
            dr_analysis = analyze_dr_distribution(metrics)
            signal_analysis = analyze_signal_quality(metrics)
            error_analysis = analyze_error_rate(metrics)

            # 출력
            if freq_analysis:
                print(f"\n주파수별 분포:")
                print_frequency_report(name, dev_eui, freq_analysis)

            if dr_analysis:
                print(f"\nDR 분포:")
                print_dr_report(dr_analysis)

            if signal_analysis:
                print(f"\n신호 품질:")
                print_signal_quality_report(signal_analysis)

            # Export용 데이터 저장
            export_data["devices"][dev_eui] = {
                "name": name,
                "total_packets": metrics["rx_count"],
                "frequency_distribution": freq_analysis,
                "dr_distribution": dr_analysis,
                "signal_quality": signal_analysis,
                "error_analysis": error_analysis
            }

        # Export
        if args.export_json:
            export_to_json(export_data, args.export_json)

        if args.export_csv:
            export_to_csv(export_data, args.export_csv)
