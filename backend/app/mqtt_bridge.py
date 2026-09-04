from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

logger = logging.getLogger("actuatorhub.mqtt")


class MqttBridge:
    """MQTT publisher/subscriber with simulated fallback when broker is unavailable."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        on_message: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.host = host or os.getenv("MQTT_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.on_message = on_message
        self._client = None
        self.connected = False
        self.mode = "simulated"
        self._lock = threading.Lock()
        self.published: list[tuple[str, dict[str, Any]]] = []

    def start(self) -> None:
        try:
            import paho.mqtt.client as mqtt

            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="actuatorhub-api")
            client.on_connect = self._on_connect
            client.on_message = self._on_mqtt_message
            client.on_disconnect = self._on_disconnect
            client.connect_async(self.host, self.port, keepalive=30)
            client.loop_start()
            self._client = client
            logger.info("MQTT bridge connecting to %s:%s", self.host, self.port)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MQTT unavailable (%s) — running in simulated mode", exc)
            self.connected = False
            self.mode = "simulated"

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        if reason_code == 0 or str(reason_code) in {"Success", "0"}:
            self.connected = True
            self.mode = "live"
            client.subscribe("actuators/+/+/+/ack")
            client.subscribe("sensors/#")
            logger.info("MQTT connected")
        else:
            self.connected = False
            self.mode = "simulated"
            logger.warning("MQTT connect failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        self.connected = False
        self.mode = "simulated"
        logger.warning("MQTT disconnected: %s", reason_code)

    def _on_mqtt_message(self, client, userdata, msg):  # noqa: ANN001
        if not self.on_message:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
        self.on_message(msg.topic, payload)

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        body = json.dumps(payload)
        with self._lock:
            self.published.append((topic, payload))
            self.published = self.published[-200:]
        if self._client is not None and self.connected:
            try:
                self._client.publish(topic, body, qos=1)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("MQTT publish failed: %s", exc)
        # Simulated success — edge agent not required for demo
        return True
