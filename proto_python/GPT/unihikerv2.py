#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from datetime import datetime
import socket
import uuid
import os
import subprocess

# --- Couleurs (reprises des captures) ---
GREEN_BG = "#33FF33"
BTN_BG = "#9E9990"
OUTER_GRAY = "#7F7F7F"
SCREEN_GRAY = "#888888"
PANEL_GRAY = "#C0C0C0"
TEXT = "#000000"

# --- Dimensions de reference (paysage pour UNIHIKER) ---
BASE_W = 320
BASE_H = 240


def set_landscape_orientation():
    """
    Tente de forcer l'orientation paysage sur UNIHIKER.
    """
    try:
        # Méthode 1: Utiliser xrandr si disponible
        subprocess.run(['xrandr', '--output', 'DSI-1', '--rotate', 'right'], 
                      check=False, capture_output=True)
    except:
        pass
    
    try:
        # Méthode 2: Configuration via framebuffer
        with open('/sys/class/graphics/fb0/rotate', 'w') as f:
            f.write('1')  # 1 = rotation 90° pour paysage
    except:
        pass


def get_local_ip() -> str:
    """
    Récupère l'IP locale la plus probable (sans dépendances externes).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Ne contacte pas réellement Internet, sert juste à choisir l'interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "IP inconnue"


def get_mac() -> str:
    """
    Récupère l'adresse MAC (format XX:XX:XX:XX:XX:XX).
    """
    node = uuid.getnode()
    mac = ":".join(f"{(node >> (i * 8)) & 0xFF:02X}" for i in range(5, -1, -1))
    return mac


class App(tk.Tk):
    def __init__(self, force_w=BASE_W, force_h=BASE_H, fullscreen=True):
        super().__init__()

        # Forcer l'orientation paysage au démarrage
        set_landscape_orientation()

        self.title("IHM UNIHIKER")
        self.configure(bg=OUTER_GRAY)

        # Sur UNIHIKER, plein écran est généralement ce qu'on veut
        self.fullscreen = fullscreen
        self.base_w = force_w
        self.base_h = force_h
        if fullscreen:
            self.overrideredirect(True)
            self.geometry(f"{force_w}x{force_h}+0+0")
        else:
            self.geometry(f"{force_w}x{force_h}")

        # Forcer la taille de la fenêtre
        self.resizable(False, False)
        self.update_idletasks()  # S'assurer que la géométrie est appliquée

        # Quitter proprement (utile sur PC / debug)
        self.bind("<Escape>", lambda e: self.quit_app())
        self.bind("<q>", lambda e: self.quit_app())

        # Conteneur des écrans
        self.container = tk.Frame(self, bg=OUTER_GRAY)
        self.container.pack(fill="both", expand=True)

        self.screens = {}
        for ScreenCls in (HomeScreen, ConfigIPScreen, ThresholdsScreen):
            scr = ScreenCls(self.container, self)
            self.screens[ScreenCls.__name__] = scr
            scr.place(x=0, y=0, relwidth=1, relheight=1)

        self.show("HomeScreen")

    def quit_app(self):
        try:
            self.destroy()
        except Exception:
            pass

    def show(self, name: str):
        scr = self.screens[name]
        scr.tkraise()
        if hasattr(scr, "on_show"):
            scr.on_show()


class HomeScreen(tk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, bg=OUTER_GRAY)
        self.app = app

        # Cadre intérieur vert (comme une bordure grise autour)
        self.inner = tk.Frame(self, bg=GREEN_BG)
        self.inner.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.98, relheight=0.96)

        self.lbl_time = tk.Label(self.inner, text="", bg=GREEN_BG, fg=TEXT)
        self.lbl_time.place(relx=0.98, rely=0.05, anchor="ne")

        self.lbl_center = tk.Label(self.inner, text="Mesure", bg=GREEN_BG, fg=TEXT)
        self.lbl_center.place(relx=0.5, rely=0.5, anchor="center")

        # Boutons bas
        self.btn_ip = tk.Button(
            self.inner, text="Config IP", bg=BTN_BG, fg=TEXT,
            activebackground=BTN_BG, relief="flat", command=lambda: self.app.show("ConfigIPScreen")
        )
        self.btn_seuils = tk.Button(
            self.inner, text="Seuils", bg=BTN_BG, fg=TEXT,
            activebackground=BTN_BG, relief="flat", command=lambda: self.app.show("ThresholdsScreen")
        )

        # Responsive
        self.bind("<Configure>", self.on_resize)
        self._tick()

    def on_resize(self, _evt=None):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        # Taille utile = intérieur
        iw = int(w * 0.98)
        ih = int(h * 0.96)

        scale = min(iw / self.app.base_w, ih / self.app.base_h)

        font_top = max(10, int(16 * scale))
        font_mid = max(18, int(60 * scale))
        font_btn = max(10, int(14 * scale))

        self.lbl_time.configure(font=("DejaVu Sans", font_top))
        self.lbl_center.configure(font=("DejaVu Sans", font_mid))

        btn_w = int(iw * 0.23)
        btn_h = int(ih * 0.13)
        pad = int(ih * 0.02)

        self.btn_ip.configure(font=("DejaVu Sans", font_btn))
        self.btn_seuils.configure(font=("DejaVu Sans", font_btn))

        self.btn_ip.place(x=pad, y=ih - btn_h - pad, width=btn_w, height=btn_h)
        self.btn_seuils.place(x=iw - btn_w - pad, y=ih - btn_h - pad, width=btn_w, height=btn_h)

    def _tick(self):
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.lbl_time.config(text=now)
        self.after(250, self._tick)


class ConfigIPScreen(tk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, bg=SCREEN_GRAY)
        self.app = app

        self.panel = tk.Frame(self, bg=PANEL_GRAY)
        self.panel.place(relx=0.5, rely=0.48, anchor="center", relwidth=0.86, relheight=0.62)

        self.title = tk.Label(self.panel, text="Adresse MAC / IP", bg=PANEL_GRAY, fg=TEXT)
        self.title.place(relx=0.5, rely=0.30, anchor="center")

        self.details = tk.Label(self.panel, text="", bg=PANEL_GRAY, fg=TEXT, justify="center")
        self.details.place(relx=0.5, rely=0.62, anchor="center")

        self.btn_back = tk.Button(
            self, text="Retour", bg=BTN_BG, fg=TEXT,
            activebackground=BTN_BG, relief="flat", command=lambda: self.app.show("HomeScreen")
        )

        self.bind("<Configure>", self.on_resize)

    def on_show(self):
        mac = get_mac()
        ip = get_local_ip()
        self.details.config(text=f"MAC : {mac}\nIP : {ip}")

    def on_resize(self, _evt=None):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        scale = min(w / self.app.base_w, h / self.app.base_h)

        font_title = max(12, int(16 * scale))
        font_details = max(10, int(14 * scale))
        font_btn = max(10, int(14 * scale))

        self.title.configure(font=("DejaVu Sans", font_title))
        self.details.configure(font=("DejaVu Sans", font_details))

        btn_w = int(w * 0.20)
        btn_h = int(h * 0.13)
        pad = int(h * 0.04)
        self.btn_back.configure(font=("DejaVu Sans", font_btn))
        self.btn_back.place(x=w - btn_w - pad, y=h - btn_h - pad, width=btn_w, height=btn_h)


class ThresholdsScreen(tk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, bg=SCREEN_GRAY)
        self.app = app

        self.panel = tk.Frame(self, bg=PANEL_GRAY)
        self.panel.place(relx=0.5, rely=0.48, anchor="center", relwidth=0.86, relheight=0.62)

        self.title = tk.Label(self.panel, text="Configuration des seuils", bg=PANEL_GRAY, fg=TEXT)
        self.title.place(relx=0.5, rely=0.5, anchor="center")

        self.btn_back = tk.Button(
            self, text="Retour", bg=BTN_BG, fg=TEXT,
            activebackground=BTN_BG, relief="flat", command=lambda: self.app.show("HomeScreen")
        )

        self.bind("<Configure>", self.on_resize)

    def on_resize(self, _evt=None):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        scale = min(w / self.app.base_w, h / self.app.base_h)

        font_title = max(12, int(16 * scale))
        font_btn = max(10, int(14 * scale))

        self.title.configure(font=("DejaVu Sans", font_title))

        btn_w = int(w * 0.20)
        btn_h = int(h * 0.13)
        pad = int(h * 0.04)
        self.btn_back.configure(font=("DejaVu Sans", font_btn))
        self.btn_back.place(x=w - btn_w - pad, y=h - btn_h - pad, width=btn_w, height=btn_h)


if __name__ == "__main__":
    # Valeurs "paysage" pour UNIHIKER (320x240)
    app = App(force_w=BASE_W, force_h=BASE_H, fullscreen=True)
    app.mainloop()
