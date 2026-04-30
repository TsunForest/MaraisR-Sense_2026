#!/usr/bin/env python3
"""
Test de connectivité MQTT/TLS — Projet Marais'R'Sense
Vérifie si le broker est accessible via une connexion sécurisée TLS.
"""

import paho.mqtt.client as mqtt
import time, os, ssl

BROKER_HOST = "marais2026.btssn.ovh"
BROKER_PORT = 8883
TIMEOUT     = 5
CA_CERT     = os.path.join(os.path.dirname(__file__), "ca.crt")

# Authentification
USERNAME = "marais2026"
PASSWORD = "hyrome49#"

connected = False

def on_connect(client, userdata, flags, rc):
    """Callback de connexion : rc == 0 → succès."""
    global connected
    connected = rc == 0
    print(f"{'✅' if connected else '❌'} Connexion TLS — code : {rc}")
    client.disconnect()

client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)
client.on_connect = on_connect

try:
    # Validation stricte  du certificat CA, paramètres TLS par défaut
    client.tls_set(ca_certs=CA_CERT, cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(False)
    print(f"🔑 TLS configuré avec : {CA_CERT}")
except Exception as e:
    print(f"❌ Erreur config TLS : {e}")
    exit(1)

try:
    print(f"🚀 Connexion à {BROKER_HOST}:{BROKER_PORT}…")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=TIMEOUT)
    client.loop_start()
    time.sleep(TIMEOUT)
    client.loop_stop()
except Exception as e:
    print(f"❌ Erreur connexion : {e}")

print("✅ Broker disponible (TLS)" if connected else "❌ Broker injoignable ou certificat invalide")