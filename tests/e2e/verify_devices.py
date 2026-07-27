from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import EnrollmentToken, HeartbeatEvent, Server
from app.version import __version__

REQUIRED_METRICS = {
    "load_average_1m",
    "memory_usage_percent",
    "disk_usage_percent",
    "uptime_seconds",
}


def main() -> None:
    with SessionLocal() as db:
        servers = list(db.scalars(select(Server).order_by(Server.platform)))
        assert len(servers) == 2, f"expected 2 servers, got {len(servers)}"

        platforms = {server.platform for server in servers}
        assert platforms == {"ubuntu", "openwrt"}, platforms

        for server in servers:
            count = db.scalar(
                select(func.count(HeartbeatEvent.id)).where(
                    HeartbeatEvent.server_id == server.id
                )
            )
            assert count is not None and count >= 2, (
                f"{server.platform}: expected >=2 heartbeats, got {count}"
            )
            latest = db.scalar(
                select(HeartbeatEvent)
                .where(HeartbeatEvent.server_id == server.id)
                .order_by(HeartbeatEvent.received_at.desc())
                .limit(1)
            )
            assert latest is not None
            system = latest.payload["system"]
            missing = REQUIRED_METRICS - system.keys()
            assert not missing, f"{server.platform}: missing metrics {sorted(missing)}"
            assert latest.payload["agent"]["version"] == __version__
            assert system["platform"] == server.platform
            assert server.last_seen_at is not None
            print(
                f"OK {server.platform}: heartbeats={count}, "
                f"load={system['load_average_1m']}, "
                f"memory={system['memory_usage_percent']}%, "
                f"disk={system['disk_usage_percent']}%"
            )

        used_tokens = db.scalar(
            select(func.count(EnrollmentToken.id)).where(
                EnrollmentToken.used_at.is_not(None)
            )
        )
        assert used_tokens == 2, f"expected 2 consumed tokens, got {used_tokens}"


if __name__ == "__main__":
    main()
