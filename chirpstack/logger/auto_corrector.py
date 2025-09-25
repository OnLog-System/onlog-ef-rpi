#!/usr/bin/env python3
"""
Device Auto-Correction Module
Automatically detects and attempts to correct message synchronization issues
"""

import os
import sqlite3
import json
import time
import configparser
from datetime import datetime, timedelta
from typing import List, Dict, Any

class DeviceAutoCorrector:
    def __init__(self, config_path: str = "/app/sync_config.conf"):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        
        self.db_path = self.config.get('database', 'db_path', fallback='/data/sensor_logs.db')
        self.expected_interval = self.config.getint('synchronization', 'expected_message_interval', fallback=60)
        self.timing_tolerance = self.config.getint('synchronization', 'timing_tolerance', fallback=10)
        self.max_missed_messages = self.config.getint('synchronization', 'max_missed_messages', fallback=3)
        self.balance_threshold = self.config.getfloat('monitoring', 'balance_threshold', fallback=0.10)
        
    def get_db_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def detect_problematic_devices(self) -> List[Dict[str, Any]]:
        """Detect devices with synchronization issues"""
        conn = self.get_db_connection()
        c = conn.cursor()
        
        print("🔍 Analyzing device message patterns...")
        
        # Get recent device statistics
        c.execute("""
            SELECT 
                device_id,
                message_count,
                actual_avg_interval,
                (strftime('%s','now') - strftime('%s',last_seen)) as seconds_since_last,
                status
            FROM device_stats 
            WHERE last_seen > datetime('now', '-1 hour')
        """)
        
        devices = c.fetchall()
        conn.close()
        
        if not devices:
            print("⚠️ No active devices found")
            return []
        
        problematic_devices = []
        message_counts = [d[1] for d in devices]
        avg_message_count = sum(message_counts) / len(message_counts)
        
        for device in devices:
            device_id, msg_count, avg_interval, seconds_ago, status = device
            issues = []
            
            # Check message count deviation
            if msg_count < avg_message_count * (1 - self.balance_threshold):
                issues.append("low_message_count")
            elif msg_count > avg_message_count * (1 + self.balance_threshold):
                issues.append("high_message_count")
            
            # Check timing deviation
            if avg_interval and abs(avg_interval - self.expected_interval) > self.timing_tolerance:
                if avg_interval > self.expected_interval + self.timing_tolerance:
                    issues.append("slow_interval")
                else:
                    issues.append("fast_interval")
            
            # Check if device is stale
            if seconds_ago > self.expected_interval * 2:
                issues.append("stale_device")
            
            if issues:
                problematic_devices.append({
                    'device_id': device_id,
                    'message_count': msg_count,
                    'avg_interval': avg_interval,
                    'seconds_since_last': seconds_ago,
                    'issues': issues,
                    'severity': self._calculate_severity(issues, msg_count, avg_message_count)
                })
        
        return problematic_devices
    
    def _calculate_severity(self, issues: List[str], msg_count: int, avg_count: float) -> str:
        """Calculate issue severity"""
        critical_issues = ['stale_device']
        warning_issues = ['slow_interval', 'fast_interval']
        
        if any(issue in critical_issues for issue in issues):
            return "critical"
        elif abs(msg_count - avg_count) / avg_count > 0.25:
            return "critical"
        elif any(issue in warning_issues for issue in issues):
            return "warning"
        else:
            return "minor"
    
    def generate_correction_actions(self, problematic_devices: List[Dict]) -> List[Dict[str, Any]]:
        """Generate correction actions for problematic devices"""
        actions = []
        
        for device in problematic_devices:
            device_actions = []
            
            if "low_message_count" in device['issues']:
                device_actions.append({
                    'type': 'monitor_closely',
                    'description': f"Monitor {device['device_id'][:8]}... for missed messages",
                    'priority': 'medium'
                })
            
            if "high_message_count" in device['issues']:
                device_actions.append({
                    'type': 'check_configuration',
                    'description': f"Check {device['device_id'][:8]}... transmission settings",
                    'priority': 'medium'
                })
            
            if "slow_interval" in device['issues']:
                device_actions.append({
                    'type': 'sync_timing',
                    'description': f"Device {device['device_id'][:8]}... sending too slowly",
                    'priority': 'high',
                    'current_interval': device['avg_interval'],
                    'expected_interval': self.expected_interval
                })
            
            if "fast_interval" in device['issues']:
                device_actions.append({
                    'type': 'throttle_device',
                    'description': f"Device {device['device_id'][:8]}... sending too frequently",
                    'priority': 'medium',
                    'current_interval': device['avg_interval'],
                    'expected_interval': self.expected_interval
                })
            
            if "stale_device" in device['issues']:
                device_actions.append({
                    'type': 'reconnect_device',
                    'description': f"Device {device['device_id'][:8]}... appears offline",
                    'priority': 'critical',
                    'last_seen': device['seconds_since_last']
                })
            
            if device_actions:
                actions.append({
                    'device_id': device['device_id'],
                    'severity': device['severity'],
                    'actions': device_actions
                })
        
        return actions
    
    def log_correction_actions(self, actions: List[Dict]) -> None:
        """Log correction actions to database"""
        if not actions:
            return
        
        conn = self.get_db_connection()
        c = conn.cursor()
        
        # Create correction log table if it doesn't exist
        c.execute("""
            CREATE TABLE IF NOT EXISTS device_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                device_id TEXT,
                severity TEXT,
                actions TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        
        for action_group in actions:
            c.execute("""
                INSERT INTO device_corrections (device_id, severity, actions)
                VALUES (?, ?, ?)
            """, (
                action_group['device_id'],
                action_group['severity'],
                json.dumps(action_group['actions'])
            ))
        
        conn.commit()
        conn.close()
    
    def run_auto_correction_cycle(self) -> None:
        """Run a complete auto-correction cycle"""
        print("\n🔧 STARTING AUTO-CORRECTION CYCLE")
        print("=" * 60)
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Step 1: Detect problematic devices
        problematic_devices = self.detect_problematic_devices()
        
        if not problematic_devices:
            print("✅ All devices are operating within acceptable parameters")
            return
        
        print(f"\n⚠️ Found {len(problematic_devices)} devices with synchronization issues:")
        
        # Step 2: Generate correction actions
        actions = self.generate_correction_actions(problematic_devices)
        
        # Step 3: Display recommendations
        for action_group in actions:
            device_short = action_group['device_id'][:8] + "..."
            severity_icon = {"critical": "🔴", "warning": "🟡", "minor": "🟢"}
            print(f"\n{severity_icon.get(action_group['severity'], '🔵')} Device: {device_short}")
            
            for action in action_group['actions']:
                priority_icon = {"critical": "🚨", "high": "⚡", "medium": "📋", "low": "💡"}
                print(f"  {priority_icon.get(action['priority'], '📝')} {action['description']}")
        
        # Step 4: Log actions
        self.log_correction_actions(actions)
        print(f"\n📊 Logged {len(actions)} correction action groups to database")
        
        # Step 5: Provide summary recommendations
        self._print_summary_recommendations(actions)
    
    def _print_summary_recommendations(self, actions: List[Dict]) -> None:
        """Print summary recommendations"""
        print("\n💡 SUMMARY RECOMMENDATIONS:")
        print("-" * 60)
        
        critical_count = sum(1 for a in actions if a['severity'] == 'critical')
        warning_count = sum(1 for a in actions if a['severity'] == 'warning')
        
        if critical_count > 0:
            print(f"🚨 CRITICAL: {critical_count} devices need immediate attention")
            print("   - Check device connectivity and power status")
            print("   - Verify LoRaWAN gateway coverage")
            print("   - Review device configuration settings")
        
        if warning_count > 0:
            print(f"⚡ WARNING: {warning_count} devices have timing issues")
            print("   - Synchronize device transmission intervals")
            print("   - Check for network latency or interference")
            print("   - Review device firmware versions")
        
        print("\n🔄 Next steps:")
        print("   1. Address critical issues first")
        print("   2. Monitor devices closely for improvement")
        print("   3. Run balance checks more frequently")
        print("   4. Update device configurations as needed")

def main():
    """Main function"""
    corrector = DeviceAutoCorrector()
    
    try:
        corrector.run_auto_correction_cycle()
    except Exception as e:
        print(f"❌ Error during auto-correction: {e}")
        raise

if __name__ == "__main__":
    main()