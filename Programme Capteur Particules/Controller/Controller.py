# Controller/Controller.py
"""
Contrôleur MVC.

Responsabilités :
  - Instancier le Model (CapteurParticules, MQTTClient) et la View (IHM).
  - Brancher les callbacks boutons exposés par la View.
  - Décider de la navigation entre les écrans et gérer le retour automatique.
  - Lancer la boucle de mesure dans un thread de fond.
  - Intercepter toutes les erreurs et les transmettre à la View via show_popup().

Principe MVC respecté :
  - Le Controller connaît le Model ET la View.
  - La View (IHM) ne connaît pas le Controller (elle expose des callbacks).
  - Le Model (CapteurParticules, MQTTClient) ne connaît ni le Controller ni la View.
"""

import time
import threading
import serial

from Model import CapteurParticules, MQTTClient
from View  import IHM

# Délai en secondes avant retour automatique à l'écran d'accueil
# quand l'utilisateur est sur une page secondaire (seuils, réseau)
AUTO_RETURN_DELAY = 60

# Topic MQTT sur lequel le broker publie la configuration des seuils PM10
TOPIC_SEUILS = "marais/seuils/config"


class Controller:

    def __init__(self):
        # ── Instanciation de la View ──────────────────────────────────────────
        self.ihm = IHM()

        # Branchement des callbacks boutons.
        # La View appellera ces méthodes sans savoir ce qu'elles font.
        self.ihm.on_btn_a = self._btn_a_appuye
        self.ihm.on_btn_b = self._btn_b_appuye

        # Référence au threading.Timer du retour automatique (peut être annulé)
        self._auto_timer = None

        # Dernière valeur PM10 mesurée (utile pour recalcul si seuils changent)
        self._last_pm10 = None

        # ── Instanciation du Model ────────────────────────────────────────────
        self.capteur = self._init_capteur()
        self.mqtt    = self._init_mqtt()

    # ══════════════════════════════════════════════════════════════════════════
    # Initialisation du Model
    # ══════════════════════════════════════════════════════════════════════════

    def _init_capteur(self) -> CapteurParticules:
        """
        Tente de se connecter au capteur SDS011 sur /dev/ttyUSB0.
        Boucle infinie jusqu'à succès : si le capteur n'est pas branché au
        démarrage, le programme attend patiemment en affichant un popup.
        """
        while True:
            try:
                capteur = CapteurParticules()
                print("Capteur PM10 connecté")
                return capteur
            except (serial.SerialException, OSError) as e:
                print(f"Capteur non trouvé ({e}), nouvelle tentative dans 2 s")
                # Popup permanent (duration=0) jusqu'à ce que le capteur soit trouvé
                self.ihm.show_popup(
                    "Capteur introuvable",
                    "Vérifiez le branchement USB\nNouvelle tentative dans 2 s…",
                    duration=0
                )
                time.sleep(2)

    def _init_mqtt(self):
        """
        Tente de se connecter au broker MQTT et s'abonne au topic des seuils.
        En cas d'échec, retourne None : le programme continue à fonctionner
        en local sans envoi des données et avec les seuils par défaut.
        """
        try:
            mqtt_client = MQTTClient()
            # Abonnement au topic de configuration des seuils PM10
            mqtt_client.subscribe_seuils(TOPIC_SEUILS, self._on_seuils_recus)
            self.ihm.hide_popup()   # efface le popup capteur si tout s'est bien passé
            return mqtt_client
        except Exception as e:
            print(f"MQTT indisponible au démarrage : {e}")
            self.ihm.show_popup(
                "Réseau indisponible",
                "Broker MQTT inaccessible.\nAffichage local actif, seuils par défaut.",
                duration=5
            )
            return None   # on continue sans MQTT

    # ══════════════════════════════════════════════════════════════════════════
    # Callback seuils reçus via MQTT
    # ══════════════════════════════════════════════════════════════════════════

    def _on_seuils_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par MQTTClient (dans le thread MQTT paho) lors de la réception
        d'un message de configuration sur TOPIC_SEUILS.
        Transmet les nouveaux seuils à la View de manière thread-safe.
        """
        print(f"Nouveaux seuils PM10 appliqués : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils(seuil_vert, seuil_orange)
        # Recalcule la couleur affichée si une mesure est déjà disponible
        if self._last_pm10 is not None:
            self.ihm.update_pm10(self._last_pm10)

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation — décisions métier, exécution déléguée à la View
    # ══════════════════════════════════════════════════════════════════════════

    def _btn_a_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton A.
        Bascule entre l'écran d'accueil et la page des seuils PM10.
        """
        if self.ihm.current_screen == 'seuils':
            self._aller_accueil()   # déjà sur les seuils → retour accueil
        else:
            self.ihm.navigate_to('seuils')
            self._armer_retour_auto()   # retour automatique dans AUTO_RETURN_DELAY s

    def _btn_b_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton B.
        Bascule entre l'écran d'accueil et la page réseau.
        """
        if self.ihm.current_screen == 'reseau':
            self._aller_accueil()
        else:
            self.ihm.navigate_to('reseau')
            self._armer_retour_auto()

    def _aller_accueil(self):
        """Annule le retour automatique en cours et navigue vers l'accueil."""
        self._annuler_retour_auto()
        self.ihm.navigate_to('accueil')

    def _armer_retour_auto(self):
        """
        Démarre un threading.Timer qui appellera _aller_accueil() après
        AUTO_RETURN_DELAY secondes. On utilise threading.Timer plutôt que
        Clock.schedule_once car cette méthode peut être appelée depuis
        n'importe quel thread (le callback Kivy des boutons).
        """
        self._annuler_retour_auto()
        self._auto_timer = threading.Timer(AUTO_RETURN_DELAY, self._aller_accueil)
        self._auto_timer.daemon = True   # le timer ne bloque pas l'arrêt du programme
        self._auto_timer.start()

    def _annuler_retour_auto(self):
        """Annule le timer de retour automatique s'il est en cours."""
        if self._auto_timer and self._auto_timer.is_alive():
            self._auto_timer.cancel()

    # ══════════════════════════════════════════════════════════════════════════
    # Boucle de mesure (thread de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_mesure(self):
        """
        Boucle principale de mesure, exécutée dans un thread daemon.
        Récupère la mesure PM10, met à jour l'affichage, et publie via MQTT.
        Gère les erreurs de capteur (débranchement) et de réseau (MQTT).
        """
        print("Boucle de mesure démarrée")
        while True:
            try:
                # Lecture bloquante (~2 minutes : wake-up + 30s mesure + 89s sleep)
                pm10 = self.capteur.get_pm10()
                print(f"PM10 : {pm10:.1f} µg/m³")

                # Stockage de la dernière valeur pour recalcul si seuils changent
                self._last_pm10 = pm10

                # Effacement du popup d'erreur précédent si tout va bien
                self.ihm.hide_popup()

                # Mise à jour de l'affichage (thread-safe via Clock interne)
                self.ihm.update_pm10(pm10)

                # Publication MQTT si le client est disponible
                if self.mqtt:
                    try:
                        self.mqtt.publish_measure(pm10)
                    except Exception as e:
                        print(f"MQTT publication échouée : {e}")
                        self.ihm.show_popup(
                            "Envoi MQTT échoué",
                            str(e)[:80],
                            duration=5
                        )
                        # Tentative de reconnexion au broker
                        self.mqtt = self._init_mqtt()

            except serial.SerialException as e:
                # Capteur débranché ou port série perdu
                print(f"Capteur débranché : {e}")
                self.ihm.show_popup(
                    "Capteur débranché",
                    "Reconnexion en cours…\nVérifiez le câble USB.",
                    duration=0   # permanent jusqu'à reconnexion
                )
                # Bloque ici jusqu'à ce que le capteur soit reconnecté
                self.capteur.reconnecter()
                self.ihm.hide_popup()

            except Exception as e:
                # Toute autre erreur imprévue
                print(f"Erreur inattendue dans la boucle de mesure : {e}")
                self.ihm.show_popup("Erreur", str(e)[:80], duration=5)

    # ══════════════════════════════════════════════════════════════════════════
    # Point d'entrée
    # ══════════════════════════════════════════════════════════════════════════

    def prise_mesure_et_envoi(self):
        """
        Lance la boucle de mesure dans un thread de fond puis démarre l'IHM.
        ihm.run() bloque jusqu'à fermeture de la fenêtre (ou Ctrl+C).
        Le thread de mesure est daemon=True : il s'arrête automatiquement
        quand le thread principal se termine.
        """
        # Thread de fond pour la lecture du capteur (opération bloquante ~2 min)
        t = threading.Thread(target=self._boucle_mesure, daemon=True)
        t.start()

        try:
            self.ihm.run()   # bloque ici — le thread principal est le thread Kivy
        except KeyboardInterrupt:
            print("Arrêt demandé par l'utilisateur (Ctrl+C)")
        finally:
            # Nettoyage à la fermeture
            self._annuler_retour_auto()
            if self.mqtt:
                self.mqtt.disconnect()
            print("Fin du programme")