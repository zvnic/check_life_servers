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

API: <http://127.0.0.1:8000/docs>

Все backend-команды, миграции и тесты выполняются в Docker. Полное техническое
задание находится в `tz_server_availability_monitoring.md`.

Одноразовая регистрация устройства:

```bash
make enrollment-create SERVER_NAME=edge-01 PLATFORM=ubuntu
```
