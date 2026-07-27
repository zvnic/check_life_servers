#!/bin/sh
set -eu

source_version=$(tr -d '\r\n' < VERSION)
runtime_version=$(docker compose exec -T api python -c \
  'from app.version import __version__; print(__version__)')
package_version=$(docker compose exec -T api python -c \
  'from importlib.metadata import version; print(version("check-life-servers"))')

if [ "$source_version" != "$runtime_version" ] || [ "$source_version" != "$package_version" ]; then
  echo "ERROR: обнаружено расхождение версий" >&2
  echo "source=$source_version runtime=$runtime_version package=$package_version" >&2
  exit 1
fi

echo "OK: source=runtime=package=$source_version"

