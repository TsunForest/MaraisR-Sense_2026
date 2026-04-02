# Controller/Controller.py
"""
Contrôleur MVC.

Responsabilités :
  - Instancier le Model (CapteurParticules, EnvoiMesures) et la View (IHM).
  - Brancher les callbacks boutons et seuils.
  - Décider de la navigation et du retour automatique à l'accueil.
  - Lancer la boucle de mesure dans un thread de fond.
  - Intercepter toutes les erreurs → ihm.show_popup().
"""

import time
import threading
import serial

from Model import CapteurParticules, MQTTClient
from View  import IHM

AUTO_RETURN_DELAY = 60   # secondes avant retour automatique à l'accueil

# Topic MQTT d'écoute des seuils (le broker publie ici la config)
TOPIC_SEUILS = "marais/seuils/config"


class Controller:

    def __init__(self):
        # ── Vue ───────────────────────────────────────────────────────────────
        self.ihm = IHM()
        self.ihm.on_btn_a = self._btn_a_appuye
        self.ihm.on_btn_b = self._btn_b_appuye
        self._auto_timer  = None
        self._last_pm10   = None

        # ── Model ─────────────────────────────────────────────────────────────
        self.capteur = self._init_capteur()
        self.mqtt    = self._init_mqtt()

    # ══════════════════════════════════════════════════════════════════════════
    # Initialisation du Model
    # ══════════════════════════════════════════════════════════════════════════

    def _init_capteur(self) -> CapteurParticules:
        while True:
            try:
                capteur = CapteurParticules()
                print("Capteur PM10 connecté")
                return capteur
            except (serial.SerialException, OSError) as e:
                print(f"Capteur non trouvé ({e}), nouvelle tentative dans 2 s")
                self.ihm.show_popup(
                    "⚠ Capteur introuvable",
                    "Vérifiez le branchement USB\nNouvelle tentative dans 2 s…",
                    duration=0
                )
                time.sleep(2)

    def _init_mqtt(self):
        """
        Tente la connexion MQTT et s'abonne au topic des seuils.
        En cas d'échec, retourne None (les mesures continuent d'être affichées).
        """
        try:
            mqtt_client = MQTTClient()
            # Abonnement au topic de configuration des seuils
            mqtt_client.subscribe_seuils(TOPIC_SEUILS, self._on_seuils_recus)
            self.ihm.hide_popup()
            return mqtt_client
        except Exception as e:
            print(f"MQTT indisponible au démarrage : {e}")
            self.ihm.show_popup(
                "⚠ Réseau indisponible",
                "Broker MQTT inaccessible.\nAffichage local actif, seuils par défaut.",
                duration=5
            )
            return None

    # ══════════════════════════════════════════════════════════════════════════
    # Callback seuils MQTT
    # ══════════════════════════════════════════════════════════════════════════

    def _on_seuils_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par EnvoiMesures (thread MQTT) quand un message de seuils arrive.
        Transmet à la View pour mise à jour de l'affichage.
        """
        print(f"Nouveaux seuils appliqués : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils(seuil_vert, seuil_orange)
        # Recalcule la couleur si une mesure est déjà disponible
        if self._last_pm10 is not None:
            self.ihm.update_pm10(self._last_pm10)

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _btn_a_appuye(self):
        if self.ihm.current_screen == 'seuils':
            self._aller_accueil()
        else:
            self.ihm.navigate_to('seuils')
            self._armer_retour_auto()

    def _btn_b_appuye(self):
        if self.ihm.current_screen == 'reseau':
            self._aller_accueil()
        else:
            self.ihm.navigate_to('reseau')
            self._armer_retour_auto()

    def _aller_accueil(self):
        self._annuler_retour_auto()
        self.ihm.navigate_to('accueil')

    def _armer_retour_auto(self):
        self._annuler_retour_auto()
        self._auto_timer = threading.Timer(AUTO_RETURN_DELAY, self._aller_accueil)
        self._auto_timer.daemon = True
        self._auto_timer.start()

    def _annuler_retour_auto(self):
        if self._auto_timer and self._auto_timer.is_alive():
            self._auto_timer.cancel()

    # ══════════════════════════════════════════════════════════════════════════
    # Boucle de mesure (thread de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_mesure(self):
        print("Boucle de mesure démarrée")
        while True:
            try:
                pm10 = self.capteur.get_pm10()
                print(f"PM10 : {pm10:.1f} µg/m³")
                self._last_pm10 = pm10
                self.ihm.hide_popup()
                self.ihm.update_pm10(pm10)

                if self.mqtt:
                    try:
                        self.mqtt.publish_measure(pm10)
                    except Exception as e:
                        print(f"MQTT publication échouée : {e}")
                        self.ihm.show_popup(
                            "⚠ Envoi MQTT échoué",
                            str(e)[:80],
                            duration=5
                        )
                        self.mqtt = self._init_mqtt()   # tentative reconnexion

            except serial.SerialException as e:
                print(f"Capteur débranché : {e}")
                self.ihm.show_popup(
                    "⚠ Capteur débranché",
                    "Reconnexion en cours…\nVérifiez le câble USB.",
                    duration=0
                )
                self.capteur.reconnecter()
                self.ihm.hide_popup()

            except Exception as e:
                print(f"Erreur inattendue : {e}")
                self.ihm.show_popup("⚠ Erreur", str(e)[:80], duration=5)

    # ══════════════════════════════════════════════════════════════════════════
    # Point d'entrée
    # ══════════════════════════════════════════════════════════════════════════

    def prise_mesure_et_envoi(self):
        t = threading.Thread(target=self._boucle_mesure, daemon=True)
        t.start()
        try:
            self.ihm.run()
        except KeyboardInterrupt:
            print("Arrêt demandé")
        finally:
            self._annuler_retour_auto()
            if self.mqtt:
                self.mqtt.disconnect()
            print("Fin du programme")