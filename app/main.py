from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.installers import linux_installer, routeros_installer
from app.models import EnrollmentToken, HeartbeatEvent, Server, User, UserSession
from app.schemas import (
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentTokenCreate,
    HeartbeatRequest,
    LoginRequest,
)
from app.security import new_token, token_hash, verify_password
from app.version import __version__

app = FastAPI(title="Check Life Servers", version=__version__)
settings = get_settings()


@app.middleware("http")
async def service_version_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-CLS-Version"] = __version__
    return response


@app.get("/api/v1/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ready"}


@app.get("/api/v1/system/version")
def system_version() -> dict[str, str]:
    return {
        "service": "check-life-servers",
        "version": __version__,
        "api_version": "v1",
    }


def current_user(
    cls_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not cls_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash(cls_session),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


@app.post("/api/v1/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.login == payload.login))
    if not user or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    raw_token = new_token(48)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.admin_session_ttl_minutes)
    db.add(UserSession(user_id=user.id, token_hash=token_hash(raw_token), expires_at=expires_at))
    db.commit()
    response.set_cookie(
        "cls_session",
        raw_token,
        httponly=True,
        secure=settings.cls_public_url.startswith("https://"),
        samesite="strict",
        max_age=settings.admin_session_ttl_minutes * 60,
        path="/",
    )
    return {
        "login": user.login,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    cls_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> None:
    if cls_session:
        session = db.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash(cls_session))
        )
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie("cls_session", path="/")


@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"login": user.login, "role": user.role}


@app.post("/api/v1/enrollment-tokens")
def create_enrollment_token(
    payload: EnrollmentTokenCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    raw_token = new_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.enrollment_ttl_minutes)
    db.add(
        EnrollmentToken(
            token_hash=token_hash(raw_token),
            server_name=payload.server_name,
            platform=payload.platform,
            expires_at=expires_at,
        )
    )
    db.commit()
    base_url = settings.cls_public_url.rstrip("/")
    if payload.platform == "routeros":
        command = (
            f'/tool fetch url="{base_url}/install/{raw_token}?platform=routeros" '
            "dst-path=cls-install.rsc check-certificate=yes; "
            "/import file-name=cls-install.rsc"
        )
    else:
        command = f"curl -fsSL {base_url}/install/{raw_token} | sudo sh"
    return {
        "command": command,
        "expires_at": expires_at,
        "platform": payload.platform,
    }


@app.get("/install/{raw_token}", response_class=PlainTextResponse)
def download_installer(
    raw_token: str,
    platform: str | None = Query(default=None, pattern="^(auto|ubuntu|openwrt|routeros)$"),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    enrollment = db.scalar(
        select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash(raw_token))
    )
    now = datetime.now(UTC)
    if not enrollment or enrollment.used_at or enrollment.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installer expired")
    selected_platform = platform or enrollment.platform
    content = (
        routeros_installer(settings.cls_public_url, raw_token)
        if selected_platform == "routeros"
        else linux_installer(settings.cls_public_url, raw_token)
    )
    filename = "cls-install.rsc" if selected_platform == "routeros" else "cls-install.sh"
    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def server_status(last_seen_at: datetime | None, now: datetime) -> str:
    if last_seen_at is None:
        return "unknown"
    return "online" if last_seen_at >= now - timedelta(seconds=180) else "offline"


def availability_segments(
    events: list[HeartbeatEvent],
    start: datetime,
    end: datetime,
    heartbeat_grace_seconds: int = 180,
) -> tuple[list[dict], int]:
    """Build explicit up/down/unknown intervals from heartbeat history."""
    points = sorted(event.received_at for event in events if event.received_at <= end)
    segments: list[dict] = []
    cursor = start
    up_seconds = 0

    for point in points:
        up_start = max(start, point)
        up_end = min(end, point + timedelta(seconds=heartbeat_grace_seconds))
        if up_end <= cursor:
            continue
        if up_start > cursor:
            segments.append({"status": "down", "from": cursor, "to": up_start})
        actual_start = max(cursor, up_start)
        segments.append({"status": "up", "from": actual_start, "to": up_end})
        up_seconds += max(0, int((up_end - actual_start).total_seconds()))
        cursor = up_end

    if cursor < end:
        segments.append(
            {
                "status": "unknown" if not points else "down",
                "from": cursor,
                "to": end,
            }
        )

    # Merge adjacent intervals so the browser receives a compact timeline.
    merged: list[dict] = []
    for segment in segments:
        if (
            merged
            and merged[-1]["status"] == segment["status"]
            and merged[-1]["to"] == segment["from"]
        ):
            merged[-1]["to"] = segment["to"]
        else:
            merged.append(segment)
    return merged, up_seconds


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    registered_servers = list(db.scalars(select(Server)))
    statuses = [server_status(server.last_seen_at, now) for server in registered_servers]
    online = statuses.count("online")
    offline = statuses.count("offline")
    unknown = statuses.count("unknown")
    total = len(registered_servers)
    return {
        "total": total,
        "online": online,
        "offline": offline,
        "unknown": unknown,
        "online_percent": round(online / total * 100, 2) if total else None,
        "active_incidents": offline,
        "generated_at": now,
    }


@app.get("/api/v1/dashboard/availability")
def dashboard_availability(
    hours: int = Query(default=24, ge=1, le=24 * 90),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)
    servers = list(db.scalars(select(Server).order_by(Server.name)))
    result = []
    total_up = 0
    total_observed = 0

    for server in servers:
        events = list(
            db.scalars(
                select(HeartbeatEvent)
                .where(
                    HeartbeatEvent.server_id == server.id,
                    HeartbeatEvent.received_at >= start - timedelta(seconds=180),
                    HeartbeatEvent.received_at <= end,
                )
                .order_by(HeartbeatEvent.received_at)
            )
        )
        segments, up_seconds = availability_segments(events, start, end)
        observed_seconds = sum(
            int((item["to"] - item["from"]).total_seconds())
            for item in segments
            if item["status"] != "unknown"
        )
        down_seconds = sum(
            int((item["to"] - item["from"]).total_seconds())
            for item in segments
            if item["status"] == "down"
        )
        total_up += up_seconds
        total_observed += observed_seconds
        latest_payload = events[-1].payload if events else {}
        result.append(
            {
                "server_id": str(server.id),
                "name": server.name,
                "platform": server.platform,
                "status": server_status(server.last_seen_at, end),
                "uptime_percent": (
                    round(up_seconds / observed_seconds * 100, 3)
                    if observed_seconds
                    else None
                ),
                "downtime_seconds": down_seconds,
                "segments": segments,
                "latest": {
                    "system": latest_payload.get("system", {}),
                    "network": latest_payload.get("network", {}),
                    "services": latest_payload.get("services", []),
                    "agent": latest_payload.get("agent", {}),
                },
            }
        )

    return {
        "from": start,
        "to": end,
        "hours": hours,
        "uptime_percent": (
            round(total_up / total_observed * 100, 3) if total_observed else None
        ),
        "servers": result,
    }


@app.get("/api/v1/servers")
def list_servers(
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    now = datetime.now(UTC)
    rows = db.execute(
        select(Server, func.count(HeartbeatEvent.id))
        .outerjoin(HeartbeatEvent, HeartbeatEvent.server_id == Server.id)
        .group_by(Server.id)
        .order_by(Server.name)
    )
    return [
        {
            "id": str(server.id),
            "name": server.name,
            "platform": server.platform,
            "status": server_status(server.last_seen_at, now),
            "last_seen_at": server.last_seen_at,
            "heartbeat_count": heartbeat_count,
            "metadata": server.metadata_json,
            "capabilities": server.capabilities,
        }
        for server, heartbeat_count in rows
    ]


@app.get("/api/v1/servers/{server_id}/heartbeats")
def server_heartbeats(
    server_id: UUID,
    limit: int = 200,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    if not db.get(Server, server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    events = db.scalars(
        select(HeartbeatEvent)
        .where(HeartbeatEvent.server_id == server_id)
        .order_by(HeartbeatEvent.received_at.desc())
        .limit(min(max(limit, 1), 1000))
    )
    return [
        {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "measured_at": event.measured_at,
            "received_at": event.received_at,
            "agent": event.payload.get("agent", {}),
            "system": event.payload.get("system", {}),
            "network": event.payload.get("network", {}),
            "services": event.payload.get("services", []),
        }
        for event in events
    ]


@app.post("/api/v1/agents/enroll", response_model=EnrollmentResponse)
def enroll(payload: EnrollmentRequest, db: Session = Depends(get_db)) -> EnrollmentResponse:
    now = datetime.now(UTC)
    enrollment = db.scalar(
        select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash(payload.token))
    )
    if not enrollment or enrollment.used_at or enrollment.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid enrollment token",
        )

    if db.scalar(select(Server).where(Server.installation_id == payload.installation_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Installation already enrolled",
        )

    credential = new_token(48)
    server = Server(
        name=enrollment.server_name,
        platform=payload.platform or enrollment.platform,
        installation_id=payload.installation_id,
        credential_hash=token_hash(credential),
        metadata_json=payload.metadata,
        capabilities=payload.capabilities,
    )
    enrollment.used_at = now
    db.add(server)
    db.commit()
    return EnrollmentResponse(server_id=str(server.id), credential=credential)


@app.post("/api/v1/agents/heartbeat")
def heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credential")
    server = db.get(Server, UUID(payload.server_id))
    if not server or server.credential_hash != token_hash(authorization.removeprefix("Bearer ")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credential")

    received_at = datetime.now(UTC)
    event = HeartbeatEvent(
        server_id=server.id,
        event_id=payload.event_id,
        sequence=payload.sequence,
        measured_at=payload.measured_at,
        received_at=received_at,
        payload=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    server.last_seen_at = received_at
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {
        "accepted": True,
        "event_id": payload.event_id,
        "received_at": received_at,
        "server_time": datetime.now(UTC),
        "next_heartbeat_seconds": 60,
        "configuration_version": 1,
    }
