# Controller/Controller.py
"""
Controleur MVC principal de l'application.

Responsabilités :
  - Détecter automatiquement les capteurs disponibles au démarrage.
  - Instancier et connecter le Model et la View.
  - Brancher les callbacks boutons exposés par la View.
  - Décider de la navigation entre les écrans.
  - Alterner automatiquement entre les deux pages de mesure (et de seuils)
    toutes les ALTERNANCE_INTERVAL secondes si les deux capteurs sont présents.
  - Lancer les boucles de mesure dans des threads de fond.
  - Gérer la déconnexion et la reconnexion du capteur TVOC/CO2 (CCS811).
  - Intercepter toutes les erreurs et les transmettre à la View via show_popup().

Principe MVC respecté :
  - Le Controller connait le Model ET la View.
  - La View (IHM) ne connait pas le Controller (elle expose des callbacks).
  - Le Model ne connait ni le Controller ni la View.

Etat des capteurs apres détection :
  Seul PM10      → écran initial "accueil", bouton A → seuils PM10
  Seul TVOC/CO2  → écran initial "capteur2", bouton A → seuils capteur2
  Les deux       → alternance "accueil" / "capteur2" toutes les ALTERNANCE_INTERVAL s
                   bouton A → seuils correspondants (alternés de la même façon)
  Aucun          → popup d'erreur permanent

Topics MQTT des seuils :
  PM10 : marais/seuils/PM10
  TVOC : marais/seuils/TVOC
  CO2  : marais/seuils/CO2
"""

import time
import threading
import serial

from Model import CapteurParticules, MesureTVOC_CO2, MQTTClient
from View  import IHM

# Secondes avant retour automatique vers les mesures depuis les seuils ou le réseau
AUTO_RETURN_DELAY = 60

# Secondes entre deux alternances d'écran quand les deux capteurs sont actifs
ALTERNANCE_INTERVAL = 10

# Topics MQTT de configuration des seuils, un par grandeur mesurée
TOPIC_SEUILS_PM10 = "marais/seuils/PM10"
TOPIC_SEUILS_TVOC = "marais/seuils/TVOC"
TOPIC_SEUILS_CO2  = "marais/seuils/CO2"


class Controller:
    """
    Orchestre le Model et la View.

    Attributs d'état principaux :
        _pm10_dispo    (bool)  : capteur SDS011 détecté et opérationnel
        _tvoc_dispo    (bool)  : capteur CCS811 détecté et opérationnel
        _deux_capteurs (bool)  : les deux capteurs sont présents
        _contexte      (str)   : "mesures" | "seuils" | "reseau"
        _alt_timer     (Timer) : timer d'alternance courant
        _retour_timer  (Timer) : timer de retour automatique
    """

    def __init__(self):
        # ── Vue ───────────────────────────────────────────────────────────────
        self.ihm = IHM()
        self.ihm.on_btn_a = self._btn_a_appuye
        self.ihm.on_btn_b = self._btn_b_appuye

        # Etat de navigation courant
        self._contexte = "mesures"

        # Timers daemon pour ne pas bloquer l'arrêt du programme
        self._alt_timer    = None
        self._retour_timer = None

        # ── Initialisation du Model ───────────────────────────────────────────
        self._pm10_dispo, self.capteur_pm10 = self._detecter_pm10()
        self._tvoc_dispo, self.capteur_tvoc = self._detecter_tvoc_co2()
        self._deux_capteurs = self._pm10_dispo and self._tvoc_dispo

        self.mqtt = self._init_mqtt()

        # ── Écran initial selon les capteurs détectés ─────────────────────────
        self._appliquer_ecran_initial()

    # ══════════════════════════════════════════════════════════════════════════
    # Détection des capteurs
    # ══════════════════════════════════════════════════════════════════════════

    def _detecter_pm10(self):
        """
        Tente de se connecter au capteur SDS011 sur /dev/ttyUSB0.
        Un seul essai au démarrage. Si absent, le Controller continue sans lui.

        :return: Tuple (disponible: bool, capteur: CapteurParticules | None).
        """
        try:
            capteur = CapteurParticules()
            print("Capteur PM10 (SDS011) detecte")
            return True, capteur
        except (serial.SerialException, OSError) as e:
            print(f"Capteur PM10 non detecte : {e}")
            return False, None

    def _detecter_tvoc_co2(self):
        """
        Tente d'initialiser le capteur CCS811 sur le bus I2C.
        Utilise la propriété is_connected pour connaitre le résultat.

        :return: Tuple (disponible: bool, capteur: MesureTVOC_CO2 | None).
        """
        try:
            capteur = MesureTVOC_CO2()
            if capteur.is_connected:
                print("Capteur TVOC/CO2 (CCS811) detecte")
                return True, capteur
            print("Capteur TVOC/CO2 non detecte sur le bus I2C")
            return False, None
        except Exception as e:
            print(f"Erreur lors de la detection TVOC/CO2 : {e}")
            return False, None

    def _appliquer_ecran_initial(self):
        """
        Navigue vers l'écran approprié selon les capteurs détectés.
        Lance l'alternance si les deux capteurs sont présents.
        """
        if not self._pm10_dispo and not self._tvoc_dispo:
            self.ihm.navigate_to('accueil')
            self.ihm.show_popup(
                "Aucun capteur detecte",
                "Verifiez les branchements.",
                duration=0
            )
            return

        if self._pm10_dispo and not self._tvoc_dispo:
            self.ihm.navigate_to('accueil')
        elif self._tvoc_dispo and not self._pm10_dispo:
            self.ihm.navigate_to('capteur2')
        else:
            # Les deux capteurs : démarrage sur PM10, alternance activée
            self.ihm.navigate_to('accueil')
            self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Initialisation MQTT
    # ══════════════════════════════════════════════════════════════════════════

    def _init_mqtt(self):
        """
        Tente de se connecter au broker MQTT et s'abonne aux topics de seuils.
        En cas d'échec, retourne None : les mesures continuent en local avec
        les seuils par défaut.
        """
        try:
            client = MQTTClient()
            # Abonnement séparé pour chaque grandeur mesurée
            client.subscribe(TOPIC_SEUILS_PM10, self._on_seuils_pm10_recus)
            client.subscribe(TOPIC_SEUILS_TVOC, self._on_seuils_tvoc_recus)
            client.subscribe(TOPIC_SEUILS_CO2,  self._on_seuils_co2_recus)
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

    # ══════════════════════════════════════════════════════════════════════════
    # Callbacks seuils MQTT — un par grandeur
    # ══════════════════════════════════════════════════════════════════════════

    def _on_seuils_pm10_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par MQTTClient à la réception de nouveaux seuils PM10.
        Délègue la mise à jour de l'affichage à la View.
        """
        print(f"Seuils PM10 mis a jour : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils(seuil_vert, seuil_orange)

    def _on_seuils_tvoc_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par MQTTClient à la réception de nouveaux seuils TVOC.
        """
        print(f"Seuils TVOC mis a jour : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils_tvoc(seuil_vert, seuil_orange)

    def _on_seuils_co2_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par MQTTClient à la réception de nouveaux seuils CO2.
        """
        print(f"Seuils CO2 mis a jour : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils_co2(seuil_vert, seuil_orange)

    # ══════════════════════════════════════════════════════════════════════════
    # Alternance automatique entre les deux écrans
    # ══════════════════════════════════════════════════════════════════════════

    def _demarrer_alternance(self):
        """
        Démarre ou réarme le timer d'alternance.
        Sans effet si les deux capteurs ne sont pas disponibles.
        """
        if not self._deux_capteurs:
            return
        self._arreter_alternance()
        self._alt_timer = threading.Timer(ALTERNANCE_INTERVAL, self._alterner)
        self._alt_timer.daemon = True
        self._alt_timer.start()

    def _arreter_alternance(self):
        """Annule le timer d'alternance courant s'il est actif."""
        if self._alt_timer and self._alt_timer.is_alive():
            self._alt_timer.cancel()
        self._alt_timer = None

    def _alterner(self):
        """
        Fait basculer l'écran entre les deux pages du contexte actif
        (mesures ou seuils), puis réarme le timer pour le prochain cycle.
        """
        ecran = self.ihm.current_screen

        if self._contexte == "mesures":
            cible = 'capteur2' if ecran == 'accueil' else 'accueil'
            self.ihm.navigate_to(cible)

        elif self._contexte == "seuils":
            cible = 'seuils_capteur2' if ecran == 'seuils' else 'seuils'
            self.ihm.navigate_to(cible)

        self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Retour automatique vers les mesures
    # ══════════════════════════════════════════════════════════════════════════

    def _armer_retour_auto(self):
        """
        Arme un timer de retour automatique vers les écrans de mesure.
        Utilisé quand l'utilisateur consulte les seuils ou le réseau.
        """
        self._annuler_retour_auto()
        self._retour_timer = threading.Timer(AUTO_RETURN_DELAY, self._retour_mesures)
        self._retour_timer.daemon = True
        self._retour_timer.start()

    def _annuler_retour_auto(self):
        """Annule le timer de retour automatique s'il est actif."""
        if self._retour_timer and self._retour_timer.is_alive():
            self._retour_timer.cancel()
        self._retour_timer = None

    def _retour_mesures(self):
        """
        Retour vers la page de mesure principale.
        Choisit la bonne page selon les capteurs disponibles.
        """
        self._annuler_retour_auto()
        self._contexte = "mesures"

        if self._pm10_dispo:
            self.ihm.navigate_to('accueil')
        elif self._tvoc_dispo:
            self.ihm.navigate_to('capteur2')

        self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation — callbacks des boutons
    # ══════════════════════════════════════════════════════════════════════════

    def _btn_a_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton A.
        Bascule entre le contexte "mesures" et le contexte "seuils".
        """
        if self._contexte in ("mesures", "reseau"):
            self._arreter_alternance()
            self._annuler_retour_auto()
            self._contexte = "seuils"

            # Sélection de la page de seuils selon l'écran de mesure actuel
            ecran = self.ihm.current_screen
            if ecran in ('accueil', 'reseau') and self._pm10_dispo:
                self.ihm.navigate_to('seuils')
            elif self._tvoc_dispo:
                self.ihm.navigate_to('seuils_capteur2')

            # Si les deux capteurs, alternance entre les deux pages de seuils
            self._demarrer_alternance()
            self._armer_retour_auto()

        else:
            # Déjà dans les seuils → retour immédiat vers les mesures
            self._retour_mesures()

    def _btn_b_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton B.
        Bascule entre la page réseau et la page de mesure courante.
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
    # Boucle de mesure PM10 (thread de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_pm10(self):
        """
        Boucle de lecture du capteur PM10 (SDS011).
        Bloquante environ 2 minutes par cycle (wake-up + stabilisation + sleep).
        Gère la déconnexion et attend la reconnexion via CapteurParticules.reconnecter().
        """
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

            except serial.SerialException as e:
                print(f"Capteur PM10 debranche : {e}")
                self.ihm.show_popup(
                    "Capteur PM10 debranche",
                    "Reconnexion en cours...\nVerifiez le cable USB.",
                    duration=0
                )
                # Bloque ici jusqu'à reconnexion (boucle interne dans reconnecter())
                self.capteur_pm10.reconnecter()
                self.ihm.hide_popup()

            except Exception as e:
                print(f"Erreur inattendue boucle PM10 : {e}")
                self.ihm.show_popup("Erreur PM10", str(e)[:80], duration=5)

    # ══════════════════════════════════════════════════════════════════════════
    # Boucle de mesure TVOC/CO2 (thread de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_tvoc_co2(self):
        """
        Boucle de lecture du capteur TVOC/CO2 (CCS811).

        Distingue trois états de retour None :
          1. Capteur physiquement absent (is_connected = False) :
             popup permanent "debranche", attente 2 s entre les relances.
          2. Capteur reconnecté mais en run-in (is_connected = True, get_mesures = None) :
             popup temporaire "chauffe en cours" le temps du run-in.
          3. Mesure pas encore prête ce cycle (data_ready non levé) :
             simple attente 1 s, aucun popup.

        La reconnexion est gérée automatiquement par MesureTVOC_CO2 :
        à chaque appel de get_mesures(), si _ccs811 est None, un
        _init_hardware() est tenté. Si le capteur est revenu sur le bus,
        il est réinitialisé silencieusement et le run-in repart.
        """
        print("Boucle TVOC/CO2 demarree")

        # Popup de run-in initial (le capteur vient d'être initialisé)
        self.ihm.show_popup(
            "Capteur TVOC/CO2",
            f"Chauffe initiale en cours ({MesureTVOC_CO2.DUREE_RUN_IN} s)...",
            duration=float(MesureTVOC_CO2.DUREE_RUN_IN)
        )

        # Suivi de l'état de connexion pour détecter les transitions
        # debranche → reconnecte et reconnecte → mesure valide.
        etait_connecte  = True    # True car is_connected est True au démarrage
        run_in_affiche  = True    # Le popup de run-in initial est déjà affiché

        while True:
            mesures = self.capteur_tvoc.get_mesures()

            if mesures is None:
                if not self.capteur_tvoc.is_connected:
                    # ── Cas 1 : capteur physiquement absent ───────────────────
                    if etait_connecte:
                        # Transition : vient de se déconnecter
                        etait_connecte = False
                        run_in_affiche = False
                        self.ihm.show_popup(
                            "Capteur TVOC/CO2 debranche",
                            "Reconnexion automatique en cours...\n"
                            "Verifiez le branchement I2C.",
                            duration=0   # permanent jusqu'à reconnexion
                        )
                    # Attente plus longue pour ne pas spammer les tentatives I2C
                    time.sleep(2)

                else:
                    # ── Cas 2 ou 3 : capteur présent, pas de mesure disponible ─
                    if not etait_connecte:
                        # Transition : vient de se reconnecter
                        etait_connecte = True

                    if not run_in_affiche:
                        # Affichage du popup de run-in une seule fois
                        run_in_affiche = True
                        self.ihm.show_popup(
                            "Capteur TVOC/CO2 reconnecte",
                            f"Chauffe en cours ({MesureTVOC_CO2.DUREE_RUN_IN} s)...",
                            duration=float(MesureTVOC_CO2.DUREE_RUN_IN)
                        )
                    # Mesure pas encore prête (run-in ou data_ready pas levé)
                    time.sleep(1)

                continue   # reprend la boucle sans publier

            # ── Mesure valide ─────────────────────────────────────────────────
            if not etait_connecte:
                # Première mesure après reconnexion : on efface le popup de run-in
                etait_connecte = True
                self.ihm.hide_popup()

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

            # Cadence de lecture limitée par data_ready du CCS811 (1 Hz max)
            time.sleep(1)

    # ══════════════════════════════════════════════════════════════════════════
    # Point d'entrée
    # ══════════════════════════════════════════════════════════════════════════

    def prise_mesure_et_envoi(self):
        """
        Lance les threads de mesure pour les capteurs disponibles,
        puis démarre l'IHM Kivy (bloquant jusqu'à fermeture de la fenêtre).
        """
        if self._pm10_dispo:
            threading.Thread(
                target=self._boucle_pm10, daemon=True, name="thread_pm10"
            ).start()

        if self._tvoc_dispo:
            threading.Thread(
                target=self._boucle_tvoc_co2, daemon=True, name="thread_tvoc"
            ).start()

        if not self._pm10_dispo and not self._tvoc_dispo:
            print("Aucun capteur detecte. IHM demarree en mode affichage seul.")

        try:
            self.ihm.run()   # bloque ici — thread principal = thread Kivy
        except KeyboardInterrupt:
            print("Arret demande par l'utilisateur")
        finally:
            self._arreter_alternance()
            self._annuler_retour_auto()
            if self.mqtt:
                self.mqtt.disconnect()
            print("Fin du programme")