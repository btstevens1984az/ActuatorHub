from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import get_user, require_role
from .models import (
    ApprovalDecision,
    CommandCreate,
    LoginRequest,
    Role,
    SensorReading,
    User,
)
from .mqtt_bridge import MqttBridge
from .seed import seed_demo
from .services import CommandService
from .store import store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("actuatorhub")

mqtt = MqttBridge()
commands = CommandService(mqtt)


def _on_mqtt_message(topic: str, payload: dict[str, Any]) -> None:
    store.status.mqtt_connected = mqtt.connected
    store.status.mqtt_mode = mqtt.mode  # type: ignore[assignment]
    if topic.startswith("sensors/"):
        sensor_id = payload.get("sensor_id")
        metric = payload.get("metric")
        value = payload.get("value")
        if sensor_id and metric is not None and value is not None:
            try:
                commands.ingest_reading(
                    SensorReading(sensor_id=str(sensor_id), metric=str(metric), value=float(value))
                )
            except HTTPException:
                pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_demo()
    mqtt.on_message = _on_mqtt_message
    mqtt.start()
    store.status.mqtt_connected = mqtt.connected
    store.status.mqtt_mode = mqtt.mode  # type: ignore[assignment]
    store.refresh_counts()
    yield
    mqtt.stop()


app = FastAPI(
    title="ActuatorHub API",
    description="Audited, role-based remote control of physical actuators via Raspberry Pi and Arduino.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ActuatorHub"}


@app.get("/api/users")
def list_users() -> list[dict]:
    return [u.model_dump(mode="json") for u in store.users.values()]


@app.post("/api/session")
def start_session(body: LoginRequest) -> dict:
    user = store.users.get(body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Unknown user")
    return {"user": user.model_dump(mode="json"), "token_header": "X-User-Id", "token_value": user.id}


@app.get("/api/me")
def me(user: User = Depends(get_user)) -> dict:
    return user.model_dump(mode="json")


@app.get("/api/status")
def status(user: User = Depends(get_user)) -> dict:
    store.status.mqtt_connected = mqtt.connected
    store.status.mqtt_mode = mqtt.mode  # type: ignore[assignment]
    store.refresh_counts()
    return store.status.model_dump(mode="json")


@app.get("/api/devices")
def list_devices(user: User = Depends(get_user), site: str | None = None, kind: str | None = None) -> list[dict]:
    items = list(store.devices.values())
    if site:
        items = [d for d in items if d.site == site]
    if kind:
        items = [d for d in items if d.kind.value == kind]
    return [d.model_dump(mode="json") for d in items]


@app.get("/api/devices/{device_id}")
def get_device(device_id: str, user: User = Depends(get_user)) -> dict:
    device = store.devices.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device.model_dump(mode="json")


@app.post("/api/commands")
def create_command(body: CommandCreate, user: User = Depends(get_user)) -> dict:
    require_role(user, Role.operator)
    return commands.create_command(user, body).model_dump(mode="json")


@app.get("/api/commands")
def list_commands(user: User = Depends(get_user), status: str | None = None) -> list[dict]:
    items = list(store.commands.values())
    items.sort(key=lambda c: c.requested_at, reverse=True)
    if status:
        items = [c for c in items if c.status.value == status]
    return [c.model_dump(mode="json") for c in items[:100]]


@app.post("/api/commands/{command_id}/decide")
def decide_command(command_id: str, body: ApprovalDecision, user: User = Depends(get_user)) -> dict:
    return commands.decide(user, command_id, body.approve, body.note).model_dump(mode="json")


@app.get("/api/audit")
def audit_log(user: User = Depends(get_user), limit: int = 100) -> list[dict]:
    return [e.model_dump(mode="json") for e in store.audit[: max(1, min(limit, 500))]]


@app.get("/api/rules")
def list_rules(user: User = Depends(get_user)) -> list[dict]:
    return [r.model_dump(mode="json") for r in store.rules.values()]


@app.post("/api/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, user: User = Depends(get_user)) -> dict:
    require_role(user, Role.approver)
    rule = store.rules.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.enabled = not rule.enabled
    store.rules[rule_id] = rule
    return rule.model_dump(mode="json")


@app.post("/api/sensors/reading")
def sensor_reading(body: SensorReading, user: User = Depends(get_user)) -> dict:
    require_role(user, Role.operator)
    fired = commands.ingest_reading(body)
    return {"accepted": True, "fired_commands": [c.model_dump(mode="json") for c in fired]}


@app.post("/api/emergency-stop")
def emergency_stop(engage: bool = True, user: User = Depends(get_user)) -> dict:
    return commands.emergency_stop(user, engage)


@app.get("/api/mqtt/recent")
def mqtt_recent(user: User = Depends(get_user)) -> list[dict]:
    require_role(user, Role.operator)
    return [{"topic": t, "payload": p} for t, p in mqtt.published[-50:]]


# Optional static frontend (Docker / combined serve)
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
