# CatCam: Cat Food Dish Monitor

A Raspberry Pi that watches the cats' food dish. When the PIR motion sensor triggers, it takes a snapshot and reports the visit to Home Assistant over MQTT.

**Status: In progress. Pi and camera set up; PIR sensor wiring and MQTT script next.**

---

## Roadmap

1. Wire the PIR sensor (see [PIR wiring](#pir-wiring)) **with the Pi powered off.**
2. Verify the PIR: power on, wait about 60 s for it to settle, then watch GPIO17 while waving a hand in front of it:
   ```bash
   for i in $(seq 30); do pinctrl lev 17; sleep 1; done
   ```
   Expect `1` (HIGH) on motion and `0` (LOW) a few seconds after it stops.
3. Write the MQTT script (see [Software](#software)).
4. Install it as a **systemd service** so it starts on boot and restarts after power cuts.
5. **Home Assistant:** entities appear via MQTT discovery. Add a dashboard card and an optional feeding-log automation.

---

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 3 Model B+ | Built-in dual-band Wi-Fi |
| Raspberry Pi Camera Module v1.3 (OV5647) | Standard version with an IR filter: normal daytime colors, no night vision |
| HC-SR501 PIR motion sensor | Repeat-trigger (H) mode |
| microSD card, 8 GB+ | |
| 3× female-to-female jumper wires | For the PIR |
| Resin-printed sensor plate | See [Enclosure](#enclosure) |
| *Optional:* 850 nm IR illuminator + NoIR camera (e.g. IMX219) | For night vision |

### PIR wiring

| HC-SR501 pin | Pi physical pin | Function |
|---|---|---|
| VCC | **Pin 2** | 5 V |
| GND | **Pin 6** | Ground |
| OUT | **Pin 11** | GPIO17 (output is 3.3 V, safe to connect directly) |

```
                 board edge
   Pin:  2    4    6    8   10   12  ...  40
        [5V] [5V] [GND][  ] [  ] [  ]
        [3V3][  ] [  ] [  ] [  ] [17]
   Pin:  1    3    5    7    9   11  ...  39
  (pin 1 end, away from USB)          (USB/Ethernet end →)
```

- **Check the VCC/OUT/GND labels under the white dome before connecting.** Pin order varies between batches, and reversing VCC and GND can destroy the sensor.
- **Time dial (Tx):** fully anticlockwise (about 3 s hold). The script handles visit duration.
- **Sensitivity dial (Sx):** middle to start. Tune it once mounted at the dish.
- **Trigger mode:** H (repeat trigger). Some boards use solder pads instead of a jumper; the script works with either mode.

---

## Pi setup

- **OS:** Raspberry Pi OS Lite (64-bit), Trixie / Debian 13, written with Raspberry Pi Imager
- **Imager settings:** hostname `catcam`, Wi-Fi, time zone, SSH with **public-key authentication only**
- **Camera:** works out of the box with `camera_auto_detect=1` (the default). Check with:
  ```bash
  rpicam-hello --list-cameras
  # 0 : ov5647 [2592x1944 10-bit GBRG] (/base/soc/i2c0mux/i2c@1/ov5647@36)
  ```
- **Network:** the Pi must be able to reach the MQTT broker (port 1883). If your router puts IoT devices on an isolated network, put the Pi on a network that can reach Home Assistant.

---

## Software

A Python script running as a systemd service on the Pi:

- **Motion:** `gpiozero` on GPIO17. A **visit** starts on the first trigger and ends after **about 30 s with no motion**, so H- or L-mode pulses both become one clean event.
- **Camera:** `picamera2`. Take a snapshot when a visit starts, and possibly periodic snapshots or a short clip during the visit.
- **MQTT:** `paho-mqtt`, connecting to the Home Assistant Mosquitto broker. **Credentials go in a local config/env file that is git-ignored, never in the script** (see `.gitignore`).
- **Home Assistant MQTT discovery** so the entities appear automatically:
  - `binary_sensor` "Cat at dish" (device class `occupancy` or `motion`)
  - `camera` showing the latest snapshot (MQTT camera entity)
  - Possibly a sensor for the last visit's duration or time
- **Warm-up:** ignore the PIR for about 60 s after boot (it gives false triggers while settling).
- **Optional later:** live view via a streaming server (e.g. MediaMTX or go2rtc) added to Home Assistant as a generic camera.

### Home Assistant requirements
- Home Assistant with the **Mosquitto broker** add-on (or any MQTT broker) and the **MQTT integration**
- A dedicated Home Assistant user for the Pi's MQTT login

---

## Enclosure

`enclosure/catcam_plate.scad` is a parametric OpenSCAD model of a flat sensor plate (`catcam_plate.stl` is the rendered output).

- 87 × 46 × 28 mm. Designed for a resin printer (Elegoo Mars 2) but small enough for most printers.
- Camera and PIR mount on the back on standoffs; the lens and PIR dome poke through openings.
- Corner legs hold the plate off the wall to leave room for the wiring.
- **Print front face down. No supports needed.**
- Hardware: 6× M2×10 screws + nuts (boards), 4× M3×40 or #4 × 1½" screws (mounting).
- **Measure your boards first.** Values marked `(verify)` in the `.scad` file are typical specs, and HC-SR501 boards vary between batches. `hole_comp` compensates for resin holes printing slightly small.
- Cured resin is not food safe: mount the plate out of the cats' reach and away from the bowl.

---

## Known issues

- **Arducam 8MP NoIR (IMX219) module not detected** on the Pi 3 B+ with auto-detection, while the official v1.3 camera works on the same Pi and cable. Untested fixes: try the known-good cable, or set `camera_auto_detect=0` and add `dtoverlay=imx219` to `/boot/firmware/config.txt`.
- **No night vision yet.** That needs an IR illuminator and a NoIR camera.
