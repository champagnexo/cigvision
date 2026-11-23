# -*- coding: utf-8 -*-
"""
MQTT client for the Peuken Stembus. Works with paho-mqtt 1.x and 2.x.
Connects in the background and reconnects by itself, so a missing broker at
boot does not crash the program.
"""
import paho.mqtt.client as mqtt

from common import mylogger


class CMqttClient:
    def __init__(self, userdata, user, pw, broker, port=1883, keepalive=60):
        self.connected = False
        self.on_connected = None   # optional callback, called after every (re)connect
        self._handlers = {}        # topic -> callable(payload_str)

        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata=userdata)
        except AttributeError:     # paho-mqtt 1.x has no CallbackAPIVersion
            self.client = mqtt.Client(userdata=userdata)

        self.client.username_pw_set(username=user, password=pw)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.connect_async(broker, port, keepalive)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            mylogger.info("MQTT connected")
            for topic in self._handlers:       # (re)subscribe after every connect
                client.subscribe(topic, 0)
            if self.on_connected:
                try:
                    self.on_connected()
                except Exception as e:
                    mylogger.error(f"MQTT on_connected failed: {e}")
        else:
            mylogger.error(f"MQTT connect refused, code {rc}")

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        mylogger.info("MQTT disconnected")

    def _on_message(self, client, userdata, msg):
        handler = self._handlers.get(msg.topic)
        if handler is None:
            return
        payload = msg.payload.decode(errors="ignore").strip()
        mylogger.info(f"MQTT received {msg.topic} {payload}")
        try:
            handler(payload)
        except Exception as e:
            mylogger.error(f"MQTT handler for {msg.topic} failed: {e}")

    def subscribe(self, topic, handler):
        self._handlers[topic] = handler
        if self.connected:
            self.client.subscribe(topic, 0)

    def publish(self, topic, payload, qos=0, retain=False):
        if not self.connected:
            mylogger.info(f"MQTT not connected, NOT publishing {topic} {payload}")
            return False
        self.client.publish(topic, str(payload), qos=qos, retain=retain)
        return True


if __name__ == "__main__":
    import time
    c = CMqttClient("test", "gui", "gui", "10.42.0.1")
    time.sleep(2)
    print("connected:", c.connected)
    c.publish("counter/1", 5, qos=1, retain=True)
    time.sleep(1)
