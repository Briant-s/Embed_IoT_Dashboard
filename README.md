# 💧 IoT Humidity & AC Dashboard

> A real-time Streamlit dashboard for monitoring air humidity and controlling an air conditioner over MQTT.

The dashboard connects to an MQTT broker, listens for live sensor status (humidity, temperature, AC state), and lets you send commands back to the device — turn the AC on/off, switch modes, toggle auto mode, and set the humidity threshold. It also keeps a rolling history you can view as a trend chart and export to CSV.

It works with a real IoT device or with the included simulator, so you can try it end-to-end without any hardware.

## Features

- Live humidity and temperature readings with trend charts
- One-click AC controls: power, mode (dry/cool), auto mode, and humidity threshold
- Connection status badges for the broker and the device, with offline detection
- A Logs page with a table view and CSV export
- Works with public or private MQTT brokers (plain TCP or WebSocket/TLS, e.g. HiveMQ)
- A built-in simulator that mimics a real device for testing
- Configurable entirely through a `.env` file — no code changes needed

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for dependency management
- An MQTT broker (a public one like `broker.hivemq.com` works out of the box)

## Getting started

**1. Install dependencies**

```bash
uv sync
```

**2. Configure your broker**

Edit the `.env` file in the project root to point at your MQTT broker and topics. The defaults connect to HiveMQ's public broker over secure WebSockets:

```bash
MQTT_HOST=broker.hivemq.com
MQTT_PORT=8884
MQTT_TRANSPORT=websockets
MQTT_WS_PATH=/mqtt
MQTT_TLS=on
MQTT_TOPIC_BASE=gio-humidity-ac
```

**3. Run the dashboard**

```bash
uv run streamlit run app.py
```

The dashboard opens in your browser at `http://localhost:8501`.

**4. (Optional) Run the simulator**

In a second terminal, start the fake device so you have live data to look at:

```bash
uv run python simulator.py
```

The simulator publishes status updates every couple of seconds and responds to the commands you send from the dashboard.

> [!TIP]
> The public `broker.hivemq.com` is shared with everyone. For cleaner testing, set a unique `MQTT_TOPIC_BASE` (e.g. `gio-humidity-ac-9f3a2`) in your `.env` so you don't pick up other people's messages.

## How it works

The device and dashboard communicate over a small set of MQTT topics under a shared prefix (`MQTT_TOPIC_BASE`):

| Topic | Direction | Payload | Purpose |
| --- | --- | --- | --- |
| `<base>/cmd/power` | Dashboard → device | `on` / `off` | Turn the AC on or off |
| `<base>/cmd/mode` | Dashboard → device | `dry` / `cool` | Change the AC mode |
| `<base>/cmd/threshold` | Dashboard → device | `30`–`95` | Set the humidity threshold |
| `<base>/cmd/auto` | Dashboard → device | `on` / `off` | Toggle auto mode |
| `<base>/status` | Device → dashboard | JSON | Humidity, temperature, threshold, mode, power, auto |

A typical `status` payload looks like:

```json
{ "temp": 24.7, "hum": 55.4, "threshold": 70, "ac": "off", "mode": "dry", "auto": true }
```

## Project structure

| File | Description |
| --- | --- |
| `app.py` | The Streamlit app: layout, pages (Dashboard + Logs), metrics, charts, and control widgets. |
| `mqtt_client.py` | Background MQTT client that connects to the broker, parses incoming status, publishes commands, and holds shared state for the UI. |
| `config.py` | Central configuration. Reads all settings from the `.env` file (broker, transport, topics, thresholds, UI behavior). |
| `simulator.py` | A fake IoT device for testing without hardware — reacts to commands and publishes status updates. |
| `.env` | Your broker connection and topic settings. |
| `.streamlit/config.toml` | Theme and font settings (colors, Plus Jakarta Sans font). |
| `static/` | Self-hosted font files served by the app. |

## Configuration

All settings live in `.env` and have sensible defaults. The most common ones:

| Variable | Default | Description |
| --- | --- | --- |
| `MQTT_HOST` | `localhost` | Broker hostname |
| `MQTT_PORT` | `1883` | Broker port (`8884` for HiveMQ WebSocket/TLS) |
| `MQTT_TRANSPORT` | `tcp` | `tcp` or `websockets` |
| `MQTT_TLS` | auto | Enable TLS (`on`/`off`; auto-on for ports 8883/8884) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | – | Credentials for private brokers (e.g. HiveMQ Cloud) |
| `MQTT_TOPIC_BASE` | `gio-humidity-ac` | Prefix for all topics |

> [!NOTE]
> To use a private HiveMQ Cloud cluster, set `MQTT_HOST` to your cluster URL and add `MQTT_USERNAME` and `MQTT_PASSWORD`. TLS and the WebSocket path are already configured for port 8884.

## Troubleshooting

- **No data on the dashboard** — Make sure something is publishing to `<base>/status`. Run the simulator, or check that your device is online and using the same `MQTT_TOPIC_BASE`.
- **"Broker connected but no sensor data" warning** — The broker link is up but no readings are arriving. It clears automatically once data resumes.
- **Changes to `.env` or the theme don't apply** — Fully restart the Streamlit process; a browser refresh is not enough.
