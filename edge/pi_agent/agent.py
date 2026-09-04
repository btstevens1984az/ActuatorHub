#!/usr/bin/env python3
"""ActuatorHub Raspberry Pi edge agent.

Subscribes to MQTT command topics and drives GPIO / simulated actuators.
Works without hardware when ACTUATORHUB_SIM=1 (default).
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pi-agent")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
SITE = os.getenv("ACTUATORHUB_SITE", "hq-dc1")
SIM = os.getenv("ACTUATORHUB_SIM", "1") == "1"
EDGE_ID = os.getenv("ACTUATORHUB_EDGE_ID", "pi-edge-01")

# Map logical actuator keys → GPIO BCM pins (when not simulating)
GPIO_MAP = {
    "relay/crac-a": 17,
    "relay/exhaust": 27,
    "fan/row3": 22,
}

state: dict[str, Any] = {k: {"on": False} for k in GPIO_MAP}


def set_actuator(key: str, on: bool, extra: dict[str, Any] | None = None) -> None:
    state.setdefault(key, {})["on"] = on
    if extra:
        state[key].update(extra)
    if SIM:
        log.info("[SIM] %s → %s %s", key, "ON" if on else "OFF", extra or {})
        return
    try:
        import RPi.GPIO as GPIO  # type: ignore

        pin = GPIO_MAP.get(key)
        if pin is None:
            log.warning("No GPIO mapping for %s", key)
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
        log.info("GPIO %s (%s) → %s", pin, key, on)
    except Exception as exc:  # noqa: BLE001
        log.error("GPIO failure: %s", exc)


def handle_command(topic: str, payload: dict[str, Any]) -> None:
    # actuators/<site>/<kind>/<name>/cmd
    parts = topic.split("/")
    if len(parts) < 5:
        return
    key = f"{parts[2]}/{parts[3]}"
    action = payload.get("action", "")
    body = payload.get("payload") or {}

    if action in {"turn_on", "outlet_on", "lock"}:
        set_actuator(key, True)
    elif action in {"turn_off", "outlet_off", "e_stop"}:
        set_actuator(key, False)
    elif action == "unlock":
        set_actuator(key, False, {"unlocked": True})
    elif action == "toggle":
        cur = bool(state.get(key, {}).get("on"))
        set_actuator(key, not cur)
    elif action == "set_speed":
        speed = int(body.get("speed_pct", 50))
        set_actuator(key, speed > 0, {"speed_pct": speed})
    elif action == "reboot_outlet":
        set_actuator(key, False)
        time.sleep(1.0)
        set_actuator(key, True, {"rebooted_outlet": body.get("outlet", 1)})
    else:
        log.warning("Unknown action %s on %s", action, key)
        return

    ack_topic = topic.replace("/cmd", "/ack")
    client.publish(ack_topic, json.dumps({"ok": True, "edge": EDGE_ID, "action": action, "key": key}))


def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
    topic = f"actuators/{SITE}/+/+/cmd"
    client.subscribe(topic)
    log.info("Connected (%s). Subscribed to %s", reason_code, topic)


def on_message(client, userdata, msg):  # noqa: ANN001
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
        payload = {}
    log.info("CMD %s %s", msg.topic, payload)
    handle_command(msg.topic, payload)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=EDGE_ID)
client.on_connect = on_connect
client.on_message = on_message


def main() -> int:
    log.info("ActuatorHub Pi agent starting (sim=%s) → %s:%s", SIM, MQTT_HOST, MQTT_PORT)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    def _stop(*_args: object) -> None:
        log.info("Stopping")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
