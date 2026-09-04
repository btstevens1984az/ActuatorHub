from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any

from .models import (
    AuditEvent,
    CommandRequest,
    Device,
    HubStatus,
    SensorRule,
    User,
    utcnow,
)


class Store:
    """Thread-safe in-memory store for demo / single-node deployments."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.users: dict[str, User] = {}
        self.devices: dict[str, Device] = {}
        self.commands: dict[str, CommandRequest] = {}
        self.audit: list[AuditEvent] = []
        self.rules: dict[str, SensorRule] = {}
        self.status = HubStatus()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "users": {k: v.model_dump(mode="json") for k, v in self.users.items()},
                "devices": {k: v.model_dump(mode="json") for k, v in self.devices.items()},
                "commands": {k: v.model_dump(mode="json") for k, v in self.commands.items()},
                "audit": [e.model_dump(mode="json") for e in self.audit[:200]],
                "rules": {k: v.model_dump(mode="json") for k, v in self.rules.items()},
                "status": self.status.model_dump(mode="json"),
            }

    def add_audit(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self.audit.insert(0, event)
            self.audit = self.audit[:500]
            return event

    def update_device(self, device_id: str, **fields: Any) -> Device | None:
        with self._lock:
            device = self.devices.get(device_id)
            if not device:
                return None
            data = device.model_dump()
            data.update(fields)
            data["last_seen"] = utcnow()
            updated = Device(**data)
            self.devices[device_id] = updated
            return updated

    def refresh_counts(self) -> None:
        with self._lock:
            self.status.devices_online = sum(1 for d in self.devices.values() if d.online)
            self.status.pending_approvals = sum(
                1 for c in self.commands.values() if c.status.value == "pending_approval"
            )


store = Store()


def clone_device(device: Device) -> Device:
    return Device(**deepcopy(device.model_dump()))
