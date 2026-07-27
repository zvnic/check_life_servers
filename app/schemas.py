from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EnrollmentRequest(BaseModel):
    token: str = Field(min_length=32)
    installation_id: str = Field(min_length=8, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class EnrollmentResponse(BaseModel):
    server_id: str
    credential: str
    next_heartbeat_seconds: int = 60


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class HeartbeatRequest(BaseModel):
    schema_version: str = "1.0"
    event_id: str = Field(min_length=8, max_length=64)
    server_id: str
    sequence: int = Field(ge=0)
    measured_at: datetime
    agent: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)
    network: dict[str, Any] = Field(default_factory=dict)
    services: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
