# Controller/Controller.py
"""
Controleur MVC principal de l'application.

Responsabilités :
  - Détecter automatiquement les capteurs disponibles au démarrage.
  - Instancier et connecter le Model et la View.
  - Brancher les callbacks boutons exposés par la View.
  - Décider de la navigation entre les écrans.
  - Alterner automatiquement entre les deux pages de mesure (et de seuils)
    toutes les 10 secondes si les deux capteurs sont présents.
  - Lancer les boucles de mesure dans des threads de fond.
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
  Aucun          → popup d'erreur permanent, relances automatiques
"""

import time
import threading
import serial

from Model import CapteurParticules, MesureTVOC_CO2, MQTTClient
from View  import IHM

# Secondes avant retour automatique à l'écran de mesure depuis les seuils ou le réseau
AUTO_RETURN_DELAY = 60

# Secondes entre deux alternances d'écran quand les deux capteurs sont actifs
ALTERNANCE_INTERVAL = 10

# Topic MQTT sur lequel le broker publie la configuration des seuils PM10
TOPIC_SEUILS = "marais/seuils/config"


class Controller:
    """
    Orchestre le Model et la View.

    Attributs d'état principaux :
        _pm10_dispo   (bool) : capteur SDS011 détecté et opérationnel
        _tvoc_dispo   (bool) : capteur CCS811 détecté et opérationnel
        _deux_capteurs(bool) : les deux capteurs sont présents
        _contexte     (str)  : "mesures" | "seuils" | "reseau"
                               indique la famille d'écrans affichée
        _alt_timer    (Timer): timer d'alternance courant (None si inactif)
        _retour_timer (Timer): timer de retour automatique vers les mesures
    """

    def __init__(self):
        # ── Vue ───────────────────────────────────────────────────────────────
        self.ihm = IHM()
        self.ihm.on_btn_a = self._btn_a_appuye
        self.ihm.on_btn_b = self._btn_b_appuye

        # ── État de navigation ────────────────────────────────────────────────
        # "mesures" : on affiche accueil/capteur2
        # "seuils"  : on affiche seuils/seuils_capteur2
        # "reseau"  : on affiche la page réseau
        self._contexte = "mesures"

        # Timers — tous daemon pour ne pas bloquer l'arrêt du programme
        self._alt_timer    = None   # alternance entre les deux pages (si deux capteurs)
        self._retour_timer = None   # retour auto vers les mesures

        # ── Initialisation du Model ───────────────────────────────────────────
        # Ordre : capteurs d'abord (détection), MQTT ensuite (réseau)
        self._pm10_dispo, self.capteur_pm10  = self._detecter_pm10()
        self._tvoc_dispo, self.capteur_tvoc  = self._detecter_tvoc_co2()
        self._deux_capteurs = self._pm10_dispo and self._tvoc_dispo

        self.mqtt = self._init_mqtt()

        # ── Écran initial selon les capteurs détectés ────────────────────────
        self._appliquer_ecran_initial()

    # ══════════════════════════════════════════════════════════════════════════
    # Détection des capteurs
    # ══════════════════════════════════════════════════════════════════════════

    def _detecter_pm10(self):
        """
        Tente de se connecter au capteur SDS011 sur /dev/ttyUSB0.

        La connexion est testée une seule fois au démarrage. Si le capteur
        n'est pas branché, le Controller continue sans lui.

        :return: Tuple (disponible: bool, capteur: CapteurParticules | None).
        """
        try:
            capteur = CapteurParticules()
            print("Capteur PM10 (SDS011) detecte et connecte")
            return True, capteur
        except (serial.SerialException, OSError) as e:
            print(f"Capteur PM10 non detecte : {e}")
            return False, None

    def _detecter_tvoc_co2(self):
        """
        Tente d'initialiser le capteur CCS811 sur le bus I2C.

        MesureTVOC_CO2.__init__ n'élève pas d'exception si le capteur est absent ;
        on utilise la propriété is_connected pour connaitre le résultat.

        :return: Tuple (disponible: bool, capteur: MesureTVOC_CO2 | None).
        """
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
        """
        Navigue vers l'écran approprié selon les capteurs détectés et,
        si les deux sont présents, lance l'alternance automatique.

        Cas :
          PM10 seul      → "accueil"
          TVOC/CO2 seul  → "capteur2"
          Les deux       → "accueil" puis alternance toutes les ALTERNANCE_INTERVAL s
          Aucun          → "accueil" + popup permanent
        """
        if not self._pm10_dispo and not self._tvoc_dispo:
            # Aucun capteur : affichage de l'écran PM10 par défaut avec erreur
            self.ihm.navigate_to('accueil')
            self.ihm.show_popup(
                "Aucun capteur detecte",
                "Verifiez les branchements.\nRetentative en cours...",
                duration=0
            )
            return

        if self._pm10_dispo and not self._tvoc_dispo:
            # Seul PM10
            self.ihm.navigate_to('accueil')

        elif self._tvoc_dispo and not self._pm10_dispo:
            # Seul TVOC/CO2
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
        Tente de se connecter au broker MQTT.
        En cas d'échec, retourne None : les mesures continuent
        en local avec les seuils par défaut.
        """
        try:
            client = MQTTClient(ca_cert="/ca.crt")
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

    # ══════════════════════════════════════════════════════════════════════════
    # Callback seuils MQTT
    # ══════════════════════════════════════════════════════════════════════════

    def _on_seuils_recus(self, seuil_vert: float, seuil_orange: float):
        """
        Appelé par MQTTClient (thread réseau paho) à la réception de nouveaux seuils.
        Délègue la mise à jour à la View de façon thread-safe.
        """
        print(f"Seuils PM10 mis a jour : vert={seuil_vert}, orange={seuil_orange}")
        self.ihm.update_seuils(seuil_vert, seuil_orange)

    # ══════════════════════════════════════════════════════════════════════════
    # Alternance automatique entre les deux écrans de mesure
    # ══════════════════════════════════════════════════════════════════════════

    def _demarrer_alternance(self):
        """
        Démarre ou réarme le timer d'alternance.
        Sans effet si les deux capteurs ne sont pas tous deux disponibles.
        Utilise un threading.Timer (pas Kivy Clock) car cette méthode peut
        être appelée depuis n'importe quel thread.
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
        Appelée par le timer : fait basculer l'écran entre les deux pages
        du contexte actif (mesures ou seuils), puis réarme le timer.
        """
        ecran = self.ihm.current_screen

        if self._contexte == "mesures":
            if ecran == 'accueil':
                self.ihm.navigate_to('capteur2')
            elif ecran == 'capteur2':
                self.ihm.navigate_to('accueil')

        elif self._contexte == "seuils":
            if ecran == 'seuils':
                self.ihm.navigate_to('seuils_capteur2')
            elif ecran == 'seuils_capteur2':
                self.ihm.navigate_to('seuils')

        # Réarme le timer pour le prochain cycle
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
        Retour automatique vers la page de mesure principale.
        Appelée par le timer de retour automatique.
        Choisit la bonne page de départ selon les capteurs disponibles.
        """
        self._annuler_retour_auto()
        self._contexte = "mesures"

        # Retour vers la page de mesure appropriée
        if self._pm10_dispo:
            self.ihm.navigate_to('accueil')
        elif self._tvoc_dispo:
            self.ihm.navigate_to('capteur2')

        # Redémarrage de l'alternance si deux capteurs
        self._demarrer_alternance()

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation — callbacks des boutons
    # ══════════════════════════════════════════════════════════════════════════

    def _btn_a_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton A.
        Alterne entre le contexte "mesures" et le contexte "seuils".

        Si on est dans les mesures → on passe aux seuils.
        Si on est dans les seuils  → on revient aux mesures.

        Dans les deux cas, si les deux capteurs sont présents,
        l'alternance reprend sur le contexte approprié.
        """
        if self._contexte in ("mesures", "reseau"):
            # Passage vers les seuils
            self._arreter_alternance()
            self._annuler_retour_auto()
            self._contexte = "seuils"

            # Choix de la page de seuils en fonction de l'écran de mesure actuel
            ecran = self.ihm.current_screen
            if ecran in ('accueil', 'reseau') and self._pm10_dispo:
                self.ihm.navigate_to('seuils')
            elif self._tvoc_dispo:
                self.ihm.navigate_to('seuils_capteur2')

            # Alternance des seuils si deux capteurs
            self._demarrer_alternance()
            self._armer_retour_auto()

        else:
            # Retour immédiat vers les mesures
            self._retour_mesures()

    def _btn_b_appuye(self):
        """
        Appelé par la View lors d'un appui sur le bouton B.
        Alterne entre la page réseau et la page de mesure courante.
        """
        if self._contexte == "reseau":
            # Retour vers les mesures
            self._retour_mesures()
        else:
            # Aller vers le réseau
            self._arreter_alternance()
            self._annuler_retour_auto()
            self._contexte = "reseau"
            self.ihm.navigate_to('reseau')
            self._armer_retour_auto()

    # ══════════════════════════════════════════════════════════════════════════
    # Boucles de mesure (threads de fond)
    # ══════════════════════════════════════════════════════════════════════════

    def _boucle_pm10(self):
        """
        Boucle de lecture du capteur PM10 (SDS011).
        Bloquante environ 2 minutes par cycle (wake-up + stabilisation + sleep).
        Lance un popup en cas de débranchement et attend la reconnexion.
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
                        self.ihm.show_popup(
                            "Envoi MQTT echoue",
                            str(e)[:80],
                            duration=5
                        )
                        self.mqtt = self._init_mqtt()

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
        """
        Boucle de lecture du capteur TVOC/CO2 (CCS811).
        Interroge le capteur toutes les secondes (data_ready).
        Publie la mesure si disponible, sinon attend silencieusement
        (run-in ou mesure pas encore prête).
        """
        print("Boucle TVOC/CO2 demarree")

        # Popup informatif pendant la periode de run-in au demarrage
        self.ihm.show_popup(
            "Capteur TVOC/CO2",
            f"Chauffe en cours ({MesureTVOC_CO2.DUREE_RUN_IN} s)...",
            duration=float(MesureTVOC_CO2.DUREE_RUN_IN)
        )

        while True:
            try:
                mesures = self.capteur_tvoc.get_mesures()

                if mesures is None:
                    # Capteur absent, run-in ou mesure pas prête : on attend
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
                        self.ihm.show_popup(
                            "Envoi MQTT echoue",
                            str(e)[:80],
                            duration=5
                        )
                        self.mqtt = self._init_mqtt()

                # La fréquence de mesure utile est limitée par data_ready (1 Hz)
                time.sleep(30)

            except Exception as e:
                print(f"Erreur inattendue boucle TVOC/CO2 : {e}")
                self.ihm.show_popup("Erreur TVOC/CO2", str(e)[:80], duration=5)
                time.sleep(5)

    # ══════════════════════════════════════════════════════════════════════════
    # Point d'entrée
    # ══════════════════════════════════════════════════════════════════════════

    def prise_mesure_et_envoi(self):
        """
        Lance les threads de mesure pour les capteurs disponibles,
        puis démarre l'IHM Kivy (bloquant jusqu'à fermeture de la fenêtre).
        """
        # Démarrage des threads de fond selon les capteurs détectés
        if self._pm10_dispo:
            t_pm10 = threading.Thread(target=self._boucle_pm10, daemon=True)
            t_pm10.start()

        if self._tvoc_dispo:
            t_tvoc = threading.Thread(target=self._boucle_tvoc_co2, daemon=True)
            t_tvoc.start()

        if not self._pm10_dispo and not self._tvoc_dispo:
            print("Aucun capteur detecte. L'IHM demarre en mode affichage seul.")

        try:
            self.ihm.run()   # bloque ici — thread principal = thread Kivy
        except KeyboardInterrupt:
            print("Arret demande par l'utilisateur")
        finally:
            # Nettoyage ordonné à la fermeture
            self._arreter_alternance()
            self._annuler_retour_auto()
            if self.mqtt:
                self.mqtt.disconnect()
            print("Fin du programme")