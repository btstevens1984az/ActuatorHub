from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException

from .models import (
    AuditEvent,
    CommandAction,
    CommandCreate,
    CommandRequest,
    CommandStatus,
    DeviceState,
    Role,
    SensorReading,
    User,
    new_id,
    utcnow,
)
from .mqtt_bridge import MqttBridge
from .store import store

# Actions that always need approver/admin when device.requires_approval is True
CRITICAL_ACTIONS = {
    CommandAction.turn_off,
    CommandAction.lock,
    CommandAction.unlock,
    CommandAction.outlet_off,
    CommandAction.reboot_outlet,
    CommandAction.e_stop,
}


def apply_device_state(device_id: str, action: CommandAction, payload: dict[str, Any]) -> None:
    device = store.devices.get(device_id)
    if not device:
        return
    kind = device.kind.value
    meta = dict(device.meta)

    if action == CommandAction.turn_on:
        store.update_device(device_id, state=DeviceState.on)
    elif action == CommandAction.turn_off:
        store.update_device(device_id, state=DeviceState.off)
    elif action == CommandAction.toggle:
        nxt = DeviceState.off if device.state == DeviceState.on else DeviceState.on
        store.update_device(device_id, state=nxt)
    elif action == CommandAction.lock:
        store.update_device(device_id, state=DeviceState.locked)
    elif action == CommandAction.unlock:
        store.update_device(device_id, state=DeviceState.unlocked)
    elif action == CommandAction.set_speed:
        speed = int(payload.get("speed_pct", meta.get("speed_pct", 50)))
        meta["speed_pct"] = max(0, min(100, speed))
        store.update_device(device_id, state=DeviceState.on if speed > 0 else DeviceState.off, meta=meta)
    elif action in {CommandAction.outlet_on, CommandAction.outlet_off, CommandAction.reboot_outlet}:
        outlets = list(meta.get("outlet_states", []))
        idx = int(payload.get("outlet", 1)) - 1
        if 0 <= idx < len(outlets):
            if action == CommandAction.outlet_on:
                outlets[idx] = 1
            elif action == CommandAction.outlet_off:
                outlets[idx] = 0
            else:
                outlets[idx] = 0
                outlets[idx] = 1
            meta["outlet_states"] = outlets
        store.update_device(device_id, state=DeviceState.on, meta=meta)
    elif action == CommandAction.e_stop:
        if kind in {"relay", "fan", "pdu"}:
            store.update_device(device_id, state=DeviceState.off)
        elif kind == "lock":
            store.update_device(device_id, state=DeviceState.locked)


class CommandService:
    def __init__(self, mqtt: MqttBridge) -> None:
        self.mqtt = mqtt

    def create_command(self, user: User, body: CommandCreate) -> CommandRequest:
        if store.status.emergency_stop and body.action != CommandAction.e_stop:
            raise HTTPException(status_code=423, detail="Emergency stop is active — commands blocked")

        device = store.devices.get(body.device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        if device.kind.value in {"sensor", "environmental"} and body.action != CommandAction.e_stop:
            raise HTTPException(status_code=400, detail="Cannot command sensor/environmental devices directly")

        needs_approval = device.requires_approval and body.action in CRITICAL_ACTIONS
        if needs_approval and user.role in {Role.viewer}:
            raise HTTPException(status_code=403, detail="Viewers cannot request actuator commands")
        if not needs_approval and user.role == Role.viewer:
            raise HTTPException(status_code=403, detail="Viewers cannot issue commands")

        cmd = CommandRequest(
            id=new_id("cmd-"),
            device_id=body.device_id,
            action=body.action,
            payload=body.payload,
            requested_by=user.id,
            reason=body.reason,
            requires_approval=needs_approval,
            status=CommandStatus.pending_approval if needs_approval else CommandStatus.approved,
        )
        store.commands[cmd.id] = cmd
        store.add_audit(
            AuditEvent(
                id=new_id("aud-"),
                actor=user.id,
                action="command.requested",
                target=device.id,
                detail=f"{body.action.value} on {device.name}"
                + (" (awaiting approval)" if needs_approval else ""),
                severity="warning" if needs_approval else "info",
            )
        )
        store.refresh_counts()

        if not needs_approval:
            return self.dispatch(cmd, actor=user.id)
        return cmd

    def decide(self, user: User, command_id: str, approve: bool, note: str = "") -> CommandRequest:
        if user.role not in {Role.approver, Role.admin}:
            raise HTTPException(status_code=403, detail="Approver or admin role required")
        cmd = store.commands.get(command_id)
        if not cmd:
            raise HTTPException(status_code=404, detail="Command not found")
        if cmd.status != CommandStatus.pending_approval:
            raise HTTPException(status_code=409, detail=f"Command is {cmd.status.value}")

        cmd.approved_by = user.id
        cmd.decided_at = utcnow()
        cmd.decision_note = note
        if approve:
            cmd.status = CommandStatus.approved
            store.commands[cmd.id] = cmd
            store.add_audit(
                AuditEvent(
                    id=new_id("aud-"),
                    actor=user.id,
                    action="command.approved",
                    target=cmd.device_id,
                    detail=note or "Approved",
                    severity="info",
                )
            )
            store.refresh_counts()
            return self.dispatch(cmd, actor=user.id)

        cmd.status = CommandStatus.rejected
        store.commands[cmd.id] = cmd
        store.add_audit(
            AuditEvent(
                id=new_id("aud-"),
                actor=user.id,
                action="command.rejected",
                target=cmd.device_id,
                detail=note or "Rejected",
                severity="warning",
            )
        )
        store.refresh_counts()
        return cmd

    def dispatch(self, cmd: CommandRequest, actor: str) -> CommandRequest:
        if store.status.emergency_stop and cmd.action != CommandAction.e_stop:
            cmd.status = CommandStatus.cancelled
            store.commands[cmd.id] = cmd
            return cmd

        device = store.devices.get(cmd.device_id)
        if not device:
            cmd.status = CommandStatus.failed
            store.commands[cmd.id] = cmd
            return cmd

        payload = {
            "command_id": cmd.id,
            "action": cmd.action.value,
            "payload": cmd.payload,
            "actor": actor,
            "ts": utcnow().isoformat(),
        }
        ok = self.mqtt.publish(f"{device.mqtt_topic}/cmd", payload)
        apply_device_state(device.id, cmd.action, cmd.payload)
        cmd.status = CommandStatus.acknowledged if ok else CommandStatus.failed
        store.commands[cmd.id] = cmd
        store.add_audit(
            AuditEvent(
                id=new_id("aud-"),
                actor=actor,
                action="command.dispatched",
                target=device.id,
                detail=f"{cmd.action.value} → {device.mqtt_topic} ({store.status.mqtt_mode})",
                severity="info" if ok else "critical",
            )
        )
        store.refresh_counts()
        return cmd

    def emergency_stop(self, user: User, engage: bool) -> dict[str, Any]:
        if user.role not in {Role.approver, Role.admin, Role.operator}:
            raise HTTPException(status_code=403, detail="Insufficient role for emergency stop")

        store.status.emergency_stop = engage
        if engage:
            for device in list(store.devices.values()):
                if device.kind.value in {"relay", "fan", "pdu"}:
                    apply_device_state(device.id, CommandAction.e_stop, {})
                    self.mqtt.publish(
                        f"{device.mqtt_topic}/cmd",
                        {"action": "e_stop", "actor": user.id, "ts": utcnow().isoformat()},
                    )
                elif device.kind.value == "lock":
                    apply_device_state(device.id, CommandAction.lock, {})
                    self.mqtt.publish(
                        f"{device.mqtt_topic}/cmd",
                        {"action": "lock", "actor": user.id, "reason": "e_stop", "ts": utcnow().isoformat()},
                    )
            store.add_audit(
                AuditEvent(
                    id=new_id("aud-"),
                    actor=user.id,
                    action="emergency.engaged",
                    target="fleet",
                    detail="Emergency stop engaged — actuators forced safe, commands blocked.",
                    severity="critical",
                )
            )
        else:
            store.add_audit(
                AuditEvent(
                    id=new_id("aud-"),
                    actor=user.id,
                    action="emergency.cleared",
                    target="fleet",
                    detail="Emergency stop cleared — normal command flow restored.",
                    severity="warning",
                )
            )
        store.refresh_counts()
        return store.status.model_dump(mode="json")

    def ingest_reading(self, reading: SensorReading) -> list[CommandRequest]:
        sensor = store.devices.get(reading.sensor_id)
        if not sensor:
            raise HTTPException(status_code=404, detail="Sensor not found")
        meta = dict(sensor.meta)
        meta["value"] = reading.value
        meta["metric"] = reading.metric
        store.update_device(sensor.id, meta=meta)

        fired: list[CommandRequest] = []
        for rule in store.rules.values():
            if not rule.enabled or rule.sensor_id != reading.sensor_id:
                continue
            if rule.metric != reading.metric:
                continue
            if rule.last_fired and utcnow() - rule.last_fired < timedelta(seconds=rule.cooldown_seconds):
                continue
            ops = {
                ">": reading.value > rule.threshold,
                ">=": reading.value >= rule.threshold,
                "<": reading.value < rule.threshold,
                "<=": reading.value <= rule.threshold,
                "==": reading.value == rule.threshold,
            }
            if not ops[rule.operator]:
                continue

            payload: dict[str, Any] = {}
            if rule.target_action == CommandAction.set_speed:
                payload["speed_pct"] = 100
            system_user = store.users.get("u-admin") or next(iter(store.users.values()))
            try:
                cmd = self.create_command(
                    system_user,
                    CommandCreate(
                        device_id=rule.target_device_id,
                        action=rule.target_action,
                        payload=payload,
                        reason=f"Sensor rule: {rule.name}",
                    ),
                )
            except HTTPException:
                continue
            rule.last_fired = utcnow()
            store.rules[rule.id] = rule
            store.add_audit(
                AuditEvent(
                    id=new_id("aud-"),
                    actor="system",
                    action="rule.fired",
                    target=rule.id,
                    detail=f"{rule.name}: {reading.metric}={reading.value} {rule.operator} {rule.threshold}",
                    severity="warning",
                )
            )
            fired.append(cmd)
        return fired
