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

## Установка агента

В web dashboard нажмите «Добавить устройство», укажите имя и платформу и
скопируйте сгенерированную команду.

Ubuntu/Debian и OpenWrt:

```bash
curl -fsSL https://monitor.example.com/install/ONE_TIME_CODE | sudo sh
```

Установщик определяет Ubuntu/Debian или OpenWrt, выполняет одноразовый enrollment,
настраивает `systemd` либо `procd` и запускает heartbeat каждые 60 секунд.
Для MikroTik RouterOS 7 dashboard формирует отдельную команду `/tool fetch` и
`.rsc`-установщик.

Перед установкой на внешних устройствах обязательно задайте публичный адрес:

```dotenv
CLS_PUBLIC_URL=https://monitor.example.com
```

Домен должен обслуживаться через HTTPS с валидным сертификатом. Bootstrap-код
действует 30 минут по умолчанию, хранится в БД только как SHA-256-хеш и
погашается при первой успешной регистрации.
