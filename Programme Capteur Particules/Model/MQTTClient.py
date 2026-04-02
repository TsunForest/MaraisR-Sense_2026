# Model/MQTTClient.py
"""
Client MQTT pour UNIHIKER.
Publication des mesures + abonnement au topic de configuration des seuils.

JSON publié  : {"timestamp": "2024-06-01T12:00:00", "mesure": {"pm10": 42.5}}
JSON seuils  : {"seuil_vert": 25.0, "seuil_orange": 50.0}
"""
import json
from datetime import datetime

import paho.mqtt.client as mqtt


class MQTTClient:

    def __init__(self,
                 broker="marais2026.btssn.ovh",
                 port=1883,
                 topic="marais/sondes/62:03:57:41:38:23",
                 client_id="62:03:57:41:38:23",
                 username="*****",
                 password="*****"):
        self.__broker    = broker
        self.__port      = port
        self.__topic     = topic
        self.__client_id = client_id
        self.__username  = username
        self.__password  = password
        self.__client    = None
        self.__cb_seuils = None   # callback(seuil_vert, seuil_orange)
        self._connect()

    # ── Connexion ─────────────────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("MQTT connecté au broker")
            # Ré-abonnement automatique après reconnexion
            if hasattr(self, '_topic_seuils') and self._topic_seuils:
                client.subscribe(self._topic_seuils)
                print(f"MQTT abonné à : {self._topic_seuils}")
        else:
            print(f"MQTT échec connexion (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """Appelé à la réception d'un message sur le topic des seuils."""
        if self.__cb_seuils is None:
            return
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            sv   = float(data['seuil_vert'])
            so   = float(data['seuil_orange'])
            print(f"Seuils reçus via MQTT : vert={sv}, orange={so}")
            self.__cb_seuils(sv, so)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Erreur parsing seuils MQTT : {e} — payload: {msg.payload}")

    def _connect(self):
        self.__client = mqtt.Client(self.__client_id)
        if self.__username:
            self.__client.username_pw_set(self.__username, self.__password)
        self.__client.on_connect = self._on_connect
        self.__client.on_message = self._on_message
        self.__client.connect(self.__broker, self.__port)
        self.__client.loop_start()
        self._topic_seuils = None

    # ── Publication mesure ────────────────────────────────────────────────────
    def publish_measure(self, pm10: float) -> bool:
        ts      = datetime.now().isoformat()
        payload = json.dumps({"timestamp": ts, "mesure": {"pm10": pm10}})
        result  = self.__client.publish(self.__topic, payload)
        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT publié → {self.__topic} : {payload}")
            return True
        print(f"MQTT publication échouée (status={result[0]})")
        return False

    # ── Abonnement seuils ─────────────────────────────────────────────────────
    def subscribe_seuils(self, topic: str, callback):
        """
        S'abonne au topic MQTT de configuration des seuils.

        Le message attendu est un JSON : {"seuil_vert": 25.0, "seuil_orange": 50.0}
        `callback(seuil_vert: float, seuil_orange: float)` est appelé à chaque
        réception. Si les seuils par défaut doivent être utilisés, ne pas appeler
        cette méthode (le Controller garde ses valeurs initiales).
        """
        self._topic_seuils = topic
        self.__cb_seuils   = callback
        self.__client.subscribe(topic)
        print(f"MQTT abonné au topic seuils : {topic}")

    # ── Déconnexion ───────────────────────────────────────────────────────────
    def disconnect(self):
        if self.__client:
            self.__client.loop_stop()
            self.__client.disconnect()
            print("MQTT déconnecté")