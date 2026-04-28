# View/IHM.py
"""
Vue MVC de l'application — logique pure, tout le layout est dans ihm.kv.

Role : afficher les données fournies par le Controller, gérer les entrées
physiques (boutons A/B) et exposer une API publique thread-safe.

Propriétés Kivy sur l'App (accessibles dans ihm.kv via 'app.xxx') :
    seuil_vert, seuil_orange           — seuils PM10    (ug/m3)
    seuil_tvoc_vert, seuil_tvoc_orange — seuils TVOC   (ppb)
    seuil_co2_vert,  seuil_co2_orange  — seuils eCO2   (ppm)

Callbacks à brancher depuis le Controller AVANT ihm.run() :
    ihm.on_btn_a = callable()
    ihm.on_btn_b = callable()

API publique (toutes thread-safe) :
    ihm.navigate_to(name)
    ihm.update_pm10(pm10)
    ihm.update_tvoc_co2(eco2, tvoc)
    ihm.update_seuils(sv, so)
    ihm.update_seuils_capteur2(tv, to, cv, co)
    ihm.show_popup(titre, message, duration)
    ihm.hide_popup()
    ihm.current_screen  → str

Écrans disponibles :
    'accueil'     – mesure PM10
    'capteur2'    – mesure TVOC + eCO2
    'seuils'      – seuils PM10
    'seuils_tvoc' – seuils TVOC  (remplace la moitié haute de l'ancien seuils_capteur2)
    'seuils_co2'  – seuils eCO2  (remplace la moitié basse de l'ancien seuils_capteur2)
    'reseau'      – info réseau
"""

# ── Configuration Kivy AVANT tout import kivy ─────────────────────────────────
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
# Polling des boutons physiques toutes les 0.1 s pour une réactivité correcte.
# La valeur précédente (6 s) était beaucoup trop lente et causait des doubles
# déclenchements car l'état du bouton pouvait changer plusieurs fois entre deux polls.
GPIO_POLL_INTERVAL = 0.1

# Durée de maintien requise pour valider un appui (secondes).
# L'utilisateur doit maintenir le bouton 3 s pour changer de page.
HOLD_DURATION = 3.0

# Seuils par défaut utilisés si aucun message MQTT n'est reçu
SEUIL_VERT_DEFAUT         = 25.0
SEUIL_ORANGE_DEFAUT       = 50.0
SEUIL_TVOC_VERT_DEFAUT    = 220.0
SEUIL_TVOC_ORANGE_DEFAUT  = 660.0
SEUIL_CO2_VERT_DEFAUT     = 800.0
SEUIL_CO2_ORANGE_DEFAUT   = 1200.0

# Couleurs RGBA
C_VERT   = [0.13, 0.86, 0.13, 1]
C_ORANGE = [1.00, 0.60, 0.00, 1]
C_ROUGE  = [0.95, 0.15, 0.15, 1]
C_DARK   = [0.35, 0.35, 0.35, 1]


# ── Helpers réseau ────────────────────────────────────────────────────────────

def _get_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Non disponible"


def _get_mac() -> str:
    try:
        n = uuid.getnode()
        return ':'.join(f'{(n >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1))
    except Exception:
        return "Non disponible"


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 1 – Accueil PM10
# ══════════════════════════════════════════════════════════════════════════════
class AccueilScreen(Screen):
    pm10_color = ListProperty(C_DARK)
    val_text   = StringProperty('-- ug/m3')
    state_text = StringProperty('En attente de la premiere mesure...')
    time_text  = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_pm10(self, pm10: float):
        app = App.get_running_app()
        sv  = app.seuil_vert
        so  = app.seuil_orange
        self.val_text = f'{pm10:.1f} ug/m3'
        if pm10 < sv:
            self.pm10_color = C_VERT
            self.state_text = f'Bonne qualite  (< {sv:.0f} ug/m3)'
        elif pm10 < so:
            self.pm10_color = C_ORANGE
            self.state_text = f'Qualite moyenne  ({sv:.0f}-{so:.0f} ug/m3)'
        else:
            self.pm10_color = C_ROUGE
            self.state_text = f'Mauvaise qualite  (>= {so:.0f} ug/m3) !'


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 2 – Seuils PM10
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsScreen(Screen):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 3 – Configuration réseau
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):
    ip_text  = StringProperty('...')
    mac_text = StringProperty('...')

    def on_enter(self, *args):
        self.ip_text  = '...'
        self.mac_text = '...'
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        ip, mac = _get_ip(), _get_mac()
        Clock.schedule_once(lambda dt: self._set(ip, mac), 0)

    def _set(self, ip: str, mac: str):
        self.ip_text  = ip
        self.mac_text = mac


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 4 – Accueil TVOC + eCO2
# ══════════════════════════════════════════════════════════════════════════════
class AccueilCapteur2Screen(Screen):
    tvoc_color      = ListProperty(C_DARK)
    tvoc_val_text   = StringProperty('-- ppb')
    tvoc_state_text = StringProperty('En attente...')
    co2_color       = ListProperty(C_DARK)
    co2_val_text    = StringProperty('-- ppm')
    co2_state_text  = StringProperty('En attente...')
    time_text       = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_tvoc(self, tvoc: int):
        app = App.get_running_app()
        sv  = app.seuil_tvoc_vert
        so  = app.seuil_tvoc_orange
        self.tvoc_val_text = f'{tvoc} ppb'
        if tvoc < sv:
            self.tvoc_color      = C_VERT
            self.tvoc_state_text = f'Bon  (< {sv:.0f} ppb)'
        elif tvoc < so:
            self.tvoc_color      = C_ORANGE
            self.tvoc_state_text = f'Moyen  ({sv:.0f}-{so:.0f} ppb)'
        else:
            self.tvoc_color      = C_ROUGE
            self.tvoc_state_text = f'Mauvais  (>= {so:.0f} ppb) !'

    def update_co2(self, eco2: int):
        app = App.get_running_app()
        sv  = app.seuil_co2_vert
        so  = app.seuil_co2_orange
        self.co2_val_text = f'{eco2} ppm'
        if eco2 < sv:
            self.co2_color      = C_VERT
            self.co2_state_text = f'Bon  (< {sv:.0f} ppm)'
        elif eco2 < so:
            self.co2_color      = C_ORANGE
            self.co2_state_text = f'Moyen  ({sv:.0f}-{so:.0f} ppm)'
        else:
            self.co2_color      = C_ROUGE
            self.co2_state_text = f'Mauvais  (>= {so:.0f} ppm) !'


# ══════════════════════════════════════════════════════════════════════════════
# ECRANS 5 & 6 – Seuils TVOC / Seuils eCO2  (anciennement SeuilsCapteur2Screen)
#
# L'ancienne page unique débordait de l'écran (≈350 px pour 240 px disponibles).
# On sépare désormais TVOC et eCO2 en deux écrans indépendants.
# Le Controller les fait alterner via _demarrer_alternance() comme les autres.
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsTVOCScreen(Screen):
    """Seuils TVOC uniquement. Binding direct sur app.seuil_tvoc_*."""
    pass


class SeuilsCO2Screen(Screen):
    """Seuils eCO2 uniquement. Binding direct sur app.seuil_co2_*."""
    pass


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
# APPLICATION PRINCIPALE — View pure
# ══════════════════════════════════════════════════════════════════════════════
class IHM(App):
    # ── Seuils PM10 ───────────────────────────────────────────────────────────
    seuil_vert   = NumericProperty(SEUIL_VERT_DEFAUT)
    seuil_orange = NumericProperty(SEUIL_ORANGE_DEFAUT)

    # ── Seuils TVOC ───────────────────────────────────────────────────────────
    seuil_tvoc_vert   = NumericProperty(SEUIL_TVOC_VERT_DEFAUT)
    seuil_tvoc_orange = NumericProperty(SEUIL_TVOC_ORANGE_DEFAUT)

    # ── Seuils eCO2 ───────────────────────────────────────────────────────────
    seuil_co2_vert   = NumericProperty(SEUIL_CO2_VERT_DEFAUT)
    seuil_co2_orange = NumericProperty(SEUIL_CO2_ORANGE_DEFAUT)

    on_btn_a = None
    on_btn_b = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._popup_event  = None
        self._last_pm10    = None
        self._btn_a        = None
        self._btn_b        = None

        # ── État pour la détection de maintien 3 s ────────────────────────────
        # _press_start_X  : monotonic() du moment où le bouton est passé à True.
        #                   None si le bouton est relâché.
        # _triggered_X    : True si l'action a déjà été déclenchée pour cet appui,
        #                   pour éviter de re-déclencher tant que le bouton reste enfoncé.
        self._press_start_a = None
        self._press_start_b = None
        self._triggered_a   = False
        self._triggered_b   = False

        Window.clearcolor = (0.82, 0.82, 0.82, 1)

    # ── Désactivation du chargement automatique du KV par Kivy ───────────────
    # Sans cette méthode, Kivy charge ihm.kv automatiquement (car le fichier porte
    # le nom de la classe en minuscules), PUIS build() le chargerait une seconde fois.
    # Ce double chargement fait que les règles KV sont appliquées deux fois :
    # chaque widget reçoit ses enfants en double → notifications affichées côte à côte.
    # On désactive l'auto-chargement et on charge manuellement dans build().
    def load_kv(self, filename=None):
        pass

    @property
    def current_screen(self) -> str:
        return self.sm.current if hasattr(self, 'sm') else 'accueil'

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        # Chargement unique et explicite du fichier KV (chemin absolu pour être
        # indépendant du répertoire de travail courant).
        kv_path = os.path.join(os.path.dirname(__file__), 'ihm.kv')
        Builder.load_file(kv_path)

        self.sm = ScreenManager(transition=NoTransition())

        self.s_accueil      = AccueilScreen(name='accueil')
        self.s_seuils       = SeuilsScreen(name='seuils')
        self.s_reseau       = ReseauScreen(name='reseau')
        self.s_capteur2     = AccueilCapteur2Screen(name='capteur2')
        self.s_seuils_tvoc  = SeuilsTVOCScreen(name='seuils_tvoc')
        self.s_seuils_co2   = SeuilsCO2Screen(name='seuils_co2')

        for s in (self.s_accueil, self.s_seuils, self.s_reseau,
                  self.s_capteur2, self.s_seuils_tvoc, self.s_seuils_co2):
            self.sm.add_widget(s)

        self._popup = PopupOverlay(
            size_hint=(0.88, None),
            height=90,
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        root = FloatLayout()
        root.add_widget(self.sm)
        root.add_widget(self._popup)

        self._init_buttons()
        Clock.schedule_interval(self._poll_buttons, GPIO_POLL_INTERVAL)
        Window.bind(on_key_down=self._on_key)

        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return root

    # ── Initialisation des boutons UNIHIKER ───────────────────────────────────
    def _init_buttons(self):
        try:
            from pinpong.board import Board
            from pinpong.extension.unihiker import button_a, button_b
            Board().begin()
            self._btn_a = button_a
            self._btn_b = button_b
            print("Boutons A/B UNIHIKER initialises")
        except ImportError:
            print("pinpong absent — mode PC, touches [a] et [b]")
        except Exception as e:
            print(f"Erreur initialisation boutons : {e}")

    # ── Polling des boutons avec détection de maintien 3 s ───────────────────
    def _poll_buttons(self, dt):
        """
        Appelée toutes les GPIO_POLL_INTERVAL secondes (0.1 s).
        L'action n'est déclenchée que lorsque le bouton est maintenu
        pendant HOLD_DURATION secondes (3 s) de façon continue.

        Principe :
          - Appui détecté (False→True) → enregistrement de l'heure de début.
          - Maintien ≥ 3 s et pas encore déclenché → déclenchement + marquage.
          - Relâchement → remise à zéro (permettra un prochain appui).
        """
        if self._btn_a is None:
            return
        try:
            now = time.monotonic()
            a   = self._btn_a.is_pressed()
            b   = self._btn_b.is_pressed()

            # ── Bouton A ──────────────────────────────────────────────────────
            if a:
                if self._press_start_a is None:
                    # Front montant : début du maintien
                    self._press_start_a = now
                elif not self._triggered_a and (now - self._press_start_a) >= HOLD_DURATION:
                    # Maintien 3 s atteint pour la première fois
                    self._triggered_a = True
                    if callable(self.on_btn_a):
                        self.on_btn_a()
            else:
                # Relâchement : remise à zéro pour le prochain appui
                self._press_start_a = None
                self._triggered_a   = False

            # ── Bouton B ──────────────────────────────────────────────────────
            if b:
                if self._press_start_b is None:
                    self._press_start_b = now
                elif not self._triggered_b and (now - self._press_start_b) >= HOLD_DURATION:
                    self._triggered_b = True
                    if callable(self.on_btn_b):
                        self.on_btn_b()
            else:
                self._press_start_b = None
                self._triggered_b   = False

        except Exception as e:
            print(f"Erreur lecture boutons : {e}")

    # ── Clavier (test sur PC) ─────────────────────────────────────────────────
    def _on_key(self, window, key, *args):
        """
        Fallback clavier pour tester sans carte UNIHIKER.
        Un appui clavier simple simule un maintien 3 s (mode test uniquement).
        """
        if key == 97 and callable(self.on_btn_a):
            self.on_btn_a()
        elif key == 98 and callable(self.on_btn_b):
            self.on_btn_b()

    # ══════════════════════════════════════════════════════════════════════════
    # API PUBLIQUE — thread-safe (passage par Clock.schedule_once)
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, screen_name: str):
        Clock.schedule_once(
            lambda dt: setattr(self.sm, 'current', screen_name), 0
        )

    def update_pm10(self, pm10: float):
        self._last_pm10 = pm10
        if hasattr(self, 's_accueil'):
            Clock.schedule_once(
                lambda dt: self.s_accueil.update_pm10(pm10), 0
            )

    def update_tvoc_co2(self, eco2: int, tvoc: int):
        if hasattr(self, 's_capteur2'):
            Clock.schedule_once(
                lambda dt: (
                    self.s_capteur2.update_tvoc(tvoc),
                    self.s_capteur2.update_co2(eco2)
                ), 0
            )

    def update_seuils(self, seuil_vert: float, seuil_orange: float):
        def _do(dt):
            self.seuil_vert   = seuil_vert
            self.seuil_orange = seuil_orange
            if self._last_pm10 is not None:
                self.s_accueil.update_pm10(self._last_pm10)
        Clock.schedule_once(_do, 0)

    def update_seuils_capteur2(self, tvoc_vert: float, tvoc_orange: float,
                                co2_vert: float, co2_orange: float):
        def _do(dt):
            self.seuil_tvoc_vert   = tvoc_vert
            self.seuil_tvoc_orange = tvoc_orange
            self.seuil_co2_vert    = co2_vert
            self.seuil_co2_orange  = co2_orange
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