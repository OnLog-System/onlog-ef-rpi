FROM eclipse-temurin:17-jdk-jammy

# TLS (MSK 필수)
RUN apt-get update && \
    apt-get install -y ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY libs ./libs
COPY src ./src

# 컴파일 결과를 /app/classes 로 고정
RUN mkdir -p classes && \
    javac -cp "libs/*" -d classes src/MskProducer.java

CMD ["java", "-cp", "classes:libs/*", "MskProducer"]
