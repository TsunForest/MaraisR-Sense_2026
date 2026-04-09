#!/usr/bin/env python3
"""
Script de test d'infrastructure pour switch Cisco
Auteur: Projet Marais'R'Sense
Description: Script complet avec menu interactif pour tester la configuration
             d'un switch Cisco et afficher/sauvegarder les configurations.
"""

from netmiko import ConnectHandler
import re
import getpass
import subprocess
from datetime import datetime
import os

# ============================================================
# CONFIGURATION
# ============================================================

SWITCH_HOST   = "switch_marais"
SWITCH_PORT   = 22
LOG_DIR_TESTS = os.path.join("logs", "tests")    # logs des tests d'infra (avec timestamp)
LOG_DIR_CONF  = os.path.join("logs", "configs")  # logs des show config (nom simple)
os.makedirs(LOG_DIR_TESTS, exist_ok=True)
os.makedirs(LOG_DIR_CONF,  exist_ok=True)

VLANS = {
    "ADMIN (372)":   "192.168.72.1",
    "ARTISAN (255)": "192.168.55.1",
    "SONDES (488)":  "192.168.88.1",
}
ROUTEUR_IP    = "10.0.0.1"
INTERNET_IP   = "8.8.8.8"
ACL_ATTENDUES = ["ACL_SONDES", "ACL_ARTISAN"]

# ============================================================
# SYSTÈME DE LOGGING ET AFFICHAGE
# ============================================================

def get_log_file(suffix="tests", simple=False):
    """
    Génère un nom de fichier de log.
    - simple=False : logs/tests/test_switch_YYYY-MM-DD_HH-MM-SS_tests.log
    - simple=True  : logs/configs/YYYY-MM-DD_HH-MM-SS_suffix.log (avec timestamp pour éviter l'écrasement)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if simple:
        return os.path.join(LOG_DIR_CONF, f"{timestamp}_{suffix}.log")
    return os.path.join(LOG_DIR_TESTS, f"test_switch_{timestamp}_{suffix}.log")

# Fichier de log principal pour la session de tests (créé seulement lors de la première écriture)
log_file = None
log_initialized = False

def get_current_log_file():
    """Retourne le fichier de log actuel, le crée si nécessaire."""
    global log_file, log_initialized
    if not log_initialized:
        log_file = get_log_file("tests")
        log_initialized = True
    return log_file

def log_message(message, log_path=None):
    """Écrit un message horodaté dans le fichier de log spécifié (ou principal)."""
    if log_path is None:
        log_path = get_current_log_file()
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n\n")

# Fonctions d'affichage coloré
ok    = lambda t: (log_message(f"✔ {t}"),  print(f"\033[92m  [OK]  {t}\033[0m"))
ko    = lambda t: (log_message(f"✘ {t}"),  print(f"\033[91m  [KO]  {t}\033[0m"))
info  = lambda t: (log_message(f"ℹ {t}"),  print(f"\033[94m  [--]  {t}\033[0m"))
titre = lambda t: (log_message(f"=== {t} ==="), print(f"\n\033[93m{'='*60}\n  {t}\n{'='*60}\033[0m"))

# ============================================================
# CONNEXION SSH
# ============================================================

def connecter(user, password):
    """Établit la connexion SSH au switch Cisco (3 essais max)."""
    max_essais = 3
    for essai in range(max_essais):
        try:
            log_message(f"Tentative de connexion {essai + 1}/{max_essais} avec : {user}")
            return ConnectHandler(device_type='cisco_ios', host=SWITCH_HOST,
                                  username=user, password=password, port=SWITCH_PORT)
        except Exception as e:
            if essai == max_essais - 1:
                ko(f"Connexion SSH échouée : {e}")
                return None
            print(f"\033[91m  Échec {essai + 1}/{max_essais} - Réessayez...\033[0m")
            user     = input("Nom d'utilisateur : ")
            password = getpass.getpass("Mot de passe : ")

def cmd(client, c, log_path=None):
    """
    Exécute une commande sur le switch.
    - log_path=None  → logue dans le log principal de session (tests)
    - log_path=<path> → logue uniquement dans le fichier dédié (configs)
    """
    log_message(f"Commande: {c}", log_path=log_path)
    return client.send_command(c)

# ============================================================
# FONCTIONS DE TEST
# ============================================================

resultats = []

def test(description, resultat):
    resultats.append((description, resultat))
    if resultat:
        ok(description)
    else:
        ko(description)

def ping_ok(output):
    log_message(f"Résultat ping: {output.strip()}")
    return "!!" in output or "Success rate is 100" in output

def ping_bloque(output):
    log_message(f"Résultat ping (bloqué): {output.strip()}")
    return any(x in output for x in ["Success rate is 0", "0 packets received", "unreachable"])

# --- TEST 1 : Connectivité ---
def test_connectivite(c):
    titre("1. TEST CONNECTIVITE (PING)")
    cibles = list(VLANS.items()) + [("Routeur", ROUTEUR_IP)]
    for nom, ip in cibles:
        test(f"Ping {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))
    try:
        result = subprocess.run(["ping", "-c", "2", INTERNET_IP],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=5)
        succes = result.returncode == 0
    except Exception:
        succes = False
    test(f"Ping Internet ({INTERNET_IP}) depuis le PC", succes)

# --- TEST 2 : Blocage inter-VLAN ---
def test_blocage_intervlan(c):
    titre("2. TEST BLOCAGE INTER-VLAN")
    gw = list(VLANS.values())
    src_sondes, src_artisan, src_admin = gw[2], gw[1], gw[0]

    info("Test SONDES → ADMIN/ARTISAN (doit echouer)")
    test("SONDES → ADMIN (bloqué)",    ping_bloque(cmd(c, f"ping {src_admin}   source {src_sondes}  repeat 2")))
    test("SONDES → ARTISAN (bloqué)",  ping_bloque(cmd(c, f"ping {src_artisan} source {src_sondes}  repeat 2")))

    info("Test ARTISAN → ADMIN/SONDES (doit echouer)")
    test("ARTISAN → ADMIN (bloqué)",   ping_bloque(cmd(c, f"ping {src_admin}   source {src_artisan} repeat 2")))
    test("ARTISAN → SONDES (bloqué)",  ping_bloque(cmd(c, f"ping {src_sondes}  source {src_artisan} repeat 2")))

    info("Test depuis VLAN ADMIN vers tous les VLAN (doit reussir)")
    for nom, ip in list(VLANS.items())[1:]:
        test(f"ADMIN → {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))

# --- TEST 3 : ACL ---
def test_acl(c):
    titre("3. VERIFICATION DES ACL")
    output = cmd(c, "show ip access-lists")
    log_message(f"Liste ACL:\n{output.strip()}")
    for acl in ACL_ATTENDUES:
        test(f"ACL présente : {acl}", acl in output)

# --- TEST 4 : DHCP ---
def test_dhcp(c):
    titre("4. VERIFICATION DHCP")
    output = cmd(c, "show ip dhcp binding")
    log_message(f"Bindings DHCP:\n{output.strip()}")
    for vlan, gw in VLANS.items():
        reseau = ".".join(gw.split(".")[:3])
        nb = len(re.findall(reseau + r"\.\d+", output))
        test(f"DHCP {vlan} : {nb} adresse(s) distribuée(s)", nb > 0)

# --- TEST 5 : VLAN ---
def test_vlan(c):
    titre("5. VERIFICATION DES VLAN")
    output = cmd(c, "show vlan brief")
    log_message(f"VLANs:\n{output.strip()}")
    vlans_attendus = {"255": "ARTISAN", "372": "ADMIN", "488": "SONDES"}
    for num, nom in vlans_attendus.items():
        test(f"VLAN {num} ({nom}) présent et actif", num in output and nom in output)

# ============================================================
# FONCTIONS D'AFFICHAGE / SAUVEGARDE DE CONFIG
# ============================================================

def afficher_et_sauvegarder(c, commande, suffixe_log, label):
    """
    Exécute une commande show, affiche le résultat dans le terminal
    et le sauvegarde dans son fichier de log dédié (logs/configs/).
    Rien n'est écrit dans le log principal de session.
    """
    lf = get_log_file(suffixe_log, simple=True)
    # Affichage terminal sans toucher au log principal
    print(f"\n\033[93m{'='*60}\n  AFFICHAGE : {label}\n{'='*60}\033[0m")
    output = cmd(c, commande, log_path=lf)
    print(f"\033[96m{output}\033[0m")
    log_message(f"=== {label} ===\nCommande : {commande}\n\n{output}", log_path=lf)
    print(f"\033[93m  → Sauvegardé dans : {lf}\033[0m")

def show_running_config(c):
    afficher_et_sauvegarder(c, "show running-config", "running-config", "Running Config")

def show_vlan(c):
    afficher_et_sauvegarder(c, "show vlan brief", "vlan-brief", "VLAN Brief")

def show_acl(c):
    afficher_et_sauvegarder(c, "show ip access-lists", "acl", "ACL (show ip access-lists)")

def show_dhcp_binding(c):
    afficher_et_sauvegarder(c, "show ip dhcp binding", "dhcp-binding", "DHCP Binding")

def show_interfaces(c):
    afficher_et_sauvegarder(c, "show interfaces status", "interfaces-status", "Interfaces Status")

def show_ip_route(c):
    afficher_et_sauvegarder(c, "show ip route", "ip-route", "Table de routage (show ip route)")

def show_ntp(c):
    afficher_et_sauvegarder(c, "show ntp status", "ntp-status", "NTP Status")

# ============================================================
# RÉSUMÉ FINAL DES TESTS
# ============================================================

def afficher_resume():
    """Affiche un tableau récapitulatif de tous les tests exécutés."""
    if not resultats:
        return
    titre("RÉSUMÉ DES TESTS")
    total = len(resultats)
    reussis = sum(1 for _, r in resultats if r)
    echoues = total - reussis

    for desc, res in resultats:
        symbole = "\033[92m✔\033[0m" if res else "\033[91m✘\033[0m"
        print(f"  {symbole}  {desc}")

    couleur = "\033[92m" if echoues == 0 else "\033[91m"
    print(f"\n{couleur}  Résultat : {reussis}/{total} tests réussis  ({echoues} échoués)\033[0m")
    log_message(f"RÉSUMÉ : {reussis}/{total} réussis, {echoues} échoués")

# ============================================================
# MENU PRINCIPAL
# ============================================================

MENU_TESTS = [
    ("Connectivité (ping gateways + Internet)",  test_connectivite),
    ("Blocage inter-VLAN",                        test_blocage_intervlan),
    ("Vérification des ACL",                      test_acl),
    ("Vérification DHCP (bindings)",              test_dhcp),
    ("Vérification des VLANs",                    test_vlan),
]

MENU_SHOW = [
    ("Running-config",           show_running_config),
    ("VLAN brief",               show_vlan),
    ("ACL (ip access-lists)",    show_acl),
    ("DHCP binding",             show_dhcp_binding),
    ("Interfaces status",        show_interfaces),
    ("Table de routage",         show_ip_route),
    ("NTP status",               show_ntp),
]

def afficher_menu(titre_menu, options, lettre_retour="r"):
    """Affiche un menu numéroté et retourne le choix validé de l'utilisateur."""
    print(f"\n\033[93m{'='*60}\n  {titre_menu}\n{'='*60}\033[0m")
    for i, (label, _) in enumerate(options, 1):
        print(f"  \033[97m[{i:2d}]\033[0m  {label}")
    print(f"  \033[97m[ a]\033[0m  Tout sélectionner")
    print(f"  \033[97m[{lettre_retour:>2}]\033[0m  Retour au menu principal\n")

    while True:
        try:
            choix = input("  Votre choix : ").strip().lower()
            if choix == lettre_retour:
                return None
            if choix == "a":
                return "all"
            if choix.isdigit():
                idx = int(choix) - 1
                if 0 <= idx < len(options):
                    return idx
            print("  \033[91m Choix invalide, réessayez.\033[0m")
        except KeyboardInterrupt:
            print("\n\033[93m  Interruption détectée - Retour au menu principal\033[0m")
            return None

def menu_tests(client):
    """Sous-menu pour choisir quels tests exécuter."""
    while True:
        choix = afficher_menu("MENU — TESTS D'INFRASTRUCTURE", MENU_TESTS)
        if choix is None:
            break
        elif choix == "all":
            for _, fn in MENU_TESTS:
                fn(client)
            afficher_resume()
        else:
            label, fn = MENU_TESTS[choix]
            fn(client)
            afficher_resume()

def menu_show(client):
    """Sous-menu pour afficher et sauvegarder des configs."""
    while True:
        choix = afficher_menu("MENU — AFFICHER / SAUVEGARDER UNE CONFIG", MENU_SHOW)
        if choix is None:
            break
        elif choix == "all":
            for _, fn in MENU_SHOW:
                fn(client)
        else:
            _, fn = MENU_SHOW[choix]
            fn(client)

def menu_principal(client):
    """Menu principal de navigation."""
    while True:
        print(f"\n\033[95m{'='*60}")
        print(f"   MENU PRINCIPAL — MARAIS'R'SENSE")
        print(f"   Switch : {SWITCH_HOST}")
        print(f"{'='*60}\033[0m")
        print("  \033[97m[1]\033[0m  Tests d'infrastructure")
        print("  \033[97m[2]\033[0m  Afficher / Sauvegarder une configuration")
        print("  \033[97m[q]\033[0m  Quitter\n")

        try:
            choix = input("  Votre choix : ").strip().lower()
            if choix == "1":
                menu_tests(client)
            elif choix == "2":
                menu_show(client)
            elif choix == "q":
                print("\n\033[93m  Au revoir !\033[0m\n")
                break
            else:
                print("  \033[91m Choix invalide.\033[0m")
        except KeyboardInterrupt:
            print("\n\033[93m  Interruption détectée - Arrêt du programme\033[0m")
            break

# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

if __name__ == "__main__":
    print(f"\n\033[95m{'='*60}\n   TEST INFRASTRUCTURE — PROJET MARAIS'R'SENSE\n"
          f"   Switch  : {SWITCH_HOST}\n"
          f"   Tests   : {LOG_DIR_TESTS}/\n"
          f"   Configs : {LOG_DIR_CONF}/\n"
          f"{'='*60}\033[0m")
    log_message(f"Démarrage du script — switch : {SWITCH_HOST}")

    username = input("Nom d'utilisateur : ")
    password = getpass.getpass("Mot de passe : ")
    log_message(f"Tentative de connexion avec : {username}")

    client = connecter(username, password)
    if not client:
        exit(1)
    ok("Connexion SSH établie avec succès")

    try:
        menu_principal(client)
    finally:
        client.disconnect()
        if log_initialized:
            print(f"\033[94m  Log principal sauvegardé : {log_file}\033[0m\n")
        else:
            print("\033[94m  Aucun test exécuté - pas de log créé\033[0m\n")