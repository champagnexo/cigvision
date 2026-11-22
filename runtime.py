# -*- coding: utf-8 -*-
"""
Peuken Stembus runtime, YOLO11 version.

Flow: wait for a cup (frame difference against an empty reference), light on,
classify a few frames with a YOLO11 classification model, majority vote,
counter +1 only for a butt, publish over MQTT, servo flips the cup.

MQTT topics (unchanged): counter/<n>, state/<n>, set_counter/<n>
"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # keeps ../Data and ../Debug valid

import threading
from datetime import datetime
from time import sleep

import cv2
import numpy as np
from ultralytics import YOLO

from common import mylogger
from CConfig import CConfig
from CMqtt import CMqttClient
from cam_illum import set_illum_white, flash_illum, init_camera
from servo_control import InitServo, SwitchAngle

MQTT_STATE_IDLE = 0
MQTT_STATE_ANALYZE = 1
MQTT_STATE_POSITIVE = 2
MQTT_STATE_NEGATIVE = 3

COUNTER_FILE = "../Debug/counter.txt"
PRESENT_FRAMES = 3  # consecutive differing frames before a cup counts as present

YOLO_DEFAULTS = {
    "model": "../Data/butt_cls.pt",
    "class_name": "butt",
    "imgsz": 224,
    "frames": 3,
    "min_votes": 2,
    "threshold": 0.7,
    "save_debug_images": True,
}


class Counter:
    """Thread-safe counter, saved to disk after every change."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.value = 0
        try:
            with open(path) as f:
                self.value = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            pass

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(self.value))
        os.replace(tmp, self.path)

    def get(self):
        with self.lock:
            return self.value

    def set(self, value):
        with self.lock:
            self.value = value
            self._save()

    def increment(self):
        with self.lock:
            self.value += 1
            self._save()
            return self.value


# ---------- image helpers ----------

def to_bgr(frame):
    """Picamera2 may return 4 channels; YOLO and OpenCV want 3 (BGR)."""
    if frame.ndim == 3 and frame.shape[2] == 4:
        return frame[:, :, :3]
    return frame


def crop_roi(frame, roi):
    # crop_w / crop_h are END coordinates (x1, y1), as in the old code
    return frame[roi["crop_y"]:roi["crop_h"], roi["crop_x"]:roi["crop_w"]]


def gray_roi(frame, roi):
    return cv2.cvtColor(crop_roi(to_bgr(frame), roi), cv2.COLOR_BGR2GRAY)


def cup_present(gray, ref, method, th):
    """Compare the cropped gray frame with the empty reference. Returns (present, score)."""
    if method == "profiles":
        diff = abs(float(gray.mean()) - float(ref.mean()))
        return diff > th["profile_difference"], diff

    diff = cv2.absdiff(gray, ref)
    diff = cv2.erode(diff, np.ones((3, 3), np.uint8))
    diff = cv2.dilate(diff, np.ones((5, 5), np.uint8))
    _, blobs = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(blobs, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    max_area = 0
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if x > 0 and y > 0:  # same filter as the old code
            max_area = max(max_area, w * h)
    return max_area > th["area_difference"], max_area


def drain(cam, n, headless):
    """Throw away buffered frames (lets exposure settle after a light change)."""
    for _ in range(n):
        frame = cam.capture_array()
        if not headless:
            cv2.imshow("img", to_bgr(frame))
            cv2.waitKey(1)


# ---------- YOLO ----------

def find_class_index(model, name):
    for idx, n in model.names.items():
        if n == name:
            return idx
    raise SystemExit(f"Class '{name}' not in model. Model classes: {model.names}")


def butt_probability(model, butt_idx, img_bgr, imgsz):
    res = model.predict(img_bgr, imgsz=imgsz, verbose=False)[0]
    return float(res.probs.data[butt_idx])


def scan_cup(cam, model, butt_idx, ycfg, roi):
    """Classify several frames, majority vote. Returns (is_butt, probs, last_crop)."""
    probs, crop = [], None
    for _ in range(ycfg["frames"]):
        crop = crop_roi(to_bgr(cam.capture_array()), roi)
        probs.append(butt_probability(model, butt_idx, crop, ycfg["imgsz"]))
        sleep(0.1)
    votes = sum(p >= ycfg["threshold"] for p in probs)
    return votes >= ycfg["min_votes"], probs, crop


# ---------- main ----------

def main():
    cfg = CConfig()
    my_id = cfg.GetMyCounter()
    headless = cfg.GetHeadlessMode()
    mqtt_cfg = cfg.GetMQTT()
    illum = cfg.GetIllum()
    servo_cfg = cfg.GetServo()
    method = cfg.GetDetectionMethod()
    th = cfg.GetDetectionThreshold()
    roi = cfg.GetDetectionCroppingArea()
    ycfg = {**YOLO_DEFAULTS, **(cfg.config.get("yolo") or {})}

    counter = Counter(COUNTER_FILE)

    mylogger.info(f"Loading YOLO model {ycfg['model']}")
    model = YOLO(ycfg["model"], task="classify")
    butt_idx = find_class_index(model, ycfg["class_name"])
    model.predict(np.zeros((224, 224, 3), np.uint8), imgsz=ycfg["imgsz"], verbose=False)  # warm-up

    # MQTT
    mqttc = CMqttClient(userdata="rpi", user=mqtt_cfg["user"], pw=mqtt_cfg["pw"],
                        broker=mqtt_cfg["broker"], port=mqtt_cfg.get("port", 1883))

    def publish_counter():
        mqttc.publish(f"counter/{my_id}", counter.get(), qos=1, retain=True)

    def publish_state(state):
        mqttc.publish(f"state/{my_id}", state)

    def on_set_counter(payload):
        counter.set(int(payload))
        publish_counter()

    mqttc.subscribe(f"set_counter/{my_id}", on_set_counter)
    mqttc.on_connected = publish_counter  # screen Pi always gets the current value

    # Hardware
    cam = init_camera()
    pin = servo_cfg["iopin"]
    servo = InitServo(pin, servo_cfg["min_duty"], servo_cfg["max_duty"])
    SwitchAngle(servo, pin)
    sleep(2)
    SwitchAngle(servo, pin)

    if not headless:
        cv2.namedWindow("img", cv2.WINDOW_NORMAL)

    set_illum_white(illum["brightness_autofocus"])
    try:
        cam.autofocus_cycle()
        mylogger.info("Autofocus finished")
    except Exception:
        mylogger.info("Autofocus not available, using fixed focus")

    ref = gray_roi(cam.capture_array(), roi)  # the cup holder must be EMPTY now
    publish_state(MQTT_STATE_IDLE)
    publish_counter()
    mylogger.info(f"Ready. Counter = {counter.get()}" + ("" if headless else ", ESC to exit"))

    present_count = 0
    try:
        while True:
            frame = cam.capture_array()
            if not headless:
                cv2.imshow("img", to_bgr(frame))
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            present, _score = cup_present(gray_roi(frame, roi), ref, method, th)
            present_count = present_count + 1 if present else 0
            if present_count < PRESENT_FRAMES:
                continue
            present_count = 0

            # --- analyse the cup ---
            publish_state(MQTT_STATE_ANALYZE)
            set_illum_white(illum["brightness_measure"])
            drain(cam, 10, headless)

            is_butt, probs, crop = scan_cup(cam, model, butt_idx, ycfg, roi)
            label = "butt" if is_butt else "not_butt"
            mylogger.info(f"Result: {label}, probs {[round(p, 2) for p in probs]}")

            if ycfg["save_debug_images"]:
                stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                cv2.imwrite(f"../Debug/{stamp}_{label}.jpg", crop)

            publish_state(MQTT_STATE_POSITIVE if is_butt else MQTT_STATE_NEGATIVE)
            if is_butt:
                counter.increment()
            publish_counter()
            flash_illum("green" if is_butt else "red", illum["flashtime"])

            # --- flip the cup, get ready for the next one ---
            SwitchAngle(servo, pin)
            sleep(1)
            set_illum_white(illum["brightness_detect"])
            drain(cam, 30, headless)
            ref = gray_roi(cam.capture_array(), roi)
            publish_state(MQTT_STATE_IDLE)
    except KeyboardInterrupt:
        pass
    finally:
        set_illum_white(0.0)
        if not headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
