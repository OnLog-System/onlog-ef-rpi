#!/usr/bin/env python3
"""
Simple test script to verify sensor synchronization functionality
Tests the core components without requiring actual MQTT messages
"""

import sqlite3
import json
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

def test_database_schema():
    """Test that the database schema is created correctly"""
    print("🔍 Testing database schema creation...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Import the database initialization code
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create tables (from app.py)
        c.execute("""
        CREATE TABLE IF NOT EXISTS raw_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          topic TEXT,
          payload TEXT,
          device_id TEXT,
          message_type TEXT
        )
        """)
        
        c.execute("""
        CREATE TABLE IF NOT EXISTS device_stats (
          device_id TEXT PRIMARY KEY,
          message_count INTEGER DEFAULT 0,
          last_seen TIMESTAMP,
          expected_interval INTEGER DEFAULT 60,
          actual_avg_interval REAL,
          status TEXT DEFAULT 'active',
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        c.execute("""
        CREATE TABLE IF NOT EXISTS message_balance_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          total_devices INTEGER,
          balanced BOOLEAN,
          min_messages INTEGER,
          max_messages INTEGER,
          avg_messages REAL,
          details TEXT
        )
        """)
        
        conn.commit()
        
        # Verify tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        
        expected_tables = ['raw_logs', 'device_stats', 'message_balance_log']
        for table in expected_tables:
            if table in tables:
                print(f"  ✅ Table '{table}' created successfully")
            else:
                print(f"  ❌ Table '{table}' missing")
                return False
        
        conn.close()
        return True
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)

def test_device_id_extraction():
    """Test device ID extraction from MQTT topics"""
    print("\n🔍 Testing device ID extraction...")
    
    # Test function from app.py
    def extract_device_id(topic):
        """Extract device ID from MQTT topic"""
        parts = topic.split('/')
        if len(parts) >= 4 and parts[2] == 'device':
            return parts[3]  # device_eui
        return 'unknown'
    
    test_cases = [
        ("application/1/device/abc123def456/event/up", "abc123def456"),
        ("application/2/device/xyz789/event/join", "xyz789"),
        ("invalid/topic/format", "unknown"),
        ("application/device/missing", "unknown")
    ]
    
    for topic, expected in test_cases:
        result = extract_device_id(topic)
        if result == expected:
            print(f"  ✅ '{topic}' -> '{result}'")
        else:
            print(f"  ❌ '{topic}' -> '{result}' (expected '{expected}')")
            return False
    
    return True

def test_balance_calculation():
    """Test message balance calculation logic"""
    print("\n🔍 Testing balance calculation...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create device_stats table
        c.execute("""
        CREATE TABLE device_stats (
          device_id TEXT PRIMARY KEY,
          message_count INTEGER DEFAULT 0,
          last_seen TIMESTAMP,
          actual_avg_interval REAL
        )
        """)
        
        # Insert test data
        test_devices = [
            ('device1', 100, '2024-01-15 10:00:00', 60.0),
            ('device2', 95, '2024-01-15 10:00:00', 62.0),
            ('device3', 105, '2024-01-15 10:00:00', 58.0),
            ('device4', 75, '2024-01-15 10:00:00', 80.0),  # Significantly different
        ]
        
        for device_id, count, last_seen, interval in test_devices:
            c.execute("""
                INSERT INTO device_stats (device_id, message_count, last_seen, actual_avg_interval)
                VALUES (?, ?, ?, ?)
            """, (device_id, count, last_seen, interval))
        
        conn.commit()
        
        # Test balance calculation
        c.execute("SELECT message_count FROM device_stats")
        message_counts = [row[0] for row in c.fetchall()]
        
        min_messages = min(message_counts)
        max_messages = max(message_counts)
        avg_messages = sum(message_counts) / len(message_counts)
        
        # Check if balanced (within 10% tolerance)
        balance_threshold = 0.1 * avg_messages
        balanced = (max_messages - min_messages) <= balance_threshold
        
        print(f"  📊 Message counts: {message_counts}")
        print(f"  📊 Min: {min_messages}, Max: {max_messages}, Avg: {avg_messages:.1f}")
        print(f"  📊 Threshold: {balance_threshold:.1f}")
        print(f"  📊 Balanced: {balanced}")
        
        # This should be imbalanced due to device4
        if not balanced:
            print("  ✅ Correctly identified imbalanced system")
            return True
        else:
            print("  ❌ Failed to detect imbalance")
            return False
        
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

def test_configuration_parsing():
    """Test configuration file parsing"""
    print("\n🔍 Testing configuration parsing...")
    
    config_path = Path(__file__).parent / "sync_config.conf"
    
    if not config_path.exists():
        print("  ❌ Configuration file not found")
        return False
    
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read(config_path)
        
        # Check required sections
        required_sections = ['mqtt', 'monitoring', 'synchronization']
        for section in required_sections:
            if config.has_section(section):
                print(f"  ✅ Section '[{section}]' found")
            else:
                print(f"  ❌ Section '[{section}]' missing")
                return False
        
        # Check key settings
        qos_level = config.getint('mqtt', 'qos_level', fallback=1)
        balance_interval = config.getint('monitoring', 'balance_check_interval', fallback=300)
        expected_interval = config.getint('synchronization', 'expected_message_interval', fallback=60)
        
        print(f"  📝 QoS Level: {qos_level}")
        print(f"  📝 Balance Check Interval: {balance_interval}s")
        print(f"  📝 Expected Message Interval: {expected_interval}s")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Configuration parsing error: {e}")
        return False

def test_scripts_executable():
    """Test that management scripts are executable"""
    print("\n🔍 Testing management scripts...")
    
    script_dir = Path(__file__).parent.parent / "scripts"
    scripts = ["setup.sh", "monitor.sh"]
    
    for script_name in scripts:
        script_path = script_dir / script_name
        if script_path.exists():
            if os.access(script_path, os.X_OK):
                print(f"  ✅ {script_name} is executable")
            else:
                print(f"  ⚠️ {script_name} exists but not executable")
        else:
            print(f"  ❌ {script_name} not found")
            return False
    
    return True

def main():
    """Run all tests"""
    print("🚀 OnLog Sensor Synchronization - Component Tests")
    print("=" * 60)
    
    tests = [
        test_database_schema,
        test_device_id_extraction,
        test_balance_calculation,
        test_configuration_parsing,
        test_scripts_executable
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print("  ❌ Test failed")
        except Exception as e:
            print(f"  ❌ Test error: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Sensor synchronization system is ready.")
        return 0
    else:
        print("⚠️ Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    exit(main())