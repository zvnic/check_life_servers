# ruff: noqa: E501

import shlex

from app.version import __version__


def linux_installer(public_url: str, enrollment_token: str) -> str:
    base_url = public_url.rstrip("/")
    quoted_url = shlex.quote(base_url)
    quoted_token = shlex.quote(enrollment_token)
    return f"""#!/bin/sh
set -eu

MONITOR_URL={quoted_url}
ENROLLMENT_TOKEN={quoted_token}

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: запустите установщик через sudo или от root" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: для установки требуется curl" >&2
  exit 1
fi

platform=ubuntu
if [ -f /etc/openwrt_release ] || command -v procd_open_instance >/dev/null 2>&1; then
  platform=openwrt
elif [ -r /etc/os-release ]; then
  . /etc/os-release
  case "${{ID:-}}" in
    ubuntu|debian) platform=ubuntu ;;
    openwrt) platform=openwrt ;;
    *) echo "ERROR: пока поддерживаются Ubuntu/Debian и OpenWrt (обнаружено ${{ID:-unknown}})" >&2; exit 2 ;;
  esac
fi

installation_id=""
[ -r /etc/machine-id ] && installation_id=$(tr -d '\\r\\n' < /etc/machine-id)
[ -n "$installation_id" ] || installation_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$(date +%s)-$$")

mkdir -p /etc/cls-agent /var/lib/cls-agent
umask 077
cat > /etc/cls-agent/bootstrap <<EOF
MONITOR_URL=$MONITOR_URL
ENROLLMENT_TOKEN=$ENROLLMENT_TOKEN
INSTALLATION_ID=$installation_id
PLATFORM=$platform
HEARTBEAT_INTERVAL=${{CLS_HEARTBEAT_INTERVAL:-60}}
EOF

cat > /usr/bin/cls-agent <<'CLS_AGENT'
#!/bin/sh
set -eu
. /etc/cls-agent/bootstrap
state=/var/lib/cls-agent
credentials=$state/credentials

json_escape() {{ printf '%s' "$1" | sed 's/\\\\/\\\\\\\\/g; s/"/\\\\"/g'; }}

if [ ! -s "$credentials" ]; then
  hostname_value=$(json_escape "$(hostname 2>/dev/null || echo unknown)")
  payload=$(printf '{{"token":"%s","installation_id":"%s","platform":"%s","metadata":{{"hostname":"%s","architecture":"%s"}},"capabilities":["heartbeat","resource_metrics","tls_verify"]}}' \
    "$ENROLLMENT_TOKEN" "$INSTALLATION_ID" "$PLATFORM" "$hostname_value" "$(uname -m)")
  response=$(curl -fsS --connect-timeout 15 --max-time 30 \
    -H 'Content-Type: application/json' -d "$payload" "$MONITOR_URL/api/v1/agents/enroll")
  server_id=$(printf '%s' "$response" | sed -n 's/.*"server_id":"\\([^"]*\\)".*/\\1/p')
  credential=$(printf '%s' "$response" | sed -n 's/.*"credential":"\\([^"]*\\)".*/\\1/p')
  if [ -z "$server_id" ] || [ -z "$credential" ]; then
    echo "ERROR: монитор вернул некорректный ответ enrollment" >&2
    exit 1
  fi
  umask 077
  printf 'SERVER_ID=%s\\nCREDENTIAL=%s\\n' "$server_id" "$credential" > "$credentials"
  sed -i '/^ENROLLMENT_TOKEN=/d' /etc/cls-agent/bootstrap
fi

. "$credentials"
sequence_file=$state/sequence
sequence=$(cat "$sequence_file" 2>/dev/null || echo 0)

while :; do
  sequence=$((sequence + 1))
  printf '%s\\n' "$sequence" > "$sequence_file"
  event_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$(date +%s)-$$-$sequence")
  measured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  uptime_seconds=$(cut -d. -f1 /proc/uptime 2>/dev/null || echo 0)
  load_average=$(awk '{{print $1}}' /proc/loadavg 2>/dev/null || echo 0)
  memory_usage_percent=$(awk '/MemTotal/ {{ total=$2 }} /MemAvailable/ {{ available=$2 }} END {{ if (total > 0) printf "%.2f", (total-available)*100/total; else print 0 }}' /proc/meminfo 2>/dev/null || echo 0)
  disk_usage_percent=$(df -P / 2>/dev/null | awk 'NR == 2 {{ gsub("%", "", $5); print $5 + 0 }}' || echo 0)
  hostname_value=$(json_escape "$(hostname 2>/dev/null || echo unknown)")
  architecture=$(json_escape "$(uname -m 2>/dev/null || echo unknown)")
  kernel=$(json_escape "$(uname -r 2>/dev/null || echo unknown)")
  body=$(printf '{{"schema_version":"1.0","event_id":"%s","server_id":"%s","sequence":%s,"measured_at":"%s","agent":{{"version":"{__version__}"}},"system":{{"hostname":"%s","platform":"%s","architecture":"%s","kernel":"%s","uptime_seconds":%s,"load_average_1m":%s,"memory_usage_percent":%s,"disk_usage_percent":%s}},"metadata":{{}}}}' \
    "$event_id" "$SERVER_ID" "$sequence" "$measured_at" "$hostname_value" "$PLATFORM" "$architecture" "$kernel" "$uptime_seconds" "$load_average" "$memory_usage_percent" "$disk_usage_percent")
  curl -fsS --connect-timeout 15 --max-time 30 \
    -H "Authorization: Bearer $CREDENTIAL" -H 'Content-Type: application/json' \
    -d "$body" "$MONITOR_URL/api/v1/agents/heartbeat" >/dev/null || true
  sleep "$HEARTBEAT_INTERVAL"
done
CLS_AGENT
chmod 0755 /usr/bin/cls-agent

if [ "$platform" = openwrt ]; then
  cat > /etc/init.d/cls-agent <<'OPENWRT_SERVICE'
#!/bin/sh /etc/rc.common
START=95
USE_PROCD=1
start_service() {{
  procd_open_instance
  procd_set_param command /usr/bin/cls-agent
  procd_set_param respawn 5 10 0
  procd_set_param stdout 1
  procd_set_param stderr 1
  procd_close_instance
}}
OPENWRT_SERVICE
  chmod 0755 /etc/init.d/cls-agent
  /etc/init.d/cls-agent enable
  /etc/init.d/cls-agent restart
else
  cat > /etc/systemd/system/cls-agent.service <<'SYSTEMD_SERVICE'
[Unit]
Description=Check Life Servers Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cls-agent
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/cls-agent /etc/cls-agent
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SYSTEMD_SERVICE
  systemctl daemon-reload
  systemctl enable --now cls-agent
fi

echo "OK: CLS agent установлен; платформа=$platform"
echo "Проверка: подождите до 60 секунд и обновите dashboard."
"""


def routeros_installer(public_url: str, enrollment_token: str) -> str:
    base_url = public_url.rstrip("/")
    return f"""# Check Life Servers bootstrap for MikroTik RouterOS 7
:local clsUrl "{base_url}"
:local clsToken "{enrollment_token}"
:local clsInstallId [/system routerboard get serial-number]
:if ([:len $clsInstallId] = 0) do={{ :set clsInstallId [/system identity get name] }}
:local clsPayload ("{{\\"token\\":\\"" . $clsToken . "\\",\\"installation_id\\":\\"routeros-" . $clsInstallId . "\\",\\"platform\\":\\"routeros\\",\\"metadata\\":{{\\"hostname\\":\\"" . [/system identity get name] . "\\",\\"architecture\\":\\"" . [/system resource get architecture-name] . "\\"}},\\"capabilities\\":[\\"heartbeat\\",\\"resource_metrics\\",\\"scheduler\\",\\"tls_verify\\"]}}")
:local clsResult [/tool fetch url=($clsUrl . "/api/v1/agents/enroll") http-method=post http-header-field="Content-Type: application/json" http-data=$clsPayload check-certificate=yes output=user as-value]
:local clsData [:deserialize from=json value=($clsResult->"data")]
:global clsServerId ($clsData->"server_id")
:global clsCredential ($clsData->"credential")
:global clsSequence 0
:global clsMonitorUrl $clsUrl

/system script remove [find name="cls-heartbeat"]
/system script add name="cls-heartbeat" policy=read,write,test source={{
  :global clsServerId
  :global clsCredential
  :global clsSequence
  :global clsMonitorUrl
  :set clsSequence ($clsSequence + 1)
  :local eventId ([/system clock get date] . "-" . [/system clock get time] . "-" . $clsSequence)
  :local measuredAt ([/system clock get date] . "T" . [/system clock get time] . "Z")
  :local body ("{{\\"schema_version\\":\\"1.0\\",\\"event_id\\":\\"" . $eventId . "\\",\\"server_id\\":\\"" . $clsServerId . "\\",\\"sequence\\":" . $clsSequence . ",\\"measured_at\\":\\"" . $measuredAt . "\\",\\"agent\\":{{\\"version\\":\\"{__version__}\\"}},\\"system\\":{{\\"hostname\\":\\"" . [/system identity get name] . "\\",\\"platform\\":\\"routeros\\",\\"architecture\\":\\"" . [/system resource get architecture-name] . "\\",\\"cpu_usage_percent\\":" . [/system resource get cpu-load] . ",\\"uptime_seconds\\":0}},\\"metadata\\":{{}}}}")
  /tool fetch url=($clsMonitorUrl . "/api/v1/agents/heartbeat") http-method=post http-header-field=("Content-Type: application/json,Authorization: Bearer " . $clsCredential) http-data=$body check-certificate=yes keep-result=no
}}
/system scheduler remove [find name="cls-heartbeat"]
/system scheduler add name="cls-heartbeat" interval=1m on-event="/system script run cls-heartbeat" start-time=startup
/system script run cls-heartbeat
:put "OK: CLS agent registered and heartbeat scheduler started"
"""
