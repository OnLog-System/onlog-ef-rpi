#!/usr/bin/env python3
"""
센서 메시지 동기화 모니터링 스크립트
실시간으로 디바이스별 메시지 동기화 상태를 분석하고 보고
"""

import os
import sqlite3
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")

def get_device_stats(hours_back=1):
    """지정된 시간 내 디바이스별 통계 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    
    # 최근 메시지 통계
    c.execute("""
        SELECT 
            SUBSTR(topic, INSTR(topic, '/') + 1, 
                   INSTR(SUBSTR(topic, INSTR(topic, '/') + 1), '/') - 1) as app_id,
            SUBSTR(topic, 
                   INSTR(topic, '/') + 1 + INSTR(SUBSTR(topic, INSTR(topic, '/') + 1), '/'),
                   INSTR(SUBSTR(topic, 
                               INSTR(topic, '/') + 1 + INSTR(SUBSTR(topic, INSTR(topic, '/') + 1), '/') + 1), '/') - 1) as device_id,
            COUNT(*) as message_count,
            MIN(received_at) as first_message,
            MAX(received_at) as last_message
        FROM raw_logs 
        WHERE received_at > ? 
        AND topic LIKE 'application/%'
        GROUP BY app_id, device_id
        ORDER BY message_count DESC
    """, (cutoff_time.isoformat(),))
    
    results = c.fetchall()
    conn.close()
    
    return results

def analyze_sync_status():
    """동기화 상태 분석"""
    print(f"🔍 Analyzing sensor message synchronization...")
    print(f"📅 Analysis time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 지난 1시간 데이터 분석
    device_stats = get_device_stats(1)
    
    if not device_stats:
        print("❌ No message data found in the last hour")
        return
    
    print(f"📊 Found {len(device_stats)} active devices in the last hour")
    print()
    
    # 메시지 수 통계
    message_counts = [stat[2] for stat in device_stats]
    avg_messages = sum(message_counts) / len(message_counts)
    max_messages = max(message_counts)
    min_messages = min(message_counts)
    
    print(f"📈 Message Count Statistics:")
    print(f"   Average: {avg_messages:.1f} messages/hour")
    print(f"   Maximum: {max_messages} messages/hour")  
    print(f"   Minimum: {min_messages} messages/hour")
    print(f"   Variance: {max_messages - min_messages} messages")
    print()
    
    # 불균형 감지
    if avg_messages > 0:
        imbalance_ratio = (max_messages - min_messages) / avg_messages
        if imbalance_ratio > 0.2:  # 20% 이상 차이
            print("⚠️  MESSAGE IMBALANCE DETECTED!")
            print(f"   Imbalance ratio: {imbalance_ratio:.2f}")
            print("   Devices with extreme counts:")
            
            # 최고/최저 디바이스 표시
            for stat in device_stats:
                app_id, device_id, count, first, last = stat
                if count == max_messages or count == min_messages:
                    status = "🔴 HIGHEST" if count == max_messages else "🟡 LOWEST"
                    print(f"   {status}: {device_id} = {count} messages")
        else:
            print("✅ Message counts are well balanced")
    
    print()
    print("📋 Device Details:")
    print("-" * 80)
    
    for i, (app_id, device_id, count, first, last) in enumerate(device_stats[:20]):  # 상위 20개만 표시
        # 마지막 메시지로부터 경과 시간 계산
        last_msg_time = datetime.fromisoformat(last.replace('Z', '+00:00').replace('+00:00', ''))
        time_since_last = datetime.now() - last_msg_time
        minutes_ago = int(time_since_last.total_seconds() / 60)
        
        # 상태 아이콘
        if minutes_ago < 5:
            status_icon = "🟢"  # 활성
        elif minutes_ago < 15:
            status_icon = "🟡"  # 지연
        else:
            status_icon = "🔴"  # 비활성
            
        print(f"{status_icon} {device_id:20} | {count:3d} msgs | Last: {minutes_ago:2d}m ago")

def get_sync_events(hours_back=24):
    """동기화 이벤트 로그 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    
    try:
        c.execute("""
            SELECT event_time, event_type, device_id, message, severity
            FROM sync_events 
            WHERE event_time > ?
            ORDER BY event_time DESC
            LIMIT 50
        """, (cutoff_time.isoformat(),))
        
        events = c.fetchall()
        return events
    except sqlite3.OperationalError:
        # 테이블이 아직 생성되지 않은 경우
        return []
    finally:
        conn.close()

def show_recent_events():
    """최근 동기화 이벤트 표시"""
    events = get_sync_events(24)
    
    if not events:
        print("📝 No synchronization events recorded in the last 24 hours")
        return
    
    print(f"📝 Recent Synchronization Events (last 24h):")
    print("-" * 80)
    
    for event_time, event_type, device_id, message, severity in events[:10]:
        severity_icon = {
            "INFO": "ℹ️ ",
            "WARNING": "⚠️ ",
            "ERROR": "❌"
        }.get(severity, "📍")
        
        device_str = f"[{device_id}] " if device_id else ""
        print(f"{severity_icon} {event_time[:19]} | {event_type:10} | {device_str}{message}")

def main():
    """메인 실행 함수"""
    try:
        analyze_sync_status()
        print()
        show_recent_events()
        
    except sqlite3.OperationalError as e:
        print(f"❌ Database error: {e}")
        print("💡 Make sure the MQTT logger is running and has created the database")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()