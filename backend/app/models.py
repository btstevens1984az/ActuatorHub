from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}"


class Role(str, Enum):
    viewer = "viewer"
    operator = "operator"
    approver = "approver"
    admin = "admin"


class DeviceKind(str, Enum):
    relay = "relay"
    fan = "fan"
    pdu = "pdu"
    lock = "lock"
    sensor = "sensor"
    environmental = "environmental"


class DeviceState(str, Enum):
    on = "on"
    off = "off"
    open = "open"
    locked = "locked"
    unlocked = "unlocked"
    unknown = "unknown"
    fault = "fault"


class CommandAction(str, Enum):
    turn_on = "turn_on"
    turn_off = "turn_off"
    toggle = "toggle"
    lock = "lock"
    unlock = "unlock"
    set_speed = "set_speed"
    outlet_on = "outlet_on"
    outlet_off = "outlet_off"
    reboot_outlet = "reboot_outlet"
    e_stop = "e_stop"


class CommandStatus(str, Enum):
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    dispatched = "dispatched"
    acknowledged = "acknowledged"
    failed = "failed"
    cancelled = "cancelled"


class User(BaseModel):
    id: str
    name: str
    role: Role
    site: str = "HQ-DC1"


class Device(BaseModel):
    id: str
    name: str
    kind: DeviceKind
    site: str
    rack: str | None = None
    mqtt_topic: str
    state: DeviceState = DeviceState.unknown
    online: bool = True
    requires_approval: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)
    last_seen: datetime = Field(default_factory=utcnow)
    tags: list[str] = Field(default_factory=list)


class CommandRequest(BaseModel):
    id: str
    device_id: str
    action: CommandAction
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str
    requested_at: datetime = Field(default_factory=utcnow)
    status: CommandStatus = CommandStatus.pending_approval
    reason: str = ""
    approved_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    requires_approval: bool = False


class AuditEvent(BaseModel):
    id: str
    ts: datetime = Field(default_factory=utcnow)
    actor: str
    action: str
    target: str
    detail: str
    severity: Literal["info", "warning", "critical"] = "info"


class SensorRule(BaseModel):
    id: str
    name: str
    sensor_id: str
    metric: str
    operator: Literal[">", ">=", "<", "<=", "=="]
    threshold: float
    target_device_id: str
    target_action: CommandAction
    enabled: bool = True
    cooldown_seconds: int = 60
    last_fired: datetime | None = None


class HubStatus(BaseModel):
    emergency_stop: bool = False
    mqtt_connected: bool = False
    mqtt_mode: Literal["live", "simulated"] = "simulated"
    devices_online: int = 0
    pending_approvals: int = 0
    version: str = "1.0.0"


class LoginRequest(BaseModel):
    user_id: str


class CommandCreate(BaseModel):
    device_id: str
    action: CommandAction
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ApprovalDecision(BaseModel):
    approve: bool
    note: str = ""


class SensorReading(BaseModel):
    sensor_id: str
    metric: str
    value: float
