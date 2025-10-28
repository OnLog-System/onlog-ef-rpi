# Battery Monitor for LHT65N Devices

## 개요

이 모듈은 Dragino LHT65N LoRa 센서의 uplink payload를 디코딩하여 배터리 전압(mV) 및 상태를 계산하는 유틸리티입니다.  
센서가 ChirpStack → SQLite 로 저장한 `event/up` 로그를 기반으로 작동하며,  
PostgreSQL 내 `battery_level` 필드와 실제 payload 간의 불일치를 검증하는 목적으로 설계되었습니다.

이번 버전에서는 다음 기능이 추가되었습니다:

- `recent <N>` 옵션: 지정한 센서의 최근 N개 데이터를 조회  
- `all` 옵션: 모든 센서의 최신 배터리 상태를 한눈에 확인  
- UTC → KST 변환 적용 및 출력에 시간 컬럼 추가  

---

## 구조

services/  
 ├─ battery-monitor/  
 │   ├─ monitor_battery.py  
 │   ├─ devices.json  
 │   └─ README.md  

---

## 실행 방법

### 1️⃣ 사전 조건

- `/mnt/nvme/infra/sqlite/` 경로에 `sensor_logs.db` 또는 `raw_logs` 테이블이 존재해야 함  
- Python 3.8 이상 환경에서 실행 가능  
- `devices.json` 파일에 각 센서의 DevEUI 정보 등록 필요  

### 2️⃣ 실행 명령

기본 실행:
python3 monitor_battery.py <센서번호>

예시:
python3 monitor_battery.py 05

최근 N개 조회:
python3 monitor_battery.py 05 recent 20

모든 센서 최신 상태 조회:
python3 monitor_battery.py all

---

## 출력 예시

센서 05 | DevEUI: a840412db25da383  

일자         시간       Payload(Base64)           Hex(BAT)   전압(mV)   배터리(%)   상태  
--------------------------------------------------------------------------------  
2025-09-25   11:12:30   zBoJbgGeAX//f/8=          0xCC1A     3098       100        Good  
2025-09-24   10:55:02   ScUIpwHXAX//f/8=          0x49C5     2501       0          Low  

모든 센서 조회(`all` 모드):

센서   일자         시간       전압(mV)   배터리(%)   상태       Payload(Base64)  
--------------------------------------------------------------------------------  
01     2025-09-25   11:19:30   2979       95          Good       y+UJbgJCAX//f/8=  
02     2025-09-25   11:19:29   2810       62          OK         y+UJbgJEAX//f/8=  
03     2025-09-25   11:19:28   2601       20          Low        y+UJbgJDAX//f/8=  

---

## 내부 동작

1. SQLite DB에서 지정한 DevEUI 또는 모든 센서의 최신 `event/up` 데이터 조회  
2. Base64 → Hex 변환 후 상위 2비트 / 하위 14비트로 분리  
3. LHT65N 공식 디코딩 규칙 적용  
   - status_code = (BAT >> 14) & 0x03  
   - voltage_mv = BAT & 0x3FFF  
4. 전압 2.5V~3.0V 구간을 0~100% 선형 비율로 변환  
5. UTC → KST 변환 후 결과를 표 형태로 출력  

---

## devices.json 구조

[
  { "devEui": "a84041f3275da38b", "name": "EF-LHT65N-01" },
  { "devEui": "a840419f755da38c", "name": "EF-LHT65N-02" },
  ...
]

센서 번호는 순서대로 매핑되어 있으며, 실행 시 인자로 전달됩니다.

---

## 전압 → 퍼센트 변환 기준

| 구간 | 전압(V)  | 배터리 상태          | 비율(%) |
|------|-----------|---------------------|---------|
| 상한 | 3.0 V     | Good               | 100 %   |
| 중간 | 2.75 V    | OK                 | 50 %    |
| 하한 | 2.5 V     | Low / Ultra-Low    | 0 %     |

---

## 활용 사례

- LoRa 센서 배터리 급락 원인 분석  
- ChirpStack/PostgreSQL의 `battery_level` 필드 검증  
- Redis metrics와 결합하여 센서별 상태 보고서 생성  
- 모든 센서의 배터리 상태 모니터링 자동화  

---

## 참고

- Dragino LHT65N-E3 KR920 공식 문서  
- ChirpStack v4 Decoder 구현부 (`BatV = ((bytes[0]<<8 | bytes[1]) & 0x3FFF) / 1000`)
