# Controller/Controller.py
import time
from Model import EnvoiMesures, CapteurParticules
import serial


class Controller():

    def __init__(self):
        self.capteur = self._init_capteur()
        self.mqtt = EnvoiMesures()
    

    def _init_capteur(self):
        while True:
            try:
                capteur = CapteurParticules()
                print("Capteur connecté")
                return capteur
            except (serial.SerialException, OSError):
                print("Capteur non trouvé, nouvelle tentative dans 2s")
                time.sleep(2)

    
    def prise_mesure_et_envoi(self):

        print("PM10 (1 msg/min)")

        try:
            while True:
                try:
                    pm10 = self.capteur.get_pm10()
                    print(f"PM10 : {pm10}")
                    self.mqtt.publish_measure(pm10)

                except serial.SerialException as e:
                    print(f"Capteur débranché : {e}")
                    self.capteur.reconnecter()  # bloque ici jusqu'à reconnexion

                except Exception as e:
                    print(f"Erreur inattendue : {e}")

        except KeyboardInterrupt:
            print("Arrêt")
        finally:
            self.mqtt.disconnect()