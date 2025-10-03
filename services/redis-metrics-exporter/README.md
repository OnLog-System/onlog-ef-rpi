# 📘 Redis Metrics Exporter

## 📌 개요

ChirpStack이 Redis에 저장하는 게이트웨이/디바이스 메트릭을 **TTL 만료 전 SQLite DB로 내보내 장기 보관**하는 도구입니다.
추후 Kafka Sink로 교체할 수 있도록 JSON 포맷을 유지합니다.

---

## 🚀 주요 기능

* Redis `metrics:*` 키 자동 스캔 및 추출
* Gateway / Device / Granularity(HOUR, DAY, MONTH) 분류
* 원본 Hash → JSON 변환 후 SQLite 저장
* 중복 방지: `(ts, obj_type, obj_id, granularity)` 기본키 기반 `INSERT OR IGNORE`
* Docker Compose 서비스로 손쉽게 실행/관리

---

## 📂 디렉토리 구조

```
redis-metrics-exporter/
 ├─ app.py          # 메인 Exporter 코드
 ├─ Dockerfile      # 컨테이너 실행 정의
 └─ README.md       # 문서 (본 파일)
```

---

## ⚙️ 실행 방법

### Docker Compose

```yaml
redis-metrics-exporter:
  build: ./redis-metrics-exporter
  container_name: redis-metrics-exporter
  restart: unless-stopped
  depends_on:
    - redis
  environment:
    - REDIS_HOST=redis
    - REDIS_PORT=6379
    - DB_PATH=/data/redis_metrics.db
  volumes:
    - /mnt/nvme/infra/redis-metrics:/data
```

실행:

```bash
docker compose up -d redis-metrics-exporter
```

---

## 📊 SQLite 스키마

```sql
CREATE TABLE IF NOT EXISTS metrics (
    ts TEXT,
    obj_type TEXT,      -- gateway/device
    obj_id TEXT,        -- gw id or devEUI
    granularity TEXT,   -- HOUR/DAY/MONTH
    data TEXT,          -- JSON dump
    PRIMARY KEY (ts, obj_type, obj_id, granularity)
);
```

---

## 📑 데이터 포맷 예시

```json
{
  "ts": "2025-10-01T13:00:00Z",
  "type": "device",
  "id": "a840419f755da38c",
  "granularity": "HOUR",
  "metrics": {
    "rx_count": "60",
    "rx_dr_4": "60",
    "rx_freq_922500000": "16",
    "rx_freq_922300000": "28",
    "rx_freq_922100000": "16",
    "gw_rssi_sum": "-6279",
    "gw_snr_sum": "-473.25"
  }
}
```

---

## 🔮 향후 확장

* Kafka Producer로 Sink 교체 예정 (`producer.send("redis-metrics", data)`)
* 장기적으로 PostgreSQL/TimescaleDB 또는 S3(Parquet)와 연동 가능
