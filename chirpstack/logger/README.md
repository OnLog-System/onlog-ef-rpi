# Sensor Message Synchronization Guide

## Overview

The OnLog system now includes advanced sensor message synchronization features to ensure all IoT devices send messages at uniform intervals and maintain balanced data collection.

## Features

### 1. Enhanced Message Logging
- **QoS 1 Reliability**: MQTT messages use QoS 1 for acknowledged delivery
- **Device Tracking**: Individual device message counting and timing analysis
- **Message Statistics**: Real-time calculation of intervals and patterns

### 2. Automatic Balance Monitoring
- **Periodic Checks**: Automated balance verification every 5 minutes (configurable)
- **Imbalance Detection**: Identifies devices sending too many or too few messages
- **Historical Tracking**: Complete history of balance check results

### 3. Auto-Correction System
- **Problem Detection**: Automatically identifies problematic devices
- **Severity Classification**: Categorizes issues as critical, warning, or minor
- **Corrective Actions**: Provides specific recommendations for each device

### 4. Monitoring Dashboard
- **Real-time Status**: Live view of all device message counts and timing
- **Balance History**: Historical view of system balance over time
- **Device Health**: Status indicators for each device (active, stale, offline)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QOS_LEVEL` | 1 | MQTT QoS level (0, 1, or 2) |
| `BALANCE_CHECK_INTERVAL` | 300 | Seconds between balance checks |
| `DB_PATH` | /data/sensor_logs.db | SQLite database file path |

### Configuration File

Edit `chirpstack/logger/sync_config.conf` to customize:

```ini
[synchronization]
# Expected message interval for all devices (seconds)
expected_message_interval = 60

# Tolerance for message timing deviation (seconds)
timing_tolerance = 10

[monitoring]
# Threshold for considering devices as imbalanced (percentage)
balance_threshold = 0.10
```

## Usage

### Running the System

1. **Start the enhanced logger**:
   ```bash
   cd chirpstack
   docker-compose up -d mqtt-logger
   ```

2. **Monitor device status**:
   ```bash
   docker exec -it mqtt-logger python monitor_dashboard.py
   ```

3. **Run auto-correction analysis**:
   ```bash
   docker exec -it mqtt-logger python auto_corrector.py
   ```

### Dashboard Output Example

```
📊 DEVICE MESSAGE STATUS
╒══════════════════╤══════════╤═══════════════╤═══════════════════╤═══════════╤══════════════╕
│ Device ID        │ Messages │ Avg Interval  │ Last Seen         │ Status    │ Seconds Ago  │
╞══════════════════╪══════════╪═══════════════╪═══════════════════╪═══════════╪══════════════╡
│ 1234567890ab...  │      145 │ 58.2s         │ 2024-01-15 10:30  │ 🟢 ACTIVE │ 45s          │
│ 2345678901bc...  │      142 │ 61.1s         │ 2024-01-15 10:29  │ 🟢 ACTIVE │ 78s          │
│ 3456789012cd...  │      118 │ 72.5s         │ 2024-01-15 10:25  │ 🟡 STALE  │ 312s         │
╘══════════════════╧══════════╧═══════════════╧═══════════════════╧═══════════╧══════════════╛
```

## Database Schema

### New Tables

#### `device_stats`
- `device_id`: Unique device identifier
- `message_count`: Total messages received
- `actual_avg_interval`: Running average of message intervals
- `status`: Current device status (active/stale/offline)
- `last_seen`: Timestamp of last received message

#### `message_balance_log`
- `check_time`: When the balance check was performed
- `balanced`: Whether the system was balanced
- `min_messages`, `max_messages`, `avg_messages`: Statistics
- `details`: JSON with detailed device information

#### `device_corrections`
- `device_id`: Device requiring correction
- `severity`: Issue severity (critical/warning/minor)
- `actions`: JSON list of recommended actions
- `status`: Action status (pending/completed)

## Troubleshooting

### Common Issues

#### 1. Messages Not Balanced
**Symptoms**: Dashboard shows imbalanced devices
**Solutions**:
- Check device configuration for consistent intervals
- Verify network connectivity for all devices
- Review LoRaWAN coverage areas

#### 2. Devices Appearing Offline
**Symptoms**: Devices show as stale or offline
**Solutions**:
- Check power status of battery-powered devices
- Verify LoRaWAN gateway connectivity
- Review device transmission schedules

#### 3. High Message Intervals
**Symptoms**: Devices sending messages too slowly
**Solutions**:
- Check device power management settings
- Verify ADR (Adaptive Data Rate) settings
- Review network congestion

### Diagnostic Commands

```bash
# View recent logs
docker logs mqtt-logger --tail 50

# Check database contents
docker exec -it mqtt-logger sqlite3 /data/sensor_logs.db "SELECT * FROM device_stats;"

# Run balance check manually
docker exec -it mqtt-logger python -c "
from app import check_message_balance
check_message_balance()
"
```

## Performance Optimization

### For Large Deployments

1. **Increase Balance Check Interval**:
   ```env
   BALANCE_CHECK_INTERVAL=600  # 10 minutes for 100+ devices
   ```

2. **Database Maintenance**:
   ```bash
   # Regular cleanup of old data
   docker exec -it mqtt-logger sqlite3 /data/sensor_logs.db "
   DELETE FROM raw_logs WHERE received_at < datetime('now', '-7 days');
   VACUUM;
   "
   ```

3. **Monitoring Resource Usage**:
   ```bash
   docker stats mqtt-logger
   ```

## Integration with ChirpStack

### Device Profile Settings

Ensure consistent settings across all devices:

- **Class**: Class A (recommended)
- **MAC Version**: LoRaWAN 1.0.3 or later
- **Regional Parameters**: Match your region
- **ADR**: Disabled for consistent timing
- **Frame Counter Validation**: Enabled

### Application Settings

Configure applications for optimal synchronization:

- **Payload Codecs**: Consistent across all devices
- **Integrations**: MQTT integration enabled
- **Downlink Queue**: Monitor for acknowledgments

## Monitoring Alerts

### Setting Up Notifications

Future implementation will include:

- Email alerts for critical imbalances
- Webhook notifications for device offline events
- Dashboard API for external monitoring systems

### Alert Thresholds

Current thresholds (configurable in `sync_config.conf`):

- **Balance Threshold**: 10% deviation triggers warning
- **Critical Imbalance**: 25% deviation triggers critical alert
- **Device Timeout**: 5 minutes for stale, 1 hour for offline

## Best Practices

1. **Regular Monitoring**: Check dashboard at least daily
2. **Proactive Maintenance**: Run auto-corrector weekly
3. **Device Consistency**: Use identical configurations for same device types
4. **Network Monitoring**: Monitor LoRaWAN gateway health
5. **Data Retention**: Clean up old logs regularly

## Support

For additional support:
- Review system logs with `docker logs mqtt-logger`
- Check ChirpStack device event logs
- Monitor MQTT broker logs for connection issues
- Use the monitoring dashboard for real-time insights