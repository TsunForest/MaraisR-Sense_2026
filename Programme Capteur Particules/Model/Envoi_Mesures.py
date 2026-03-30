# Model/Envoi_Mesures.py
"""
Client MQTT pour UNIHIKER + publication mesures capteurs.
JSON : {"timestamp": "2024-06-01T12:00:00", "mesure": {"pm10": 42.5}}
"""
import json
import time
from datetime import datetime
import paho.mqtt.client as mqtt

class EnvoiMesures:
    def __init__(self, broker="marais2026.btssn.ovh", port=1883, topic="marais/sondes/62:03:57:41:38:23",
                 client_id="62:03:57:41:38:23", username="*****", password="*****"):
        self.__broker: str = broker
        self.__port: int = port
        self.__topic: str = topic
        self.__client_id: str = client_id
        self.__username: str = username
        self.__password: str = password
        self.__client: mqtt.Client = None
        self._connect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("MQTT connecté au broker")
        else:
            print(f"MQTT échec (rc={rc})")

    def _connect(self):
        self.__client: mqtt.Client = mqtt.Client(self.__client_id)
        if self.__username:
            self.__client.username_pw_set(self.__username, self.__password)
        self.__client.on_connect = self._on_connect
        self.__client.connect(self.__broker, self.__port)
        self.__client.loop_start()

    def publish_measure(self, pm10):
        ts = datetime.now().isoformat()
        payload = {"timestamp": ts, "mesure": {"PM10": pm10}}
        msg = json.dumps(payload)

        result = self.__client.publish(self.__topic, msg)
        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT {self.__topic} : {msg}")
            return True
        print(f"MQTT échoué (status={result[0]})")
        return False

    def disconnect(self):
        if self.__client:
            self.__client.loop_stop()
            self.__client.disconnect()
            print("MQTT déconnecté")
