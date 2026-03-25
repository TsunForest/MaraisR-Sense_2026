import time
from utils import MesureTVOC_CO2, MQTT

def main():
    mqtt = MQTT()
    capteur = MesureTVOC_CO2()

    try:
        while True:
            mesures = capteur.get_mesures()

            if mesures is None:
                # Pas de données à envoyer (run-in, capteur absent, pas prêt)
                print("ATTENTE / AUCUNE DONNEE VALIDE")
            else:
                eco2, tvoc = mesures
                print(f"eCO2:{eco2} TVOC:{tvoc}")
                mqtt.publish_measure(eco2, tvoc)

            time.sleep(60)  # 1 mesure par minute

    except KeyboardInterrupt:
        print("Arret")
    finally:
        mqtt.disconnect()

if __name__ == "__main__":
    main()
