# 센서 메시지 동기화 모니터링

OnLog 시스템에 센서 메시지 동기화 문제를 감지하고 모니터링하는 기능이 추가되었습니다.

## 🎯 기능 개요

### 문제 상황
- 모든 센서가 동일한 시간에 동일한 수의 메시지를 전송해야 하나, 실제로는 디바이스 간 메시지 수가 불균형하게 발생
- MQTT Explorer에서 확인 시 디바이스별로 다른 메시지 수 확인됨

### 해결 방안
1. **실시간 동기화 모니터링**: MQTT 메시지 수신 시 디바이스별 카운트 및 간격 추적
2. **자동 불균형 감지**: 설정된 임계값을 초과하는 메시지 불균형 자동 탐지
3. **웹 대시보드**: 실시간 동기화 상태 시각화
4. **이벤트 로깅**: 동기화 관련 이벤트 기록 및 분석

## 🚀 새로운 구성 요소

### 1. 향상된 MQTT Logger (`app.py`)
- 디바이스별 메시지 카운트 추적
- 메시지 간격 분석
- 자동 불균형 감지 (기본값: 10% 임계값)
- QoS 1로 변경하여 메시지 유실 방지

### 2. 동기화 모니터링 스크립트 (`sync_monitor.py`)
```bash
# 동기화 상태 확인
python sync_monitor.py
```

### 3. 웹 대시보드 (`dashboard.py`)
- 실시간 디바이스 상태 모니터링
- 메시지 균형 분석
- 이벤트 로그 확인
- 접속: `http://raspberry-pi-ip:8082`

### 4. 개선된 MQTT 브로커 설정
- QoS 1,2 메시지를 위한 persistence 활성화
- 메시지 큐 및 연결 설정 최적화
- 상세 로깅 활성화

## 📊 모니터링 대시보드

### 접속 방법
```
http://YOUR-RPI-IP:8082
```

### 제공 정보
- **총 디바이스 수**: 활성 디바이스 개수
- **평균 메시지/시간**: 시간당 평균 메시지 수
- **불균형 비율**: 최대-최소 메시지 수 차이 비율
- **활성 디바이스**: 최근 5분 내 메시지 전송 디바이스 수
- **디바이스별 상태**: 실시간 메시지 수 및 마지막 활동 시간
- **최근 이벤트**: 동기화 관련 이벤트 로그

## ⚙️ 설정

### 환경 변수
```yaml
# MQTT Logger 설정
SYNC_CHECK_INTERVAL: 300        # 동기화 체크 주기 (초)
MESSAGE_BALANCE_THRESHOLD: 0.1  # 불균형 감지 임계값 (10%)

# 대시보드 설정  
DASHBOARD_PORT: 8082           # 웹 대시보드 포트
```

### 불균형 임계값 조정
기본값 10% 임계값은 다음과 같이 작동합니다:
- 평균 메시지 수: 100개
- 최대 메시지 수: 110개, 최소 메시지 수: 90개
- 불균형 비율: (110-90)/100 = 0.2 (20%)
- 20% > 10% 임계값이므로 불균형 감지

## 🔍 사용법

### 1. 실시간 모니터링
```bash
# 서비스 시작 후 로그 확인
docker logs -f mqtt-logger

# 수동 동기화 상태 확인
docker exec mqtt-logger python sync_monitor.py
```

### 2. 웹 대시보드 사용
1. 브라우저에서 `http://RPI-IP:8082` 접속
2. 실시간 디바이스 상태 확인
3. 불균형 감지 시 경고 표시 확인
4. 30초마다 자동 새로고침

### 3. 데이터베이스 직접 조회
```sql
-- 디바이스별 메시지 수 확인
SELECT 
  SUBSTR(topic, INSTR(topic, '/') + 1) as device_info,
  COUNT(*) as message_count,
  MAX(received_at) as last_message
FROM raw_logs 
WHERE topic LIKE 'application/%'
GROUP BY device_info
ORDER BY message_count DESC;

-- 동기화 이벤트 확인
SELECT * FROM sync_events 
ORDER BY event_time DESC 
LIMIT 20;
```

## 🎛️ 서비스 관리

### 시작/중지
```bash
# 전체 서비스 시작
cd chirpstack
docker compose up -d

# 로그 확인
docker logs -f mqtt-logger
docker logs -f sync-dashboard

# 서비스 재시작
docker compose restart mqtt-logger sync-dashboard
```

### 문제 해결
```bash
# 컨테이너 상태 확인
docker ps | grep -E "mqtt-logger|sync-dashboard"

# 데이터베이스 파일 확인
ls -la /mnt/nvme/infra/sqlite/

# 네트워크 연결 확인
docker exec mqtt-logger ping mosquitto
```

## 🚨 알림 및 경고

### 자동 감지 이벤트
- **IMBALANCE**: 메시지 불균형 감지
- **INACTIVE**: 10분 이상 메시지 없는 디바이스
- **DELAYED**: 예상 간격보다 지연된 메시지
- **SYSTEM**: 시스템 시작/종료 이벤트

### 상태 표시
- 🟢 **활성**: 5분 내 메시지 수신
- 🟡 **지연**: 5-15분 전 마지막 메시지
- 🔴 **비활성**: 15분 이상 메시지 없음

이제 센서 메시지 동기화 문제를 실시간으로 모니터링하고 자동으로 감지할 수 있습니다!