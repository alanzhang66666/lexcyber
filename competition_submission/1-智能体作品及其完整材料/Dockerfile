FROM node:22-bookworm AS web-build
WORKDIR /build/web
ARG NPM_REGISTRY=https://registry.npmjs.org
COPY src/web/package*.json ./
RUN npm config set registry "$NPM_REGISTRY" \
    && npm ci
COPY src/web/ ./
RUN npm run build

FROM maven:3.9.9-eclipse-temurin-21 AS java-build
WORKDIR /build/server
ARG MAVEN_MIRROR_URL=
COPY src/server/pom.xml ./
RUN if [ -n "$MAVEN_MIRROR_URL" ]; then \
      mkdir -p /root/.m2 && printf '%s\n' \
      "<settings><mirrors><mirror><id>configured-mirror</id><url>${MAVEN_MIRROR_URL}</url><mirrorOf>*</mirrorOf></mirror></mirrors></settings>" \
      > /root/.m2/settings.xml; \
    fi \
    && mvn -B dependency:go-offline
COPY src/server/src ./src
RUN mvn -B package -DskipTests

FROM python:3.12-slim-bookworm AS python-build
WORKDIR /build/src
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
COPY src/ ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/lexcyber/src \
    SERVER_PORT=8081 \
    PATH=/opt/lexcyber/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl nginx openjdk-21-jre-headless postgresql-16 redis-server supervisor \
       python3.12 python3.12-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://repo1.maven.org/maven2/org/flywaydb/flyway-commandline/10.20.1/flyway-commandline-10.20.1-linux-x64.tar.gz" \
    | tar -xz -C /opt \
    && mv /opt/flyway-* /opt/flyway

WORKDIR /opt/lexcyber
COPY --from=java-build /build/server/target/lexcyber-server-0.8.0-SNAPSHOT.jar /opt/lexcyber/server.jar
COPY --from=web-build /build/web/dist /opt/lexcyber/web
COPY --from=python-build /wheels /opt/lexcyber/wheels
COPY src/ /opt/lexcyber/src/
COPY prompts/ /opt/lexcyber/prompts/
COPY knowledge/ /opt/lexcyber/knowledge/
COPY container/ /opt/lexcyber/container/

RUN python3.12 -m venv /opt/lexcyber/venv \
    && /opt/lexcyber/venv/bin/pip install --no-index --find-links=/opt/lexcyber/wheels lex-multi-agent-backend \
    && rm -rf /opt/lexcyber/wheels \
    && chmod +x /opt/lexcyber/container/*.sh \
    && mkdir -p /data /var/log/supervisor /run/redis \
    && chown -R postgres:postgres /data

COPY .env.example /opt/lexcyber/.env.example
COPY container/supervisord.conf /etc/supervisor/conf.d/lexcyber.conf
COPY container/nginx.conf /etc/nginx/sites-enabled/default

EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=12 \
  CMD ["/opt/lexcyber/container/healthcheck.sh"]
ENTRYPOINT ["/opt/lexcyber/container/entrypoint.sh"]
