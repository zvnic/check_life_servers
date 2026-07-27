import re
import subprocess
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import EnrollmentToken, HeartbeatEvent, Server, User, UserSession
from app.security import hash_password


def test_bootstrap_enrolls_device_and_accepts_heartbeat() -> None:
    suffix = uuid.uuid4().hex
    login = f"bootstrap-{suffix}"
    password = "Bootstrap9"
    installation_id = f"integration-{suffix}"
    server_name = f"Integration device {suffix}"
    server_id = None
    user_id = None

    with SessionLocal.begin() as db:
        user = User(
            login=login,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(user)
        db.flush()
        user_id = user.id

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/auth/login",
                json={"login": login, "password": password},
            )
            assert login_response.status_code == 200

            token_response = client.post(
                "/api/v1/enrollment-tokens",
                json={"server_name": server_name, "platform": "auto"},
            )
            assert token_response.status_code == 200
            command = token_response.json()["command"]
            match = re.search(r"/install/([A-Za-z0-9_-]+)", command)
            assert match
            raw_token = match.group(1)

            installer_response = client.get(f"/install/{raw_token}")
            assert installer_response.status_code == 200
            assert installer_response.headers["cache-control"] == "no-store"
            subprocess.run(
                ["sh", "-n"],
                input=installer_response.text,
                text=True,
                check=True,
            )

            enrollment_response = client.post(
                "/api/v1/agents/enroll",
                json={
                    "token": raw_token,
                    "installation_id": installation_id,
                    "platform": "ubuntu",
                    "metadata": {"hostname": "integration-device"},
                    "capabilities": ["heartbeat"],
                },
            )
            assert enrollment_response.status_code == 200
            enrollment = enrollment_response.json()
            server_id = enrollment["server_id"]

            heartbeat_response = client.post(
                "/api/v1/agents/heartbeat",
                headers={"Authorization": f"Bearer {enrollment['credential']}"},
                json={
                    "schema_version": "1.0",
                    "event_id": str(uuid.uuid4()),
                    "server_id": server_id,
                    "sequence": 1,
                    "measured_at": datetime.now(UTC).isoformat(),
                    "agent": {"version": "integration"},
                    "system": {"hostname": "integration-device"},
                },
            )
            assert heartbeat_response.status_code == 200

            servers_response = client.get("/api/v1/servers")
            assert servers_response.status_code == 200
            created = next(
                server for server in servers_response.json() if server["id"] == server_id
            )
            assert created["status"] == "online"
    finally:
        with SessionLocal.begin() as db:
            if server_id:
                parsed_server_id = uuid.UUID(server_id)
                db.execute(
                    delete(HeartbeatEvent).where(
                        HeartbeatEvent.server_id == parsed_server_id
                    )
                )
                db.execute(delete(Server).where(Server.id == parsed_server_id))
            db.execute(
                delete(EnrollmentToken).where(
                    EnrollmentToken.server_name == server_name
                )
            )
            if user_id:
                db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
