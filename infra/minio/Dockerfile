# The original MinIO release images are no longer publicly pullable.
# Build the same upstream release, pinned to its signed tag's commit.
FROM golang:1.23.2-alpine AS build
RUN apk add --no-cache ca-certificates git
WORKDIR /src
RUN git init && \
    git remote add origin https://github.com/minio/minio.git && \
    git fetch --depth=1 origin d10bb7e1b667c2df72c394ef1fa52ab4a6802d0f && \
    git checkout --detach FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = d10bb7e1b667c2df72c394ef1fa52ab4a6802d0f
RUN CGO_ENABLED=0 go build -p 2 -trimpath \
    -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go 2024-10-13T13:34:11Z)" \
    -o /out/minio .

FROM alpine:3.20.3
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="d10bb7e1b667c2df72c394ef1fa52ab4a6802d0f" \
      org.opencontainers.image.version="RELEASE.2024-10-13T13-34-11Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /src/CREDITS /licenses/
RUN minio --version && mkdir /data
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
