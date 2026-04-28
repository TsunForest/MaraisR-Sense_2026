#!/usr/bin/env python3
"""
Script de test d'infrastructure pour switch Cisco - Version Améliorée
Auteur: Projet Marais'R'Sense
Description: Script complet pour tester la configuration d'un switch Cisco
             avec logging avancé et sauvegarde automatique des configurations.
             
             FONCTIONNALITÉS :
             - Tests complets d'infrastructure réseau
             - Logging séparé (tests vs configurations)
             - Sauvegarde automatique des configurations du switch
             - Exécution automatique sans interface menu
             
             CONCEPTS RÉSEAU VÉRIFIÉS :
             - VLAN : Segmentation logique des réseaux
             - ACL : Filtrage du trafic inter-VLAN
             - DHCP : Distribution automatique d'adresses IP
             - Inter-VLAN : Communication contrôlée entre VLANs
             - SSH : Administration sécurisée des équipements
"""

# Import des bibliothèques nécessaires pour l'administration réseau
from netmiko import ConnectHandler  # Bibliothèque principale pour connexion SSH aux équipements Cisco
import re                        # Expressions régulières pour analyse des résultats
import getpass                   # Saisie sécurisée des mots de passe (masqués à l'écran)
import subprocess                # Exécution de commandes système locales (ping)
from datetime import datetime    # Gestion des timestamps pour les logs
import os                        # Gestion des fichiers et répertoires

# NOTE PÉDAGOGIQUE : Netmiko est la bibliothèque de référence en Python
# pour l'automatisation des équipements réseaux (Cisco, Juniper, etc.)
# Elle simplifie énormément les connexions SSH et l'exécution de commandes

# ============================================================
# SECTION 1 : CONFIGURATION DES PARAMÈTRES RÉSEAU
# ============================================================
# Cette section contient tous les paramètres modifiables du script
# Adapter ces valeurs pour un environnement différent

# --- Paramètres de connexion au switch ---
SWITCH_HOST = "switch_marais"  # Nom d'hôte ou adresse IP du switch (doit être dans /etc/hosts ou DNS)
SWITCH_PORT = 22               # Port SSH standard (22 par défaut)

# --- Configuration des répertoires de logs ---
# Séparation des logs pour une meilleure organisation
LOG_DIR_TESTS = os.path.join("logs", "tests")    # Logs des tests d'infrastructure
LOG_DIR_CONF  = os.path.join("logs", "configs")  # Logs des configurations sauvegardées

# Création automatique des répertoires s'ils n'existent pas
# exist_ok=True évite les erreurs si les répertoires existent déjà
os.makedirs(LOG_DIR_TESTS, exist_ok=True)
os.makedirs(LOG_DIR_CONF,  exist_ok=True)

# --- Configuration des VLANs et passerelles ---
# FORMAT : "Nom du VLAN (numéro)" : "adresse_IP_de_la_passerelle"
# Les VLANs permettent de segmenter un réseau physique en réseaux logiques isolés
# Chaque VLAN a sa propre plage d'adresses IP et sa propre passerelle par défaut
VLANS = {
    "ADMIN (372)":   "192.168.72.1",  # VLAN 372 : Administration du projet
    "ARTISAN (255)": "192.168.55.1",  # VLAN 255 : Équipe des artisans
    "SONDES (488)":  "192.168.88.1",  # VLAN 488 : Capteurs et sondes IoT
}

# --- Adresses IP de référence pour les tests ---
ROUTEUR_IP   = "10.0.0.1"   # Passerelle inter-VLAN qui connecte les VLANs entre eux
INTERNET_IP  = "8.8.8.8"    # DNS public Google pour tester la connectivité Internet

# --- ACLs (Access Control Lists) à vérifier ---
# Les ACLs sont des règles de filtrage qui contrôlent le trafic réseau
# Elles sont essentielles pour la sécurité et l'isolation des VLANs
ACL_ATTENDUES = ["ACL_SONDES", "ACL_ARTISAN"]  # Noms des ACLs qui doivent être présentes

# ============================================================
# SECTION 2 : SYSTÈME DE LOGGING AVANCÉ ET AFFICHAGE COLORÉ
# ============================================================
# Cette section gère l'enregistrement des actions et l'affichage dans le terminal
# Logging séparé : logs/tests/ pour les tests, logs/configs/ pour les configurations

def get_log_file(suffix="tests", simple=False):
    """
    Génère un nom de fichier de log avec timestamp unique
    
    PARAMÈTRES :
    - suffix : suffixe ajouté au nom du fichier ("tests" par défaut)
    - simple : False = logs/tests/ (tests d'infra), True = logs/configs/ (configurations)
    
    RETOURNE : chemin complet du fichier de log
    
    EXEMPLES :
    - simple=False : logs/tests/test_switch_2024-04-28_14-30-25_tests.log
    - simple=True  : logs/configs/2024-04-28_14-30-25_running-config.log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if simple:
        return os.path.join(LOG_DIR_CONF, f"{timestamp}_{suffix}.log")
    return os.path.join(LOG_DIR_TESTS, f"test_switch_{timestamp}_{suffix}.log")

# Variables globales pour la gestion du fichier de log principal
# Pattern "lazy initialization" : le fichier n'est créé qu'à la première écriture
log_file = None          # Contiendra le chemin du fichier de log principal
log_initialized = False  # Indique si le fichier de log a été initialisé

def get_current_log_file():
    """
    Retourne le fichier de log actuel, le crée si nécessaire (pattern singleton)
    
    PRINCIPE : Garantit qu'il n'y a qu'un seul fichier de log par session
    
    UTILITÉ : Permet à toutes les fonctions d'écrire dans le même fichier log
    """
    global log_file, log_initialized
    if not log_initialized:
        log_file = get_log_file("tests")
        log_initialized = True
    return log_file

def log_message(message, log_path=None):
    """
    Écrit un message horodaté dans un fichier de log
    
    PARAMÈTRES :
    - message : texte à enregistrer
    - log_path : None = fichier principal, chemin = fichier dédié
    
    FONCTIONNEMENT :
    1. Utilise le fichier principal si log_path est None
    2. Ajoute un timestamp (heure seulement)
    3. Écrit en mode "append" (ajout à la fin)
    4. encoding="utf-8" pour gérer les caractères accentués
    """
    if log_path is None:
        log_path = get_current_log_file()
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n\n")

# --- Fonctions d'affichage coloré avec logging automatique ---
# Les codes ANSI (\033[XXm) permettent de colorer le texte dans le terminal
# Chaque fonction combine affichage ET enregistrement dans les logs

ok    = lambda t: (log_message(f"✔ {t}"),  print(f"\033[92m  [OK]  {t}\033[0m"))
    # Vert (92) pour un test réussi
ko    = lambda t: (log_message(f"✘ {t}"),  print(f"\033[91m  [KO]  {t}\033[0m"))
    # Rouge (91) pour un test échoué
info  = lambda t: (log_message(f"ℹ {t}"),  print(f"\033[94m  [--]  {t}\033[0m"))
    # Bleu (94) pour une information
titre = lambda t: (log_message(f"=== {t} ==="), print(f"\n\033[93m{'='*60}\n  {t}\n{'='*60}\033[0m"))
    # Jaune (93) pour un titre de section
    # \033[0m réinitialise la couleur pour ne pas affecter le texte suivant

# ============================================================
# SECTION 3 : CONNEXION SSH ET EXÉCUTION DE COMMANDES
# ============================================================
# Cette section gère la communication sécurisée avec le switch Cisco

# --- Variables globales pour stocker les résultats des tests ---
# FORMAT : [(description_du_test, résultat_booléen), ...]
# Exemple : [("Ping VLAN ADMIN", True), ("Ping VLAN ARTISAN", False)]
resultats = []

def connecter(user, password):
    """
    Établit la connexion SSH au switch Cisco avec gestion des erreurs et tentatives multiples
    
    PARAMÈTRES :
    - user : nom d'utilisateur pour la connexion SSH
    - password : mot de passe pour la connexion SSH
    
    FONCTIONNEMENT :
    1. Essai de connexion jusqu'à 3 fois maximum
    2. Si échec, demande à nouveau les identifiants
    3. Utilise Netmiko pour la connexion Cisco IOS
    4. Retourne None en cas d'échec total
    
    NOTE PÉDAGOGIQUE :
    - device_type='cisco_ios' indique à Netmiko le type d'équipement
    - La gestion des erreurs est cruciale en administration réseau
    - Le port 22 est le port SSH standard
    """
    max_essais = 3  # On autorise 3 tentatives de connexion
    for essai in range(max_essais):
        try:
            log_message(f"Tentative de connexion {essai + 1}/{max_essais} avec : {user}")
            # ConnectHandler est la fonction principale de Netmiko
            return ConnectHandler(
                device_type='cisco_ios',  # Type d'équipement Cisco
                host=SWITCH_HOST,         # Adresse du switch
                username=user,            # Nom d'utilisateur
                password=password,        # Mot de passe
                port=SWITCH_PORT          # Port SSH (22 par défaut)
            )
        except Exception as e:
            # Si c'est la dernière tentative, on abandonne
            if essai == max_essais - 1:
                ko(f"Connexion SSH échouée : {e}")
                return None
            # Sinon on demande à nouveau les identifiants
            print(f"\033[91m  Échec {essai + 1}/{max_essais} - Réessayez...\033[0m")
            user = input("Nom d'utilisateur : ")
            password = getpass.getpass("Mot de passe : ")

def cmd(client, c, log_path=None):
    """
    Exécute une commande sur le switch et enregistre l'action dans les logs
    
    PARAMÈTRES :
    - client : objet de connexion Netmiko au switch
    - c : commande Cisco à exécuter (ex: "show vlan brief")
    - log_path : None = log principal, chemin = fichier dédié
    
    FONCTIONNEMENT :
    1. Enregistre la commande dans les logs
    2. Envoie la commande au switch via Netmiko
    3. Retourne le résultat de la commande
    
    EXEMPLES DE COMMANDES :
    - "show vlan brief" : affiche les VLANs configurés
    - "ping 192.168.1.1" : teste la connectivité
    - "show running-config" : affiche la configuration complète
    
    NOTE : send_command() est la méthode principale de Netmiko
    """
    log_message(f"Commande: {c}", log_path=log_path)
    return client.send_command(c)

# ============================================================
# SECTION 4 : FONCTIONS DE TESTS D'INFRASTRUCTURE
# ============================================================
# Cette section contient toutes les fonctions qui vérifient que l'infrastructure
# réseau fonctionne correctement. Chaque test vérifie un aspect différent.

def test(description, resultat):
    """
    Enregistre et affiche le résultat d'un test
    
    PARAMÈTRES :
    - description : texte décrivant ce qui est testé
    - resultat : True si le test réussit, False s'il échoue
    
    FONCTIONNEMENT :
    1. Ajoute le résultat à la liste globale resultats
    2. Affiche le résultat avec la couleur appropriée
    3. Enregistre automatiquement dans les logs
    
    UTILITÉ : Centralise la gestion des résultats pour générer un résumé final
    """
    resultats.append((description, resultat))
    if resultat:
        ok(description)
    else:
        ko(description)

def ping_ok(output):
    """
    Analyse le résultat d'une commande ping pour déterminer si elle a réussi
    
    PARAMÈTRE :
    - output : texte retourné par la commande ping Cisco
    
    RETOURNE : True si le ping a réussi, False sinon
    
    LOGIQUE :
    - "!!" dans la sortie indique une réponse reçue (format Cisco)
    - "Success rate is 100" indique 100% de succès
    
    NOTE PÉDAGOGIQUE : Les équipements Cisco ont un format de sortie ping
    spécifique avec des indicateurs comme "!!" pour les réponses reçues
    """
    log_message(f"Résultat ping: {output.strip()}")
    return "!!" in output or "Success rate is 100" in output

def ping_bloque(output):
    """
    Analyse le résultat d'une commande ping pour déterminer si elle a été bloquée
    
    PARAMÈTRE :
    - output : texte retourné par la commande ping Cisco
    
    RETOURNE : True si le ping a été bloqué (ce qui est attendu dans certains cas)
    
    LOGIQUE :
    - "Success rate is 0" = 0% de paquets reçus
    - "0 packets received" = aucun paquet reçu
    - "unreachable" = destination inaccessible
    
    UTILITÉ : Vérifie que le filtrage inter-VLAN fonctionne correctement
    """
    log_message(f"Résultat ping (bloqué): {output.strip()}")
    return any(x in output for x in ["Success rate is 0", "0 packets received", "unreachable"])

# --- TEST 1 : CONNECTIVITÉ DE BASE ---
def test_connectivite(c):
    """
    Test 1 : Vérifie la connectivité de base du réseau
    
    OBJECTIF : S'assurer que toutes les passerelles sont joignables
    et que la connexion Internet fonctionne
    
    PARAMÈTRE : c = client de connexion au switch
    
    TESTS EFFECTUÉS :
    1. Ping des passerelles de chaque VLAN depuis le switch
    2. Ping du routeur inter-VLAN
    3. Ping Internet depuis le PC local
    
    NOTE PÉDAGOGIQUE : La connectivité de base est le fondement de tout réseau
    """
    titre("1. TEST CONNECTIVITE (PING)")
    
    # Crée la liste des cibles à pinger : les VLANs + le routeur
    cibles = list(VLANS.items()) + [("Routeur", ROUTEUR_IP)]
    
    # Test de chaque passerelle VLAN depuis le switch
    for nom, ip in cibles:
        test(f"Ping {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))
    
    # Test de connectivité Internet depuis le PC local
    try:
        result = subprocess.run(
            ["ping", "-c", "2", INTERNET_IP],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        succes = result.returncode == 0
    except Exception:
        succes = False
    test(f"Ping Internet ({INTERNET_IP}) depuis le PC", succes)

# --- TEST 2 : BLOCAGE INTER-VLAN (SÉCURITÉ) ---
def test_blocage_intervlan(c):
    """
    Test 2 : Vérifie que le filtrage inter-VLAN fonctionne correctement
    
    OBJECTIF : S'assurer que les VLANs ne peuvent pas communiquer entre eux
    (sauf le VLAN ADMIN qui doit pouvoir accéder à tout)
    
    PRINCIPE DE SÉCURITÉ :
    - Les VLANs ARTISAN et SONDES doivent être isolés
    - Le VLAN ADMIN doit pouvoir accéder à tous les autres VLANs
    - Architecture de sécurité classique en entreprise
    
    PARAMÈTRE : c = client de connexion au switch
    
    NOTE PÉDAGOGIQUE :
    - "source X.X.X.X" force l'interface source dans la commande ping
    - Les ACLs sont responsables de ce filtrage
    """
    titre("2. TEST BLOCAGE INTER-VLAN")
    
    # Récupère les adresses IP des passerelles de chaque VLAN
    gw = list(VLANS.values())
    src_sondes, src_artisan, src_admin = gw[2], gw[1], gw[0]  # Ordre : ADMIN, ARTISAN, SONDES

    # Test 1 : Depuis le VLAN SONDES, on ne doit PAS pouvoir joindre les autres VLANs
    info("Test SONDES → ADMIN/ARTISAN (doit échouer - sécurité)")
    test("SONDES → ADMIN (bloqué)",    ping_bloque(cmd(c, f"ping {src_admin}   source {src_sondes}  repeat 2")))
    test("SONDES → ARTISAN (bloqué)",  ping_bloque(cmd(c, f"ping {src_artisan} source {src_sondes}  repeat 2")))

    # Test 2 : Depuis le VLAN ARTISAN, on ne doit PAS pouvoir joindre les autres VLANs
    info("Test ARTISAN → ADMIN/SONDES (doit échouer - sécurité)")
    test("ARTISAN → ADMIN (bloqué)",   ping_bloque(cmd(c, f"ping {src_admin}   source {src_artisan} repeat 2")))
    test("ARTISAN → SONDES (bloqué)",  ping_bloque(cmd(c, f"ping {src_sondes}  source {src_artisan} repeat 2")))

    # Test 3 : Depuis le VLAN ADMIN, on DOIT pouvoir joindre tous les autres VLANs
    info("Test depuis VLAN ADMIN vers tous les VLAN (doit réussir - admin)")
    for nom, ip in list(VLANS.items())[1:]:  # Exclut ADMIN (index 0)
        test(f"ADMIN → {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))

# --- TEST 3 : VÉRIFICATION DES ACL (LISTES DE CONTRÔLE D'ACCÈS) ---
def test_acl(c):
    """
    Test 3 : Vérifie que les ACLs de sécurité sont bien présentes
    
    OBJECTIF : S'assurer que les règles de filtrage de trafic sont configurées
    
    CONCEPT PÉDAGOGIQUE :
    - ACL = Access Control List (liste de contrôle d'accès)
    - Les ACLs filtrent le trafic réseau selon des règles prédéfinies
    - Elles bloquent ou autorisent certains types de trafic
    - Essentielles pour la sécurité et l'isolation des VLANs
    
    PARAMÈTRE : c = client de connexion au switch
    
    NOTE : Si les ACLs ne sont pas présentes, le filtrage inter-VLAN ne fonctionnera pas
    """
    titre("3. VERIFICATION DES ACL")
    
    # Affiche toutes les ACLs configurées sur le switch
    output = cmd(c, "show ip access-lists")
    log_message(f"Liste ACL:\n{output.strip()}")
    
    # Vérifie que chaque ACL attendue est bien présente
    for acl in ACL_ATTENDUES:
        test(f"ACL présente : {acl}", acl in output)

# --- TEST 4 : VÉRIFICATION DU SERVICE DHCP ---
def test_dhcp(c):
    """
    Test 4 : Vérifie que le service DHCP fonctionne et distribue des adresses
    
    OBJECTIF : S'assurer que les équipements peuvent obtenir automatiquement
    des adresses IP dans chaque VLAN
    
    CONCEPT PÉDAGOGIQUE :
    - DHCP = Dynamic Host Configuration Protocol
    - Le switch agit comme serveur DHCP pour chaque VLAN
    - Les "bindings" sont les adresses IP déjà attribuées
    - Chaque VLAN doit avoir au moins une adresse distribuée
    
    PARAMÈTRE : c = client de connexion au switch
    
    LOGIQUE DE COMPTAGE :
    1. Pour chaque VLAN, on extrait le réseau (ex: 192.168.72 de 192.168.72.1)
    2. On compte combien d'adresses de ce réseau sont dans les bindings
    3. On vérifie qu'il y en a au moins une par VLAN
    """
    titre("4. VERIFICATION DHCP")
    
    # Affiche toutes les adresses IP déjà distribuées par le DHCP du switch
    output = cmd(c, "show ip dhcp binding")
    log_message(f"Bindings DHCP:\n{output.strip()}")
    
    # Pour chaque VLAN, on vérifie qu'il y a des adresses distribuées
    for vlan, gw in VLANS.items():
        # Extrait le réseau (ex: "192.168.72" à partir de "192.168.72.1")
        reseau = ".".join(gw.split(".")[:3])
        
        # Compte combien d'adresses IP de ce réseau sont distribuées
        # Le regex cherche : réseau.n'importe_quel_chiffre (ex: 192.168.72.45)
        nb = len(re.findall(reseau + r"\.\d+", output))
        
        test(f"DHCP {vlan} : {nb} adresse(s) distribuée(s)", nb > 0)

# --- TEST 5 : VÉRIFICATION DES CONFIGURATIONS VLAN ---
def test_vlan(c):
    """
    Test 5 : Vérifie que les VLANs sont correctement configurés sur le switch
    
    OBJECTIF : S'assurer que tous les VLANs nécessaires existent et sont actifs
    
    CONCEPT PÉDAGOGIQUE :
    - VLAN = Virtual Local Area Network
    - Les VLANs segmentent un réseau physique en réseaux logiques
    - Chaque VLAN a un numéro d'identification unique
    - "show vlan brief" affiche un résumé de tous les VLANs configurés
    
    PARAMÈTRE : c = client de connexion au switch
    
    TEST EFFECTUÉ :
    Pour chaque VLAN attendu, on vérifie :
    1. Que le numéro de VLAN est présent
    2. Que le nom du VLAN est correct
    3. (Implicitement) que le VLAN est actif
    """
    titre("5. VERIFICATION DES VLAN")
    
    # Affiche tous les VLANs configurés sur le switch
    output = cmd(c, "show vlan brief")
    log_message(f"VLANs:\n{output.strip()}")
    
    # Définit les VLANs qui doivent être présents (numéro → nom)
    vlans_attendus = {"255": "ARTISAN", "372": "ADMIN", "488": "SONDES"}
    
    # Vérifie chaque VLAN attendu
    for num, nom in vlans_attendus.items():
        test(f"VLAN {num} ({nom}) présent et actif", num in output and nom in output)

# ============================================================
# SECTION 5 : SAUVEGARDE AUTOMATIQUE DES CONFIGURATIONS
# ============================================================
# Cette section contient les fonctions pour sauvegarder automatiquement
# les configurations importantes du switch après les tests

def sauvegarder_configurations(c):
    """
    Sauvegarde automatique de toutes les configurations importantes du switch
    
    OBJECTIF : Créer une archive complète de l'état du switch après les tests
    
    CONFIGURATIONS SAUVEGARDÉES :
    - Configuration complète (running-config)
    - Configuration des VLANs
    - Règles ACL de sécurité
    - Adresses IP distribuées par DHCP
    - État des interfaces physiques
    - Table de routage
    - État du service NTP
    
    PARAMÈTRE : c = client de connexion au switch
    
    NOTE : Chaque configuration est sauvegardée dans un fichier séparé
    avec timestamp pour éviter les écrasements
    """
    titre("SAUVEGARDE AUTOMATIQUE DES CONFIGURATIONS")
    
    # Liste des configurations à sauvegarder avec (commande, suffixe_fichier, description)
    configs_a_sauvegarder = [
        ("show running-config", "running-config", "Configuration complète"),
        ("show vlan brief", "vlan-brief", "Configuration VLAN"),
        ("show ip access-lists", "acl", "Règles ACL"),
        ("show ip dhcp binding", "dhcp-binding", "Baux DHCP"),
        ("show interfaces status", "interfaces-status", "État interfaces"),
        ("show ip route", "ip-route", "Table de routage"),
        ("show ntp status", "ntp-status", "État NTP")
    ]
    
    for commande, suffixe, description in configs_a_sauvegarder:
        try:
            # Crée un fichier de log dédié pour cette configuration
            log_file_config = get_log_file(suffixe, simple=True)
            
            # Exécute la commande et récupère le résultat
            output = cmd(c, commande, log_path=log_file_config)
            
            # Sauvegarde le résultat complet dans le fichier dédié
            log_message(f"=== {description} ===\nCommande : {commande}\n\n{output}", log_path=log_file_config)
            
            ok(f"{description} sauvegardée")
            info(f"Fichier : {log_file_config}")
            
        except Exception as e:
            ko(f"Erreur lors de la sauvegarde {description} : {e}")

# ============================================================
# SECTION 6 : RÉSUMÉ FINAL DES TESTS
# ============================================================

def afficher_resume():
    """
    Affiche un résumé détaillé de tous les tests effectués
    
    FONCTIONNEMENT :
    1. Vérifie qu'il y a des tests à afficher
    2. Compte le nombre total de tests, réussis et échoués
    3. Affiche chaque test avec un symbole coloré (✔/✘)
    4. Affiche un résumé statistique final
    5. Enregistre le résumé dans les logs
    
    UTILITÉ :
    - Permet de voir rapidement l'état de santé de l'infrastructure
    - Facilite l'identification des problèmes
    - Donne une vue d'ensemble pour les rapports
    """
    if not resultats:
        return  # Si aucun test n'a été effectué
    
    titre("RÉSUMÉ DES TESTS D'INFRASTRUCTURE")
    
    # Calcul des statistiques
    total = len(resultats)
    reussis = sum(1 for _, r in resultats if r)
    echoues = total - reussis

    # Affichage détaillé de chaque test
    for desc, res in resultats:
        symbole = "\033[92m✔\033[0m" if res else "\033[91m✘\033[0m"
        print(f"  {symbole}  {desc}")

    # Affichage du résumé statistique avec couleur adaptée
    couleur = "\033[92m" if echoues == 0 else "\033[91m"
    print(f"\n{couleur}  Résultat : {reussis}/{total} tests réussis  ({echoues} échoués)\033[0m")
    
    # Enregistrement du résumé dans les logs
    log_message(f"RÉSUMÉ FINAL : {reussis}/{total} réussis, {echoues} échoués")

# ============================================================
# SECTION 7 : PROGRAMME PRINCIPAL - EXÉCUTION AUTOMATIQUE
# ============================================================

if __name__ == "__main__":
    """
    Point d'entrée principal du programme - Version Améliorée
    
    DÉROULEMENT AUTOMATIQUE :
    1. Création des répertoires de logs
    2. Affichage de l'en-tête avec informations
    3. Saisie sécurisée des identifiants
    4. Connexion au switch avec tentatives multiples
    5. Exécution automatique de TOUS les tests d'infrastructure
    6. Sauvegarde automatique de toutes les configurations
    7. Affichage du résumé détaillé des résultats
    8. Déconnexion propre du switch
    
    NOUVEAUTÉS DE CETTE VERSION :
    - Logging séparé (tests vs configurations)
    - Sauvegarde automatique des configurations
    - Résumé détaillé avec statistiques
    - Commentaires pédagogiques améliorés
    """
    
    # 1. Création des répertoires de logs s'ils n'existent pas
    os.makedirs(LOG_DIR_TESTS, exist_ok=True)
    os.makedirs(LOG_DIR_CONF,  exist_ok=True)
    
    # 2. Affichage de l'en-tête avec informations de la session
    print(f"\n\033[95m{'='*60}\n   TEST INFRASTRUCTURE - PROJET MARAIS'R'SENSE - VERSION AMÉLIORÉE\n"
          f"   Switch : {SWITCH_HOST}\n   Logs tests : {LOG_DIR_TESTS}\n"
          f"   Logs configs : {LOG_DIR_CONF}\n{'='*60}\033[0m")
    
    # 3. Saisie sécurisée des identifiants de connexion
    username = input("Nom d'utilisateur : ")
    password = getpass.getpass("Mot de passe : ")
    log_message(f"Début des tests sur {SWITCH_HOST} avec utilisateur : {username}")

    # 4. Connexion au switch avec 3 essais maximum
    client = connecter(username, password)
    if not client:
        ko("Impossible de se connecter au switch - Arrêt du programme")
        exit(1)
    
    ok("Connexion réussie au switch")

    # 5. Exécution séquentielle de TOUS les tests d'infrastructure
    tests_a_executer = [
        test_connectivite,      # Test 1: Connectivité de base
        test_blocage_intervlan,  # Test 2: Blocage inter-VLAN (sécurité)
        test_acl,               # Test 3: Configuration des ACLs
        test_dhcp,              # Test 4: Serveur DHCP
        test_vlan               # Test 5: Configuration des VLANs
    ]
    
    titre("DÉBUT DES TESTS D'INFRASTRUCTURE AUTOMATIQUES")
    for test_function in tests_a_executer:
        try:
            test_function(client)
        except Exception as e:
            ko(f"Erreur lors du test {test_function.__name__} : {e}")

    # 6. Sauvegarde automatique de toutes les configurations importantes
    sauvegarder_configurations(client)

    # 7. Affichage du résumé détaillé des résultats
    afficher_resume()

    # 8. Déconnexion propre du switch
    client.disconnect()
    ok("Déconnexion réussie du switch")
    
    # Message final avec emplacement des logs
    log_file_final = get_current_log_file()
    print(f"\n\033[93m{'='*60}\n   SESSION TERMINÉE AVEC SUCCÈS\n"
          f"   Log principal : {log_file_final}\n"
          f"   Configurations sauvegardées dans : {LOG_DIR_CONF}\n"
          f"   Tests sauvegardés dans : {LOG_DIR_TESTS}\n{'='*60}\033[0m")
    
    log_message("Fin de la session - Tests et sauvegarde terminés")