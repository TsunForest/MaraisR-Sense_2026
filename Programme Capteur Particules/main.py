from time import time
from utils import EnvoiMesures, CapteurParticules
import serial


class Controller():

    def __init__(self):
        self.capteur = CapteurParticules()
        self.mqtt = EnvoiMesures(
            broker="marais2026.btssn.ovh", 
            port=1883,
            topic="marais/sondes/62:03:57:41:38:23",
            client_id="62:03:57:41:38:23",
            username="marais2026", 
            password="hyrome49#"
        )
    
    def prise_mesure_et_envoi(self):
        capteur = self.capteur
        mqtt = self.mqtt

        print("PM10 (1 msg/min)")

        try:
            while True:
                try:
                    pm10 = capteur.get_pm10()
                    print(f"PM10 : {pm10}")
                    mqtt.publish_measure(pm10)

                except serial.SerialException as e:
                    print(f"Capteur débranché : {e}")
                    capteur.reconnecter()  # bloque ici jusqu'à reconnexion

                except Exception as e:
                    print(f"Erreur inattendue : {e}")

        except KeyboardInterrupt:
            print("Arrêt")
        finally:
            mqtt.disconnect()


if __name__ == "__main__":
    controller = Controller()
    controller.prise_mesure_et_envoi()