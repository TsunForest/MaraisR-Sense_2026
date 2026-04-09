# Model/MQTTClient.py
"""
Client MQTT unifié pour l'UNIHIKER — partie Model MVC.

Gere :
  - La connexion au broker et son maintien (loop_start de paho).
  - La publication des mesures PM10 et TVOC/CO2 sur des topics distincts.
  - L'abonnement à plusieurs topics de configuration des seuils via
    une méthode générique subscribe(), avec dispatch automatique.

Topics de publication :
  PM10     : marais/sondes/<MAC>/pm10
  TVOC/CO2 : marais/sondes/<MAC>/tvoc_co2

Topics de souscription (configurés dans le Controller) :
  Seuils PM10 : marais/seuils/PM10
  Seuils TVOC : marais/seuils/TVOC
  Seuils CO2  : marais/seuils/CO2

Format JSON des messages de seuils (identique pour tous les capteurs) :
  {"seuil_vert": <float>, "seuil_orange": <float>}
"""

import json
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt


class MQTTClient:
    """
    Client MQTT unique gérant la publication de tous les capteurs et
    les abonnements aux topics de configuration.
    """

    def __init__(self,
                 broker="marais2026.btssn.ovh",
                 port=1883,
                 topic_base="marais/sondes/",
                 username="marais2026",
                 password="hyrome49#"):
        """
        Initialise le client et établit la connexion au broker.

        L'adresse MAC est calculée automatiquement pour construire les topics
        de publication, ce qui permet au programme de fonctionner sur
        n'importe quelle carte sans configuration manuelle.

        :param broker:     Adresse hostname ou IP du broker MQTT.
        :param port:       Port TCP du broker (1883 = non chiffré).
        :param topic_base: Préfixe commun des topics de publication.
        :param username:   Identifiant d'authentification.
        :param password:   Mot de passe d'authentification.
        """
        # Calcul de l'adresse MAC pour identifier cette carte de façon unique
        mac_int    = uuid.getnode()
        self._mac  = ':'.join(
            [f'{(mac_int >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1)]
        ).upper()

        self._broker    = broker
        self._port      = port
        self._client_id = self._mac
        self._username  = username
        self._password  = password

        # Topics de publication
        self._topic_pm10 = f"{topic_base}{self._mac}/pm10"
        self._topic_tvoc = f"{topic_base}{self._mac}/tvoc_co2"

        # Dictionnaire topic → callback pour les souscriptions multiples.
        # Clé : topic MQTT (str), Valeur : callable(seuil_vert, seuil_orange).
        self._subscriptions = {}

        self._client = None
        self._connect()

    # ══════════════════════════════════════════════════════════════════════════
    # Connexion et callbacks paho
    # ══════════════════════════════════════════════════════════════════════════

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback paho déclenché lors de l'établissement ou du rétablissement
        de la connexion au broker.
        Ré-abonne automatiquement à tous les topics enregistrés pour ne pas
        rater de messages après une reconnexion.
        """
        if rc == 0:
            print(f"MQTT connecte au broker ({self._broker})")
            for topic in self._subscriptions:
                client.subscribe(topic)
                print(f"MQTT re-abonne a : {topic}")
        else:
            print(f"MQTT echec de connexion (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """
        Callback paho déclenché à la réception d'un message sur un topic abonné.
        Dispatche vers le callback enregistré pour ce topic spécifique.
        S'exécute dans le thread réseau interne de paho.
        """
        topic    = msg.topic
        callback = self._subscriptions.get(topic)

        if callback is None:
            return   # topic non enregistré, message ignoré

        try:
            data = json.loads(msg.payload.decode('utf-8'))
            sv   = float(data['seuil_vert'])
            so   = float(data['seuil_orange'])
            print(f"Seuils recus sur {topic} : vert={sv}, orange={so}")
            callback(sv, so)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Erreur parsing message MQTT ({topic}) : {e} | payload : {msg.payload}")

    def _connect(self):
        """
        Cree l'instance paho, configure les credentials et démarre la boucle
        réseau en arrière-plan.
        Lève une exception si le broker est inaccessible (gérée par le Controller).
        """
        self._client = mqtt.Client(self._client_id)
        if self._username:
            self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self._broker, self._port)
        self._client.loop_start()

    # ══════════════════════════════════════════════════════════════════════════
    # Publication des mesures
    # ══════════════════════════════════════════════════════════════════════════

    def publish_pm10(self, pm10: float) -> bool:
        """
        Publie une mesure PM10 sur le topic dédié.

        :param pm10: Valeur PM10 en ug/m3.
        :return:     True si la publication a réussi, False sinon.
        """
        ts      = datetime.now().isoformat()
        payload = json.dumps({"timestamp": ts, "mesure": {"PM10": pm10}})
        result  = self._client.publish(self._topic_pm10, payload)

        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT publie → {self._topic_pm10} : {payload}")
            return True
        print(f"MQTT publication PM10 echouee (status={result[0]})")
        return False

    def publish_tvoc_co2(self, eco2: int, tvoc: int) -> bool:
        """
        Publie les mesures eCO2 et TVOC du CCS811 sur le topic dédié.

        :param eco2: Valeur eCO2 en ppm.
        :param tvoc: Valeur TVOC en ppb.
        :return:     True si la publication a réussi, False sinon.
        """
        ts      = datetime.now().isoformat()
        payload = json.dumps({"timestamp": ts, "mesure": {"ECO2": eco2, "TVOC": tvoc}})
        result  = self._client.publish(self._topic_tvoc, payload)

        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT publie → {self._topic_tvoc} : {payload}")
            return True
        print(f"MQTT publication TVOC/CO2 echouee (status={result[0]})")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # Abonnement générique aux topics de seuils
    # ══════════════════════════════════════════════════════════════════════════

    def subscribe(self, topic: str, callback):
        """
        S'abonne à un topic MQTT de configuration des seuils.

        Le message attendu sur ce topic est un JSON :
            {"seuil_vert": <float>, "seuil_orange": <float>}

        callback(seuil_vert: float, seuil_orange: float) est appelé
        dans le thread réseau paho à chaque réception.

        Cette méthode peut être appelée plusieurs fois pour abonner
        plusieurs topics (PM10, TVOC, CO2) avec des callbacks différents.

        :param topic:    Topic MQTT (ex. "marais/seuils/PM10").
        :param callback: Fonction(seuil_vert, seuil_orange).
        """
        self._subscriptions[topic] = callback
        self._client.subscribe(topic)
        print(f"MQTT abonne au topic seuils : {topic}")

    # ══════════════════════════════════════════════════════════════════════════
    # Déconnexion propre
    # ══════════════════════════════════════════════════════════════════════════

    def disconnect(self):
        """
        Arrête proprement le thread réseau paho et ferme la connexion MQTT.
        A appeler dans le bloc finally du Controller.
        """
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            print("MQTT deconnecte")