from app.installers import linux_installer, routeros_installer
from app.version import __version__


def test_linux_installer_detects_and_configures_supported_platforms() -> None:
    script = linux_installer("https://monitor.example.com", "token-value")

    assert "platform=openwrt" in script
    assert "systemctl enable --now cls-agent" in script
    assert "/etc/init.d/cls-agent enable" in script
    assert "/api/v1/agents/enroll" in script
    assert "/api/v1/agents/heartbeat" in script
    assert "memory_usage_percent" in script
    assert "disk_usage_percent" in script
    assert "load_average_1m" in script
    assert "memory_total_bytes" in script
    assert "network_rx_bytes" in script
    assert "docker_unhealthy" in script
    assert '"schema_version":"1.1"' in script
    assert f'"version":"{__version__}"' in script
    assert "HEARTBEAT_INTERVAL=${CLS_HEARTBEAT_INTERVAL:-60}" in script
    assert "token-value" in script


def test_routeros_installer_enrolls_and_schedules_heartbeat() -> None:
    script = routeros_installer("https://monitor.example.com", "token-value")

    assert "check-certificate=yes" in script
    assert "/api/v1/agents/enroll" in script
    assert "/api/v1/agents/heartbeat" in script
    assert "cpu_usage_percent" in script
    assert f'\\"version\\":\\"{__version__}\\"' in script
    assert '/system scheduler add name="cls-heartbeat"' in script
