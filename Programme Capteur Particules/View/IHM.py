# View/IHM.py
"""
IHM Kivy pour UNIHIKER - Mode paysage (rotation 90°, résolution physique 240x320)
  Page accueil  : mesure PM10 colorée + date/heure
  Page seuils   : bouton A intégré UNIHIKER
  Page réseau   : bouton B intégré UNIHIKER
Retour automatique à l'accueil après AUTO_RETURN_DELAY secondes.
"""

# ── Config Kivy AVANT tout import kivy ───────────────────────────────────────
from kivy.config import Config
Config.set('graphics', 'width', '240')
Config.set('graphics', 'height', '320')
Config.set('graphics', 'rotation', '90')
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'show_cursor', '1')
Config.set('kivy', 'keyboard_mode', 'system')

import kivy
kivy.require('2.1.0')

import threading
import socket
import uuid
from datetime import datetime

from kivy.app               import App
from kivy.clock             import Clock
from kivy.core.window       import Window
from kivy.graphics          import Color, Rectangle
from kivy.uix.boxlayout     import BoxLayout
from kivy.uix.label         import Label
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition

# ── Constantes ────────────────────────────────────────────────────────────────
AUTO_RETURN_DELAY  = 60     # secondes avant retour accueil automatique
GPIO_POLL_INTERVAL = 0.5   # secondes entre deux lectures des boutons

SEUIL_VERT   = 25.0
SEUIL_ORANGE = 50.0

C_GRIS   = (0.82, 0.82, 0.82, 1)
C_VERT   = (0.13, 0.86, 0.13, 1)
C_ORANGE = (1.00, 0.60, 0.00, 1)
C_ROUGE  = (0.95, 0.15, 0.15, 1)
C_DARK   = (0.35, 0.35, 0.35, 1)
C_NOIR   = (0.00, 0.00, 0.00, 1)
C_BLANC  = (1.00, 1.00, 1.00, 1)


# ── Helpers ───────────────────────────────────────────────────────────────────
def bg_rect(widget, rgba):
    with widget.canvas.before:
        col  = Color(*rgba)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos  = lambda w, v: setattr(rect, 'pos',  v),
                size = lambda w, v: setattr(rect, 'size', v))
    return col


def colored_box(parent, rgba, height=None, padding=8):
    kw = {'orientation': 'vertical', 'padding': padding}
    if height:
        kw['size_hint'] = (1, None)
        kw['height']    = height
    box = BoxLayout(**kw)
    bg_rect(box, rgba)
    parent.add_widget(box)
    return box


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/A"


def get_mac():
    try:
        n = uuid.getnode()
        return ':'.join(f'{(n >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1))
    except Exception:
        return "N/A"


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 1 – Accueil
# ══════════════════════════════════════════════════════════════════════════════
class AccueilScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()
        Clock.schedule_interval(self._tick, 1)

    def _build(self):
        bg_rect(self, C_GRIS)
        root = BoxLayout(orientation='vertical', padding=[6, 6, 6, 4], spacing=5)

        # En-tête
        header = BoxLayout(orientation='horizontal',
                           size_hint=(1, None), height=24)
        header.add_widget(Label(
            text='[b]Qualité de l\'air — PM10[/b]', markup=True,
            font_size='13sp', halign='left', valign='middle',
            color=C_NOIR, size_hint=(0.55, 1)
        ))
        self.lbl_time = Label(
            text='--:--:--', font_size='13sp',
            halign='right', valign='middle',
            color=C_NOIR, size_hint=(0.45, 1)
        )
        self.lbl_time.bind(size=self.lbl_time.setter('text_size'))
        header.add_widget(self.lbl_time)
        root.add_widget(header)

        # Bloc PM10
        self.pm10_box = BoxLayout(orientation='vertical', padding=12, spacing=6)
        self._pm10_col = bg_rect(self.pm10_box, C_DARK)
        self.lbl_val = Label(text='-- µg/m³', font_size='26sp', bold=True,
                             halign='center', color=C_NOIR)
        self.lbl_state = Label(text='En attente de la première mesure…',
                               font_size='12sp', halign='center', color=C_NOIR,
                               text_size=(290, None))
        self.pm10_box.add_widget(self.lbl_val)
        self.pm10_box.add_widget(self.lbl_state)
        root.add_widget(self.pm10_box)

        # Légende
        leg = BoxLayout(orientation='horizontal',
                        size_hint=(1, None), height=16, spacing=2)
        for txt, col in [
            (f'● < {SEUIL_VERT:.0f} µg/m³',             C_VERT),
            (f'● {SEUIL_VERT:.0f}–{SEUIL_ORANGE:.0f}',  C_ORANGE),
            (f'● ≥ {SEUIL_ORANGE:.0f} µg/m³',           C_ROUGE),
        ]:
            leg.add_widget(Label(text=txt, font_size='10sp',
                                 color=col, halign='center'))
        root.add_widget(leg)
        self.add_widget(root)

    def _tick(self, dt):
        self.lbl_time.text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_pm10(self, pm10: float):
        self.lbl_val.text = f'PM10   {pm10:.1f} µg/m³'
        if pm10 < SEUIL_VERT:
            self._pm10_col.rgba = C_VERT
            self.lbl_state.text = f'Bonne qualité  (< {SEUIL_VERT:.0f} µg/m³)'
        elif pm10 < SEUIL_ORANGE:
            self._pm10_col.rgba = C_ORANGE
            self.lbl_state.text = f'Qualité moyenne  ({SEUIL_VERT:.0f}–{SEUIL_ORANGE:.0f} µg/m³)'
        else:
            self._pm10_col.rgba = C_ROUGE
            self.lbl_state.text = f'Mauvaise qualité  (≥ {SEUIL_ORANGE:.0f} µg/m³) !'


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 2 – Seuils  (bouton A)
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    def _build(self):
        bg_rect(self, C_GRIS)
        root = BoxLayout(orientation='vertical', padding=8, spacing=8)
        root.add_widget(Label(
            text='[b]Seuils configurés[/b]', markup=True,
            font_size='15sp', color=C_NOIR,
            size_hint=(1, None), height=28,
            halign='center', valign='middle'
        ))
        for color, titre, valeur in [
            (C_VERT,   'Seuil 1 — Vert',   f'PM10 < {SEUIL_VERT:.0f} µg/m³'),
            (C_ORANGE, 'Seuil 2 — Orange', f'PM10  {SEUIL_VERT:.0f} – {SEUIL_ORANGE:.0f} µg/m³'),
            (C_ROUGE,  'Seuil 3 — Rouge',  f'PM10 ≥ {SEUIL_ORANGE:.0f} µg/m³'),
        ]:
            box = colored_box(root, color, height=55, padding=8)
            box.add_widget(Label(
                text=f'[b]{titre}[/b]\n{valeur}', markup=True,
                font_size='13sp', halign='center', color=C_NOIR
            ))
        root.add_widget(Label(
            text='[i]Retour auto dans 60 s   (bouton A = basculer)[/i]',
            markup=True, font_size='10sp', color=C_DARK,
            size_hint=(1, None), height=16, halign='center'
        ))
        self.add_widget(root)


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 3 – Réseau  (bouton B)
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    def _build(self):
        bg_rect(self, C_GRIS)
        root = BoxLayout(orientation='vertical', padding=8, spacing=10)
        root.add_widget(Label(
            text='[b]Configuration réseau[/b]', markup=True,
            font_size='15sp', color=C_NOIR,
            size_hint=(1, None), height=28,
            halign='center', valign='middle'
        ))
        ip_box = colored_box(root, C_DARK, height=72, padding=10)
        ip_box.add_widget(Label(text='Adresse IP', font_size='12sp',
                                bold=True, color=C_BLANC, halign='center'))
        self.lbl_ip = Label(text='…', font_size='16sp',
                            color=C_BLANC, halign='center')
        ip_box.add_widget(self.lbl_ip)

        mac_box = colored_box(root, C_DARK, height=72, padding=10)
        mac_box.add_widget(Label(text='Adresse MAC', font_size='12sp',
                                 bold=True, color=C_BLANC, halign='center'))
        self.lbl_mac = Label(text='…', font_size='16sp',
                             color=C_BLANC, halign='center')
        mac_box.add_widget(self.lbl_mac)

        root.add_widget(Label(
            text='[i]Retour auto dans 60 s   (bouton B = basculer)[/i]',
            markup=True, font_size='10sp', color=C_DARK,
            size_hint=(1, None), height=16, halign='center'
        ))
        self.add_widget(root)

    def on_enter(self, *args):
        self.lbl_ip.text  = '…'
        self.lbl_mac.text = '…'
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        ip, mac = get_ip(), get_mac()
        Clock.schedule_once(lambda dt: self._set(ip, mac), 0)

    def _set(self, ip, mac):
        self.lbl_ip.text  = ip
        self.lbl_mac.text = mac


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════
class IHM(App):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._auto_event = None
        self._last_pm10  = None
        # Objets boutons UNIHIKER (initialisés dans build → thread principal)
        self._btn_a = None
        self._btn_b = None
        # Mémorise l'état précédent pour détecter le front (appui = True→False)
        self._prev_a = False
        self._prev_b = False
        Window.clearcolor = C_GRIS

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        self.sm = ScreenManager(transition=FadeTransition(duration=0.15))
        self.s_accueil = AccueilScreen(name='accueil')
        self.s_seuils  = SeuilsScreen(name='seuils')
        self.s_reseau  = ReseauScreen(name='reseau')
        for s in (self.s_accueil, self.s_seuils, self.s_reseau):
            self.sm.add_widget(s)

        # Boutons UNIHIKER — doit être dans le thread principal
        self._init_buttons()

        # Polling dans le thread principal via Clock (pas de problème signal)
        Clock.schedule_interval(self._poll_buttons, GPIO_POLL_INTERVAL)

        # Fallback clavier (test PC ou mapping clavier UNIHIKER)
        Window.bind(on_key_down=self._on_key)

        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return self.sm

    # ── Initialisation boutons UNIHIKER ───────────────────────────────────────
    def _init_buttons(self):
        """
        Les boutons A et B intégrés à l'UNIHIKER s'accèdent via
        pinpong.extension.unihiker : button_a et button_b.
        La méthode is_pressed() retourne True quand le bouton est enfoncé.
        """
        try:
            from pinpong.board import Board
            from pinpong.extension.unihiker import button_a, button_b
            Board().begin()
            self._btn_a = button_a
            self._btn_b = button_b
            print("Boutons A et B UNIHIKER initialisés")
        except ImportError:
            print("pinpong absent — mode PC, utilisez les touches [a] et [b]")
        except Exception as e:
            print(f"Erreur init boutons : {e}")

    # ── Polling boutons (Clock → thread principal) ────────────────────────────
    def _poll_buttons(self, dt):
        """
        Lit l'état des boutons à chaque tick Clock.
        Déclenche l'action sur le front montant (False → True = appui).
        """
        if self._btn_a is None:
            return
        try:
            a = self._btn_a.is_pressed()
            b = self._btn_b.is_pressed()

            # Front montant bouton A : False → True
            if a and not self._prev_a:
                target = 'accueil' if self.sm.current == 'seuils' else 'seuils'
                self._go(target)

            # Front montant bouton B : False → True
            if b and not self._prev_b:
                target = 'accueil' if self.sm.current == 'reseau' else 'reseau'
                self._go(target)

            self._prev_a, self._prev_b = a, b

        except Exception as e:
            print(f"Erreur lecture boutons : {e}")

    # ── Navigation ────────────────────────────────────────────────────────────
    def _go(self, name: str):
        self.sm.current = name
        if name != 'accueil':
            self._arm_auto_return()
        else:
            self._cancel_auto_return()

    def _arm_auto_return(self):
        self._cancel_auto_return()
        self._auto_event = Clock.schedule_once(
            lambda dt: self._go('accueil'), AUTO_RETURN_DELAY
        )

    def _cancel_auto_return(self):
        if self._auto_event:
            self._auto_event.cancel()
            self._auto_event = None

    # ── Clavier (test PC ou mapping clavier des boutons UNIHIKER) ─────────────
    def _on_key(self, window, key, scancode, codepoint, modifier):
        # Sur UNIHIKER, bouton A → touche 'a' (keycode 97), B → 'b' (98)
        mapping = {97: 'seuils', 98: 'reseau', 27: 'accueil'}
        if key in mapping:
            self._go(mapping[key])

    # ── API publique thread-safe ──────────────────────────────────────────────
    def update_pm10(self, pm10: float):
        self._last_pm10 = pm10
        if hasattr(self, 's_accueil'):
            Clock.schedule_once(lambda dt: self.s_accueil.update_pm10(pm10), 0)