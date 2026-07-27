#!/bin/sh
set -eu

target=${1:-.env}
template=${2:-.env.example}

if [ -e "$target" ]; then
  echo "ERROR: $target уже существует; файл не перезаписан" >&2
  echo "Для пересоздания сначала сохраните его: mv $target $target.backup" >&2
  exit 2
fi

command -v openssl >/dev/null 2>&1 || {
  echo "ERROR: для генерации секретов требуется openssl" >&2
  exit 1
}
test -f "$template" || {
  echo "ERROR: шаблон $template не найден" >&2
  exit 1
}

postgres_password=$(openssl rand -hex 32)
temporary="${target}.tmp.$$"
trap 'rm -f "$temporary"' EXIT INT TERM
umask 077

sed \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$postgres_password|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://cls:$postgres_password@db:5432/cls|" \
  "$template" > "$temporary"

chmod 600 "$temporary"
mv "$temporary" "$target"
trap - EXIT INT TERM

echo "$target создан с новым случайным паролем PostgreSQL."
echo "Настройте CLS_PUBLIC_URL, WEB_BIND_ADDRESS и WEB_PORT."
