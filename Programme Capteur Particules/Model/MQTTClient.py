# Model/MQTTClient.py
"""
Client MQTT pour UNIHIKER — partie Model MVC.

Responsabilités :
  - Se connecter au broker MQTT et maintenir la connexion active.
  - Publier les mesures PM10 sous forme de JSON horodaté.
  - S'abonner au topic de configuration des seuils et appeler
    un callback fourni par le Controller lors de la réception.

Format JSON publié :
    {"timestamp": "2024-06-01T12:00:00", "mesure": {"PM 10": 42.5}}

Format JSON seuils attendu :
    {"seuil_vert": 25.0, "seuil_orange": 50.0}
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
                 username="marais2026",
                 password="hyrome49#"):
        """
        Initialise le client MQTT et établit la connexion au broker.

        :param broker:    Adresse hostname ou IP du broker MQTT.
        :param port:      Port TCP du broker (1883 = non chiffré).
        :param topic:     Topic sur lequel les mesures sont publiées.
        :param client_id: Identifiant unique de ce client côté broker.
        :param username:  Identifiant d'authentification (optionnel).
        :param password:  Mot de passe d'authentification (optionnel).
        """
        self.__broker    = broker
        self.__port      = port
        self.__topic     = topic       # topic de publication des mesures
        self.__client_id = client_id
        self.__username  = username
        self.__password  = password
        self.__client    = None        # instance paho MQTT (créée dans _connect)
        self.__cb_seuils = None        # callback(sv, so) fourni par le Controller

        # Établissement de la connexion dès l'instanciation
        self._connect()

    # ══════════════════════════════════════════════════════════════════════════
    # Gestion de la connexion
    # ══════════════════════════════════════════════════════════════════════════

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback paho appelé automatiquement lors de l'établissement (ou
        rétablissement) de la connexion au broker.
        rc=0 signifie succès ; toute autre valeur indique une erreur.
        En cas de reconnexion, on ré-abonne au topic des seuils pour ne pas
        manquer de messages.
        """
        if rc == 0:
            print("MQTT connecté au broker")
            # Ré-abonnement automatique après reconnexion (paho peut se reconnecter)
            if hasattr(self, '_topic_seuils') and self._topic_seuils:
                client.subscribe(self._topic_seuils)
                print(f"MQTT ré-abonné à : {self._topic_seuils}")
        else:
            print(f"MQTT échec connexion (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """
        Callback paho appelé à la réception d'un message sur n'importe quel
        topic auquel ce client est abonné (ici uniquement le topic des seuils).
        Tourne dans le thread MQTT de paho → ne pas toucher à l'UI directement.
        """
        if self.__cb_seuils is None:
            return   # aucun callback enregistré, on ignore

        try:
            # Décodage du JSON et extraction des deux seuils
            data = json.loads(msg.payload.decode('utf-8'))
            sv   = float(data['seuil_vert'])
            so   = float(data['seuil_orange'])
            print(f"Seuils reçus via MQTT : vert={sv}, orange={so}")
            # Appel du callback Controller (qui appellera ensuite ihm.update_seuils)
            self.__cb_seuils(sv, so)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Erreur parsing seuils MQTT : {e} — payload brut : {msg.payload}")

    def _connect(self):
        """
        Crée l'instance paho, configure les credentials et démarre la
        boucle réseau en arrière-plan (loop_start → thread interne paho).
        """
        self.__client = mqtt.Client(self.__client_id)

        # Authentification si identifiants fournis
        if self.__username:
            self.__client.username_pw_set(self.__username, self.__password)

        # Enregistrement des callbacks paho
        self.__client.on_connect = self._on_connect
        self.__client.on_message = self._on_message

        # Connexion synchrone (lève une exception si le broker est inaccessible)
        self.__client.connect(self.__broker, self.__port)

        # Démarrage du thread réseau interne de paho (non bloquant)
        self.__client.loop_start()

        # Initialisation du topic seuils à None (défini via subscribe_seuils)
        self._topic_seuils = None

    # ══════════════════════════════════════════════════════════════════════════
    # Publication des mesures
    # ══════════════════════════════════════════════════════════════════════════

    def publish_measure(self, pm10: float) -> bool:
        """
        Publie une mesure PM10 sur le topic configuré.
        Le message est un JSON avec un timestamp ISO 8601 et la valeur mesurée.

        :param pm10: Valeur PM10 en µg/m³.
        :return: True si la publication a réussi, False sinon.
        """
        ts      = datetime.now().isoformat()   # ex. "2024-06-01T14:32:05.123456"
        payload = json.dumps({"timestamp": ts, "mesure": {"PM 10": pm10}})
        result  = self.__client.publish(self.__topic, payload)

        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT publié → {self.__topic} : {payload}")
            return True

        print(f"MQTT publication échouée (status={result[0]})")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # Abonnement aux seuils
    # ══════════════════════════════════════════════════════════════════════════

    def subscribe_seuils(self, topic: str, callback):
        """
        S'abonne au topic MQTT de configuration des seuils.
        À chaque message reçu, callback(seuil_vert, seuil_orange) est appelé.

        Si cette méthode n'est pas appelée, les seuils par défaut définis dans
        IHM.py restent actifs indéfiniment.

        :param topic:    Topic MQTT d'écoute (ex. "marais/seuils/config").
        :param callback: Fonction appelée avec (seuil_vert: float, seuil_orange: float).
        """
        self._topic_seuils = topic
        self.__cb_seuils   = callback
        self.__client.subscribe(topic)
        print(f"MQTT abonné au topic seuils : {topic}")

    # ══════════════════════════════════════════════════════════════════════════
    # Déconnexion propre
    # ══════════════════════════════════════════════════════════════════════════

    def disconnect(self):
        """
        Arrête la boucle réseau paho et ferme la connexion proprement.
        À appeler dans le bloc finally du Controller avant la fin du programme.
        """
        if self.__client:
            self.__client.loop_stop()    # arrête le thread réseau interne
            self.__client.disconnect()   # envoie un DISCONNECT au broker
            print("MQTT déconnecté")