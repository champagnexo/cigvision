# -*- coding: utf-8 -*-
"""Quick install check. Run: ../venv/bin/python check_install.py"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import socket

problems = 0


def check(name, fn, warn_only=False):
    global problems
    try:
        msg = fn()
        print(f"[ OK ] {name}" + (f": {msg}" if msg else ""))
    except Exception as e:
        tag = "WAIT" if warn_only else "FAIL"
        if not warn_only:
            problems += 1
        print(f"[{tag}] {name}: {e}")


def importer(mod):
    def f():
        __import__(mod)
    return f


for name, mod in [
    ("ultralytics", "ultralytics"),
    ("OpenCV", "cv2"),
    ("picamera2", "picamera2"),
    ("paho-mqtt", "paho.mqtt.client"),
    ("PyYAML", "yaml"),
    ("RPi.GPIO (lgpio)", "RPi.GPIO"),
    ("gpiozero", "gpiozero"),
    ("Blinka board", "board"),
    ("NeoPixel Pi 5", "adafruit_raspberry_pi5_neopixel_write"),
]:
    check(name, importer(mod))


def pio():
    if not os.path.exists("/dev/pio0"):
        raise RuntimeError("/dev/pio0 missing, update firmware (see install.sh output)")
    if not os.access("/dev/pio0", os.R_OK | os.W_OK):
        raise RuntimeError("no permission, reboot after install so the gpio group applies")


def camera():
    from picamera2 import Picamera2
    infos = Picamera2.global_camera_info()
    if not infos:
        raise RuntimeError("no camera detected, check the ribbon cable")
    return infos[0].get("Model", "camera found")


check("NeoPixel access (/dev/pio0)", pio)
check("Camera", camera)

try:
    from CConfig import CConfig
    cfg = CConfig()
except Exception as e:
    cfg = None
    problems += 1
    print(f"[FAIL] config.yaml: {e}")

if cfg:
    def broker():
        m = cfg.GetMQTT()
        socket.create_connection((m["broker"], m.get("port", 1883)), timeout=3).close()
        return f"{m['broker']} reachable"

    def model():
        y = cfg.config.get("yolo") or {}
        path = y.get("model", "../Data/butt_cls.pt")
        if not os.path.exists(path):
            raise RuntimeError(f"{path} not found yet, train the model first (see README.md)")
        from ultralytics import YOLO
        m = YOLO(path, task="classify")
        want = y.get("class_name", "butt")
        if want not in m.names.values():
            raise RuntimeError(f"class '{want}' not in model classes {m.names}")
        return f"classes {m.names}"

    check("MQTT broker", broker)
    check("YOLO model", model, warn_only=True)

print("\nAll good." if problems == 0 else f"\n{problems} problem(s) above.")
