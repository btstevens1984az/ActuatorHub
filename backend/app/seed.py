from __future__ import annotations

from .models import (
    AuditEvent,
    Device,
    DeviceKind,
    DeviceState,
    Role,
    SensorRule,
    CommandAction,
    User,
    new_id,
)
from .store import store


def seed_demo() -> None:
    if store.users:
        return

    users = [
        User(id="u-admin", name="Alex Rivera", role=Role.admin, site="HQ-DC1"),
        User(id="u-approver", name="Jordan Lee", role=Role.approver, site="HQ-DC1"),
        User(id="u-ops", name="Sam Patel", role=Role.operator, site="HQ-DC1"),
        User(id="u-viewer", name="Casey Ng", role=Role.viewer, site="HQ-DC1"),
    ]
    for u in users:
        store.users[u.id] = u

    devices = [
        Device(
            id="dev-relay-crac",
            name="CRAC Contactor A",
            kind=DeviceKind.relay,
            site="HQ-DC1",
            rack="MECH-01",
            mqtt_topic="actuators/hq-dc1/relay/crac-a",
            state=DeviceState.on,
            requires_approval=True,
            tags=["cooling", "critical"],
            meta={"gpio": 17, "edge": "pi-edge-01"},
        ),
        Device(
            id="dev-fan-row3",
            name="Hot-Aisle Fan Row 3",
            kind=DeviceKind.fan,
            site="HQ-DC1",
            rack="ROW-03",
            mqtt_topic="actuators/hq-dc1/fan/row3",
            state=DeviceState.on,
            tags=["cooling"],
            meta={"speed_pct": 65, "edge": "pi-edge-01"},
        ),
        Device(
            id="dev-pdu-r12",
            name="Smart PDU Rack 12",
            kind=DeviceKind.pdu,
            site="HQ-DC1",
            rack="R12",
            mqtt_topic="actuators/hq-dc1/pdu/r12",
            state=DeviceState.on,
            requires_approval=True,
            tags=["power", "critical"],
            meta={"outlets": 8, "outlet_states": [1, 1, 1, 1, 1, 0, 1, 1], "edge": "pi-edge-02"},
        ),
        Device(
            id="dev-lock-cage",
            name="Cage Door Lock B",
            kind=DeviceKind.lock,
            site="HQ-DC1",
            rack="CAGE-B",
            mqtt_topic="actuators/hq-dc1/lock/cage-b",
            state=DeviceState.locked,
            requires_approval=True,
            tags=["physical-security"],
            meta={"edge": "arduino-gate-01"},
        ),
        Device(
            id="dev-env-temp",
            name="Row 3 Intake Temp",
            kind=DeviceKind.sensor,
            site="HQ-DC1",
            rack="ROW-03",
            mqtt_topic="sensors/hq-dc1/temp/row3",
            state=DeviceState.on,
            tags=["environment"],
            meta={"metric": "celsius", "value": 24.6, "edge": "pi-edge-01"},
        ),
        Device(
            id="dev-env-humidity",
            name="Mech Room Humidity",
            kind=DeviceKind.environmental,
            site="HQ-DC1",
            rack="MECH-01",
            mqtt_topic="sensors/hq-dc1/humidity/mech",
            state=DeviceState.on,
            tags=["environment"],
            meta={"metric": "rh_pct", "value": 42.0, "edge": "pi-edge-01"},
        ),
        Device(
            id="dev-relay-exhaust",
            name="Exhaust Damper Relay",
            kind=DeviceKind.relay,
            site="HQ-DC1",
            rack="MECH-01",
            mqtt_topic="actuators/hq-dc1/relay/exhaust",
            state=DeviceState.off,
            tags=["cooling"],
            meta={"gpio": 27, "edge": "pi-edge-01"},
        ),
        Device(
            id="dev-pdu-lab",
            name="Lab Bench PDU",
            kind=DeviceKind.pdu,
            site="LAB-01",
            rack="BENCH-A",
            mqtt_topic="actuators/lab-01/pdu/bench-a",
            state=DeviceState.on,
            tags=["lab", "power"],
            meta={"outlets": 4, "outlet_states": [1, 1, 0, 1], "edge": "pi-edge-lab"},
        ),
    ]
    for d in devices:
        store.devices[d.id] = d

    rules = [
        SensorRule(
            id="rule-temp-fan",
            name="Boost fans when intake > 28°C",
            sensor_id="dev-env-temp",
            metric="celsius",
            operator=">",
            threshold=28.0,
            target_device_id="dev-fan-row3",
            target_action=CommandAction.set_speed,
            cooldown_seconds=120,
        ),
        SensorRule(
            id="rule-humid-exhaust",
            name="Open exhaust when RH > 60%",
            sensor_id="dev-env-humidity",
            metric="rh_pct",
            operator=">",
            threshold=60.0,
            target_device_id="dev-relay-exhaust",
            target_action=CommandAction.turn_on,
            cooldown_seconds=180,
        ),
    ]
    for r in rules:
        store.rules[r.id] = r

    store.add_audit(
        AuditEvent(
            id=new_id("aud-"),
            actor="system",
            action="hub.seeded",
            target="ActuatorHub",
            detail="Demo inventory loaded: relays, fans, PDUs, locks, sensors.",
            severity="info",
        )
    )
    store.refresh_counts()
