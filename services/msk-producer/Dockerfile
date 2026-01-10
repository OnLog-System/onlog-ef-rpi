FROM maven:3.9.6-eclipse-temurin-17 AS build

WORKDIR /build
COPY pom.xml .
COPY src ./src

RUN mvn clean package

FROM eclipse-temurin:17-jdk-jammy

WORKDIR /app
COPY --from=build /build/target/msk-producer-1.0.0.jar app.jar

CMD ["java", "-jar", "app.jar"]
