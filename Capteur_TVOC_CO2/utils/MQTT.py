# -*- coding: utf-8 -*-
"""
Client MQTT pour UNIHIKER + publication mesures capteurs.
JSON : {"timestamp": "...", "eco2": 400, "tvoc": 20}
"""
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt

class MQTT:
    def __init__(self, broker="172.16.4.35", port=1883, topic="marais/sondes/MAC/00:e0:4c:d1:72:81",
                 client_id="00:e0:4c:d1:72:81", username=None, password=None):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client_id = client_id
        self.username = username
        self.password = password
        self.client = None
        self._connect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("MQTT connecté au broker")
        else:
            print(f"MQTT échec (rc={rc})")

    def _connect(self):
        self.client = mqtt.Client(self.client_id)
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self._on_connect
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish_measure(self, eco2, tvoc):
        ts = datetime.now().isoformat()
        payload = {"timestamp": ts, "eco2": eco2, "tvoc": tvoc}
        msg = json.dumps(payload)

        result = self.client.publish(self.topic, msg)
        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT {self.topic} : {msg}")
            return True
        print(f"MQTT échoué (status={result[0]})")
        return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("MQTT déconnecté")
