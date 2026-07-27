from app.installers import linux_installer, routeros_installer


def test_linux_installer_detects_and_configures_supported_platforms() -> None:
    script = linux_installer("https://monitor.example.com", "token-value")

    assert "platform=openwrt" in script
    assert "systemctl enable --now cls-agent" in script
    assert "/etc/init.d/cls-agent enable" in script
    assert "/api/v1/agents/enroll" in script
    assert "/api/v1/agents/heartbeat" in script
    assert "token-value" in script


def test_routeros_installer_enrolls_and_schedules_heartbeat() -> None:
    script = routeros_installer("https://monitor.example.com", "token-value")

    assert "check-certificate=yes" in script
    assert "/api/v1/agents/enroll" in script
    assert "/api/v1/agents/heartbeat" in script
    assert '/system scheduler add name="cls-heartbeat"' in script
