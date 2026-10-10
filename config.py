# Central configuration for the IoT humidity dashboard.

import os
from dotenv import load_dotenv

load_dotenv()

# --- MQTT broker ---------------------------------------------------------
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "60"))

# --- Transport / TLS -----------------------------------------------------
MQTT_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp").lower()
MQTT_WS_PATH = os.getenv("MQTT_WS_PATH", "/mqtt")
MQTT_TLS = os.getenv("MQTT_TLS", "").lower()
if MQTT_TLS in ("1", "true", "yes", "on"):
    MQTT_USE_TLS = True
elif MQTT_TLS in ("0", "false", "no", "off"):
    MQTT_USE_TLS = False
else:
    MQTT_USE_TLS = MQTT_PORT in (8883, 8884)
    
    
    
import os as _os
import uuid as _uuid

MQTT_CLIENT_ID = os.getenv(
    "MQTT_CLIENT_ID",
    f"iot-dashboard-{_os.getpid()}-{_uuid.uuid4().hex[:6]}",
)

# --- Topics --------------------------------------------------------------
MQTT_TOPIC_BASE = os.getenv("MQTT_TOPIC_BASE", "gio-humidity-ac")

# Dashboard -> device commands (plain-string payloads).
TOPIC_CMD_POWER = os.getenv("TOPIC_CMD_POWER", f"{MQTT_TOPIC_BASE}/cmd/power")
TOPIC_CMD_MODE = os.getenv("TOPIC_CMD_MODE", f"{MQTT_TOPIC_BASE}/cmd/mode")
TOPIC_CMD_THRESHOLD = os.getenv(
    "TOPIC_CMD_THRESHOLD", f"{MQTT_TOPIC_BASE}/cmd/threshold"
)
TOPIC_CMD_AUTO = os.getenv("TOPIC_CMD_AUTO", f"{MQTT_TOPIC_BASE}/cmd/auto")

# Device -> dashboard status (temp, humidity threshold, AC status/mode).
TOPIC_STATUS = os.getenv("TOPIC_STATUS", f"{MQTT_TOPIC_BASE}/status")

# Valid threshold range accepted by cmd/threshold.
THRESHOLD_MIN = int(os.getenv("THRESHOLD_MIN", "30"))
THRESHOLD_MAX = int(os.getenv("THRESHOLD_MAX", "95"))

# --- Dashboard behaviour -------------------------------------------------
# How many recent readings to keep in memory for the trend chart.
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "200"))

# Comfort band shown on the chart (percent relative humidity).
COMFORT_LOW = float(os.getenv("COMFORT_LOW", "40"))
COMFORT_HIGH = float(os.getenv("COMFORT_HIGH", "60"))

# Default auto-mode thresholds (percent RH). Humidity above HIGH -> DRY,
# below LOW -> OFF/FAN, in between -> FAN. These are user-adjustable in the UI.
AUTO_DRY_THRESHOLD = float(os.getenv("AUTO_DRY_THRESHOLD", "65"))
AUTO_FAN_THRESHOLD = float(os.getenv("AUTO_FAN_THRESHOLD", "45"))

# Valid AC modes.
AC_MODES = ["OFF", "FAN", "COOL", "DRY", "AUTO"]

# Device-liveness: if no humidity reading arrives within this many seconds,
# treat the IoT device/simulator as offline even if the broker link is up.
# Rule of thumb: 2-3x the device's publish interval (simulator = 2s).
DEVICE_TIMEOUT_SECONDS = float(os.getenv("DEVICE_TIMEOUT_SECONDS", "6"))

# How long the broker must stay disconnected before the UI shows the
# "disconnected" warning. Avoids a warning flash on startup or brief blips.
DISCONNECT_GRACE_SECONDS = float(os.getenv("DISCONNECT_GRACE_SECONDS", "5"))
