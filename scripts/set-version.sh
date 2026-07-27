#!/bin/sh
set -eu

new_version=${1:-}
if ! printf '%s\n' "$new_version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$'; then
  echo "ERROR: задайте SemVer в формате X.Y.Z, например NEW_VERSION=0.3.0" >&2
  exit 2
fi

printf '%s\n' "$new_version" > VERSION
echo "Версия сервиса установлена: $new_version"
