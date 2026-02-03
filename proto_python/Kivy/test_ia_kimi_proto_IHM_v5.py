
# -*- coding: utf-8 -*-
# IHM UNIHIKER : écran "Mesure" + pages "Seuils" et "Config IP"
# Affichage en mode paysage 320 x 240

from unihiker import GUI
import time

# On considère l'écran en paysage : largeur 320, hauteur 240
SCREEN_W = 320
SCREEN_H = 240
OFFSCREEN_X = 500      # position hors-écran pour "cacher" un objet

gui = GUI()            # création de l'objet graphique

# --------------------------------------------------------------------
# Création de TOUS les objets graphiques une seule fois
# puis on les déplace pour afficher / cacher les pages.
# --------------------------------------------------------------------

# ---------- Page MESURE ----------
bg_mesure = gui.fill_rect(
    x=0, y=0, w=SCREEN_W, h=SCREEN_H, color="lime green"
)   # fond vert

txt_couleur = gui.draw_text(
    text="Couleur de fond",
    x=5, y=5,
    font_size=16,
    color="black",
    angle=-90      # texte tourné paysage
)

txt_date = gui.draw_text(
    text="Date et heure",
    x=SCREEN_W - 110, y=5,
    font_size=16,
    color="black",
    angle=-90
)

txt_mesure = gui.draw_text(
    text="Mesure",
    x=SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=40,
    color="black",
    angle=-90
)


# Boutons bas de page
def show_ip():
    show_page("ip")

def show_seuils():
    show_page("seuils")

btn_config_ip = gui.add_button(
    x=5, y=SCREEN_H - 45,
    w=110, h=40,
    text="Config IP",
    origin="top_left",
    onclick=show_ip
)

btn_seuils = gui.add_button(
    x=SCREEN_W - 115, y=SCREEN_H - 45,
    w=110, h=40,
    text="Seuils",
    origin="top_left",
    onclick=show_seuils
)

# ---------- Page SEUILS ----------
bg_seuils = gui.fill_rect(
    x=OFFSCREEN_X, y=0, w=SCREEN_W, h=SCREEN_H, color="#DDDDDD"
)

txt_seuils = gui.draw_text(
    text="Configuration des seuils",
    x=OFFSCREEN_X + SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=22,
    color="black"
)

def back_from_seuils():
    show_page("mesure")

btn_retour_seuils = gui.add_button(
    x=OFFSCREEN_X + SCREEN_W - 100, y=SCREEN_H - 45,
    w=90, h=40,
    text="Retour",
    origin="top_left",
    onclick=back_from_seuils
)

# ---------- Page CONFIG IP ----------
bg_ip = gui.fill_rect(
    x=OFFSCREEN_X, y=0, w=SCREEN_W, h=SCREEN_H, color="#DDDDDD"
)

txt_ip = gui.draw_text(
    text="Adresse MAC / IP",
    x=OFFSCREEN_X + SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=22,
    color="black"
)

def back_from_ip():
    show_page("mesure")

btn_retour_ip = gui.add_button(
    x=OFFSCREEN_X + SCREEN_W - 100, y=SCREEN_H - 45,
    w=90, h=40,
    text="Retour",
    origin="top_left",
    onclick=back_from_ip
)

# --------------------------------------------------------------------
# Fonctions d'affichage des pages
# --------------------------------------------------------------------

def page_mesure_on():
    # fond vert visible
    bg_mesure.config(x=0, y=0)
    txt_couleur.config(x=5, y=5)
    txt_date.config(x=SCREEN_W - 150, y=5)
    txt_mesure.config(x=SCREEN_W // 2, y=SCREEN_H // 2)

    btn_config_ip.config(x=5, y=SCREEN_H - 45, state="normal")
    btn_seuils.config(x=SCREEN_W - 115, y=SCREEN_H - 45, state="normal")

def page_mesure_off():
    bg_mesure.config(x=OFFSCREEN_X)
    txt_couleur.config(x=OFFSCREEN_X)
    txt_date.config(x=OFFSCREEN_X)
    txt_mesure.config(x=OFFSCREEN_X)
    btn_config_ip.config(x=OFFSCREEN_X, state="disabled")
    btn_seuils.config(x=OFFSCREEN_X, state="disabled")

def page_seuils_on():
    bg_seuils.config(x=0, y=0)
    txt_seuils.config(x=SCREEN_W // 2, y=SCREEN_H // 2)
    btn_retour_seuils.config(x=SCREEN_W - 100, y=SCREEN_H - 45, state="normal")

def page_seuils_off():
    bg_seuils.config(x=OFFSCREEN_X)
    txt_seuils.config(x=OFFSCREEN_X)
    btn_retour_seuils.config(x=OFFSCREEN_X, state="disabled")

def page_ip_on():
    bg_ip.config(x=0, y=0)
    txt_ip.config(x=SCREEN_W // 2, y=SCREEN_H // 2)
    btn_retour_ip.config(x=SCREEN_W - 100, y=SCREEN_H - 45, state="normal")

def page_ip_off():
    bg_ip.config(x=OFFSCREEN_X)
    txt_ip.config(x=OFFSCREEN_X)
    btn_retour_ip.config(x=OFFSCREEN_X, state="disabled")

def show_page(name):
    """Change de page : 'mesure', 'seuils' ou 'ip'."""
    if name == "mesure":
        page_seuils_off()
        page_ip_off()
        page_mesure_on()
    elif name == "seuils":
        page_mesure_off()
        page_ip_off()
        page_seuils_on()
    elif name == "ip":
        page_mesure_off()
        page_seuils_off()
        page_ip_on()

# Afficher la page principale au démarrage
show_page("mesure")

# Boucle principale (évite que le programme se termine)
while True:
    time.sleep(0.1)
