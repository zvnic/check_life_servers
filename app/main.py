from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import EnrollmentToken, HeartbeatEvent, Server, User, UserSession
from app.schemas import EnrollmentRequest, EnrollmentResponse, HeartbeatRequest, LoginRequest
from app.security import new_token, token_hash, verify_password

app = FastAPI(title="Check Life Servers", version="0.1.0")
settings = get_settings()


@app.get("/api/v1/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ready"}


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


def server_status(last_seen_at: datetime | None, now: datetime) -> str:
    if last_seen_at is None:
        return "unknown"
    return "online" if last_seen_at >= now - timedelta(seconds=180) else "offline"


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
        "uptime_percent": round(online / total * 100, 2) if total else None,
        "active_incidents": offline,
        "generated_at": now,
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
            "latency_ms": max(
                0,
                round((event.received_at - event.measured_at).total_seconds() * 1000),
            ),
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
        platform=enrollment.platform,
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
