# Check Life Servers

Система мониторинга доступности и состояния удалённых серверов, роутеров и
Docker-хостов через исходящие heartbeat-запросы.

Dashboard разделяет оперативный обзор и диагностику:

- «Обзор» — uptime-таймлайн с точными интервалами недоступности за 24 часа,
  7 или 30 дней;
- «Объекты» — текущий статус, uptime и суммарный простой каждого устройства;
- «Инциденты» — устройства, heartbeat которых перестал поступать;
- «Аналитика» — ресурсы, Docker, сеть и задержка heartbeat выбранного устройства.

План дальнейшего развития находится в
[`docs/monitoring-roadmap.md`](docs/monitoring-roadmap.md).

## Быстрый старт

```bash
make env
# случайный пароль PostgreSQL будет создан и согласован автоматически
# настройте CLS_PUBLIC_URL, WEB_BIND_ADDRESS и WEB_PORT в .env
make build
make up
make admin-create
```

Web dashboard: <http://127.0.0.1:8080>

OpenAPI через reverse proxy: <http://127.0.0.1:8080/docs>

Порт и адрес публикации web-панели задаются в `.env`:

```dotenv
WEB_BIND_ADDRESS=127.0.0.1
WEB_PORT=8080
```

По умолчанию панель доступна только с самого сервера. Для production-домена
рекомендуется оставить `127.0.0.1` и направить внешний HTTPS reverse proxy на
`127.0.0.1:${WEB_PORT}`. Значение `0.0.0.0` открывает порт на всех интерфейсах
и должно использоваться только при осознанно настроенном firewall.

PostgreSQL и API не публикуют порты на хост: web-контейнер обращается к ним по
внутренним Docker-сетям.

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

## Полный тест агентов перед deployment

Команда создаёт отдельный временный stack с PostgreSQL, API, reverse proxy,
Ubuntu 24.04 и OpenWrt 24.10.8. На оба устройства агент устанавливается
настоящей командой `curl | sh`. Проверяются systemd/procd, права credentials,
несколько heartbeat, системные метрики и единая версия агента.

```bash
make test-devices
```

После теста контейнеры, сеть и тестовая БД удаляются автоматически. Для
диагностики неуспешного прогона стенд можно временно сохранить:

```bash
KEEP_E2E=1 make test-devices
docker compose -p cls-device-e2e -f tests/e2e/compose.yaml down --volumes
```
