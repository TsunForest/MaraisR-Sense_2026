# -*- coding: utf-8 -*-
from unihiker import GUI
import time
import socket
import uuid
from datetime import datetime
import os

# Rotation de l'écran de 90° via la commande système
os.system('xrandr -o left')  # Rotation de 90° vers la gauche

# Initialisation du GUI en mode portrait (240x320)
gui = GUI()

# Variables globales
current_page = "mesure"
background_color = "#00FF00"  # Vert par défaut
seuil_min = 20
seuil_max = 80

# Éléments GUI à mettre à jour
elements = {}

# Fonction pour obtenir l'adresse MAC
def get_mac_address():
    mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
                    for ele in range(0,8*6,8)][::-1])
    return mac.upper()

# Fonction pour obtenir l'adresse IP
def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "Non connecté"

# Fonction pour effacer l'écran
def clear_screen():
    global elements
    for element in elements.values():
        try:
            element.config(state='hidden')
        except:
            pass
    elements = {}

# PAGE 1: Adresse MAC / IP
def show_page_config_ip():
    global current_page, elements
    current_page = "config_ip"
    clear_screen()
    
    # Fond gris
    elements['bg'] = gui.fill_rect(x=0, y=0, w=240, h=320, color="#D3D3D3")
    
    # Zone centrale grise claire
    elements['center_box'] = gui.fill_rect(x=15, y=60, w=210, h=200, color="#C0C0C0")
    
    # Titre centré
    elements['title'] = gui.draw_text(text="Adresse MAC / IP", x=120, y=100, 
                                      font_size=18, color="#000000", origin="center")
    
    # Affichage MAC
    mac = get_mac_address()
    elements['mac_label'] = gui.draw_text(text="MAC:", x=30, y=140, 
                                          font_size=12, color="#000000")
    elements['mac_value'] = gui.draw_text(text=mac, x=30, y=160, 
                                          font_size=10, color="#000000")
    
    # Affichage IP
    ip = get_ip_address()
    elements['ip_label'] = gui.draw_text(text="IP:", x=30, y=200, 
                                         font_size=12, color="#000000")
    elements['ip_value'] = gui.draw_text(text=ip, x=30, y=220, 
                                         font_size=10, color="#000000")
    
    # Bouton Retour
    elements['btn_retour'] = gui.add_button(text="Retour", x=155, y=280, 
                                            w=70, h=30, onclick=show_page_mesure)

# PAGE 2: Mesure (Page principale)
def show_page_mesure():
    global current_page, elements, background_color
    current_page = "mesure"
    clear_screen()
    
    # Fond de couleur (vert par défaut)
    elements['bg'] = gui.fill_rect(x=0, y=0, w=240, h=320, color=background_color)
    
    # Titre "Mesure" au centre
    elements['title'] = gui.draw_text(text="Mesure", x=120, y=150, 
                                      font_size=45, color="#000000", origin="center")
    
    # Bouton "Couleur de fond" en haut à gauche
    elements['btn_couleur'] = gui.add_button(text="Couleur de fond", x=10, y=10, 
                                             w=110, h=30, onclick=change_couleur)
    
    # Texte "Date et heure" en haut à droite
    elements['date_label'] = gui.draw_text(text="Date et heure", x=130, y=10, 
                                           font_size=11, color="#000000")
    elements['datetime'] = gui.draw_text(text="", x=130, y=28, 
                                         font_size=9, color="#000000")
    
    # Bouton "Config IP" en bas à gauche
    elements['btn_config_ip'] = gui.add_button(text="Config IP", x=10, y=280, 
                                               w=90, h=30, onclick=show_page_config_ip)
    
    # Bouton "Seuils" en bas à droite
    elements['btn_seuils'] = gui.add_button(text="Seuils", x=140, y=280, 
                                            w=90, h=30, onclick=show_page_seuils)

def update_datetime():
    if current_page == "mesure" and 'datetime' in elements:
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y\n%H:%M:%S")
        try:
            elements['datetime'].config(text=date_str)
        except:
            pass

# PAGE 3: Configuration des seuils
def show_page_seuils():
    global current_page, elements
    current_page = "seuils"
    clear_screen()
    
    # Fond gris
    elements['bg'] = gui.fill_rect(x=0, y=0, w=240, h=320, color="#D3D3D3")
    
    # Zone centrale grise claire
    elements['center_box'] = gui.fill_rect(x=15, y=60, w=210, h=200, color="#C0C0C0")
    
    # Titre centré
    elements['title'] = gui.draw_text(text="Configuration des seuils", x=120, y=90, 
                                      font_size=15, color="#000000", origin="center")
    
    # Affichage des seuils
    elements['seuil_min_label'] = gui.draw_text(text=f"Seuil min: {seuil_min}", 
                                                x=30, y=130, font_size=13, color="#000000")
    elements['seuil_max_label'] = gui.draw_text(text=f"Seuil max: {seuil_max}", 
                                                x=30, y=160, font_size=13, color="#000000")
    
    # Boutons pour modifier les seuils
    # Seuil min
    elements['label_min'] = gui.draw_text(text="Min:", x=30, y=195, 
                                          font_size=11, color="#000000")
    elements['btn_min_moins'] = gui.add_button(text="-", x=65, y=190, 
                                               w=30, h=30, onclick=lambda: adjust_seuil('min', -5))
    elements['btn_min_plus'] = gui.add_button(text="+", x=100, y=190, 
                                              w=30, h=30, onclick=lambda: adjust_seuil('min', 5))
    
    # Seuil max
    elements['label_max'] = gui.draw_text(text="Max:", x=145, y=195, 
                                          font_size=11, color="#000000")
    elements['btn_max_moins'] = gui.add_button(text="-", x=180, y=190, 
                                               w=30, h=30, onclick=lambda: adjust_seuil('max', -5))
    elements['btn_max_plus'] = gui.add_button(text="+", x=150, y=225, 
                                              w=30, h=30, onclick=lambda: adjust_seuil('max', 5))
    
    # Bouton Retour
    elements['btn_retour'] = gui.add_button(text="Retour", x=155, y=280, 
                                            w=70, h=30, onclick=show_page_mesure)

def adjust_seuil(type_seuil, delta):
    global seuil_min, seuil_max
    if type_seuil == 'min':
        seuil_min = max(0, min(100, seuil_min + delta))
    else:
        seuil_max = max(0, min(100, seuil_max + delta))
    show_page_seuils()

# Fonction pour changer la couleur de fond
def change_couleur():
    global background_color
    colors = ["#00FF00", "#FF0000", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF"]
    current_index = colors.index(background_color) if background_color in colors else 0
    background_color = colors[(current_index + 1) % len(colors)]
    show_page_mesure()

# Démarrage sur la page Mesure
show_page_mesure()

# Boucle principale
try:
    while True:
        update_datetime()
        time.sleep(0.5)
except KeyboardInterrupt:
    # Remettre l'écran en position normale à la sortie
    os.system('xrandr -o normal')
    print("Programme arrêté")
