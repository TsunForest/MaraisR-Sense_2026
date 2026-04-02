# View/IHM.py
"""
Vue MVC — logique uniquement, tout le layout est dans ihm.kv.

Propriétés Kivy exposées (bindées automatiquement dans ihm.kv) :
    app.seuil_vert    NumericProperty  — seuil vert (µg/m³)
    app.seuil_orange  NumericProperty  — seuil orange (µg/m³)

Callbacks à brancher depuis le Controller AVANT ihm.run() :
    ihm.on_btn_a = callable()
    ihm.on_btn_b = callable()

API publique thread-safe :
    ihm.navigate_to(name)
    ihm.update_pm10(pm10: float)
    ihm.update_seuils(seuil_vert, seuil_orange)
    ihm.show_popup(titre, message, duration=4)
    ihm.hide_popup()
    ihm.current_screen  → str
"""

# ── Config Kivy AVANT tout import kivy ───────────────────────────────────────
from kivy.config import Config
Config.set('graphics', 'width',      '240')
Config.set('graphics', 'height',     '320')
Config.set('graphics', 'rotation',   '90')
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'show_cursor','0')
Config.set('kivy',     'keyboard_mode', 'system')

import kivy
kivy.require('2.1.0')

import os
import time
import threading
import socket
import uuid
from datetime import datetime

from kivy.app                import App
from kivy.clock              import Clock
from kivy.core.window        import Window
from kivy.lang               import Builder
from kivy.properties         import (BooleanProperty, ListProperty,
                                     NumericProperty, StringProperty)
from kivy.uix.floatlayout    import FloatLayout
from kivy.uix.boxlayout      import BoxLayout
from kivy.uix.screenmanager  import ScreenManager, Screen, NoTransition

# ── Constantes ────────────────────────────────────────────────────────────────
GPIO_POLL_INTERVAL = 0.05
DEBOUNCE_DELAY     = 0.35

# Seuils par défaut (µg/m³) — remplacés si reçus via MQTT
SEUIL_VERT_DEFAUT   = 25.0
SEUIL_ORANGE_DEFAUT = 50.0

C_VERT   = [0.13, 0.86, 0.13, 1]
C_ORANGE = [1.00, 0.60, 0.00, 1]
C_ROUGE  = [0.95, 0.15, 0.15, 1]
C_DARK   = [0.35, 0.35, 0.35, 1]


# ── Helpers réseau ────────────────────────────────────────────────────────────
def _get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Non disponible"


def _get_mac():
    try:
        n = uuid.getnode()
        return ':'.join(f'{(n >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1))
    except Exception:
        return "Non disponible"


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 1 – Accueil
# ══════════════════════════════════════════════════════════════════════════════
class AccueilScreen(Screen):
    # Propriétés bindées dans ihm.kv
    pm10_color = ListProperty(C_DARK)
    val_text   = StringProperty('-- µg/m³')
    state_text = StringProperty('En attente de la première mesure…')
    time_text  = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_pm10(self, pm10: float):
        """Met à jour la valeur et la couleur selon les seuils actifs."""
        app = App.get_running_app()
        sv  = app.seuil_vert
        so  = app.seuil_orange

        self.val_text = f'{pm10:.1f} µg/m³'
        if pm10 < sv:
            self.pm10_color = C_VERT
            self.state_text = f'Bonne qualité  (< {sv:.0f} µg/m³)'
        elif pm10 < so:
            self.pm10_color = C_ORANGE
            self.state_text = f'Qualité moyenne  ({sv:.0f}–{so:.0f} µg/m³)'
        else:
            self.pm10_color = C_ROUGE
            self.state_text = f'Mauvaise qualité  (≥ {so:.0f} µg/m³) !'


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 2 – Seuils  (bouton A)
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsScreen(Screen):
    # Pas de propriétés propres : les labels du KV utilisent app.seuil_vert
    # et app.seuil_orange directement → mise à jour automatique.
    pass


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 3 – Réseau  (bouton B)
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):
    ip_text  = StringProperty('…')
    mac_text = StringProperty('…')

    def on_enter(self, *args):
        self.ip_text  = '…'
        self.mac_text = '…'
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        ip, mac = _get_ip(), _get_mac()
        Clock.schedule_once(lambda dt: self._set(ip, mac), 0)

    def _set(self, ip, mac):
        self.ip_text  = ip
        self.mac_text = mac


# ══════════════════════════════════════════════════════════════════════════════
# POPUP overlay
# ══════════════════════════════════════════════════════════════════════════════
class PopupOverlay(BoxLayout):
    is_visible = BooleanProperty(False)
    titre      = StringProperty('')
    message    = StringProperty('')

    def show(self, titre: str, message: str):
        self.titre      = titre
        self.message    = message
        self.is_visible = True

    def hide(self):
        self.is_visible = False


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION — View pure
# ══════════════════════════════════════════════════════════════════════════════
class IHM(App):
    # Seuils accessibles dans le KV via app.seuil_vert / app.seuil_orange
    seuil_vert   = NumericProperty(SEUIL_VERT_DEFAUT)
    seuil_orange = NumericProperty(SEUIL_ORANGE_DEFAUT)

    # Callbacks branchés par le Controller
    on_btn_a = None
    on_btn_b = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._popup_event  = None
        self._last_pm10    = None
        self._btn_a        = None
        self._btn_b        = None
        self._prev_a       = False
        self._prev_b       = False
        self._last_press_a = 0.0
        self._last_press_b = 0.0
        Window.clearcolor  = (0.82, 0.82, 0.82, 1)

    # ── Propriété lecture seule ───────────────────────────────────────────────
    @property
    def current_screen(self) -> str:
        return self.sm.current if hasattr(self, 'sm') else 'accueil'

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        # Chargement explicite du KV (robuste quel que soit le répertoire courant)
        kv_path = os.path.join(os.path.dirname(__file__), 'ihm.kv')
        Builder.load_file(kv_path)

        # Écrans
        self.sm = ScreenManager(transition=NoTransition())
        self.s_accueil = AccueilScreen(name='accueil')
        self.s_seuils  = SeuilsScreen(name='seuils')
        self.s_reseau  = ReseauScreen(name='reseau')
        for s in (self.s_accueil, self.s_seuils, self.s_reseau):
            self.sm.add_widget(s)

        # Popup overlay
        self._popup = PopupOverlay(
            size_hint=(0.88, None),
            height=90,
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        # FloatLayout racine
        root = FloatLayout()
        root.add_widget(self.sm)
        root.add_widget(self._popup)

        # Boutons (thread principal obligatoire pour pinpong)
        self._init_buttons()
        Clock.schedule_interval(self._poll_buttons, GPIO_POLL_INTERVAL)
        Window.bind(on_key_down=self._on_key)

        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return root

    # ── Boutons UNIHIKER ──────────────────────────────────────────────────────
    def _init_buttons(self):
        try:
            from pinpong.board import Board
            from pinpong.extension.unihiker import button_a, button_b
            Board().begin()
            self._btn_a = button_a
            self._btn_b = button_b
            print("Boutons A/B UNIHIKER initialisés")
        except ImportError:
            print("pinpong absent — mode PC, touches [a] et [b]")
        except Exception as e:
            print(f"Erreur init boutons : {e}")

    def _poll_buttons(self, dt):
        if self._btn_a is None:
            return
        try:
            now = time.monotonic()
            a   = self._btn_a.is_pressed()
            b   = self._btn_b.is_pressed()

            if a and not self._prev_a and now - self._last_press_a >= DEBOUNCE_DELAY:
                self._last_press_a = now
                if callable(self.on_btn_a):
                    self.on_btn_a()

            if b and not self._prev_b and now - self._last_press_b >= DEBOUNCE_DELAY:
                self._last_press_b = now
                if callable(self.on_btn_b):
                    self.on_btn_b()

            self._prev_a, self._prev_b = a, b
        except Exception as e:
            print(f"Erreur lecture boutons : {e}")

    def _on_key(self, window, key, *args):
        if key == 97 and callable(self.on_btn_a):    # 'a'
            self.on_btn_a()
        elif key == 98 and callable(self.on_btn_b):  # 'b'
            self.on_btn_b()

    # ══════════════════════════════════════════════════════════════════════════
    # API PUBLIQUE — thread-safe
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, screen_name: str):
        Clock.schedule_once(lambda dt: setattr(self.sm, 'current', screen_name), 0)

    def update_pm10(self, pm10: float):
        self._last_pm10 = pm10
        if hasattr(self, 's_accueil'):
            Clock.schedule_once(lambda dt: self.s_accueil.update_pm10(pm10), 0)

    def update_seuils(self, seuil_vert: float, seuil_orange: float):
        """
        Met à jour les seuils affichés (page Seuils + couleur Accueil).
        Thread-safe. Appelée par le Controller quand un message MQTT arrive.
        """
        def _do(dt):
            self.seuil_vert   = seuil_vert
            self.seuil_orange = seuil_orange
            # Recalcule la couleur avec les nouveaux seuils si une mesure existe
            if self._last_pm10 is not None:
                self.s_accueil.update_pm10(self._last_pm10)
        Clock.schedule_once(_do, 0)

    def show_popup(self, titre: str, message: str, duration: float = 4):
        Clock.schedule_once(
            lambda dt: self._do_show_popup(titre, message, duration), 0
        )

    def _do_show_popup(self, titre: str, message: str, duration: float):
        if self._popup_event:
            self._popup_event.cancel()
            self._popup_event = None
        self._popup.show(titre, message)
        if duration > 0:
            self._popup_event = Clock.schedule_once(
                lambda dt: self.hide_popup(), duration
            )

    def hide_popup(self):
        Clock.schedule_once(lambda dt: self._popup.hide(), 0)