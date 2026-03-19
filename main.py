import time
from pinpong.board import Board
from utils import Ccs811, MQTT, MesureTVOC_CO2

def main():
    Board("UNIHIKER").begin()

    mqtt = MQTT()

    # Variables état
    ccs811_ok = False
    last_scan = 0

    try:
        while True:
            # RESCAN 30s
            if time.time() - last_scan > 30:
                last_scan = time.time()
                print("SCAN I2C...")

                try:
                    ccs811 = Ccs811()  # Nouveau !
                    ccs811.ccs811_init()
                    ccs811_ok = True
                    print("CAPTEUR OK")
                except:
                    ccs811_ok = False
                    print("CAPTEUR ABSENT")

            if ccs811_ok:
                try:
                    if ccs811.data_ready():
                        eco2, tvoc = ccs811.read_eco2_tvoc()
                        print(f"eCO2:{eco2} TVOC:{tvoc}")
                        mqtt.publish_measure(eco2, tvoc)
                    else:
                        print(".", end="", flush=True)
                except PermissionError:
                    print("DEBRANCHE")
                    ccs811_ok = False
                    mqtt.publish_measure(-999, -999)
                except:
                    print("ERREUR LECTURE")

            time.sleep(1)

    except KeyboardInterrupt:
        print("Arret")
    finally:
        mqtt.disconnect()

if __name__ == "__main__":
    main()
