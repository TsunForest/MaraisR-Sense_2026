# -*- coding: utf-8 -*-
# Lecture eCO2 (ppm) et TVOC (ppb) avec UNIHIKER + SEN-CCS811V1
# et envoi de chaque mesure à un broker MQTT

import time
import json
from datetime import datetime

from pinpong.board import Board, I2C
import paho.mqtt.client as mqtt  # pip install paho-mqtt

# --- Paramètres MQTT à ADAPTER à ton environnement ---
MQTT_BROKER   = "172.16.4.35"      # IP ou nom du broker (ex: "broker.emqx.io", "test.mosquitto.org"...)
MQTT_PORT     = 1883                # port MQTT standard sans TLS
MQTT_TOPIC    = "marais/sondes/MAC/00:e0:4c:d1:72:81" # Mac de la sonde
MQTT_CLIENTID = "00:e0:4c:d1:72:81" # Mac de la sonde

MQTT_USERNAME = None                # ou "siot" si tu utilises le broker local UNIHIKER [web:98]
MQTT_PASSWORD = None                # ou "dfrobot" pour le broker local UNIHIKER [web:98]

# --- Initialisation de la carte et du bus I2C ---
Board("UNIHIKER").begin()
i2c = I2C()

CCS811_ADDR = 0x5A  # Adresse I2C par défaut

# Registres CCS811
REG_STATUS        = 0x00
REG_MEAS_MODE     = 0x01
REG_ALG_RESULT    = 0x02
REG_HW_ID         = 0x20
REG_APP_START     = 0xF4

HW_ID_EXPECTED    = 0x81


def read_reg(reg, length=1):
    data = i2c.readfrom_mem(CCS811_ADDR, reg, length)
    return list(data)


def write_reg(reg, data_bytes):
    i2c.writeto_mem(CCS811_ADDR, reg, data_bytes)


def ccs811_init():
    print("Scan I2C en cours...")
    devices = i2c.scan()
    print("Périphériques I2C détectés :", devices)
    if CCS811_ADDR not in devices:
        raise RuntimeError("CCS811 non trouvé (adresse 0x5A ou 0x5B).")

    hw_id = read_reg(REG_HW_ID, 1)[0]
    print("HW_ID lu =", hex(hw_id))
    if hw_id != HW_ID_EXPECTED:
        raise RuntimeError("HW_ID incorrect (attendu 0x81).")

    # APP_START
    i2c.writeto(CCS811_ADDR, [REG_APP_START])
    time.sleep(0.1)

    # Mode mesure toutes les 1 s (DRIVE_MODE = 1 -> 0x10)
    MEAS_MODE_1SEC = 0x10
    write_reg(REG_MEAS_MODE, [MEAS_MODE_1SEC])

    print("CCS811 initialisé en mode mesure 1 s.")


def ccs811_data_ready():
    status = read_reg(REG_STATUS, 1)[0]
    return (status & 0x08) != 0  # bit DATA_READY


def ccs811_read_eco2_tvoc():
    data = read_reg(REG_ALG_RESULT, 4)
    eco2 = (data[0] << 8) | data[1]
    tvoc = (data[2] << 8) | data[3]
    return eco2, tvoc


# --- Partie MQTT ---

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connecté au broker MQTT.")
    else:
        print("Échec de connexion MQTT, code de retour :", rc)


def create_mqtt_client():
    client = mqtt.Client(MQTT_CLIENTID)

    if MQTT_USERNAME is not None:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect

    client.connect(MQTT_BROKER, MQTT_PORT)
    # Démarre le loop dans un thread séparé pour gérer les ACK, reconnect, etc. [web:84][web:90]
    client.loop_start()
    return client


def publish_measure_mqtt(client, timestamp_iso, eco2, tvoc):
    """
    Publie une mesure sur le topic MQTT au format JSON.
    """
    payload = {
        "timestamp": timestamp_iso,
        "eco2": eco2,
        "tvoc": tvoc
    }
    # Conversion en chaîne JSON
    msg = json.dumps(payload)

    # QoS 0 par défaut, pas de retain (adapter si besoin). [web:91]
    result = client.publish(MQTT_TOPIC, msg)
    status = result[0]
    if status == 0:
        print(f"MQTT → {MQTT_TOPIC} : {msg}")
    else:
        print("Échec d'envoi MQTT (code status =", status, ")")


def main():
    ccs811_init()

    mqtt_client = create_mqtt_client()

    print("Démarrage des mesures eCO2 / TVOC (1 mesure / s) et publication MQTT...")
    print("Attention au burn-in et run-in du capteur (48 h + ~20 min).")

    try:
        while True:
            if ccs811_data_ready():
                eco2, tvoc = ccs811_read_eco2_tvoc()

                # Affichage console
                print(f"eCO2 : {eco2} ppm, TVOC : {tvoc} ppb")

                # Timestamp ISO
                ts = datetime.now().isoformat()

                # Publication MQTT
                publish_measure_mqtt(mqtt_client, ts, eco2, tvoc)
            else:
                print("Données non prêtes...")

            time.sleep(1)
    except KeyboardInterrupt:
        print("Arrêt du programme.")
    finally:
        # Arrêt propre du client MQTT
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("Client MQTT déconnecté.")


if __name__ == "__main__":
    main()
