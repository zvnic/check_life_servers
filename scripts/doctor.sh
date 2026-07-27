#!/bin/sh
set -eu

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: Docker не найден" >&2
  exit 1
}
docker compose version >/dev/null
test -f .env || {
  echo "ERROR: отсутствует .env; выполните make env" >&2
  exit 1
}
docker compose config --quiet
echo "OK: Docker Compose и конфигурация доступны"

