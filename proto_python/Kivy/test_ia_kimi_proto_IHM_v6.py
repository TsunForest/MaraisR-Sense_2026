# -*- coding: utf-8 -*-
# IHM UNIHIKER : écran "Mesure" + pages "Seuils" et "Config IP"
# Affichage physique en portrait 240x320, mais tout le texte est tourné (mode paysage)

from unihiker import GUI
import time

# Dimension de l'écran UNIHIKER : 240 x 320 pixels
SCREEN_W = 240
SCREEN_H = 320
OFFSCREEN_X = 400      # position hors-écran pour "cacher" un objet

gui = GUI()            # création de l'objet graphique

# --------------------------------------------------------------------
# Petite fabrique de boutons "maison" (rectangle + texte tourné)
# --------------------------------------------------------------------
def make_button(x, y, w, h, text, onclick):
    # fond du bouton
    rect = gui.fill_round_rect(
        x=x, y=y, w=w, h=h, r=5,
        color="#CCCCCC",
        onclick=onclick
    )
    # texte du bouton (pivoté) centré dans le rectangle
    label = gui.draw_text(
        text=text,
        x=x + w // 2,
        y=y + h // 2,
        origin="center",
        font_size=16,
        angle=-90,          # texte paysage
        onclick=onclick
    )
    return rect, label

# --------------------------------------------------------------------
# Création de TOUS les objets graphiques une seule fois
# puis on les déplace pour afficher / cacher les pages.
# --------------------------------------------------------------------

# ---------- Page MESURE ----------
bg_mesure = gui.fill_rect(
    x=0, y=0, w=SCREEN_W, h=SCREEN_H, color="lime green"
)

txt_couleur = gui.draw_text(
    text="Couleur de fond",
    x=5, y=5,
    font_size=16,
    color="black",
    angle=-90
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

# Boutons bas de page (fabriqués maison)
def show_ip():
    show_page("ip")

def show_seuils():
    show_page("seuils")

btn_config_ip_rect, btn_config_ip_txt = make_button(
    x=5, y=SCREEN_H - 45,
    w=90, h=40,
    text="Config IP",
    onclick=show_ip
)

btn_seuils_rect, btn_seuils_txt = make_button(
    x=SCREEN_W - 95, y=SCREEN_H - 45,
    w=90, h=40,
    text="Seuils",
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
    color="black",
    angle=-90
)

def back_from_seuils():
    show_page("mesure")

btn_retour_seuils_rect, btn_retour_seuils_txt = make_button(
    x=OFFSCREEN_X + SCREEN_W - 95, y=SCREEN_H - 45,
    w=90, h=40,
    text="Retour",
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
    color="black",
    angle=-90
)

def back_from_ip():
    show_page("mesure")

btn_retour_ip_rect, btn_retour_ip_txt = make_button(
    x=OFFSCREEN_X + SCREEN_W - 95, y=SCREEN_H - 45,
    w=90, h=40,
    text="Retour",
    onclick=back_from_ip
)

# --------------------------------------------------------------------
# Fonctions d'affichage des pages
# --------------------------------------------------------------------

def page_mesure_on():
    bg_mesure.config(x=0, y=0)
    txt_couleur.config(x=5, y=5)
    txt_date.config(x=SCREEN_W - 110, y=5)
    txt_mesure.config(x=SCREEN_W // 2, y=SCREEN_H // 2)

    btn_config_ip_rect.config(x=5, y=SCREEN_H - 45)
    btn_config_ip_txt.config(x=5 + 45, y=SCREEN_H - 45 + 20)

    btn_seuils_rect.config(x=SCREEN_W - 95, y=SCREEN_H - 45)
    btn_seuils_txt.config(x=SCREEN_W - 95 + 45, y=SCREEN_H - 45 + 20)

def page_mesure_off():
    bg_mesure.config(x=OFFSCREEN_X)
    txt_couleur.config(x=OFFSCREEN_X)
    txt_date.config(x=OFFSCREEN_X)
    txt_mesure.config(x=OFFSCREEN_X)

    btn_config_ip_rect.config(x=OFFSCREEN_X)
    btn_config_ip_txt.config(x=OFFSCREEN_X)

    btn_seuils_rect.config(x=OFFSCREEN_X)
    btn_seuils_txt.config(x=OFFSCREEN_X)

def page_seuils_on():
    bg_seuils.config(x=0, y=0)
    txt_seuils.config(x=SCREEN_W // 2, y=SCREEN_H // 2)

    btn_retour_seuils_rect.config(x=SCREEN_W - 95, y=SCREEN_H - 45)
    btn_retour_seuils_txt.config(x=SCREEN_W - 95 + 45, y=SCREEN_H - 45 + 20)

def page_seuils_off():
    bg_seuils.config(x=OFFSCREEN_X)
    txt_seuils.config(x=OFFSCREEN_X)
    btn_retour_seuils_rect.config(x=OFFSCREEN_X)
    btn_retour_seuils_txt.config(x=OFFSCREEN_X)

def page_ip_on():
    bg_ip.config(x=0, y=0)
    txt_ip.config(x=SCREEN_W // 2, y=SCREEN_H // 2)

    btn_retour_ip_rect.config(x=SCREEN_W - 95, y=SCREEN_H - 45)
    btn_retour_ip_txt.config(x=SCREEN_W - 95 + 45, y=SCREEN_H - 45 + 20)

def page_ip_off():
    bg_ip.config(x=OFFSCREEN_X)
    txt_ip.config(x=OFFSCREEN_X)
    btn_retour_ip_rect.config(x=OFFSCREEN_X)
    btn_retour_ip_txt.config(x=OFFSCREEN_X)

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
