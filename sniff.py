"""Debug helper: print every message under the project's topic base.

Run in a terminal, then click buttons in the dashboard to watch the
command payloads arrive live:

    uv run python sniff.py

Uses the same broker/transport/TLS settings as the dashboard (config.py),
so it works against HiveMQ's WebSocket port 8884 out of the box.
"""

from __future__ import annotations

import os
import uuid

import paho.mqtt.client as mqtt

import config


def _make_client() -> mqtt.Client:
    client = mqtt.Client(
        client_id=f"iot-sniff-{os.getpid()}-{uuid.uuid4().hex[:6]}",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        transport=config.MQTT_TRANSPORT,
    )
    if config.MQTT_TRANSPORT == "websockets":
        client.ws_set_options(path=config.MQTT_WS_PATH)
    if config.MQTT_USE_TLS:
        client.tls_set()
    if config.MQTT_USERNAME:
        client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    return client


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[sniff] connected rc={reason_code}")
    topic = f"{config.MQTT_TOPIC_BASE}/#"
    client.subscribe(topic, qos=1)
    print(f"[sniff] subscribed to {topic}")


def on_message(client, userdata, msg):
    print(f"[sniff] {msg.topic} = {msg.payload.decode(errors='replace')!r}")


def main() -> None:
    client = _make_client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print(f"[sniff] listening on {config.MQTT_HOST}:{config.MQTT_PORT} "
          f"(transport={config.MQTT_TRANSPORT}, tls={config.MQTT_USE_TLS})")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
