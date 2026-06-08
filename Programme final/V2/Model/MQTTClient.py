# Model/MQTTClient.py
"""
Client MQTT unifié pour l'UNIHIKER — partie Model MVC.

Gere :
  - La connexion au broker et son maintien (loop_start de paho).
  - La publication des mesures PM10 et TVOC/CO2 sur des topics distincts.
  - L'abonnement au topic de configuration des seuils et l'appel du
    callback fourni par le Controller lors de la réception.

Topics utilisés :
  Publication PM10       : marais/sondes/<MAC>/pm10
  Publication TVOC/CO2   : marais/sondes/<MAC>/tvoc_co2
  Abonnement seuils      : configurable via subscribe_seuils()

Formats JSON publiés :
  PM10     : {"timestamp": "...", "mesure": {"PM10": 42.5}}
  TVOC/CO2 : {"timestamp": "...", "mesure": {"ECO2": 850, "TVOC": 320}}
  Seuils   : {"seuil_vert": 25.0, "seuil_orange": 50.0}
"""

import json
import uuid
from datetime import datetime
import ssl
import paho.mqtt.client as mqtt


class MQTTClient:
    """
    Client MQTT unique gérant la publication de tous les capteurs.
    Un seul client par application évite les connexions multiples au broker.
    """

    def __init__(self,
                 broker="marais2026.btssn.ovh",
                 port=8883,
                 topic_base="marais/sondes/",
                 username="marais2026",
                 password="hyrome49#",
                 ca_cert="ca.crt",
                 certfile=None,
                 keyfile=None):
        """
        Initialise le client et établit la connexion au broker.

        L'adresse MAC est calculée automatiquement pour construire les topics,
        ce qui permet au programme de fonctionner sans configuration manuelle
        sur n'importe quelle carte UNIHIKER.

        :param broker:     Adresse hostname ou IP du broker MQTT.
        :param port:       Port TCP du broker (1883 = non chiffré).
        :param topic_base: Préfixe commun des topics (ex. "marais/sondes/").
        :param username:   Identifiant d'authentification.
        :param password:   Mot de passe d'authentification.
        """
        # Calcul de l'adresse MAC pour identifier cette carte de façon unique
        mac_int = uuid.getnode()
        self._mac = ':'.join(
            f'{(mac_int >> i) & 0xff:02x}' for i in range(0, 48, 8)
        )[::-1].upper()
        # Correction de l'ordre des octets (uuid.getnode donne le LSB en premier)
        mac_int = uuid.getnode()
        self._mac = ':'.join(
            [f'{(mac_int >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1)]
        ).upper()

        self._broker     = broker
        self._port       = port
        self._ca_cert   = ca_cert
        self._certfile  = certfile
        self._keyfile   = keyfile
        self._client_id  = self._mac
        self._username   = username
        self._password   = password 

        # Topics de publication
        self._topic_pm10    = f"{topic_base}{self._mac}/pm10"
        self._topic_tvoc    = f"{topic_base}{self._mac}/tvoc_co2"

        # Topic de souscription seuils (défini via subscribe_seuils)
        self._topic_seuils  = None

        # Callback appelé par le Controller quand des seuils sont reçus
        self._cb_seuils     = None

        self._client = None
        self._connect()

    # ══════════════════════════════════════════════════════════════════════════
    # Connexion et callbacks paho
    # ══════════════════════════════════════════════════════════════════════════

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback paho déclenché lors de l'établissement ou du rétablissement
        de la connexion au broker.
        Le ré-abonnement automatique au topic des seuils garantit qu'on ne
        rate aucun message après une reconnexion.
        """
        if rc == 0:
            print(f"MQTT connecte au broker ({self._broker})")
            # Ré-abonnement automatique après reconnexion
            if self._topic_seuils:
                client.subscribe(self._topic_seuils)
                print(f"MQTT re-abonne a : {self._topic_seuils}")
        else:
            print(f"MQTT echec de connexion (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """
        Callback paho déclenché à la réception d'un message sur un topic abonné.
        S'exécute dans le thread réseau interne de paho.
        Ne pas toucher à l'UI directement depuis cette méthode.

        Format attendu du payload (tous les capteurs et toutes les valeurs
        sont optionnels — seules les clés présentes seront mises à jour) :
          {
            "PM 10": {"valeur_alerte_seuil": 20.0,   "valeur_danger_seuil": 50.0},
            "TVOC":  {"valeur_alerte_seuil": 1000.0, "valeur_danger_seuil": 10000.0},
            "ECO2":  {"valeur_alerte_seuil": 1000.0, "valeur_danger_seuil": 2004.0}
          }
        """
        if self._cb_seuils is None:
            return

        try:
            data = json.loads(msg.payload.decode('utf-8'))

            def _get(capteur, cle):
                """Retourne float si présent, None sinon."""
                bloc = data.get(capteur, {})
                return float(bloc[cle]) if cle in bloc else None

            pm10_alerte = _get('PM 10', 'valeur_alerte_seuil')
            pm10_danger = _get('PM 10', 'valeur_danger_seuil')
            tvoc_alerte = _get('TVOC',  'valeur_alerte_seuil')
            tvoc_danger = _get('TVOC',  'valeur_danger_seuil')
            co2_alerte  = _get('ECO2',  'valeur_alerte_seuil')
            co2_danger  = _get('ECO2',  'valeur_danger_seuil')

            print(
                f"Seuils reçus via MQTT — "
                f"PM10: alerte={pm10_alerte}, danger={pm10_danger} | "
                f"TVOC: alerte={tvoc_alerte}, danger={tvoc_danger} | "
                f"CO2: alerte={co2_alerte}, danger={co2_danger}"
            )

            self._cb_seuils(pm10_alerte, pm10_danger,
                            tvoc_alerte, tvoc_danger,
                            co2_alerte,  co2_danger)

        except (ValueError, json.JSONDecodeError) as e:
            print(f"Erreur parsing seuils MQTT : {e} | payload : {msg.payload}")

    def _connect(self):
        """
        Cree l'instance paho, configure les credentials et démarre la boucle
        réseau en arrière-plan.
        Leve une exception si le broker est inaccessible (gérée par le Controller).
        """
        self._client = mqtt.Client(self._client_id)
        if self._username:
            self._client.username_pw_set(self._username, self._password)

        self._client.tls_set(
            ca_certs=self._ca_cert,
            certfile=self._certfile,   # None si pas de mTLS
            keyfile=self._keyfile,     # None si pas de mTLS
            tls_version=ssl.PROTOCOL_TLS
        )
        
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        # connect() est bloquant et leve socket.error si le broker est injoignable
        self._client.connect(self._broker, self._port)
        # loop_start() démarre un thread réseau interne non bloquant
        self._client.loop_start()

    # ══════════════════════════════════════════════════════════════════════════
    # Publication des mesures
    # ══════════════════════════════════════════════════════════════════════════

    def publish_pm10(self, pm10: float) -> bool:
        """
        Publie une mesure PM10 sur le topic dédié.

        :param pm10: Valeur PM10 en µg/m³.
        :return:     True si la publication a réussi, False sinon.
        """
        ts      = datetime.now().isoformat()
        payload = json.dumps({"timestamp": ts, "mesure": {"PM 10": pm10}})
        result  = self._client.publish(self._topic_pm10, payload)

        if result[0] == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT → {self._topic_pm10} : {payload}")
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
            print(f"MQTT → {self._topic_tvoc} : {payload}")
            return True
        print(f"MQTT publication TVOC/CO2 echouee (status={result[0]})")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # Abonnement aux seuils
    # ══════════════════════════════════════════════════════════════════════════

    def subscribe_seuils(self, topic: str, callback):
        """
        S'abonne au topic MQTT de configuration des seuils.
        A chaque message, callback est appelé avec 6 arguments (tous optionnels) :
          callback(pm10_alerte, pm10_danger,
                   tvoc_alerte, tvoc_danger,
                   co2_alerte,  co2_danger)
        Chaque argument vaut None si le champ correspondant est absent du payload.
        Le Controller utilise alors la valeur courante de l'IHM comme fallback.

        :param topic:    Topic MQTT d'écoute (ex. "marais/sondes/seuils").
        :param callback: Fonction appelée avec les 6 valeurs décrites ci-dessus.
        """
        self._topic_seuils = topic
        self._cb_seuils    = callback
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