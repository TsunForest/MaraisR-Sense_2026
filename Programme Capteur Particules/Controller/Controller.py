# Controller/Controller.py
"""
Controller principal.
- Lance la boucle capteur dans un thread de fond
- Exécute l'IHM Kivy dans le thread principal (obligatoire pour Kivy)
"""
import time
import threading
import serial

from Model import EnvoiMesures, CapteurParticules
from View  import IHM


class Controller:

    def __init__(self):
        self.ihm    = IHM()          # créé AVANT run(), pas encore rendu
        self.capteur = self._init_capteur()
        self.mqtt    = EnvoiMesures()

    # ── Initialisation capteur avec retry ────────────────────────────────────
    def _init_capteur(self) -> CapteurParticules:
        while True:
            try:
                capteur = CapteurParticules()
                print("Capteur connecté")
                return capteur
            except (serial.SerialException, OSError):
                print("Capteur non trouvé, nouvelle tentative dans 2 s")
                time.sleep(2)

    # ── Boucle de mesure (thread de fond) ────────────────────────────────────
    def _boucle_mesure(self):
        print("Boucle de mesure démarrée")
        while True:
            try:
                pm10 = self.capteur.get_pm10()
                print(f"PM10 : {pm10} µg/m³")

                # Mise à jour IHM (thread-safe via Clock interne)
                self.ihm.update_pm10(pm10)

                # Publication MQTT
                self.mqtt.publish_measure(pm10)

            except serial.SerialException as e:
                print(f"Capteur débranché : {e}")
                self.capteur.reconnecter()   # bloque jusqu'à reconnexion

            except Exception as e:
                print(f"Erreur inattendue : {e}")

    # ── Point d'entrée ────────────────────────────────────────────────────────
    def prise_mesure_et_envoi(self):
        """Lance le thread capteur puis exécute l'IHM (bloquant)."""
        t = threading.Thread(target=self._boucle_mesure, daemon=True)
        t.start()

        try:
            self.ihm.run()       # ← bloque ici jusqu'à fermeture de la fenêtre
        except KeyboardInterrupt:
            print("Arrêt demandé")
        finally:
            self.mqtt.disconnect()
            print("Fin du programme")