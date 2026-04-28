#!/usr/bin/env python3
"""
Script de test d'infrastructure pour switch Cisco
Auteur: Projet Marais'R'Sense
Description: Script complet avec menu interactif pour tester la configuration
             d'un switch Cisco et afficher/sauvegarder les configurations.
             
             BUT PÉDAGOGIQUE : Ce script permet de vérifier automatiquement que
             l'infrastructure réseau est correctement configurée.
             
             CONCEPTS CLÉS À EXPLIQUER :
             - VLAN : Segmentation logique du réseau
             - ACL : Listes de contrôle d'accès pour filtrer le trafic
             - DHCP : Service d'attribution automatique d'adresses IP
             - Inter-VLAN : Communication entre différents VLAN
             - SSH : Connexion sécurisée pour administrer le switch
"""

# Import des bibliothèques nécessaires
from netmiko import ConnectHandler    # Bibliothèque pour se connecter à des équipements réseau
import re                              # Expressions régulières pour analyser les résultats
import getpass                         # Pour saisir le mot de passe sans l'afficher
import subprocess                      # Pour exécuter des commandes système (ping local)
from datetime import datetime          # Pour horodater les logs
import os                              # Pour gérer les fichiers et répertoires

# NOTE PÉDAGOGIQUE : Netmiko est une bibliothèque Python très utilisée en réseau
# qui simplifie la connexion SSH aux équipements Cisco, Juniper, etc.

# ============================================================
# SECTION 1 : CONFIGURATION DES PARAMÈTRES
# ============================================================
# Cette section contient tous les paramètres configurables du script
# C'est ici qu'on modifierait les valeurs pour adapter le script à un autre environnement

# Paramètres de connexion au switch
SWITCH_HOST   = "switch_marais"  # Nom d'hôte ou adresse IP du switch à tester
SWITCH_PORT   = 22               # Port SSH (22 par défaut)

# Répertoires de stockage des logs
LOG_DIR_TESTS = os.path.join("logs", "tests")    # Pour les résultats des tests d'infrastructure
LOG_DIR_CONF  = os.path.join("logs", "configs")  # Pour les configurations affichées/sauvegardées

# Création automatique des répertoires s'ils n'existent pas
# exist_ok=True évite une erreur si le répertoire existe déjà
os.makedirs(LOG_DIR_TESTS, exist_ok=True)
os.makedirs(LOG_DIR_CONF,  exist_ok=True)

# Définition des VLANs et de leurs passerelles (gateways)
# FORMAT : "Nom du VLAN (numéro)" : "adresse IP de la passerelle"
# NOTE : Les VLANs permettent de segmenter un réseau physique en plusieurs réseaux logiques
# Chaque VLAN a sa propre plage d'adresses IP et sa propre passerelle
VLANS = {
    "ADMIN (372)":   "192.168.72.1",   # VLAN 372 pour l'administration
    "ARTISAN (255)": "192.168.55.1",   # VLAN 255 pour les artisans
    "SONDES (488)":  "192.168.88.1",   # VLAN 488 pour les capteurs/sondes
}

# Adresses IP importantes pour les tests
ROUTEUR_IP    = "10.0.0.1"    # IP du routeur qui connecte les VLANs entre eux
INTERNET_IP   = "8.8.8.8"     # DNS public de Google pour tester la connectivité Internet

# ACLs (Access Control Lists) qui doivent être présentes sur le switch
# Les ACLs sont des règles de filtrage qui contrôlent quel trafic est autorisé ou bloqué
ACL_ATTENDUES = ["ACL_SONDES", "ACL_ARTISAN"]  # Noms des ACLs à vérifier

# ============================================================
# SECTION 2 : SYSTÈME DE LOGGING ET AFFICHAGE
# ============================================================
# Cette section gère tout ce qui concerne l'enregistrement des actions
# et l'affichage coloré dans le terminal pour une meilleure lisibilité

def get_log_file(suffix="tests", simple=False):
    """
    Génère un nom de fichier de log avec timestamp pour éviter les écrasements
    
    PARAMÈTRES :
    - suffix : suffixe ajouté au nom du fichier (ex: "tests", "running-config")
    - simple : False = logs/tests/ (tests d'infra), True = logs/configs/ (configurations)
    
    EXPLICATION :
    Le timestamp permet d'avoir des fichiers uniques et de savoir quand chaque
    action a été effectuée. C'est crucial pour le dépannage et l'audit.
    
    EXEMPLES DE NOMS :
    - simple=False : logs/tests/test_switch_2024-04-28_14-30-25_tests.log
    - simple=True  : logs/configs/2024-04-28_14-30-25_running-config.log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # Format AAAA-MM-JJ_HH-MM-SS
    if simple:
        return os.path.join(LOG_DIR_CONF, f"{timestamp}_{suffix}.log")
    return os.path.join(LOG_DIR_TESTS, f"test_switch_{timestamp}_{suffix}.log")

# Variables globales pour la gestion du fichier de log principal
# NOTE : On utilise un pattern "lazy initialization" - le fichier n'est créé
# que lors de la première écriture pour éviter de créer des fichiers vides
log_file = None          # Contiendra le chemin du fichier de log principal
log_initialized = False  # Indique si le fichier de log a déjà été initialisé

def get_current_log_file():
    """
    Retourne le fichier de log actuel, le crée si nécessaire (pattern singleton)
    
    PRINCIPE : Cette fonction garantit qu'il n'y a qu'un seul fichier de log
    par session d'exécution du script. Si le fichier n'existe pas encore,
    il est créé automatiquement.
    
    UTILITÉ : Permet à toutes les fonctions du script d'écrire dans le même
    fichier de log sans avoir à passer le nom en paramètre à chaque fois.
    """
    global log_file, log_initialized  # On utilise les variables globales
    if not log_initialized:           # Si c'est la première fois qu'on appelle cette fonction
        log_file = get_log_file("tests")  # On crée le fichier de log
        log_initialized = True           # On marque qu'il est maintenant initialisé
    return log_file

def log_message(message, log_path=None):
    """
    Écrit un message horodaté dans un fichier de log
    
    PARAMÈTRES :
    - message : le texte à enregistrer
    - log_path : chemin du fichier (None = utilise le fichier principal)
    
    FONCTIONNEMENT :
    1. Si log_path est None, on utilise le fichier de log principal de la session
    2. On ajoute un timestamp (heure seulement) pour savoir quand l'action a eu lieu
    3. On ouvre le fichier en mode "append" (ajout à la fin)
    4. On écrit le message avec un formatage clair
    
    NOTE : encoding="utf-8" est important pour gérer les caractères accentués
    """
    if log_path is None:
        log_path = get_current_log_file()  # Utilise le fichier principal par défaut
    timestamp = datetime.now().strftime("%H:%M:%S")  # Heure format HH:MM:SS
    with open(log_path, "a", encoding="utf-8") as f:  # "a" = append (ajout à la fin)
        f.write(f"[{timestamp}] {message}\n\n")  # Double saut de ligne pour la lisibilité

# Fonctions d'affichage coloré avec logging automatique
# Ces fonctions combinent deux actions : afficher dans le terminal ET logger
# Les codes ANSI (\033[XXm) permettent de colorer le texte dans le terminal

ok    = lambda t: (log_message(f"✔ {t}"),  print(f"\033[92m  [OK]  {t}\033[0m"))
    # Vert (92) pour un test réussi
ko    = lambda t: (log_message(f"✘ {t}"),  print(f"\033[91m  [KO]  {t}\033[0m"))
    # Rouge (91) pour un test échoué
info  = lambda t: (log_message(f"ℹ {t}"),  print(f"\033[94m  [--]  {t}\033[0m"))
    # Bleu (94) pour une information
titre = lambda t: (log_message(f"=== {t} ==="), print(f"\n\033[93m{'='*60}\n  {t}\n{'='*60}\033[0m"))
    # Jaune (93) pour un titre de section
    # \033[0m réinitialise la couleur pour ne pas affecter le texte suivant

# NOTE PÉDAGOGIQUE : L'utilisation de lambda ici permet de définir des fonctions
# courtes en une seule ligne. C'est pratique pour des actions répétitives simples.

# ============================================================
# CONNEXION SSH
# ============================================================

def connecter(user, password):
    """
    Établit la connexion SSH au switch Cisco avec gestion des erreurs et tentatives multiples
    
    PARAMÈTRES :
    - user : nom d'utilisateur pour la connexion SSH
    - password : mot de passe pour la connexion SSH
    
    FONCTIONNEMENT :
    1. On essaie de se connecter jusqu'à 3 fois maximum
    2. Si la connexion échoue, on demande à nouveau les identifiants
    3. On utilise Netmiko qui simplifie la connexion aux équipements Cisco
    4. En cas d'échec total, on retourne None
    
    NOTE PÉDAGOGIQUE :
    - device_type='cisco_ios' indique à Netmiko qu'on parle à un équipement Cisco IOS
    - Le port 22 est le port SSH standard
    - La gestion des erreurs est cruciale en administration réseau
    """
    max_essais = 3  # On autorise 3 tentatives de connexion
    for essai in range(max_essais):
        try:
            log_message(f"Tentative de connexion {essai + 1}/{max_essais} avec : {user}")
            # ConnectionHandler est la fonction principale de Netmiko pour se connecter
            return ConnectHandler(
                device_type='cisco_ios',  # Type d'équipement Cisco
                host=SWITCH_HOST,         # Adresse du switch
                username=user,             # Nom d'utilisateur
                password=password,         # Mot de passe
                port=SWITCH_PORT           # Port SSH (22 par défaut)
            )
        except Exception as e:
            # Si c'est la dernière tentative, on abandonne
            if essai == max_essais - 1:
                ko(f"Connexion SSH échouée : {e}")
                return None
            # Sinon on demande à nouveau les identifiants pour réessayer
            print(f"\033[91m  Échec {essai + 1}/{max_essais} - Réessayez...\033[0m")
            user     = input("Nom d'utilisateur : ")
            password = getpass.getpass("Mot de passe : ")  # Masque le mot de passe à l'écran

def cmd(client, c, log_path=None):
    """
    Exécute une commande sur le switch et enregistre l'action dans les logs
    
    PARAMÈTRES :
    - client : objet de connexion Netmiko au switch
    - c : commande Cisco à exécuter (ex: "show vlan brief")
    - log_path : None = log principal, chemin = fichier dédié
    
    FONCTIONNEMENT :
    1. On enregistre d'abord la commande dans les logs
    2. On envoie la commande au switch via Netmiko
    3. On retourne le résultat de la commande
    
    EXEMPLES DE COMMANDES :
    - "show vlan brief" : affiche les VLANs configurés
    - "ping 192.168.1.1" : teste la connectivité
    - "show running-config" : affiche la configuration complète
    
    NOTE : send_command() est la méthode principale de Netmiko pour exécuter des commandes
    """
    log_message(f"Commande: {c}", log_path=log_path)
    return client.send_command(c)  # Envoie la commande et retourne le résultat

# ============================================================
# SECTION 3 : FONCTIONS DE TESTS D'INFRASTRUCTURE
# ============================================================
# Cette section contient toutes les fonctions qui vérifient que l'infrastructure
# réseau fonctionne correctement. Chaque test vérifie un aspect différent du réseau.

# Liste globale pour stocker les résultats de tous les tests
# FORMAT : [(description_du_test, resultat_booléen), ...]
# Exemple : [("Ping VLAN ADMIN", True), ("Ping VLAN ARTISAN", False)]
resultats = []

def test(description, resultat):
    """
    Enregistre et affiche le résultat d'un test
    
    PARAMÈTRES :
    - description : texte décrivant ce qui est testé
    - resultat : True si le test réussit, False s'il échoue
    
    FONCTIONNEMENT :
    1. On ajoute le résultat à la liste globale resultats
    2. On affiche le résultat avec la couleur appropriée (vert/rouge)
    3. On enregistre automatiquement dans les logs
    
    UTILITÉ : Cette fonction centralise la gestion des résultats de tests
    pour pouvoir générer un résumé final à la fin.
    """
    resultats.append((description, resultat))  # Stocke pour le résumé final
    if resultat:
        ok(description)  # Affiche en vert + log
    else:
        ko(description)  # Affiche en rouge + log

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
    
    UTILITÉ : Cette fonction est utilisée pour vérifier que le filtrage
    inter-VLAN fonctionne correctement (les pings doivent être bloqués)
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
    3. Ping Internet depuis le PC local (vérifie la connectivité sortante)
    
    NOTE PÉDAGOGIQUE : La connectivité de base est le fondement de tout réseau.
    Si ces tests échouent, les autres tests n'auront pas de sens.
    """
    titre("1. TEST CONNECTIVITE (PING)")
    
    # Crée la liste des cibles à pinger : les VLANs + le routeur
    cibles = list(VLANS.items()) + [("Routeur", ROUTEUR_IP)]
    
    # Test de chaque passerelle VLAN depuis le switch
    for nom, ip in cibles:
        test(f"Ping {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))
    
    # Test de connectivité Internet depuis le PC local (pas depuis le switch)
    # On utilise subprocess pour exécuter la commande ping locale du système
    try:
        result = subprocess.run(
            ["ping", "-c", "2", INTERNET_IP],  # ping -c 2 = 2 paquets sous Linux
            stdout=subprocess.DEVNULL,  # Cache la sortie
            stderr=subprocess.DEVNULL,  # Cache les erreurs
            timeout=5  # Timeout de 5 secondes
        )
        succes = result.returncode == 0  # returncode 0 = succès
    except Exception:
        succes = False  # En cas d'erreur (timeout, etc.)
    test(f"Ping Internet ({INTERNET_IP}) depuis le PC", succes)

# --- TEST 2 : BLOCAGE INTER-VLAN (SÉCURITÉ) ---
def test_blocage_intervlan(c):
    """
    Test 2 : Vérifie que le filtrage inter-VLAN fonctionne correctement
    
    OBJECTIF : S'assurer que les VLANs ne peuvent pas communiquer entre eux
    (sauf le VLAN ADMIN qui doit pouvoir accéder à tout)
    
    PRINCIPE DE SÉCURITÉ :
    - Les VLANs ARTISAN et SONDES doivent être isolés les uns des autres
    - Le VLAN ADMIN doit pouvoir accéder à tous les autres VLANs
    - C'est une architecture de sécurité classique en entreprise
    
    PARAMÈTRE : c = client de connexion au switch
    
    NOTE PÉDAGOGIQUE :
    - "source X.X.X.X" dans la commande ping Cisco force l'interface source
    - Les ACLs (Access Control Lists) sont responsables de ce filtrage
    - Ce test vérifie que la politique de sécurité est respectée
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
    # [1:] pour exclure le VLAN ADMIN lui-même de la liste
    for nom, ip in list(VLANS.items())[1:]:
        test(f"ADMIN → {nom} ({ip})", ping_ok(cmd(c, f"ping {ip} repeat 2")))

# --- TEST 3 : VÉRIFICATION DES ACL (LISTES DE CONTRÔLE D'ACCÈS) ---
def test_acl(c):
    """
    Test 3 : Vérifie que les ACLs de sécurité sont bien présentes
    
    OBJECTIF : S'assurer que les règles de filtrage de trafic sont configurées
    
    CONCEPT PÉDAGOGIQUE :
    - ACL = Access Control List (liste de contrôle d'accès)
    - Les ACLs sont des règles qui filtrent le trafic réseau
    - Elles peuvent autoriser ou bloquer des types de trafic spécifiques
    - Dans notre cas, elles bloquent la communication inter-VLAN
    
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
# SECTION 4 : AFFICHAGE ET SAUVEGARDE DES CONFIGURATIONS
# ============================================================
# Cette section contient les fonctions pour afficher les configurations
# du switch et les sauvegarder dans des fichiers dédiés.
# 
# NOTE : Ces fonctions n'écrivent PAS dans le log principal de tests.
# Elles créent leurs propres fichiers de log dans logs/configs/

def afficher_et_sauvegarder(c, commande, suffixe_log, label):
    """
    Fonction générique pour afficher et sauvegarder une configuration du switch
    
    PARAMÈTRES :
    - c : client de connexion au switch
    - commande : commande Cisco à exécuter (ex: "show running-config")
    - suffixe_log : suffixe pour le nom du fichier de sauvegarde
    - label : titre affiché dans le terminal
    
    FONCTIONNEMENT :
    1. Crée un fichier de log dédié avec timestamp
    2. Exécute la commande sur le switch
    3. Affiche le résultat dans le terminal (en couleur)
    4. Sauvegarde le résultat dans le fichier dédié
    5. Indique où le fichier a été sauvegardé
    
    NOTE IMPORTANTE : Cette fonction n'utilise PAS le log principal de tests.
    Elle crée des fichiers séparés dans logs/configs/ pour garder les configurations
    organisées et facilement consultables.
    """
    lf = get_log_file(suffixe_log, simple=True)  # Crée un fichier dédié
    
    # Affiche un titre clair dans le terminal
    print(f"\n\033[93m{'='*60}\n  AFFICHAGE : {label}\n{'='*60}\033[0m")
    
    # Exécute la commande et récupère le résultat
    output = cmd(c, commande, log_path=lf)
    
    # Affiche le résultat en cyan pour une meilleure lisibilité
    print(f"\033[96m{output}\033[0m")
    
    # Sauvegarde le résultat complet dans le fichier dédié
    log_message(f"=== {label} ===\nCommande : {commande}\n\n{output}", log_path=lf)
    
    # Informe l'utilisateur où le fichier a été sauvegardé
    print(f"\033[93m  → Sauvegardé dans : {lf}\033[0m")

# Fonctions spécifiques pour chaque type de configuration
# Chaque fonction appelle afficher_et_sauvegarder avec les bons paramètres

def show_running_config(c):
    """
    Affiche et sauvegarde la configuration complète du switch
    
    CONCEPT PÉDAGOGIQUE :
    - La running-config est la configuration actuellement active
    - Elle contient TOUTES les commandes configurées sur le switch
    - C'est l'équivalent d'un "état complet" de l'équipement
    """
    afficher_et_sauvegarder(c, "show running-config", "running-config", "Running Config")

def show_vlan(c):
    """
    Affiche et sauvegarde la configuration des VLANs
    
    CONCEPT PÉDAGOGIQUE :
    - Montre tous les VLANs créés et leurs ports associés
    - Permet de vérifier que les VLANs sont correctement configurés
    """
    afficher_et_sauvegarder(c, "show vlan brief", "vlan-brief", "VLAN Brief")

def show_acl(c):
    """
    Affiche et sauvegarde les listes de contrôle d'accès
    
    CONCEPT PÉDAGOGIQUE :
    - Montre les règles de filtrage configurées
    - Essentiel pour comprendre la politique de sécurité
    """
    afficher_et_sauvegarder(c, "show ip access-lists", "acl", "ACL (show ip access-lists)")

def show_dhcp_binding(c):
    """
    Affiche et sauvegarde les baux DHCP
    
    CONCEPT PÉDAGOGIQUE :
    - Montre quelles adresses IP ont été distribuées
    - Permet de vérifier que le DHCP fonctionne
    """
    afficher_et_sauvegarder(c, "show ip dhcp binding", "dhcp-binding", "DHCP Binding")

def show_interfaces(c):
    """
    Affiche et sauvegarde l'état des interfaces
    
    CONCEPT PÉDAGOGIQUE :
    - Montre l'état de chaque port (up/down, vitesse, VLAN, etc.)
    - Permet de vérifier que les interfaces physiques fonctionnent
    """
    afficher_et_sauvegarder(c, "show interfaces status", "interfaces-status", "Interfaces Status")

def show_ip_route(c):
    """
    Affiche et sauvegarde la table de routage
    
    CONCEPT PÉDAGOGIQUE :
    - Montre comment le switch sait atteindre les différents réseaux
    - Essentiel pour comprendre la connectivité inter-VLAN
    """
    afficher_et_sauvegarder(c, "show ip route", "ip-route", "Table de routage (show ip route)")

def show_ntp(c):
    """
    Affiche et sauvegarde l'état du service NTP
    
    CONCEPT PÉDAGOGIQUE :
    - NTP = Network Time Protocol (synchronisation de l'heure)
    - Important pour avoir des logs synchronisés
    """
    afficher_et_sauvegarder(c, "show ntp status", "ntp-status", "NTP Status")

# ============================================================
# SECTION 5 : RÉSUMÉ FINAL DES TESTS
# ============================================================
# Cette section génère un résumé de tous les tests effectués
# pour avoir une vue d'ensemble rapide de l'état de l'infrastructure

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
    
    NOTE PÉDAGOGIQUE :
    Cette fonction est essentielle pour l'audit et le suivi
    de l'état de l'infrastructure réseau.
    """
    if not resultats:
        return  # Si aucun test n'a été effectué, on ne fait rien
    
    titre("RÉSUMÉ DES TESTS")
    
    # Calcul des statistiques
    total = len(resultats)
    reussis = sum(1 for _, r in resultats if r)  # Compte les True
    echoues = total - reussis  # Le reste sont des échecs

    # Affichage détaillé de chaque test
    for desc, res in resultats:
        symbole = "\033[92m✔\033[0m" if res else "\033[91m✘\033[0m"
        print(f"  {symbole}  {desc}")

    # Affichage du résumé statistique avec couleur adaptée
    couleur = "\033[92m" if echoues == 0 else "\033[91m"  # Vert si tout réussi, rouge sinon
    print(f"\n{couleur}  Résultat : {reussis}/{total} tests réussis  ({echoues} échoués)\033[0m")
    
    # Enregistrement du résumé dans les logs
    log_message(f"RÉSUMÉ : {reussis}/{total} réussis, {echoues} échoués")

# ============================================================
# SECTION 6 : INTERFACE UTILISATEUR (MENUS)
# ============================================================
# Cette section contient tout ce qui permet à l'utilisateur d'interagir
# avec le script : menus, choix, navigation, etc.
# 
# CONCEPT PÉDAGOGIQUE :
# Une bonne interface utilisateur est essentielle pour un outil d'administration
# réseau. Elle doit être intuitive, claire et permettre d'accéder facilement
# à toutes les fonctionnalités du script.

# Définition des menus sous forme de listes de tuples
# FORMAT : ("texte affiché", fonction_à_appeler)
# Cette structure permet d'ajouter facilement de nouvelles options

MENU_TESTS = [
    ("Connectivité (ping gateways + Internet)",  test_connectivite),
    # Test de base : vérifie que tout est joignable
    
    ("Blocage inter-VLAN",                        test_blocage_intervlan),
    # Test de sécurité : vérifie l'isolation des VLANs
    
    ("Vérification des ACL",                      test_acl),
    # Vérifie les règles de filtrage réseau
    
    ("Vérification DHCP (bindings)",              test_dhcp),
    # Vérifie que les adresses IP sont distribuées
    
    ("Vérification des VLANs",                    test_vlan),
    # Vérifie que les VLANs sont configurés
]

MENU_SHOW = [
    ("Running-config",           show_running_config),
    # Configuration complète et active du switch
    
    ("VLAN brief",               show_vlan),
    # Résumé des VLANs configurés
    
    ("ACL (ip access-lists)",    show_acl),
    # Règles de filtrage de trafic
    
    ("DHCP binding",             show_dhcp_binding),
    # Adresses IP distribuées par le DHCP
    
    ("Interfaces status",        show_interfaces),
    # État des ports physiques du switch
    
    ("Table de routage",         show_ip_route),
    # Comment le switch route le trafic
    
    ("NTP status",               show_ntp),
    # Synchronisation de l'heure
]

def afficher_menu(titre_menu, options, lettre_retour="r"):
    """
    Affiche un menu interactif et gère les choix de l'utilisateur
    
    PARAMÈTRES :
    - titre_menu : titre affiché en haut du menu
    - options : liste de tuples (texte, fonction) comme MENU_TESTS ou MENU_SHOW
    - lettre_retour : lettre pour revenir au menu précédent ("r" par défaut)
    
    RETOURNE :
    - None si l'utilisateur veut revenir en arrière
    - "all" si l'utilisateur veut tout sélectionner
    - un nombre (index) si l'utilisateur choisit une option spécifique
    
    FONCTIONNEMENT :
    1. Affiche le menu avec numérotation automatique
    2. Gère les entrées utilisateur avec validation
    3. Gère les interruptions (Ctrl+C)
    4. Boucle jusqu'à obtenir un choix valide
    
    NOTE PÉDAGOGIQUE :
    Cette fonction rend l'interface utilisateur robuste et conviviale.
    La gestion des erreurs et des interruptions est essentielle en production.
    """
    # Affichage du titre et des options
    print(f"\n\033[93m{'='*60}\n  {titre_menu}\n{'='*60}\033[0m")
    for i, (label, _) in enumerate(options, 1):  # Commence à 1 pour l'affichage
        print(f"  \033[97m[{i:2d}]\033[0m  {label}")  # :2d pour aligner les nombres
    print(f"  \033[97m[ a]\033[0m  Tout sélectionner")
    print(f"  \033[97m[{lettre_retour:>2}]\033[0m  Retour au menu principal\n")

    # Boucle de gestion des entrées utilisateur
    while True:
        try:
            choix = input("  Votre choix : ").strip().lower()  # strip() enlève les espaces, lower() ignore la casse
            
            # Cas 1 : Retour au menu précédent
            if choix == lettre_retour:
                return None
                
            # Cas 2 : Tout sélectionner
            if choix == "a":
                return "all"
                
            # Cas 3 : Choix numérique d'une option
            if choix.isdigit():
                idx = int(choix) - 1  # Convertit en index 0-based
                if 0 <= idx < len(options):  # Vérifie que l'index est valide
                    return idx
                    
            # Si on arrive ici, le choix est invalide
            print("  \033[91m Choix invalide, réessayez.\033[0m")
            
        except KeyboardInterrupt:
            # Gestion de l'interruption par Ctrl+C
            print("\n\033[93m  Interruption détectée - Retour au menu principal\033[0m")
            return None

def menu_tests(client):
    """
    Sous-menu pour choisir et exécuter les tests d'infrastructure
    
    PARAMÈTRE : client = connexion SSH au switch
    
    FONCTIONNEMENT :
    1. Affiche le menu des tests disponibles
    2. Permet de choisir un test spécifique ou tous
    3. Exécute le(s) test(s) choisi(s)
    4. Affiche le résumé des résultats
    5. Permet de revenir au menu principal
    
    NOTE PÉDAGOGIQUE :
    Ce menu permet de tester l'infrastructure de manière ciblée
    ou complète, selon les besoins du diagnostic.
    """
    while True:
        choix = afficher_menu("MENU — TESTS D'INFRASTRUCTURE", MENU_TESTS)
        
        if choix is None:
            # L'utilisateur veut revenir au menu principal
            break
            
        elif choix == "all":
            # Exécute TOUS les tests disponibles
            for _, fn in MENU_TESTS:
                fn(client)  # Exécute la fonction de test
            afficher_resume()  # Affiche le résumé de tous les tests
            
        else:
            # Exécute un test spécifique
            label, fn = MENU_TESTS[choix]  # Récupère le texte et la fonction
            fn(client)  # Exécute le test choisi
            afficher_resume()  # Affiche le résumé (même pour un seul test)

def menu_show(client):
    """
    Sous-menu pour afficher et sauvegarder les configurations du switch
    
    PARAMÈTRE : client = connexion SSH au switch
    
    FONCTIONNEMENT :
    1. Affiche le menu des configurations disponibles
    2. Permet de choisir une configuration spécifique ou toutes
    3. Exécute la commande show correspondante
    4. Sauvegarde automatiquement le résultat dans un fichier
    5. Permet de revenir au menu principal
    
    NOTE PÉDAGOGIQUE :
    Ce menu permet d'inspecter l'état du switch et de conserver
    des copies des configurations pour analyse ou audit.
    """
    while True:
        choix = afficher_menu("MENU — AFFICHER / SAUVEGARDER UNE CONFIG", MENU_SHOW)
        
        if choix is None:
            # L'utilisateur veut revenir au menu principal
            break
            
        elif choix == "all":
            # Affiche et sauvegarde TOUTES les configurations
            for _, fn in MENU_SHOW:
                fn(client)  # Exécute chaque fonction d'affichage
                
        else:
            # Affiche et sauvegarde une configuration spécifique
            _, fn = MENU_SHOW[choix]  # Récupère juste la fonction
            fn(client)  # Exécute la fonction choisie

def menu_principal(client):
    """
    Menu principal du programme - point d'entrée de l'interface utilisateur
    
    PARAMÈTRE : client = connexion SSH au switch
    
    FONCTIONNEMENT :
    1. Affiche le menu principal avec les options principales
    2. Gère les choix de l'utilisateur
    3. Redirige vers les sous-menus appropriés
    4. Gère la sortie propre du programme
    5. Gère les interruptions (Ctrl+C)
    
    OPTIONS :
    1. Tests d'infrastructure → menu_tests()
    2. Afficher configurations → menu_show()
    q. Quitter → fermeture propre
    
    NOTE PÉDAGOGIQUE :
    Ce menu est la "porte d'entrée" de l'application.
    Il doit être simple, clair et permettre d'accéder à toutes les fonctionnalités.
    """
    while True:
        # Affichage du menu principal avec couleurs
        print(f"\n\033[95m{'='*60}")  # Violet pour le menu principal
        print(f"   MENU PRINCIPAL — MARAIS'R'SENSE")
        print(f"   Switch : {SWITCH_HOST}")  # Affiche le switch connecté
        print(f"{'='*60}\033[0m")
        print("  \033[97m[1]\033[0m  Tests d'infrastructure")
        print("  \033[97m[2]\033[0m  Afficher / Sauvegarder une configuration")
        print("  \033[97m[q]\033[0m  Quitter\n")

        try:
            choix = input("  Votre choix : ").strip().lower()
            
            if choix == "1":
                menu_tests(client)  # Vers les tests d'infra
            elif choix == "2":
                menu_show(client)   # Vers l'affichage des configs
            elif choix == "q":
                print("\n\033[93m  Au revoir !\033[0m\n")
                break  # Sort de la boucle, termine le programme
            else:
                print("  \033[91m Choix invalide.\033[0m")
                
        except KeyboardInterrupt:
            # Gestion propre de l'interruption
            print("\n\033[93m  Interruption détectée - Arrêt du programme\033[0m")
            break

# ============================================================
# SECTION 7 : PROGRAMME PRINCIPAL
# ============================================================
# Cette section contient le point d'entrée du programme (main)
# Elle orchestre toute l'exécution : connexion, menus, nettoyage
# 
# CONCEPT PÉDAGOGIQUE :
# Le programme principal suit le pattern "setup → main loop → cleanup"
# qui est une pratique standard en programmation pour garantir
# une exécution propre et une gestion correcte des ressources.

if __name__ == "__main__":
    """
    Point d'entrée principal du programme
    
    FONCTIONNEMENT COMPLET :
    1. Affiche un écran de démarrage avec les informations
    2. Demande les identifiants de connexion
    3. Établit la connexion SSH au switch
    4. Lance le menu principal
    5. Gère la déconnexion propre et le nettoyage
    
    GESTION DES ERREURS :
    - Si la connexion échoue, le programme se termine
    - Le bloc finally garantit la déconnexion même en cas d'erreur
    - Les logs sont correctement fermés et sauvegardés
    
    NOTE PÉDAGOGIQUE :
    __name__ == "__main__" est le pattern standard en Python pour
    identifier le point d'entrée d'un script. Le bloc try/finally
    garantit que les ressources (connexion SSH) sont correctement
    libérées même si une erreur se produit.
    """
    # Écran de démarrage avec informations sur l'environnement
    print(f"\n\033[95m{'='*60}\n   TEST INFRASTRUCTURE — PROJET MARAIS'R'SENSE\n"
          f"   Switch  : {SWITCH_HOST}\n"
          f"   Tests   : {LOG_DIR_TESTS}/\n"
          f"   Configs : {LOG_DIR_CONF}/\n"
          f"{'='*60}\033[0m")
    
    # Enregistrement du démarrage dans les logs
    log_message(f"Démarrage du script — switch : {SWITCH_HOST}")

    # Demande des identifiants de connexion
    username = input("Nom d'utilisateur : ")
    password = getpass.getpass("Mot de passe : ")  # Masque le mot de passe
    log_message(f"Tentative de connexion avec : {username}")

    # Tentative de connexion au switch
    client = connecter(username, password)
    if not client:
        # Si la connexion échoue, on quitte avec un code d'erreur
        exit(1)  # Code d'erreur 1 = échec de connexion
        
    ok("Connexion SSH établie avec succès")

    # Lancement du menu principal dans un bloc try/finally
    try:
        menu_principal(client)  # Boucle principale de l'interface
    finally:
        # NETTOYAGE : Exécuté même si une erreur se produit dans le menu
        client.disconnect()  # Ferme la connexion SSH proprement
        
        # Affiche l'état des logs à la fin
        if log_initialized:
            print(f"\033[94m  Log principal sauvegardé : {log_file}\033[0m\n")
        else:
            print("\033[94m  Aucun test exécuté - pas de log créé\033[0m\n")