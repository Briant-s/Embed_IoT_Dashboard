"""Fake IoT device for testing the dashboard without real hardware.

Connects with the SAME broker/transport/TLS settings as the dashboard
(config.py), so it works against HiveMQ's WebSocket port 8884.

It listens on the four command topics and maintains AC state accordingly,
then periodically publishes a combined `status` payload (random-walk
humidity + temp + current settings). Run in a second terminal:

    uv run python simulator.py
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid

import paho.mqtt.client as mqtt

import config

# --- simulated device state ---------------------------------------------
state = {
    "power": "off",   # on | off
    "mode": "cool",   # dry | cool
    "auto": "off",    # on | off
    "threshold": 65,  # 30-95
}


def _make_client() -> mqtt.Client:
    client = mqtt.Client(
        client_id=f"iot-simulator-{os.getpid()}-{uuid.uuid4().hex[:6]}",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        transport=config.MQTT_TRANSPORT,
    )
    if config.MQTT_TRANSPORT == "websockets":
        client.ws_set_options(path=config.MQTT_WS_PATH)
    if config.MQTT_USE_TLS:
        client.tls_set()
    if config.MQTT_USERNAME:
        client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[sim] connected rc={reason_code}")
    for topic in (
        config.TOPIC_CMD_POWER,
        config.TOPIC_CMD_MODE,
        config.TOPIC_CMD_THRESHOLD,
        config.TOPIC_CMD_AUTO,
    ):
        client.subscribe(topic, qos=1)
        print(f"[sim] subscribed {topic}")


def on_message(client, userdata, msg):
    payload = msg.payload.decode(errors="replace").strip().lower()
    topic = msg.topic
    if topic == config.TOPIC_CMD_POWER:
        state["power"] = "on" if payload == "on" else "off"
        if state["power"] == "off":
            state["auto"] = "off"  # power off also forces auto off
    elif topic == config.TOPIC_CMD_MODE:
        if payload in ("dry", "cool"):
            state["mode"] = payload
    elif topic == config.TOPIC_CMD_AUTO:
        state["auto"] = "on" if payload == "on" else "off"
    elif topic == config.TOPIC_CMD_THRESHOLD:
        try:
            val = int(payload)
            state["threshold"] = max(
                config.THRESHOLD_MIN, min(config.THRESHOLD_MAX, val)
            )
        except ValueError:
            print(f"[sim] bad threshold: {payload!r}")
    else:
        return
    print(f"[sim] cmd {topic} -> {payload!r} | state={state}")


def main() -> None:
    client = _make_client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT,
                         config.MQTT_KEEPALIVE)
    client.loop_start()
    print(f"[sim] -> {config.MQTT_HOST}:{config.MQTT_PORT} "
          f"(transport={config.MQTT_TRANSPORT}, tls={config.MQTT_USE_TLS})")

    humidity = 55.0
    temp = 27.0
    try:
        while True:
            humidity += random.uniform(-3, 3)
            humidity = max(20.0, min(90.0, humidity))
            temp += random.uniform(-0.5, 0.5)
            temp = max(18.0, min(35.0, temp))
            payload = json.dumps({
                "humidity": round(humidity, 1),
                "temp": round(temp, 1),
                "threshold": state["threshold"],
                "mode": state["mode"],
                "power": state["power"],
                "auto": state["auto"],
                "ts": time.time(),
            })
            info = client.publish(config.TOPIC_STATUS, payload, qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[sim] publish failed rc={info.rc} (broker down? retry)")
            else:
                print(f"[sim] status {payload}")
            time.sleep(2)
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
