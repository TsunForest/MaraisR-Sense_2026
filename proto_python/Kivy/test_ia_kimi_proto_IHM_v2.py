# -*- coding: utf-8 -*-
# IHM UNIHIKER en mode "paysage" : écran Mesure + pages Seuils et Config IP

from unihiker import GUI
import time

# Pour un affichage paysage on considère 320 x 240
SCREEN_W = 320
SCREEN_H = 240
OFFSCREEN_X = 500      # position hors-écran

gui = GUI()

# --------------------------------------------------------------------
# PAGE MESURE
# --------------------------------------------------------------------
bg_mesure = gui.fill_rect(
    x=0, y=0, w=SCREEN_W, h=SCREEN_H, color="lime green"
)

txt_couleur = gui.draw_text(
    text="Couleur de fond",
    x=5, y=5,
    font_size=18,
    color="black"
)

txt_date = gui.draw_text(
    text="Date et heure",
    x=SCREEN_W - 150, y=5,
    font_size=18,
    color="black"
)

txt_mesure = gui.draw_text(
    text="Mesure",
    x=SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=48,
    color="black"
)

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

# --------------------------------------------------------------------
# PAGE SEUILS
# --------------------------------------------------------------------
bg_seuils = gui.fill_rect(
    x=OFFSCREEN_X, y=0, w=SCREEN_W, h=SCREEN_H, color="#DDDDDD"
)

txt_seuils = gui.draw_text(
    text="Configuration des seuils",
    x=OFFSCREEN_X + SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=24,
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

# --------------------------------------------------------------------
# PAGE CONFIG IP
# --------------------------------------------------------------------
bg_ip = gui.fill_rect(
    x=OFFSCREEN_X, y=0, w=SCREEN_W, h=SCREEN_H, color="#DDDDDD"
)

txt_ip = gui.draw_text(
    text="Adresse MAC / IP",
    x=OFFSCREEN_X + SCREEN_W // 2, y=SCREEN_H // 2,
    w=SCREEN_W,
    origin="center",
    font_size=24,
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
# GESTION DES PAGES
# --------------------------------------------------------------------
def page_mesure_on():
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

# Affichage initial
show_page("mesure")

while True:
    time.sleep(0.1)
