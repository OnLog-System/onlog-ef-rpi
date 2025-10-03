FROM python:3.11-slim

WORKDIR /app

# 필요한 라이브러리만 설치
RUN pip install --no-cache-dir redis

# 앱 코드 복사
COPY app.py .

# 로그 전용 user 생성 (root 아님)
RUN adduser --disabled-password --gecos "" logger
USER logger

# healthcheck: DB 파일 쓰기 가능 여부 확인
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD test -w /data || exit 1

CMD ["python", "app.py"]