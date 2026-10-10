# Background MQTT client for the Streamlit dashboard.


from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import paho.mqtt.client as mqtt

import config


def _as_bool(value) -> bool:
    """Coerce "on"/"off"/"true"/1/True etc. into a bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("on", "true", "1", "yes")


@dataclass
class Reading:
    """A single humidity sample."""
    timestamp: float
    humidity: float


@dataclass
class DashboardState:
    # Shared state updated by the MQTT thread, read by the Streamlit UI.
    lock: threading.Lock = field(default_factory=threading.Lock)
    connected: bool = False
    disconnected_since: Optional[float] = None
    history: Deque[Reading] = field(
        default_factory=lambda: deque(maxlen=config.HISTORY_SIZE)
    )
    latest_humidity: Optional[float] = None
    previous_humidity: Optional[float] = None
    ac_mode: str = "UNKNOWN"
    ac_on: bool = False
    auto: bool = False
    temperature: Optional[float] = None
    previous_temperature: Optional[float] = None
    threshold: Optional[float] = None
    last_update: Optional[float] = None
    last_error: Optional[str] = None
    # Raw status payload (status schema not finalised yet).
    last_status_raw: Optional[str] = None

    def add_reading(self, humidity: float, ts: float) -> None:
        with self.lock:
            self.previous_humidity = self.latest_humidity
            self.latest_humidity = humidity
            self.history.append(Reading(ts, humidity))
            self.last_update = ts

    def clear_history(self) -> None:
        """Empty the recorded reading history (used by the Logs page).

        Only clears the logged history/trend data; the latest live values
        keep updating from incoming status messages.
        """
        with self.lock:
            self.history.clear()
            self.previous_humidity = None

    def snapshot(self) -> dict:
        """Return a plain-dict copy safe to use in the UI thread."""
        with self.lock:
            return {
                "connected": self.connected,
                "disconnected_since": self.disconnected_since,
                "latest_humidity": self.latest_humidity,
                "previous_humidity": self.previous_humidity,
                "ac_mode": self.ac_mode,
                "ac_on": self.ac_on,
                "auto": self.auto,
                "temperature": self.temperature,
                "previous_temperature": self.previous_temperature,
                "threshold": self.threshold,
                "last_update": self.last_update,
                "last_error": self.last_error,
                "last_status_raw": self.last_status_raw,
                "history": [(r.timestamp, r.humidity) for r in self.history],
            }


class MqttService:
    """Owns the paho client and routes messages into DashboardState."""

    def __init__(self) -> None:
        self.state = DashboardState()
        # paho-mqtt v2 requires an explicit callback API version.
        self._client = mqtt.Client(
            client_id=config.MQTT_CLIENT_ID,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            transport=config.MQTT_TRANSPORT,
        )
        # For WebSocket transport (e.g. HiveMQ port 8884) the broker serves
        # MQTT at a specific path, typically "/mqtt".
        if config.MQTT_TRANSPORT == "websockets":
            self._client.ws_set_options(path=config.MQTT_WS_PATH)
        # Enable TLS for secure ports (8883 TCP / 8884 WSS). Uses the
        # system CA bundle to verify the broker certificate.
        if config.MQTT_USE_TLS:
            self._client.tls_set()
        if config.MQTT_USERNAME:
            self._client.username_pw_set(
                config.MQTT_USERNAME, config.MQTT_PASSWORD
            )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._started = False

    # --- lifecycle -------------------------------------------------------
    def start(self) -> None:
        # Spin up the network loop and connect, with auto-reconnect.
        if self._started:
            return
        # Retry backoff between 1s and 30s on connection loss.
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            self._client.connect_async(
                config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE
            )
            self._client.loop_start()  # background thread drives (re)connect
            self._started = True
        except Exception as exc:  # noqa: BLE001 - surface any error to UI
            with self.state.lock:
                self.state.last_error = f"connect failed: {exc}"

    def stop(self) -> None:
        if not self._started:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._started = False

    def set_power(self, on: bool) -> None:
        """Turn the AC on/off. Turning on/off also disables auto on device."""
        self._client.publish(config.TOPIC_CMD_POWER, "on" if on else "off", qos=1)

    def set_mode(self, mode: str) -> None:
        """Change AC mode. Expected values: "dry" | "cool"."""
        self._client.publish(config.TOPIC_CMD_MODE, mode.lower(), qos=1)

    def set_threshold(self, value: int) -> None:
        """Set humidity threshold (clamped to the configured valid range)."""
        clamped = max(config.THRESHOLD_MIN, min(config.THRESHOLD_MAX, int(value)))
        self._client.publish(config.TOPIC_CMD_THRESHOLD, str(clamped), qos=1)

    def set_auto(self, on: bool) -> None:
        """Enable/disable auto mode."""
        self._client.publish(config.TOPIC_CMD_AUTO, "on" if on else "off", qos=1)

    # --- paho callbacks (run on the network thread) ----------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            with self.state.lock:
                self.state.connected = True
                self.state.disconnected_since = None
                self.state.last_error = None
            # (re)subscribe on every successful connect.
            # Status schema is TBD; parsing is handled in _on_message later.
            client.subscribe(config.TOPIC_STATUS, qos=1)
        else:
            with self.state.lock:
                self.state.connected = False
                self.state.last_error = f"connect rc={reason_code}"

    def _on_disconnect(self, client, userdata, *args):
        with self.state.lock:
            self.state.connected = False
            # Record when we lost the link, but don't overwrite an existing
            # timestamp (repeated disconnect callbacks shouldn't reset the
            # grace-period clock).
            if self.state.disconnected_since is None:
                self.state.disconnected_since = time.time()

    def _on_message(self, client, userdata, msg):
        try:
            text = msg.payload.decode("utf-8").strip()
            if msg.topic == config.TOPIC_STATUS:
                self._handle_status(text)
        except Exception as exc:  # noqa: BLE001 - bad payloads shouldn't crash loop
            with self.state.lock:
                self.state.last_error = f"bad message on {msg.topic}: {exc}"

    def _handle_status(self, text: str) -> None:
        # Parse a status JSON payload and update DashboardState.
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("status payload is not a JSON object")

        ts = float(data.get("ts", time.time()))

        # humidity -> drives the trend chart + top metric
        hum = data.get("hum", data.get("humidity"))
        if hum is not None:
            self.state.add_reading(float(hum), ts)

        with self.state.lock:
            self.state.last_status_raw = text
            self.state.last_update = ts
            self.state.last_error = None

            if "temp" in data and data["temp"] is not None:
                self.state.previous_temperature = self.state.temperature
                self.state.temperature = float(data["temp"])

            if "threshold" in data and data["threshold"] is not None:
                self.state.threshold = float(data["threshold"])

            if "mode" in data and data["mode"] is not None:
                self.state.ac_mode = str(data["mode"]).upper()

            power = data.get("ac", data.get("power"))
            if power is not None:
                self.state.ac_on = _as_bool(power)

            if "auto" in data and data["auto"] is not None:
                self.state.auto = _as_bool(data["auto"])

    @staticmethod
    def _parse_humidity(text: str) -> tuple[float, float]:
        """Accept either a bare number ("62.5") or JSON ({"humidity":62.5})."""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return float(data["humidity"]), float(data.get("ts", time.time()))
            return float(data), time.time()
        except (json.JSONDecodeError, ValueError, KeyError):
            return float(text), time.time()


# Module-level singleton. Streamlit imports this once per process and
# reuses it across reruns via st.cache_resource (see app.py).
def create_service() -> MqttService:
    service = MqttService()
    service.start()
    return service
