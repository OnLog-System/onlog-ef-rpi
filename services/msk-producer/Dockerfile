FROM eclipse-temurin:17-jdk-jammy

# ---- CA 인증서 (MSK TLS 필수) ----
RUN apt-get update && \
    apt-get install -y ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 라이브러리 및 소스 복사
COPY libs ./libs
COPY src ./src

# 컴파일
RUN javac -cp "libs/*" src/MskProducer.java

# 실행
CMD ["java", "-cp", "src:libs/*", "MskProducer"]
