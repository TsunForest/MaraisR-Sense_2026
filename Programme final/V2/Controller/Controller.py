# Controller/Controller.py
"""
Controleur MVC principal de l'application.

Responsabilités :
  - Détecter automatiquement les capteurs disponibles au démarrage.
  - Instancier et connecter le Model et la View.
  - Brancher les callbacks boutons exposés par la View.
  - Décider de la navigation entre les écrans.
  - Alterner automatiquement entre les pages de mesure et de seuils
    toutes les ALTERNANCE_INTERVAL secondes si les capteurs sont présents.
  - Lancer les boucles de mesure dans des threads de fond.
  - Intercepter toutes les erreurs et les transmettre à la View via show_popup().

Écrans gérés :
  'accueil'     – mesure PM10
  'capteur2'    – mesure TVOC + eCO2
  'seuils'      – seuils PM10
  'seuils_tvoc' – seuils TVOC   (1ère des 2 pages capteur2 seuils)
  'seuils_co2'  – seuils eCO2   (2ème des 2 pages capteur2 seuils)
  'reseau'      – info réseau

Alternance dans le contexte "seuils" :
  PM10 seul      → 'seuils' uniquement (pas d'alternance)
  TVOC seul      → 'seuils_tvoc' ↔ 'seuils_co2'
  Les deux       → cycle : 'seuils' → 'seuils_tvoc' → 'seuils_co2' → 'seuils' → ...
"""

import time
import threading
import serial

from Model import CapteurParticules, MesureTVOC_CO2, MQTTClient
from View  import IHM

AUTO_RETURN_DELAY   = 60    # secondes avant retour automatique vers les mesures
ALTERNANCE_INTERVAL = 10    # secondes entre deux changements d'écran automatiques
TOPIC_SEUILS        = "marais/sondes/seuils"  # topic MQTT pour recevoir les seuils PM10 et TVOC/CO2


class Controller:
    """
    Orchestre le Model et la View.

    Attributs d'état principaux :
        _pm10_dispo    (bool) : capteur SDS011 détecté et opérationnel
        _tvoc_dispo    (bool) : capteur CCS811 détecté et opérationnel
        _deux_capteurs (bool) : les deux capteurs sont présents
        _contexte      (str)  : "mesures" | "seuils" | "reseau"
        _alt_timer     (Timer): timer d'alternance courant
        _retour_timer  (Timer): timer de retour automatique
    """

    def __init__(self):
        self.ihm = IHM()
        self.ihm.on_btn_a = self._btn_a_appuye
        self.ihm.on_btn_b = self._btn_b_appuye

        self._contexte     = "mesures"
        self._alt_timer    = None
        self._retour_timer = None

        self._pm10_dispo, self.capteur_pm10 = self._detecter_pm10()
        self._tvoc_dispo, self.capteur_tvoc = self._detecter_tvoc_co2()
        self._deux_capteurs = self._pm10_dispo and self._tvoc_dispo

        self.mqtt = self._init_mqtt()
        self._appliquer_ecran_initial()

    # ══════════════════════════════════════════════════════════════════════════
    # Détection des capteurs
    # ══════════════════════════════════════════════════════════════════════════

    def _detecter_pm10(self):
        try:
            capteur = CapteurParticules()
            print("Capteur PM10 (SDS011) detecte et connecte")
            return True, capteur
        except (serial.SerialException, OSError) as e:
            print(f"Capteur PM10 non detecte : {e}")
            return False, None

    def _detecter_tvoc_co2(self):
        try:
            capteur = MesureTVOC_CO2()
            if capteur.is_connected:
                print("Capteur TVOC/CO2 (CCS811) detecte et initialise")
                return True, capteur
            else:
                print("Capteur TVOC/CO2 non detecte sur le bus I2C")
                return False, None
        except Exception as e:
            print(f"Erreur lors de la detection TVOC/CO2 : {e}")
            return False, None

    def _appliquer_ecran_initial(self):
        if not self._pm10_dispo and not self._tvoc_dispo:
            self.ihm.navigate_to('accueil')
            self.ihm.show_popup(
                "Aucun capteur detecte",
                "Verifiez les branchements.\nRetentative en cours...",
                duration=0
            )
            return

        if self._pm10_dispo and not self._tvoc_dispo:
            self.ihm.navigate_to('accueil')
        elif self._tvoc_dispo and not self._pm10_dispo:
            self.ihm.navigate_to('capteur2')
        else:
            self.ihm.navigate_to('accueil')
            self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Initialisation MQTT
    # ══════════════════════════════════════════════════════════════════════════

    def _init_mqtt(self):
        try:
            client = MQTTClient(ca_cert="./Controller/ca.crt")
            client.subscribe_seuils(TOPIC_SEUILS, self._on_seuils_recus)
            self.ihm.hide_popup()
            return client
        except Exception as e:
            print(f"MQTT indisponible au demarrage : {e}")
            self.ihm.show_popup(
                "Reseau indisponible",
                "Broker MQTT inaccessible.\nSeuils par defaut actifs.",
                duration=5
            )
            return None

    def _on_seuils_recus(self, pm10_alerte, pm10_danger,
                         tvoc_alerte, tvoc_danger,
                         co2_alerte,  co2_danger):
        """
        Callback appelé par MQTTClient à la réception d'un message de seuils.
        Chaque argument peut être un float ou None si absent du payload.
        Pour toute valeur absente, on conserve le seuil courant de l'IHM.
        Les trois groupes (PM10, TVOC, CO2) sont indépendants : un seul champ
        suffit pour déclencher la mise à jour du groupe concerné.
        """
        # ── PM10 ──────────────────────────────────────────────────────────────
        if pm10_alerte is not None or pm10_danger is not None:
            sv = pm10_alerte if pm10_alerte is not None else self.ihm.seuil_vert
            so = pm10_danger if pm10_danger is not None else self.ihm.seuil_orange
            print(f"Seuils PM10 mis a jour : alerte={sv}, danger={so}")
            self.ihm.update_seuils(sv, so)

        # ── TVOC + CO2 (un seul appel pour éviter la race condition Clock) ────
        # Si les deux blocs faisaient chacun un appel séparé à
        # update_seuils_capteur2, le second lirait des valeurs stale pour
        # l'autre capteur (le Clock n'ayant pas encore exécuté le premier
        # appel) et écraserait les nouvelles valeurs avec les anciennes.
        if (tvoc_alerte is not None or tvoc_danger is not None or
                co2_alerte is not None or co2_danger is not None):
            tv = tvoc_alerte if tvoc_alerte is not None else self.ihm.seuil_tvoc_vert
            to = tvoc_danger if tvoc_danger is not None else self.ihm.seuil_tvoc_orange
            cv = co2_alerte  if co2_alerte  is not None else self.ihm.seuil_co2_vert
            co = co2_danger  if co2_danger  is not None else self.ihm.seuil_co2_orange
            print(
                f"Seuils TVOC/CO2 mis a jour : "
                f"tvoc_alerte={tv}, tvoc_danger={to}, "
                f"co2_alerte={cv}, co2_danger={co}"
            )
            self.ihm.update_seuils_capteur2(tv, to, cv, co)

    # ══════════════════════════════════════════════════════════════════════════
    # Alternance automatique entre les écrans
    # ══════════════════════════════════════════════════════════════════════════

    def _demarrer_alternance(self):
        """Démarre ou réarme le timer d'alternance automatique."""
        self._arreter_alternance()
        self._alt_timer = threading.Timer(ALTERNANCE_INTERVAL, self._alterner)
        self._alt_timer.daemon = True
        self._alt_timer.start()

    def _arreter_alternance(self):
        if self._alt_timer and self._alt_timer.is_alive():
            self._alt_timer.cancel()
        self._alt_timer = None

    def _alterner(self):
        """
        Fait avancer le cycle d'écrans selon le contexte et les capteurs présents.

        Contexte "mesures" :
          accueil  → capteur2  → accueil  → ...  (si deux capteurs)

        Contexte "seuils" :
          PM10 seul      : pas d'alternance (un seul écran seuils)
          TVOC seul      : seuils_tvoc ↔ seuils_co2
          Les deux       : seuils → seuils_tvoc → seuils_co2 → seuils → ...
        """
        ecran = self.ihm.current_screen

        if self._contexte == "mesures":
            if ecran == 'accueil':
                self.ihm.navigate_to('capteur2')
            elif ecran == 'capteur2':
                self.ihm.navigate_to('accueil')

        elif self._contexte == "seuils":
            if self._pm10_dispo and self._tvoc_dispo:
                # Cycle à trois : seuils PM10 → TVOC → CO2 → seuils PM10 → ...
                if ecran == 'seuils':
                    self.ihm.navigate_to('seuils_tvoc')
                elif ecran == 'seuils_tvoc':
                    self.ihm.navigate_to('seuils_co2')
                else:  # seuils_co2 ou autre
                    self.ihm.navigate_to('seuils')
            elif self._tvoc_dispo:
                # Alternance TVOC ↔ CO2
                if ecran == 'seuils_tvoc':
                    self.ihm.navigate_to('seuils_co2')
                else:
                    self.ihm.navigate_to('seuils_tvoc')
            # PM10 seul : pas d'alternance, on ne réarme pas

        self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Retour automatique vers les mesures
    # ══════════════════════════════════════════════════════════════════════════

    def _armer_retour_auto(self):
        self._annuler_retour_auto()
        self._retour_timer = threading.Timer(AUTO_RETURN_DELAY, self._retour_mesures)
        self._retour_timer.daemon = True
        self._retour_timer.start()

    def _annuler_retour_auto(self):
        if self._retour_timer and self._retour_timer.is_alive():
            self._retour_timer.cancel()
        self._retour_timer = None

    def _retour_mesures(self):
        self._annuler_retour_auto()
        self._contexte = "mesures"
        if self._pm10_dispo:
            self.ihm.navigate_to('accueil')
        elif self._tvoc_dispo:
            self.ihm.navigate_to('capteur2')
        if self._deux_capteurs:
            self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation — callbacks des boutons
    # ══════════════════════════════════════════════════════════════════════════

    def _btn_a_appuye(self):
        """
        Bouton A maintenu 3 s :
          mesures / reseau → seuils (page adaptée à l'écran courant)
          seuils           → retour immédiat aux mesures
        """
        if self._contexte in ("mesures", "reseau"):
            self._arreter_alternance()
            self._annuler_retour_auto()
            self._contexte = "seuils"

            ecran = self.ihm.current_screen
            if ecran in ('accueil', 'reseau') and self._pm10_dispo:
                self.ihm.navigate_to('seuils')
            elif self._tvoc_dispo:
                self.ihm.navigate_to('seuils_tvoc')

            # Alternance dans les seuils si nécessaire
            if self._tvoc_dispo:
                self._demarrer_alternance()
            self._armer_retour_auto()

        else:
            # Retour immédiat vers les mesures
            self._retour_mesures()

    def _btn_b_appuye(self):
        """
        Bouton B maintenu 3 s :
          mesures / seuils → page réseau
          reseau           → retour aux mesures
        """
        if self._contexte == "reseau":
            self._retour_mesures()
        else:
            self._arreter_alternance()
            self._annuler_retour_auto()
            self._contexte = "reseau"
            self.ihm.navigate_to('reseau')
            self._armer_retour_auto()

    # ══════════════════════════════════════════════════════════════════════════
    # Boucles de mesure (threads de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_pm10(self):
        print("Boucle PM10 demarree")
        while True:
            try:
                
                pm10 = self.capteur_pm10.get_pm10()
                print(f"PM10 : {pm10:.1f} ug/m3")
                self.ihm.hide_popup()
                self.ihm.update_pm10(pm10)

                if self.mqtt:
                    try:
                        self.mqtt.publish_pm10(pm10)
                    except Exception as e:
                        print(f"MQTT publication PM10 echouee : {e}")
                        self.ihm.show_popup("Envoi MQTT echoue", str(e)[:80], duration=5)
                        self.mqtt = self._init_mqtt()
                
                time.sleep(89)

            except serial.SerialException as e:
                print(f"Capteur PM10 debranche : {e}")
                self.ihm.show_popup(
                    "Capteur PM10 debranche",
                    "Reconnexion en cours...\nVerifiez le cable USB.",
                    duration=0
                )
                self.capteur_pm10.reconnecter()
                self.ihm.hide_popup()

            except Exception as e:
                print(f"Erreur inattendue boucle PM10 : {e}")
                self.ihm.show_popup("Erreur PM10", str(e)[:80], duration=5)

    def _boucle_tvoc_co2(self):
        print("Boucle TVOC/CO2 demarree")

        # Popup run-in affiché UNE SEULE fois, avec durée automatique.
        # On ne l'affiche plus dans la boucle pour éviter tout doublon avec
        # d'autres popups actifs (ex. MQTT indisponible).
        self.ihm.show_popup(
            "Capteur TVOC/CO2",
            f"Chauffe en cours ({MesureTVOC_CO2.DUREE_RUN_IN} s)...",
            duration=float(MesureTVOC_CO2.DUREE_RUN_IN)
        )

        while True:
            try:
                mesures = self.capteur_tvoc.get_mesures()

                if mesures is None:
                    time.sleep(1)
                    continue

                eco2, tvoc = mesures
                print(f"ECO2 : {eco2} ppm | TVOC : {tvoc} ppb")
                self.ihm.update_tvoc_co2(eco2, tvoc)

                if self.mqtt:
                    try:
                        self.mqtt.publish_tvoc_co2(eco2, tvoc)
                    except Exception as e:
                        print(f"MQTT publication TVOC/CO2 echouee : {e}")
                        self.ihm.show_popup("Envoi MQTT echoue", str(e)[:80], duration=5)
                        self.mqtt = self._init_mqtt()

                time.sleep(30)

            except Exception as e:
                print(f"Erreur inattendue boucle TVOC/CO2 : {e}")
                self.ihm.show_popup("Erreur TVOC/CO2", str(e)[:80], duration=5)
                time.sleep(5)

    # ══════════════════════════════════════════════════════════════════════════
    # Point d'entrée
    # ══════════════════════════════════════════════════════════════════════════

    def prise_mesure_et_envoi(self):
        if self._pm10_dispo:
            threading.Thread(target=self._boucle_pm10, daemon=True).start()

        if self._tvoc_dispo:
            threading.Thread(target=self._boucle_tvoc_co2, daemon=True).start()

        if not self._pm10_dispo and not self._tvoc_dispo:
            print("Aucun capteur detecte. L'IHM demarre en mode affichage seul.")

        try:
            self.ihm.run()
        except KeyboardInterrupt:
            print("Arret demande par l'utilisateur")
        finally:
            self._arreter_alternance()
            self._annuler_retour_auto()
            if self.mqtt:
                self.mqtt.disconnect()
            print("Fin du programme")