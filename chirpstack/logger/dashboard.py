#!/usr/bin/env python3
"""
센서 동기화 상태 웹 대시보드
실시간으로 디바이스 동기화 상태를 웹에서 확인
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

DB_PATH = os.getenv("DB_PATH", "/data/sensor_logs.db")
PORT = int(os.getenv("DASHBOARD_PORT", "8082"))

class SyncDashboardHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == '/':
            self.serve_dashboard()
        elif self.path == '/api/stats':
            self.serve_stats_api()
        elif self.path == '/api/events':
            self.serve_events_api()
        else:
            self.send_error(404)
    
    def serve_dashboard(self):
        """메인 대시보드 HTML 제공"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Sensor Sync Monitor</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .device-list { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .device-item { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }
        .status-active { color: #27ae60; }
        .status-delayed { color: #f39c12; }
        .status-inactive { color: #e74c3c; }
        .events { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-top: 20px; }
        .event-item { padding: 8px 0; border-bottom: 1px solid #eee; font-size: 14px; }
        .refresh-btn { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #2980b9; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔄 Sensor Message Synchronization Monitor</h1>
            <p>실시간 센서 메시지 동기화 상태 모니터링</p>
            <button class="refresh-btn" onclick="refreshData()">🔄 Refresh</button>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>📊 총 디바이스</h3>
                <div id="totalDevices" style="font-size: 24px; font-weight: bold;">-</div>
            </div>
            <div class="stat-card">
                <h3>📈 평균 메시지/시간</h3>
                <div id="avgMessages" style="font-size: 24px; font-weight: bold;">-</div>
            </div>
            <div class="stat-card">
                <h3>⚖️ 불균형 비율</h3>
                <div id="imbalanceRatio" style="font-size: 24px; font-weight: bold;">-</div>
            </div>
            <div class="stat-card">
                <h3>🟢 활성 디바이스</h3>
                <div id="activeDevices" style="font-size: 24px; font-weight: bold;">-</div>
            </div>
        </div>
        
        <div class="device-list">
            <h3>📱 디바이스 상태</h3>
            <div id="deviceList">Loading...</div>
        </div>
        
        <div class="events">
            <h3>📝 최근 이벤트</h3>
            <div id="eventList">Loading...</div>
        </div>
    </div>
    
    <script>
        function refreshData() {
            fetchStats();
            fetchEvents();
        }
        
        function fetchStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('totalDevices').textContent = data.total_devices;
                    document.getElementById('avgMessages').textContent = data.avg_messages.toFixed(1);
                    document.getElementById('imbalanceRatio').textContent = (data.imbalance_ratio * 100).toFixed(1) + '%';
                    document.getElementById('activeDevices').textContent = data.active_devices;
                    
                    const deviceList = document.getElementById('deviceList');
                    deviceList.innerHTML = '';
                    
                    data.devices.forEach(device => {
                        const item = document.createElement('div');
                        item.className = 'device-item';
                        
                        const statusClass = device.status === 'active' ? 'status-active' : 
                                          device.status === 'delayed' ? 'status-delayed' : 'status-inactive';
                        
                        item.innerHTML = `
                            <span><strong>${device.id}</strong></span>
                            <span class="${statusClass}">${device.count} msgs (${device.last_seen})</span>
                        `;
                        deviceList.appendChild(item);
                    });
                })
                .catch(error => console.error('Error fetching stats:', error));
        }
        
        function fetchEvents() {
            fetch('/api/events')
                .then(response => response.json())
                .then(data => {
                    const eventList = document.getElementById('eventList');
                    eventList.innerHTML = '';
                    
                    data.events.forEach(event => {
                        const item = document.createElement('div');
                        item.className = 'event-item';
                        item.innerHTML = `
                            <strong>${event.time}</strong> | ${event.type} | ${event.message}
                        `;
                        eventList.appendChild(item);
                    });
                })
                .catch(error => console.error('Error fetching events:', error));
        }
        
        // 페이지 로드 시 데이터 가져오기
        window.onload = refreshData;
        
        // 30초마다 자동 새로고침
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_stats_api(self):
        """통계 API 엔드포인트"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            cutoff_time = datetime.now() - timedelta(hours=1)
            
            # 디바이스별 통계 조회
            c.execute("""
                SELECT 
                    SUBSTR(topic, 
                           LENGTH('application/') + 1,
                           INSTR(SUBSTR(topic, LENGTH('application/') + 1), '/') - 1) as device_id,
                    COUNT(*) as message_count,
                    MAX(received_at) as last_message
                FROM raw_logs 
                WHERE received_at > ? 
                AND topic LIKE 'application/%/%'
                GROUP BY device_id
                ORDER BY message_count DESC
            """, (cutoff_time.isoformat(),))
            
            device_stats = c.fetchall()
            conn.close()
            
            if device_stats:
                message_counts = [stat[1] for stat in device_stats]
                avg_messages = sum(message_counts) / len(message_counts)
                max_messages = max(message_counts)
                min_messages = min(message_counts)
                imbalance_ratio = (max_messages - min_messages) / avg_messages if avg_messages > 0 else 0
                
                devices = []
                active_count = 0
                
                for device_id, count, last_msg in device_stats:
                    last_msg_time = datetime.fromisoformat(last_msg.replace('Z', '+00:00').replace('+00:00', ''))
                    minutes_ago = int((datetime.now() - last_msg_time).total_seconds() / 60)
                    
                    if minutes_ago < 5:
                        status = 'active'
                        active_count += 1
                    elif minutes_ago < 15:
                        status = 'delayed'
                    else:
                        status = 'inactive'
                    
                    devices.append({
                        'id': device_id,
                        'count': count,
                        'status': status,
                        'last_seen': f"{minutes_ago}분 전"
                    })
                
                stats = {
                    'total_devices': len(device_stats),
                    'avg_messages': avg_messages,
                    'imbalance_ratio': imbalance_ratio,
                    'active_devices': active_count,
                    'devices': devices[:20]  # 상위 20개만
                }
            else:
                stats = {
                    'total_devices': 0,
                    'avg_messages': 0,
                    'imbalance_ratio': 0,
                    'active_devices': 0,
                    'devices': []
                }
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def serve_events_api(self):
        """이벤트 API 엔드포인트"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            try:
                c.execute("""
                    SELECT event_time, event_type, message
                    FROM sync_events 
                    WHERE event_time > ?
                    ORDER BY event_time DESC
                    LIMIT 20
                """, (cutoff_time.isoformat(),))
                
                events_data = c.fetchall()
                events = []
                
                for event_time, event_type, message in events_data:
                    events.append({
                        'time': event_time[:19],  # 초까지만
                        'type': event_type,
                        'message': message
                    })
            except sqlite3.OperationalError:
                events = []
            
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'events': events}).encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, str(e))

def main():
    """웹 서버 시작"""
    server = HTTPServer(('0.0.0.0', PORT), SyncDashboardHandler)
    print(f"🌐 Sensor Sync Dashboard starting on http://0.0.0.0:{PORT}")
    print(f"📊 Access dashboard at: http://localhost:{PORT}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down dashboard server...")
        server.shutdown()

if __name__ == "__main__":
    main()