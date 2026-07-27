#!/bin/sh
set -eu

compose_file=tests/e2e/compose.yaml
project=cls-device-e2e
keep="${KEEP_E2E:-0}"

compose() {
  docker compose -p "$project" -f "$compose_file" "$@"
}

cleanup() {
  if [ "$keep" = "1" ]; then
    echo "KEEP_E2E=1: тестовый стенд оставлен запущенным"
  else
    compose down --volumes --remove-orphans
  fi
}
trap cleanup EXIT INT TERM

token_for() {
  platform=$1
  name=$2
  compose exec -T api python -m app.cli enrollment-create \
    --server-name "$name" --platform "$platform" \
    | sed -n 's/^Enrollment token (показывается один раз): //p'
}

install_agent() {
  service=$1
  token=$2
  compose exec -T "$service" sh -c \
    "curl -fsSL 'http://frontend:8080/install/$token' | CLS_HEARTBEAT_INTERVAL=5 sh"
}

echo "[1/7] Сборка изолированного monitoring stack и образов устройств"
compose build

echo "[2/7] Запуск PostgreSQL, API, reverse proxy и устройств"
compose up -d db api frontend ubuntu-device openwrt-device

echo "[3/7] Миграции из только что собранного API image"
compose exec -T api alembic upgrade head

echo "[4/7] Создание одноразовых enrollment tokens"
ubuntu_token=$(token_for ubuntu e2e-ubuntu)
openwrt_token=$(token_for openwrt e2e-openwrt)
test -n "$ubuntu_token"
test -n "$openwrt_token"

echo "[5/7] Установка тем же curl | sh, который используется на устройствах"
install_agent ubuntu-device "$ubuntu_token"
install_agent openwrt-device "$openwrt_token"

echo "[6/7] Проверка менеджеров сервисов и защищённых credentials"
compose exec -T ubuntu-device systemctl is-active --quiet cls-agent
compose exec -T openwrt-device /etc/init.d/cls-agent enabled
compose exec -T ubuntu-device sh -c \
  'test "$(stat -c %a /var/lib/cls-agent/credentials)" = 600'
compose exec -T openwrt-device sh -c \
  'test "$(ls -l /var/lib/cls-agent/credentials | cut -c1-10)" = "-rw-------"'

echo "Ожидание нескольких heartbeat (интервал E2E: 5 секунд)"
attempt=0
until compose exec -T api python -m tests.e2e.verify_devices; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 12 ]; then
    echo "ERROR: устройства не передали ожидаемые heartbeat/метрики" >&2
    compose logs --no-color api ubuntu-device openwrt-device
    exit 1
  fi
  sleep 2
done

echo "[7/7] Полный E2E успешно завершён"
