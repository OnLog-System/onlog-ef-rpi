FROM python:3.11-slim

# 비필수지만 locale 설정 (로그 한글 깨짐 방지)
ENV LANG=C.UTF-8

WORKDIR /app

# requirements.txt로 의존성 관리
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY app.py .
COPY sync_monitor.py .
COPY dashboard.py .

# 로그 전용 user 생성 (root 아님)
RUN adduser --disabled-password --gecos "" logger
USER logger

# healthcheck: DB 파일 쓰기 가능 여부 확인
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD test -w /data || exit 1

CMD ["python", "app.py"]
