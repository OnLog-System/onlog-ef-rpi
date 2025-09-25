#!/bin/bash
#
# Device Message Synchronization Monitor Script
# Quick access to monitoring and diagnostic tools
#

set -e

CONTAINER_NAME="mqtt-logger"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHIRPSTACK_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if container is running
check_container() {
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo -e "${RED}❌ Container $CONTAINER_NAME is not running${NC}"
        echo -e "${BLUE}💡 Start it with: cd $CHIRPSTACK_DIR && docker-compose up -d mqtt-logger${NC}"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "🚀 OnLog Device Message Synchronization Monitor"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  dashboard     Show device status dashboard"
    echo "  balance       Check current message balance"
    echo "  correct       Run auto-correction analysis"
    echo "  logs          Show recent logger logs"
    echo "  stats         Show database statistics"
    echo "  tail          Follow logger logs in real-time"
    echo "  cleanup       Clean old database entries"
    echo "  export        Export device data to CSV"
    echo "  status        Show container and service status"
    echo ""
    echo "Examples:"
    echo "  $0 dashboard      # Show full monitoring dashboard"
    echo "  $0 balance        # Quick balance check"
    echo "  $0 logs           # View recent activity"
}

# Show service status
show_status() {
    echo -e "${BLUE}📊 Service Status${NC}"
    echo "================================="
    
    if docker ps | grep -q "$CONTAINER_NAME"; then
        echo -e "${GREEN}✅ MQTT Logger: Running${NC}"
        
        # Get container stats
        echo ""
        echo "Container Stats:"
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" "$CONTAINER_NAME"
        
        # Check log for recent activity
        echo ""
        echo "Recent Activity:"
        docker logs "$CONTAINER_NAME" --tail 3 2>/dev/null || echo "No recent logs available"
    else
        echo -e "${RED}❌ MQTT Logger: Stopped${NC}"
    fi
    
    echo ""
    echo "Related Services:"
    docker-compose -f "$CHIRPSTACK_DIR/docker-compose.yml" ps mosquitto chirpstack postgres 2>/dev/null || \
        echo "Could not check related services"
}

# Show dashboard
show_dashboard() {
    echo -e "${BLUE}📊 Loading Device Message Dashboard...${NC}"
    docker exec -it "$CONTAINER_NAME" python monitor_dashboard.py
}

# Quick balance check
quick_balance() {
    echo -e "${BLUE}⚖️ Quick Balance Check${NC}"
    echo "========================"
    
    docker exec "$CONTAINER_NAME" python -c "
import sqlite3
from datetime import datetime

conn = sqlite3.connect('/data/sensor_logs.db')
c = conn.cursor()

# Get latest balance result
c.execute('SELECT balanced, total_devices, avg_messages FROM message_balance_log ORDER BY check_time DESC LIMIT 1')
result = c.fetchone()

if result:
    balanced, devices, avg_msg = result
    status = '✅ BALANCED' if balanced else '⚠️ IMBALANCED'
    print(f'{status} - {devices} devices, avg {avg_msg:.1f} messages')
else:
    print('⚠️ No balance checks available yet')

conn.close()
"
}

# Run auto-correction
run_correction() {
    echo -e "${BLUE}🔧 Running Auto-Correction Analysis...${NC}"
    docker exec -it "$CONTAINER_NAME" python auto_corrector.py
}

# Show recent logs
show_logs() {
    echo -e "${BLUE}📋 Recent Logger Activity${NC}"
    echo "============================"
    docker logs "$CONTAINER_NAME" --tail 50
}

# Follow logs
tail_logs() {
    echo -e "${BLUE}📋 Following Logger Activity (Ctrl+C to stop)${NC}"
    echo "==============================================="
    docker logs -f "$CONTAINER_NAME"
}

# Database statistics
show_stats() {
    echo -e "${BLUE}📈 Database Statistics${NC}"
    echo "======================"
    
    docker exec "$CONTAINER_NAME" python -c "
import sqlite3
from datetime import datetime

conn = sqlite3.connect('/data/sensor_logs.db')
c = conn.cursor()

# Total messages
c.execute('SELECT COUNT(*) FROM raw_logs')
total_msgs = c.fetchone()[0]
print(f'📨 Total Messages: {total_msgs:,}')

# Active devices
c.execute('SELECT COUNT(*) FROM device_stats WHERE last_seen > datetime(\"now\", \"-1 hour\")')
active_devices = c.fetchone()[0]
print(f'📱 Active Devices (last hour): {active_devices}')

# Balance checks
c.execute('SELECT COUNT(*) FROM message_balance_log')
balance_checks = c.fetchone()[0]
print(f'⚖️ Balance Checks Performed: {balance_checks}')

# Database size
import os
if os.path.exists('/data/sensor_logs.db'):
    size_mb = os.path.getsize('/data/sensor_logs.db') / (1024 * 1024)
    print(f'💾 Database Size: {size_mb:.1f} MB')

conn.close()
"
}

# Clean old data
cleanup_data() {
    echo -e "${YELLOW}🧹 Cleaning Old Database Entries${NC}"
    echo "=================================="
    
    read -p "Remove raw logs older than 7 days? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker exec "$CONTAINER_NAME" python -c "
import sqlite3

conn = sqlite3.connect('/data/sensor_logs.db')
c = conn.cursor()

# Count before cleanup
c.execute('SELECT COUNT(*) FROM raw_logs WHERE received_at < datetime(\"now\", \"-7 days\")')
old_count = c.fetchone()[0]

if old_count > 0:
    c.execute('DELETE FROM raw_logs WHERE received_at < datetime(\"now\", \"-7 days\")')
    conn.commit()
    print(f'🗑️ Removed {old_count:,} old log entries')
    
    # Vacuum database
    c.execute('VACUUM')
    print('✅ Database optimized')
else:
    print('✅ No old entries to remove')

conn.close()
"
    else
        echo "Cleanup cancelled"
    fi
}

# Export data
export_data() {
    echo -e "${BLUE}📤 Exporting Device Data${NC}"
    echo "========================"
    
    OUTPUT_DIR="/tmp/onlog-exports"
    mkdir -p "$OUTPUT_DIR"
    
    docker exec "$CONTAINER_NAME" python -c "
import sqlite3
import csv
from datetime import datetime

conn = sqlite3.connect('/data/sensor_logs.db')
c = conn.cursor()

# Export device stats
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
filename = f'/tmp/device_stats_{timestamp}.csv'

c.execute('''
    SELECT device_id, message_count, actual_avg_interval, 
           datetime(last_seen, 'localtime'), status, 
           datetime(created_at, 'localtime')
    FROM device_stats 
    ORDER BY message_count DESC
''')

with open(filename, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['Device ID', 'Message Count', 'Avg Interval (s)', 
                     'Last Seen', 'Status', 'First Seen'])
    writer.writerows(c.fetchall())

print(f'✅ Device stats exported to {filename}')
conn.close()
"
    
    # Copy from container to host
    docker cp "$CONTAINER_NAME:/tmp/device_stats_$(date +%Y%m%d_%H%M%S).csv" "$OUTPUT_DIR/" 2>/dev/null || \
        echo "Note: Export file remains in container at /tmp/"
    
    echo -e "${GREEN}📁 Export completed${NC}"
}

# Main script logic
main() {
    case "${1:-}" in
        "dashboard")
            check_container
            show_dashboard
            ;;
        "balance")
            check_container
            quick_balance
            ;;
        "correct")
            check_container
            run_correction
            ;;
        "logs")
            check_container
            show_logs
            ;;
        "tail")
            check_container
            tail_logs
            ;;
        "stats")
            check_container
            show_stats
            ;;
        "cleanup")
            check_container
            cleanup_data
            ;;
        "export")
            check_container
            export_data
            ;;
        "status")
            show_status
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        "")
            show_usage
            ;;
        *)
            echo -e "${RED}❌ Unknown command: $1${NC}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

main "$@"