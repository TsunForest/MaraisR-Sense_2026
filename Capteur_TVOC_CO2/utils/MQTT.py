# -*- coding: utf-8 -*-
"""
Client MQTT pour UNIHIKER + publication mesures capteurs.
JSON : {"timestamp": "...", "mesure" : {"ECO2":eco2,"TVOC":tvoc}}
"""
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt
import uuid

class MQTT:
    def __init__(self, broker="marais2026.btssn.ovh", port=1883, topic_base="marais/sondes/",
                 username="marais2026", password="hyrome49#"):
        mac_int = uuid.getnode()
        mac_str = ':'.join(['{:02x}'.format((mac_int >> i) & 0xff) for i in range(0,48,8)][::-1]).upper()

        self.broker = broker
        self.port = port
        self.topic = topic_base + mac_str
        self.client_id = mac_str
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
        payload = { "timestamp": ts, "mesure" : {"ECO2":eco2,"TVOC":tvoc}}
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
