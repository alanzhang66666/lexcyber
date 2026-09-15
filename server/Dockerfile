FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /app
ARG MAVEN_MIRROR_URL=
RUN if [ -n "$MAVEN_MIRROR_URL" ]; then \
      mkdir -p /root/.m2 && \
      printf '%s\n' \
        "<settings><mirrors><mirror><id>configured-mirror</id><url>${MAVEN_MIRROR_URL}</url><mirrorOf>*</mirrorOf></mirror></mirrors></settings>" \
        > /root/.m2/settings.xml; \
    fi
COPY pom.xml .
COPY src src
RUN mvn -B package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/target/lexcyber-server-0.8.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
