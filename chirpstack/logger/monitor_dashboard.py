#!/usr/bin/env python3
"""
Device Message Balance Monitoring Dashboard
Provides real-time insights into sensor message synchronization
"""

import os
import sqlite3
import json
import time
from datetime import datetime, timedelta
from tabulate import tabulate

DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")

def get_db_connection():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)

def show_device_status():
    """Display current device status and message counts"""
    conn = get_db_connection()
    c = conn.cursor()
    
    print("\n📊 DEVICE MESSAGE STATUS")
    print("=" * 80)
    
    # Get device statistics
    c.execute("""
        SELECT 
            device_id,
            message_count,
            actual_avg_interval,
            (strftime('%s','now') - strftime('%s',last_seen)) as seconds_since_last,
            status,
            datetime(last_seen, 'localtime') as last_seen_local
        FROM device_stats 
        WHERE last_seen > datetime('now', '-24 hours')
        ORDER BY message_count DESC
    """)
    
    devices = c.fetchall()
    
    if not devices:
        print("⚠️ No active devices found in the last 24 hours")
        conn.close()
        return
    
    # Format data for table
    headers = ["Device ID", "Messages", "Avg Interval", "Last Seen", "Status", "Seconds Ago"]
    table_data = []
    
    for device in devices:
        device_id = device[0][:12] + "..." if len(device[0]) > 15 else device[0]
        messages = device[1]
        avg_interval = f"{device[2]:.1f}s" if device[2] else "N/A"
        seconds_ago = device[3]
        status = "🟢 ACTIVE" if seconds_ago < 300 else "🟡 STALE" if seconds_ago < 3600 else "🔴 OFFLINE"
        last_seen = device[5]
        
        table_data.append([
            device_id, messages, avg_interval, last_seen, status, f"{seconds_ago}s"
        ])
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    conn.close()

def show_balance_history():
    """Display recent balance check history"""
    conn = get_db_connection()
    c = conn.cursor()
    
    print("\n📈 MESSAGE BALANCE HISTORY (Last 24 hours)")
    print("=" * 80)
    
    c.execute("""
        SELECT 
            datetime(check_time, 'localtime') as check_time_local,
            total_devices,
            balanced,
            min_messages,
            max_messages,
            ROUND(avg_messages, 1) as avg_messages
        FROM message_balance_log 
        WHERE check_time > datetime('now', '-24 hours')
        ORDER BY check_time DESC
        LIMIT 10
    """)
    
    history = c.fetchall()
    
    if not history:
        print("⚠️ No balance checks found in the last 24 hours")
        conn.close()
        return
    
    headers = ["Check Time", "Devices", "Balanced", "Min Msg", "Max Msg", "Avg Msg"]
    table_data = []
    
    for entry in history:
        balance_status = "✅ YES" if entry[2] else "❌ NO"
        table_data.append([
            entry[0], entry[1], balance_status, entry[3], entry[4], entry[5]
        ])
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    conn.close()

def show_message_timeline():
    """Show message count timeline for the last hour"""
    conn = get_db_connection()
    c = conn.cursor()
    
    print("\n⏰ HOURLY MESSAGE TIMELINE")
    print("=" * 80)
    
    c.execute("""
        SELECT 
            device_id,
            COUNT(*) as messages,
            MIN(datetime(received_at, 'localtime')) as first_msg,
            MAX(datetime(received_at, 'localtime')) as last_msg
        FROM raw_logs 
        WHERE received_at > datetime('now', '-1 hour')
        GROUP BY device_id
        ORDER BY messages DESC
    """)
    
    timeline = c.fetchall()
    
    if not timeline:
        print("⚠️ No messages found in the last hour")
        conn.close()
        return
    
    headers = ["Device ID", "Messages", "First Message", "Last Message"]
    table_data = []
    
    for entry in timeline:
        device_id = entry[0][:12] + "..." if len(entry[0]) > 15 else entry[0]
        table_data.append([device_id, entry[1], entry[2], entry[3]])
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    conn.close()

def detect_imbalances():
    """Detect and report current imbalances"""
    conn = get_db_connection()
    c = conn.cursor()
    
    print("\n🔍 IMBALANCE DETECTION")
    print("=" * 80)
    
    # Get latest balance check
    c.execute("""
        SELECT balanced, details FROM message_balance_log 
        ORDER BY check_time DESC LIMIT 1
    """)
    
    result = c.fetchone()
    if not result:
        print("⚠️ No balance checks available")
        conn.close()
        return
    
    balanced, details_json = result
    
    if balanced:
        print("✅ System is currently BALANCED - all devices sending similar message counts")
        conn.close()
        return
    
    print("⚠️ System is currently IMBALANCED")
    
    try:
        details = json.loads(details_json)
        devices = details['devices']
        
        # Find problematic devices
        message_counts = [d['message_count'] for d in devices]
        avg_count = sum(message_counts) / len(message_counts)
        
        print(f"\n📊 Average message count: {avg_count:.1f}")
        
        print("\n🔴 Devices BELOW average:")
        below_avg = [d for d in devices if d['message_count'] < avg_count * 0.9]
        for device in below_avg:
            print(f"  - {device['device_id'][:12]}...: {device['message_count']} messages "
                  f"(avg interval: {device['avg_interval']:.1f}s)")
        
        print("\n🔵 Devices ABOVE average:")
        above_avg = [d for d in devices if d['message_count'] > avg_count * 1.1]
        for device in above_avg:
            print(f"  - {device['device_id'][:12]}...: {device['message_count']} messages "
                  f"(avg interval: {device['avg_interval']:.1f}s)")
    
    except json.JSONDecodeError:
        print("❌ Could not parse balance check details")
    
    conn.close()

def show_recommendations():
    """Show recommendations for improving balance"""
    print("\n💡 RECOMMENDATIONS FOR MESSAGE SYNCHRONIZATION")
    print("=" * 80)
    print("""
1. 🔧 CONFIGURATION ADJUSTMENTS:
   - Ensure all devices use the same transmission interval
   - Check device configuration for consistent timing settings
   - Verify network connectivity for all devices

2. 📡 MQTT OPTIMIZATION:
   - QoS level is set to 1 for reliable delivery
   - Monitor MQTT broker logs for connection issues
   - Check for network latency between devices and broker

3. 🔍 MONITORING ACTIONS:
   - Review device logs for transmission errors
   - Check power management settings on battery devices
   - Verify LoRaWAN coverage for all device locations

4. 🛠️ TROUBLESHOOTING STEPS:
   - Restart devices showing significant deviation
   - Check ChirpStack device profiles for consistent settings
   - Monitor system resources (CPU, memory, network)

5. 📊 ONGOING MONITORING:
   - Run this dashboard regularly to track improvements
   - Set up alerts for balance threshold violations
   - Document device placement and configuration changes
""")

def main():
    """Main dashboard function"""
    print("🚀 SENSOR MESSAGE SYNCHRONIZATION DASHBOARD")
    print("=" * 80)
    print(f"⏰ Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        show_device_status()
        show_balance_history()
        show_message_timeline()
        detect_imbalances()
        show_recommendations()
    except sqlite3.OperationalError as e:
        print(f"❌ Database error: {e}")
        print("💡 Make sure the logger service is running and database is initialized")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()