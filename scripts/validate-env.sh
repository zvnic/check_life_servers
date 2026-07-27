#!/bin/sh
set -eu

env_file=${1:-.env}
test -f "$env_file" || {
  echo "ERROR: отсутствует $env_file; выполните make env" >&2
  exit 1
}

value_of() {
  key=$1
  sed -n "s/^${key}=//p" "$env_file" | tail -n 1
}

postgres_db=$(value_of POSTGRES_DB)
postgres_user=$(value_of POSTGRES_USER)
postgres_password=$(value_of POSTGRES_PASSWORD)
database_url=$(value_of DATABASE_URL)

test -n "$postgres_db" || postgres_db=cls
test -n "$postgres_user" || postgres_user=cls

if [ -z "$postgres_password" ]; then
  echo "ERROR: POSTGRES_PASSWORD отсутствует или пуст" >&2
  exit 1
fi

expected_url="postgresql+psycopg://${postgres_user}:${postgres_password}@db:5432/${postgres_db}"
if [ "$database_url" != "$expected_url" ]; then
  echo "ERROR: пароль или реквизиты в DATABASE_URL не совпадают с POSTGRES_*" >&2
  echo "Безопаснее пересоздать конфигурацию: mv .env .env.backup && make env" >&2
  exit 1
fi

echo "OK: POSTGRES_* и DATABASE_URL согласованы"
