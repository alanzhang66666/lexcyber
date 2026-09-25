#!/usr/bin/env bash
set -Eeuo pipefail
curl --fail --silent --show-error http://127.0.0.1:8080/healthz > /dev/null
curl --fail --silent --show-error http://127.0.0.1:8100/healthz > /dev/null
