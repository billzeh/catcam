#!/usr/bin/env python3
"""CatCam: watch the cats' food dish and report visits to Home Assistant over MQTT.

A visit starts on the first PIR trigger and ends after VISIT_TIMEOUT seconds with
no motion. A snapshot is taken when a visit starts and every SNAPSHOT_INTERVAL
seconds during it. Entities are created in Home Assistant via MQTT discovery.

All settings come from environment variables (see catcam.env.example).
"""

import io
import json
import logging
import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from gpiozero import MotionSensor

log = logging.getLogger("catcam")


# --- Configuration ----------------------------------------------------------

def env(name, default=None, cast=str):
    value = os.environ.get(name)
    if value is None or value == "":
        if default is None:
            raise SystemExit(f"Missing required setting {name} (see catcam.env.example)")
        return default
    return cast(value)


MQTT_HOST = env("MQTT_HOST")
MQTT_PORT = env("MQTT_PORT", 1883, int)
MQTT_USER = env("MQTT_USER", "")
MQTT_PASSWORD = env("MQTT_PASSWORD", "")
DISCOVERY_PREFIX = env("DISCOVERY_PREFIX", "homeassistant")
DEVICE_ID = env("DEVICE_ID", "catcam")

PIR_GPIO = env("PIR_GPIO", 17, int)
VISIT_TIMEOUT = env("VISIT_TIMEOUT", 30, float)      # s without motion that ends a visit
WARMUP = env("WARMUP", 60, float)                    # s after boot to ignore the PIR
SNAPSHOT_INTERVAL = env("SNAPSHOT_INTERVAL", 10, float)  # s between snapshots in a visit; 0 = first only
SNAPSHOT_SIZE = tuple(int(x) for x in env("SNAPSHOT_SIZE", "1296x972").lower().split("x"))
SNAPSHOT_DIR = env("SNAPSHOT_DIR", "")               # also save JPEGs here; empty = don't
SNAPSHOT_KEEP = env("SNAPSHOT_KEEP", 500, int)       # max JPEGs kept in SNAPSHOT_DIR

BASE = DEVICE_ID
T_STATUS = f"{BASE}/status"
T_VISIT = f"{BASE}/visit"
T_SNAPSHOT = f"{BASE}/snapshot"
T_LAST_VISIT = f"{BASE}/last_visit"
T_HA_STATUS = f"{DISCOVERY_PREFIX}/status"


# --- Camera -----------------------------------------------------------------

class Camera:
    """Keeps the camera running so a snapshot is quick and correctly exposed.

    If no camera is found, the script keeps running without snapshots.
    """

    def __init__(self):
        self.cam = None
        try:
            from picamera2 import Picamera2
            self.cam = Picamera2()
            self.cam.configure(self.cam.create_still_configuration(main={"size": SNAPSHOT_SIZE}))
            self.cam.start()
            log.info("Camera started at %dx%d", *SNAPSHOT_SIZE)
        except Exception:
            log.exception("Camera unavailable; continuing without snapshots")
            self.cam = None

    def jpeg(self):
        if self.cam is None:
            return None
        try:
            buf = io.BytesIO()
            self.cam.capture_file(buf, format="jpeg")
            return buf.getvalue()
        except Exception:
            log.exception("Snapshot failed")
            return None

    def close(self):
        if self.cam is not None:
            self.cam.close()


def save_snapshot(data):
    if not SNAPSHOT_DIR:
        return
    folder = Path(SNAPSHOT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / datetime.now().strftime("%Y%m%d-%H%M%S.jpg")).write_bytes(data)
    files = sorted(folder.glob("*.jpg"))
    for old in files[:-SNAPSHOT_KEEP] if SNAPSHOT_KEEP > 0 else []:
        old.unlink(missing_ok=True)


# --- MQTT / Home Assistant --------------------------------------------------

DEVICE = {
    "identifiers": [DEVICE_ID],
    "name": "CatCam",
    "model": "Raspberry Pi 3 B+ food dish monitor",
    "manufacturer": "DIY",
}


def discovery_configs():
    common = {"availability_topic": T_STATUS, "device": DEVICE}
    return {
        f"{DISCOVERY_PREFIX}/binary_sensor/{DEVICE_ID}/visit/config": {
            **common,
            "name": "Cat at dish",
            "unique_id": f"{DEVICE_ID}_visit",
            "state_topic": T_VISIT,
            "device_class": "occupancy",
        },
        f"{DISCOVERY_PREFIX}/camera/{DEVICE_ID}/snapshot/config": {
            **common,
            "name": "Snapshot",
            "unique_id": f"{DEVICE_ID}_snapshot",
            "topic": T_SNAPSHOT,
        },
        f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/last_visit_start/config": {
            **common,
            "name": "Last visit",
            "unique_id": f"{DEVICE_ID}_last_visit_start",
            "state_topic": T_LAST_VISIT,
            "value_template": "{{ value_json.start }}",
            "device_class": "timestamp",
        },
        f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/last_visit_duration/config": {
            **common,
            "name": "Last visit duration",
            "unique_id": f"{DEVICE_ID}_last_visit_duration",
            "state_topic": T_LAST_VISIT,
            "value_template": "{{ value_json.duration_s }}",
            "device_class": "duration",
            "unit_of_measurement": "s",
            "state_class": "measurement",
        },
    }


class Publisher:
    def __init__(self):
        self.visit_on = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=DEVICE_ID)
        if MQTT_USER:
            self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        self.client.will_set(T_STATUS, "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def start(self):
        # connect_async + loop_start keeps retrying until the broker is reachable.
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect refused: %s", reason_code)
            return
        log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
        client.subscribe(T_HA_STATUS)
        self.announce()

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: %s", reason_code)

    def on_message(self, client, userdata, msg):
        # Home Assistant restarted: re-send discovery and current state.
        if msg.topic == T_HA_STATUS and msg.payload == b"online":
            log.info("Home Assistant came online; re-announcing")
            self.announce()

    def announce(self):
        for topic, config in discovery_configs().items():
            self.client.publish(topic, json.dumps(config), qos=1, retain=True)
        self.client.publish(T_STATUS, "online", qos=1, retain=True)
        self.visit(self.visit_on)

    def visit(self, on):
        self.visit_on = on
        self.client.publish(T_VISIT, "ON" if on else "OFF", qos=1, retain=True)

    def snapshot(self, data):
        self.client.publish(T_SNAPSHOT, data, qos=0, retain=True)

    def last_visit(self, start, duration_s):
        payload = {"start": start.isoformat(timespec="seconds"), "duration_s": duration_s}
        self.client.publish(T_LAST_VISIT, json.dumps(payload), qos=1, retain=True)

    def stop(self):
        # If we can't say goodbye, the broker's last-will message sets "offline" anyway.
        if self.client.is_connected():
            try:
                self.client.publish(T_STATUS, "offline", qos=1, retain=True).wait_for_publish(5)
            except (RuntimeError, ValueError):
                pass
        self.client.disconnect()
        self.client.loop_stop()


# --- Main loop --------------------------------------------------------------

def seconds_since_boot():
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    pub = Publisher()
    pub.start()
    camera = Camera()
    pir = MotionSensor(PIR_GPIO)

    # Only wait out the PIR warm-up if we're starting soon after boot.
    warmup_left = WARMUP - seconds_since_boot()
    if warmup_left > 0:
        log.info("Waiting %.0f s for the PIR to settle", warmup_left)
        stop.wait(warmup_left)
    log.info("Watching GPIO%d", PIR_GPIO)

    visit_start = None        # wall-clock time the visit started
    visit_start_mono = 0.0
    last_motion = 0.0
    last_snap = 0.0

    def take_snapshot():
        nonlocal last_snap
        last_snap = time.monotonic()
        data = camera.jpeg()
        if data:
            pub.snapshot(data)
            save_snapshot(data)

    def end_visit():
        nonlocal visit_start
        duration = round(last_motion - visit_start_mono)
        log.info("Visit ended after %d s", duration)
        pub.visit(False)
        pub.last_visit(visit_start, duration)
        visit_start = None

    try:
        while not stop.is_set():
            now = time.monotonic()
            if pir.motion_detected:
                last_motion = now
                if visit_start is None:
                    visit_start = datetime.now().astimezone()
                    visit_start_mono = now
                    log.info("Visit started")
                    pub.visit(True)
                    take_snapshot()
            if visit_start is not None:
                if now - last_motion >= VISIT_TIMEOUT:
                    end_visit()
                elif SNAPSHOT_INTERVAL > 0 and now - last_snap >= SNAPSHOT_INTERVAL:
                    take_snapshot()
            stop.wait(0.25)
    finally:
        log.info("Shutting down")
        if visit_start is not None:
            end_visit()
        pub.stop()
        camera.close()
        pir.close()


if __name__ == "__main__":
    main()
