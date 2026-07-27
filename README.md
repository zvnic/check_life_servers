# Check Life Servers

Система мониторинга доступности удалённых серверов через исходящие heartbeat-запросы.

## Быстрый старт

```bash
make env
# замените POSTGRES_PASSWORD и пароль в DATABASE_URL в .env
make build
make up
make admin-create
```

Web dashboard: <http://127.0.0.1:8080>

OpenAPI через reverse proxy: <http://127.0.0.1:8080/docs>

## Версия

Единственный источник версии — файл `VERSION`. Backend, Python package metadata,
OpenAPI и dashboard получают значение из него.

```bash
make version
make version-check
make version-set NEW_VERSION=0.3.0
make build
make restart
```

Все backend-команды, миграции и тесты выполняются в Docker. Полное техническое
задание находится в `tz_server_availability_monitoring.md`.

Одноразовая регистрация устройства:

```bash
make enrollment-create SERVER_NAME=edge-01 PLATFORM=ubuntu
```
