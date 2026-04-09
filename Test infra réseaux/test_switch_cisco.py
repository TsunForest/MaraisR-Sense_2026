#!/usr/bin/env python3
"""
Script de test d'infrastructure pour switch Cisco
Auteur: Projet Marais'R'Sense
Description: Script complet pour tester la configuration d'un switch Cisco
             - Connectivité réseau
             - Blocage inter-VLAN
             - Configuration des ACL
             - Serveur DHCP
             - Configuration des VLANs
"""

from netmiko import ConnectHandler  # Bibliothèque pour connexion SSH aux équipements Cisco
import re  # Expressions régulières pour la recherche de patterns
import getpass  # Pour la saisie sécurisée du mot de passe
import subprocess  # Pour exécuter des commandes système locales
from datetime import datetime  # Pour les timestamps dans les logs
import os  # Pour la gestion des fichiers et dossiers

# ============================================================
# CONFIGURATION
# ============================================================

# ============================================================
# CONFIGURATION DU SWITCH
# ============================================================

SWITCH_HOST = "switch_marais"  # Nom d'hôte du switch (doit être dans /etc/hosts ou DNS)
SWITCH_PORT = 22  # Port SSH standard
LOG_DIR = "logs"  # Dossier pour stocker les fichiers de log
os.makedirs(LOG_DIR, exist_ok=True)  # Crée le dossier logs s'il n'existe pas

# Dictionnaire des VLANs avec leurs gateways respectives
# Clé: Nom du VLAN avec numéro, Valeur: Adresse IP de la gateway
VLANS = {
    "ADMIN (372)":   "192.168.72.1",  # VLAN administratif
    "ARTISAN (255)": "192.168.55.1",  # VLAN artisans
    "SONDES (488)":  "192.168.88.1",  # VLAN des sondes
}
ROUTEUR_IP   = "10.0.0.1"  # Adresse IP du routeur principal
INTERNET_IP  = "8.8.8.8"  # Adresse IP de test de connectivité Internet (Google DNS)
ACL_ATTENDUES = ["ACL_SONDES", "ACL_ARTISAN"]  # Liste des ACLs qui doivent être présentes sur le switch

# ============================================================
# SYSTÈME DE LOGGING ET AFFICHAGE
# ============================================================

def get_log_file():
    """
    Génère le nom du fichier de log avec timestamp unique
    Format: logs/test_switch_YYYY-MM-DD_HH-MM-SS.log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"logs/test_switch_{timestamp}.log"

# Initialiser le fichier log au début du programme
log_file = get_log_file()

def log_message(message):
    """
    Écrit un message dans le fichier de log avec timestamp
    Ajoute une ligne vide après chaque message pour la lisibilité
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n\n")  # Ligne vide après chaque message

# Fonctions d'affichage avec couleurs et logging automatique
# Utilisent des symboles Unicode pour une meilleure lisibilité
ok    = lambda t: (log_message(f"✓ {t}"), print(f"\033[92m  [OK]  {t}\033[0m"))  # Vert pour succès
ko    = lambda t: (log_message(f"✗ {t}"), print(f"\033[91m  [KO]  {t}\033[0m"))  # Rouge pour échec
info  = lambda t: (log_message(f"ℹ {t}"), print(f"\033[94m  [--]  {t}\033[0m"))  # Bleu pour information
titre = lambda t: (log_message(f"=== {t} ==="), print(f"\n\033[93m{'='*60}\n  {t}\n{'='*60}\033[0m"))  # Jaune pour titres

# ============================================================
# CONNEXION SSH ET EXÉCUTION DE COMMANDES
# ============================================================

def connecter(user, password):
    """
    Établit la connexion SSH au switch Cisco avec 3 essais maximum
    
    Args:
        user (str): Nom d'utilisateur pour la connexion
        password (str): Mot de passe pour la connexion
    
    Returns:
        ConnectHandler: Objet de connexion Netmiko si succès, None si échec
    """
    max_essais = 3  # Nombre maximum de tentatives de connexion
    for essai in range(max_essais):
        try:
            log_message(f"Tentative de connexion {essai + 1}/{max_essais} avec l'utilisateur: {user}")
            return ConnectHandler(device_type='cisco_ios', host=SWITCH_HOST,
                                  username=user, password=password, port=SWITCH_PORT)
        except Exception as e:
            if essai == max_essais - 1:
                ko(f"Connexion SSH échouée : {e}")
                return None
            else:
                log_message(f"Échec de connexion {essai + 1}/{max_essais}: {e}")
                if essai < max_essais - 1:
                    print(f"\033[91m  Échec {essai + 1}/{max_essais} - Réessayez...\033[0m")
                    user = input("Nom d'utilisateur : ")
                    password = getpass.getpass("Mot de passe : ")

def cmd(client, c):
    """
    Exécute une commande sur le switch et log la commande
    
    Args:
        client: Objet de connexion Netmiko
        c (str): Commande à exécuter
    
    Returns:
        str: Résultat de la commande
    """
    log_message(f"Commande: {c}")
    return client.send_command(c)

# ============================================================
# FONCTIONS DE TEST ET VALIDATION
# ============================================================

resultats = []  # Liste pour stocker les résultats des tests

def test(description, resultat):
    """
    Enregistre et affiche le résultat d'un test
    
    Args:
        description (str): Description du test
        resultat (bool): True si succès, False si échec
    """
    resultats.append((description, resultat))
    if resultat:
        ok(description)
    else:
        ko(description)

def ping_ok(output):
    """
    Vérifie si un ping a réussi
    
    Args:
        output (str): Résultat de la commande ping
    
    Returns:
        bool: True si ping réussi, False sinon
    """
    log_message(f"Résultat ping: {output.strip()}")
    return "!!" in output or "Success rate is 100" in output

def ping_bloque(output):
    """
    Vérifie si un ping est bloqué (échoue comme attendu)
    
    Args:
        output (str): Résultat de la commande ping
    
    Returns:
        bool: True si ping bloqué, False sinon
    """
    log_message(f"Résultat ping (bloqué): {output.strip()}")
    return any(x in output for x in ["Success rate is 0", "0 packets received", "unreachable"])

# --- 1. Connectivité ---
# ============================================================
# FONCTIONS DE TESTS D'INFRASTRUCTURE
# ============================================================

def test_connectivite(c):
    """
    Test 1: Vérifie la connectivité de base
    - Ping des gateways de chaque VLAN depuis le switch
    - Ping du routeur principal
    - Ping d'Internet depuis le PC local
    
    Args:
        c: Objet de connexion Netmiko
    """
    titre("1. TEST CONNECTIVITE (PING)")
    
    # Test des gateways VLAN depuis le switch
    cibles = list(VLANS.items()) + [("Routeur", ROUTEUR_IP)]
    for nom, ip in cibles:
        test(f"Ping {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))
    
    # Test de connectivité Internet depuis le PC local
    import subprocess
    try:
        result = subprocess.run(["ping", "-c", "2", INTERNET_IP], 
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL, 
                              timeout=5)
        succes = result.returncode == 0
    except Exception:
        succes = False
    test(f"Ping Internet ({INTERNET_IP}) depuis le PC", succes)

def test_blocage_intervlan(c):
    """
    Test 2: Vérifie les règles de blocage inter-VLAN
    - SONDES ne doit pas pouvoir joindre ADMIN et ARTISAN
    - ARTISAN ne doit pas pouvoir joindre ADMIN et SONDES
    - ADMIN doit pouvoir joindre tous les autres VLANs
    
    Args:
        c: Objet de connexion Netmiko
    """
    titre("2. TEST BLOCAGE INTER-VLAN")
    # Récupération des adresses IP des gateways
    gw = list(VLANS.values())
    src_sondes, src_artisan, src_admin = gw[2], gw[1], gw[0]  # SONDES, ARTISAN, ADMIN
    
    # Tests de blocage depuis SONDES (doivent échouer)
    info("Test SONDES → ADMIN/ARTISAN (doit echouer)")
    test(f"SONDES → ADMIN (bloque)", ping_bloque(cmd(c, f"ping {src_admin} source {src_sondes} repeat 2")))
    test(f"SONDES → ARTISAN (bloque)", ping_bloque(cmd(c, f"ping {src_artisan} source {src_sondes} repeat 2")))
    
    # Tests de blocage depuis ARTISAN (doivent échouer)
    info("Test ARTISAN → ADMIN/SONDES (doit echouer)")
    test(f"ARTISAN → ADMIN (bloque)", ping_bloque(cmd(c, f"ping {src_admin} source {src_artisan} repeat 2")))
    test(f"ARTISAN → SONDES (bloque)", ping_bloque(cmd(c, f"ping {src_sondes} source {src_artisan} repeat 2")))
    
    # Test de routage normal depuis ADMIN (doit réussir)
    info("Test depuis VLAN ADMIN vers tous les VLAN (doit reussir)")
    for nom, ip in list(VLANS.items())[1:]:  # Skip ADMIN (index 0)
        test(f"ADMIN → {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))

# --- 3. VERIFICATION DES ACL ---
def test_acl(c):
    """
    Test 3: Vérifie la présence des ACLs configurées
    - Vérifie que ACL_SONDES et ACL_ARTISAN sont présentes
    
    Args:
        c: Objet de connexion Netmiko
    """
    titre("3. VERIFICATION DES ACL")
    output = cmd(c, "show ip access-lists")
    log_message(f"Liste ACL: {output.strip()}")
    for acl in ACL_ATTENDUES:
        test(f"ACL presente : {acl}", acl in output)

# --- 4. VERIFICATION DHCP ---
def test_dhcp(c):
    """
    Test 4: Vérifie le fonctionnement du serveur DHCP
    - Compte le nombre d'adresses IP distribuées par VLAN
    
    Args:
        c: Objet de connexion Netmiko
    """
    titre("4. VERIFICATION DHCP")
    output = cmd(c, "show ip dhcp binding")
    log_message(f"Bindings DHCP: {output.strip()}")
    for vlan, gw in VLANS.items():
        # Extrait le réseau (ex: 192.168.72) de la gateway
        reseau = ".".join(gw.split(".")[:3])
        # Compte combien d'adresses IP de ce réseau sont distribuées
        nb = len(re.findall(reseau + r"\.\d+", output))
        test(f"DHCP {vlan} : {nb} adresse(s) distribuee(s)", nb > 0)

# --- 5. VERIFICATION DES VLAN ---
def test_vlan(c):
    """
    Test 5: Vérifie la configuration des VLANs
    - Vérifie que les VLANs 255 (ARTISAN), 372 (ADMIN), 488 (SONDES) existent
    - Vérifie qu'ils sont actifs
    
    Args:
        c: Objet de connexion Netmiko
    """
    titre("5. VERIFICATION DES VLAN")
    output = cmd(c, "show vlan brief")
    log_message(f"VLANs: {output.strip()}")
    # Dictionnaire des VLANs attendus: numéro -> nom
    vlans_attendus = {"255": "ARTISAN", "372": "ADMIN", "488": "SONDES"}
    for num, nom in vlans_attendus.items():
        test(f"VLAN {num} ({nom}) present et actif", num in output and nom in output)

# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

if __name__ == "__main__":
    """
    Point d'entrée principal du programme
    - Crée le dossier de logs
    - Affiche l'en-tête du programme
    - Demande les identifiants de connexion
    - Lance tous les tests d'infrastructure
    - Déconnecte proprement du switch
    """
    # Créer le dossier logs s'il n'existe pas
    os.makedirs("logs", exist_ok=True)
    
    # Affichage de l'en-tête avec informations de la session
    print(f"\n\033[95m{'='*60}\n   TEST INFRASTRUCTURE - PROJET MARAIS'R'SENSE\n"
          f"   Switch : {SWITCH_HOST}\n   Log : {log_file}\n{'='*60}\033[0m")
    log_message(f"Début des tests sur {SWITCH_HOST}")

    # Saisie sécurisée des identifiants
    username = input("Nom d'utilisateur : ")
    password = getpass.getpass("Mot de passe : ")
    log_message(f"Tentative de connexion avec l'utilisateur: {username}")

    # Connexion au switch avec 3 essais maximum
    client = connecter(username, password)
    if not client:
        exit(1)  # Arrêt du programme si connexion échouée
    ok("Connexion réussie au switch avec succès")

    # Exécution séquentielle de tous les tests
    tests_a_executer = [
        test_connectivite,      # Test 1: Connectivité de base
        test_blocage_intervlan,  # Test 2: Blocage inter-VLAN
        test_acl,               # Test 3: Configuration des ACLs
        test_dhcp,              # Test 4: Serveur DHCP
        test_vlan               # Test 5: Configuration des VLANs
    ]
    
    for test_function in tests_a_executer:
        test_function(client)

    # Déconnexion propre du switch
    client.disconnect()
    log_message("Fin des tests - Déconnexion du switch")