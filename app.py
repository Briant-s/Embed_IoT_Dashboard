"""Streamlit IoT humidity dashboard.

UI is split into small, self-contained render_* functions. Each one takes
only what it needs (a `snap` dict for display, and/or the `service` for
commands) and renders into whatever Streamlit container is *currently
active*. That means you can freely rearrange the layout in `main()` — put
any piece inside a column, tab, expander, or sidebar — without touching the
logic inside the functions.

Conventions
-----------
* Display widgets take `snap: dict` (a DashboardState snapshot).
* Command widgets take `service: MqttService`.
* No function assumes it's at the top level, so nesting them in
  `st.columns`, `st.tabs`, `with st.container()`, etc. all work.
"""

from __future__ import annotations

import datetime as dt
import time

import altair as alt
import pandas as pd
import streamlit as st

import config
from mqtt_client import create_service


@st.cache_resource
def get_service():
    return create_service()


# ---------------------------------------------------------------------------
# Helpers (pure logic, no Streamlit calls)
# ---------------------------------------------------------------------------
def _device_badge(snap: dict) -> tuple[str, str, str, str]:
    """Device badge props derived from reading freshness.

    Returns (label, color, icon, severity) where severity is
    "ok" | "stale" | "nodata".
    """
    last = snap["last_update"]
    if last is None:
        return ("Device: no data", "gray", ":material/sensors_off:", "nodata")
    age = time.time() - last
    if age <= config.DEVICE_TIMEOUT_SECONDS:
        return (f"Device: online ({age:.0f}s ago)", "green",
                ":material/sensors:", "ok")
    return (f"Device: offline ({age:.0f}s)", "orange",
            ":material/sensors_off:", "stale")


def _warn_disconnected(snap: dict) -> bool:
    """True only once the broker has been down past the grace period."""
    disconnected_since = snap.get("disconnected_since")
    return (
        not snap["connected"]
        and disconnected_since is not None
        and (time.time() - disconnected_since) >= config.DISCONNECT_GRACE_SECONDS
    )


# ---------------------------------------------------------------------------
# Display components — each takes `snap` and renders into the active container
# ---------------------------------------------------------------------------
def render_status(snap: dict) -> None:
    """Broker + device connection status (as badges) and any warnings.

    Renders into the current container. For live updates, call it from a
    timed fragment (see `status_fragment`) rather than a manual placeholder
    loop — a fresh element tree per run avoids stale/stuck messages.
    """
    broker_label, broker_color, broker_icon = (
        ("Broker: connected", "green", ":material/cloud_done:")
        if snap["connected"]
        else ("Broker: disconnected", "red", ":material/cloud_off:")
    )
    dev_label, dev_color, dev_icon, severity = _device_badge(snap)
    last = (dt.datetime.fromtimestamp(snap["last_update"]).strftime("%H:%M:%S")
            if snap["last_update"] else "—")

    st.badge(broker_label, icon=broker_icon, color=broker_color)
    st.badge(dev_label, icon=dev_icon, color=dev_color)
    st.caption(f"Last update: {last}")

    if _warn_disconnected(snap):
        st.warning("Broker disconnected — attempting to reconnect…")
    elif snap["connected"] and severity == "stale":
        st.warning(
            "Broker is connected but no sensor data is arriving — "
            "the IoT device/simulator may be offline."
        )
    elif snap["connected"] and severity == "nodata":
        st.info("Connected to broker. Waiting for the first reading…")
    if snap["last_error"]:
        st.caption(f"MQTT: {snap['last_error']}")


@st.fragment(run_every="1s")
def status_fragment(service) -> None:
    """Self-refreshing status block.

    Runs on its own ~1s timer and rebuilds a fresh element tree each tick,
    so transient elements (warnings / info) appear and disappear cleanly
    with no placeholder diffing, flicker, or stuck messages. Pulls a fresh
    snapshot from the service every run.
    """
    render_status(service.state.snapshot())


def render_humidity_metric(snap: dict) -> None:
    """Single humidity metric (with delta vs previous reading)."""
    humidity = snap["latest_humidity"]
    if humidity is not None:
        delta = None
        if snap["previous_humidity"] is not None:
            delta = round(humidity - snap["previous_humidity"], 1)
        st.metric("Humidity", f"{humidity:.1f} %", delta=delta, border=True)
    else:
        st.metric("Humidity", "—", border=True)


def render_temperature_metric(snap: dict) -> None:
    """Single temperature metric (with delta vs previous reading)."""
    temp = snap.get("temperature")
    if temp is not None:
        delta = None
        prev = snap.get("previous_temperature")
        if prev is not None:
            delta = round(temp - prev, 1)
        st.metric("Temperature", f"{temp:.1f} °C", delta=delta, border=True)
    else:
        st.metric("Temperature", "—", border=True)


def render_mode_metric(snap: dict) -> None:
    """Single AC mode metric."""
    st.metric("AC Mode", snap["ac_mode"], border=True)


def render_power_metric(snap: dict) -> None:
    """Single AC power metric (shows AUTO tag when auto mode is on)."""
    label = "ON" if snap["ac_on"] else "OFF"
    if snap.get("auto"):
        label += " (AUTO)"
    st.metric("AC Power", label, border=True)


def render_threshold_caption(snap: dict) -> None:
    """Device-reported humidity threshold caption (no-op if unknown)."""
    thr = snap.get("threshold")
    if thr is not None:
        st.caption(f"Device humidity threshold: **{thr:.0f}%**")


def render_metrics_row(snap: dict) -> None:
    # Convenience: all four metrics in one row.
    c1, c2, c3, c4 = st.columns(4)
    render_threshold_caption(snap)
    with c1:
        render_humidity_metric(snap)
    with c2:
        render_temperature_metric(snap)
    with c3:
        render_mode_metric(snap)
    with c4:
        render_power_metric(snap)



def build_humidity_chart(history: list) -> alt.LayerChart:
    """Build (but don't render) the humidity trend chart from history."""
    df = pd.DataFrame(history, columns=["ts", "humidity"])
    df["time"] = pd.to_datetime(df["ts"], unit="s")

    line = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("time:T", title="Time"),
            y=alt.Y("humidity:Q", title="Humidity (%)",
                    scale=alt.Scale(domain=[0, 100])),
            tooltip=["time:T", "humidity:Q"],
        )
    )
    band = (
        alt.Chart(pd.DataFrame({"low": [config.COMFORT_LOW],
                                "high": [config.COMFORT_HIGH]}))
        .mark_rect(opacity=0.12, color="green")
        .encode(y="low:Q", y2="high:Q")
    )
    return band + line


def render_humidity_chart(snap: dict) -> None:
    """Humidity trend chart, or an empty-state caption."""
    history = snap["history"]
    if history:
        st.altair_chart(build_humidity_chart(history), width="stretch")
    else:
        st.caption("No readings yet. Humidity data will appear once the "
                   f"status topic (`{config.TOPIC_STATUS}`) sends data.")


# ---------------------------------------------------------------------------
# Command components — each takes `service` and publishes on click
# ---------------------------------------------------------------------------
def render_power_controls(service, key_prefix: str = "") -> None:
    """Power ON / OFF buttons."""
    k = f"{key_prefix}power"
    c1, c2 = st.columns(2)
    if c1.button("Power ON", type="primary", width="stretch", key=f"{k}_on"):
        service.set_power(True)
        st.success("Sent: power on")
    if c2.button("Power OFF", width="stretch", key=f"{k}_off"):
        service.set_power(False)
        st.success("Sent: power off")


def render_mode_controls(service, key_prefix: str = "") -> None:
    """Mode DRY / COOL buttons."""
    k = f"{key_prefix}mode"
    c1, c2 = st.columns(2)
    if c1.button("Mode: DRY", width="stretch", key=f"{k}_dry"):
        service.set_mode("dry")
        st.success("Sent: mode dry")
    if c2.button("Mode: COOL", width="stretch", key=f"{k}_cool"):
        service.set_mode("cool")
        st.success("Sent: mode cool")


def render_auto_control(service, key_prefix: str = "") -> None:
    """Auto-mode toggle + apply button."""
    k = f"{key_prefix}auto"
    auto_on = st.toggle("Auto mode", key=f"{k}_toggle")
    if st.button("Apply Auto", width="stretch", key=f"{k}_apply"):
        service.set_auto(auto_on)
        st.success(f"Sent: auto {'on' if auto_on else 'off'}")


def render_threshold_control(service, key_prefix: str = "") -> None:
    """Humidity-threshold slider + apply button."""
    k = f"{key_prefix}threshold"
    threshold = st.slider(
        "Humidity threshold (%)",
        config.THRESHOLD_MIN, config.THRESHOLD_MAX,
        min(max(int(config.AUTO_DRY_THRESHOLD), config.THRESHOLD_MIN),
            config.THRESHOLD_MAX),
        1,
        key=f"{k}_slider",
    )
    if st.button("Apply Threshold", width="stretch", key=f"{k}_apply"):
        service.set_threshold(threshold)
        st.success(f"Sent: threshold {threshold}")


def render_controls(service, key_prefix: str = "") -> None:
    """Convenience: all command controls stacked.

    Prefer the individual render_*_control(s) functions for custom layouts.
    Pass a distinct `key_prefix` if you render these in more than one place.
    """
    render_power_controls(service, key_prefix)
    render_mode_controls(service, key_prefix)
    render_auto_control(service, key_prefix)
    render_threshold_control(service, key_prefix)


def render_sidebar(service):
    """Settings sidebar.

    Also hosts the app title and the self-refreshing status block. Returns
    the refresh interval (seconds) for the metrics/chart area.
    """
    with st.sidebar:
        st.title("💧 Air Humidity & AC Control")
        st.badge("LA01 - Group 9")
        st.divider()

        # Self-refreshing status block (runs on its own ~1s timer).
        status_fragment(service)
        st.divider()

        st.header("⚙️ Settings")
        st.caption(f"Broker: `{config.MQTT_HOST}:{config.MQTT_PORT}`")
        refresh = st.slider("Refresh interval (s)", 1, 10, 2, key="refresh")
        st.divider()
        st.caption("Set MQTT_HOST etc. as env vars to point at your broker.")
    return refresh


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def dashboard_page() -> None:
    """Main dashboard: live metrics, controls, and humidity trend."""
    service = get_service()

    # Sidebar hosts the title + self-refreshing status block.
    refresh = render_sidebar(service)

    @st.fragment(run_every=f"{refresh}s")
    def data_area() -> None:
        snap = service.state.snapshot()
        st.subheader("Metrics")
        # Two metrics per row so they stay readable in the narrower column.
        m1, m2 = st.columns(2)
        with m1:
            render_humidity_metric(snap)
            render_mode_metric(snap)
        with m2:
            render_temperature_metric(snap)
            render_power_metric(snap)
        render_threshold_caption(snap)

    # Metrics (left) and controls (right) side by side.
    col_metrics, col_controls = st.columns(2)
    with col_metrics:
        data_area()
    with col_controls:
        st.subheader("AC Control")
        render_controls(service)

    # Humidity trend chart spans the full width below the two columns.
    st.subheader("Humidity Trend")

    @st.fragment(run_every=f"{refresh}s")
    def chart_area() -> None:
        render_humidity_chart(service.state.snapshot())

    chart_area()


def logs_dataframe(snap: dict) -> pd.DataFrame:
    """Build a tidy logs DataFrame (timestamp + humidity) from history."""
    df = pd.DataFrame(snap["history"], columns=["timestamp", "humidity"])
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    return df


def logs_page() -> None:
    """Logs page: a table of recorded readings and a CSV export button."""
    st.title("Logs")
    service = get_service()
    df = logs_dataframe(service.state.snapshot())

    if df.empty:
        st.info("No logs recorded yet. Readings will appear here as they "
                "arrive.")
        return

    st.dataframe(df, width="stretch", hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    c1, c2 = st.columns(2)
    c1.download_button(
        "Export to CSV",
        data=csv,
        file_name="humidity_logs.csv",
        mime="text/csv",
        icon=":material/download:",
        width="stretch",
    )
    if c2.button("Clear logs", icon=":material/delete:", width="stretch"):
        service.state.clear_history()
        st.toast("Logs cleared.")
        st.rerun()


# ---------------------------------------------------------------------------
# Entry point: multipage navigation (pages share the cached MQTT service)
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="IoT Humidity Dashboard", page_icon="💧",
                       layout="wide")
    pages = [
        st.Page(dashboard_page, title="Dashboard", icon=":material/dashboard:",
                default=True),
        st.Page(logs_page, title="Logs", icon=":material/receipt_long:"),
    ]
    st.navigation(pages).run()


if __name__ == "__main__":
    main()
