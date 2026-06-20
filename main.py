import time
from pinpong.board import Board, I2C
from utils import Ccs811, MQTT, MesureTVOC_CO2

def main():
    Board("UNIHIKER").begin()
    i2c = I2C()

    # Capteur
    ccs811 = Ccs811()
    ccs811.ccs811_init()

    # MQTT
    mqtt = MQTT(broker="172.16.4.35")  # Vérifie IP !
    print("Test MQTT...")
    mqtt_ok = mqtt.publish_measure(999, 999)
    print(f"MQTT test: {' OK' if mqtt_ok else 'KO'}")

    # Gestion erreurs
    gestion = MesureTVOC_CO2()
    gestion.i2c = i2c
    gestion.mqtt = mqtt

    mesure_prec = 0
    compteur = 0

    try:
        while True:
            if gestion.check_capteur():  # ← Scan simple 100ms
                if ccs811.data_ready():   # ← STATUS DATA_READY bit 3
                    eco2, tvoc = ccs811.read_eco2_tvoc()
                    print(f"eCO2:{eco2} TVOC:{tvoc}")
                    mqtt.publish_measure(eco2, tvoc)
                else:
                    print(".", end="", flush=True)  # Point discret
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nArrêt")
    finally:
        mqtt.disconnect()



if __name__ == "__main__":
    main()
