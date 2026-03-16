import time
from utils import Ccs811, MQTT

def main():
    ccs811 = Ccs811()
    ccs811.ccs811_init()

    mqtt = MQTT(broker="172.16.4.35", topic="marais/sondes/a2:c4:cb:3d:e9:1a")

    print("CO2/TVOC + MQTT (1 msg/min)")

    try:
        while True:
            if ccs811.data_ready():
                eco2, tvoc = ccs811.read_eco2_tvoc()
                print(f"eCO2: {eco2}ppm TVOC: {tvoc}ppb")
                mqtt.publish_measure(eco2, tvoc)
            time.sleep(60)

    except KeyboardInterrupt:
        print("Arrêt")
    finally:
        mqtt.disconnect()

if __name__ == "__main__":
    main()
