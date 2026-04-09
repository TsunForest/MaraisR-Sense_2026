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
"""

# ── Configuration Kivy AVANT tout import kivy ─────────────────────────────────
# Ces lignes doivent précéder tous les imports kivy, sinon les valeurs sont
# ignorées car la fenêtre est déjà créée.
from kivy.config import Config
Config.set('graphics', 'width',      '240')   # largeur physique de l'écran UNIHIKER
Config.set('graphics', 'height',     '320')   # hauteur physique de l'écran UNIHIKER
Config.set('graphics', 'rotation',   '90')    # rotation → paysage effectif 320x240
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'show_cursor','0')     # pas de curseur souris sur la carte
Config.set('kivy',     'keyboard_mode', 'system')

import kivy
kivy.require('2.1.0')

import os           # pour construire le chemin vers ihm.kv
import time         # pour le debounce des boutons (time.monotonic)
import threading    # pour la récupération IP/MAC en arrière-plan
import socket       # pour récupérer l'adresse IP
import uuid         # pour récupérer l'adresse MAC
from datetime import datetime   # pour l'horloge

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
# Intervalle de polling des boutons physiques (secondes)
GPIO_POLL_INTERVAL = 0.05

# Délai minimum entre deux appuis acceptés (anti-rebond logiciel)
DEBOUNCE_DELAY = 0.5

# Seuils par défaut utilisés si aucun message MQTT n'est reçu
SEUIL_VERT_DEFAUT         = 25.0    # PM10  ug/m3
SEUIL_ORANGE_DEFAUT       = 50.0    # PM10  ug/m3
SEUIL_TVOC_VERT_DEFAUT    = 220.0   # TVOC  ppb
SEUIL_TVOC_ORANGE_DEFAUT  = 660.0   # TVOC  ppb
SEUIL_CO2_VERT_DEFAUT     = 800.0   # eCO2  ppm
SEUIL_CO2_ORANGE_DEFAUT   = 1200.0  # eCO2  ppm

# Couleurs RGBA (listes car Kivy utilise des listes pour ListProperty)
C_VERT   = [0.13, 0.86, 0.13, 1]   # vert   : qualité bonne
C_ORANGE = [1.00, 0.60, 0.00, 1]   # orange : qualité moyenne
C_ROUGE  = [0.95, 0.15, 0.15, 1]   # rouge  : mauvaise qualité
C_DARK   = [0.35, 0.35, 0.35, 1]   # gris foncé : état initial (pas de mesure)


# ── Helpers réseau (exécutés dans un thread de fond pour ne pas bloquer l'UI) ─

def _get_ip() -> str:
    """
    Retourne l'adresse IP locale en tentant une connexion UDP vers 8.8.8.8.
    Aucun paquet n'est réellement envoyé : c'est une astuce pour identifier
    l'interface réseau active sans parser ifconfig.
    """
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
    """
    Retourne l'adresse MAC de l'interface principale au format xx:xx:xx:xx:xx:xx
    via uuid.getnode().
    """
    try:
        n = uuid.getnode()
        return ':'.join(f'{(n >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1))
    except Exception:
        return "Non disponible"


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 1 – Accueil PM10
# ══════════════════════════════════════════════════════════════════════════════
class AccueilScreen(Screen):
    """
    Écran principal PM10 : affiche la mesure de particules fines avec un fond
    coloré selon le seuil actif et une horloge temps réel.

    Propriétés bindées dans ihm.kv :
        pm10_color  : couleur RGBA du fond du bloc mesure
        val_text    : valeur affichée (ex. "42.3 ug/m3")
        state_text  : état qualitatif (ex. "Qualite moyenne")
        time_text   : horloge (ex. "07/04  14:32:05")
    """
    pm10_color = ListProperty(C_DARK)
    val_text   = StringProperty('-- ug/m3')
    state_text = StringProperty('En attente de la premiere mesure...')
    time_text  = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Mise à jour de l'horloge toutes les secondes via le scheduler Kivy
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        """Rafraichit l'horloge. Appelée par Clock chaque seconde."""
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_pm10(self, pm10: float):
        """
        Met à jour la valeur et la couleur de fond selon les seuils actifs.
        Les seuils sont lus en temps réel depuis l'App (app.seuil_vert, etc.)
        ce qui permet une mise à jour immédiate si les seuils changent via MQTT.

        :param pm10: Valeur PM10 en ug/m3.
        """
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
    """
    Écran des seuils PM10.
    Pas de propriétés propres : le KV lit directement app.seuil_vert et
    app.seuil_orange, qui sont des NumericProperty sur l'App.
    La mise à jour est donc automatique quand le broker MQTT envoie
    de nouveaux seuils.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 3 – Configuration réseau
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):
    """
    Affiche l'adresse IP et l'adresse MAC de la carte UNIHIKER.
    Les valeurs sont récupérées dans un thread de fond à chaque entrée dans
    l'écran pour ne pas bloquer l'UI pendant la résolution réseau.

    Propriétés bindées dans ihm.kv :
        ip_text  : adresse IP (ex. "192.168.1.42")
        mac_text : adresse MAC (ex. "62:03:57:41:38:23")
    """
    ip_text  = StringProperty('...')
    mac_text = StringProperty('...')

    def on_enter(self, *args):
        """Déclenché automatiquement par Kivy à chaque entrée dans cet écran."""
        self.ip_text  = '...'
        self.mac_text = '...'
        # Thread daemon pour ne pas bloquer l'UI ni l'arrêt du programme
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        """
        Récupère IP et MAC dans un thread de fond, puis reposte le résultat
        dans le thread UI via Clock.schedule_once (obligatoire pour modifier
        des propriétés Kivy depuis un thread autre que le thread principal).
        """
        ip, mac = _get_ip(), _get_mac()
        Clock.schedule_once(lambda dt: self._set(ip, mac), 0)

    def _set(self, ip: str, mac: str):
        """Met à jour les labels. Appelée dans le thread UI via Clock."""
        self.ip_text  = ip
        self.mac_text = mac


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 4 – Accueil TVOC + eCO2
# ══════════════════════════════════════════════════════════════════════════════
class AccueilCapteur2Screen(Screen):
    """
    Écran de mesure qualité d'air intérieur (CCS811).
    Deux blocs colorés empilés : TVOC en ppb et eCO2 en ppm.
    Chaque bloc a sa propre couleur dynamique selon ses seuils.

    Propriétés bindées dans ihm.kv :
        tvoc_color      : couleur RGBA du bloc TVOC
        tvoc_val_text   : valeur TVOC affichée (ex. "320 ppb")
        tvoc_state_text : état qualitatif TVOC
        co2_color       : couleur RGBA du bloc eCO2
        co2_val_text    : valeur eCO2 affichée (ex. "850 ppm")
        co2_state_text  : état qualitatif eCO2
        time_text       : horloge (même format que AccueilScreen)
    """
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
        """Rafraichit l'horloge. Appelée par Clock chaque seconde."""
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_tvoc(self, tvoc: int):
        """
        Met à jour l'affichage TVOC selon les seuils actifs.

        :param tvoc: Valeur TVOC en ppb (retournée par CCS811).
        """
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
        """
        Met à jour l'affichage eCO2 selon les seuils actifs.
        Le paramètre est nommé eco2 pour correspondre à la sortie du CCS811.

        :param eco2: Valeur eCO2 en ppm (retournée par CCS811).
        """
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
# ECRAN 5 – Seuils TVOC + eCO2
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsCapteur2Screen(Screen):
    """
    Écran des seuils pour TVOC et eCO2.
    Comme SeuilsScreen, pas de propriétés propres : le KV lit directement
    app.seuil_tvoc_* et app.seuil_co2_* et se met à jour automatiquement.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# POPUP overlay
# ══════════════════════════════════════════════════════════════════════════════
class PopupOverlay(BoxLayout):
    """
    Bandeau d'alerte semi-transparent affiché par-dessus n'importe quel écran.
    Rendu visible/invisible via la BooleanProperty is_visible, ce qui modifie
    l'opacité sans recréer de widget (pas de recomposition de l'arbre).

    Propriétés bindées dans ihm.kv :
        is_visible : True = affiché, False = invisible
        titre      : titre de l'alerte (rouge)
        message    : message détaillé (blanc)
    """
    is_visible = BooleanProperty(False)
    titre      = StringProperty('')
    message    = StringProperty('')

    def show(self, titre: str, message: str):
        """Affiche le popup avec le titre et le message fournis."""
        self.titre      = titre
        self.message    = message
        self.is_visible = True

    def hide(self):
        """Masque le popup."""
        self.is_visible = False


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION PRINCIPALE — View pure
# ══════════════════════════════════════════════════════════════════════════════
class IHM(App):
    """
    Classe principale Kivy. Ne contient aucune logique métier.

    Les NumericProperty déclarées ici sont accessibles dans ihm.kv via 'app.xxx'.
    Kivy observe automatiquement ces propriétés : tout widget du KV qui les
    référence se redessine lorsqu'elles changent.
    """

    # ── Seuils PM10 ───────────────────────────────────────────────────────────
    seuil_vert   = NumericProperty(SEUIL_VERT_DEFAUT)
    seuil_orange = NumericProperty(SEUIL_ORANGE_DEFAUT)

    # ── Seuils TVOC ───────────────────────────────────────────────────────────
    seuil_tvoc_vert   = NumericProperty(SEUIL_TVOC_VERT_DEFAUT)
    seuil_tvoc_orange = NumericProperty(SEUIL_TVOC_ORANGE_DEFAUT)

    # ── Seuils eCO2 ───────────────────────────────────────────────────────────
    seuil_co2_vert   = NumericProperty(SEUIL_CO2_VERT_DEFAUT)
    seuil_co2_orange = NumericProperty(SEUIL_CO2_ORANGE_DEFAUT)

    # Callbacks branchés par le Controller AVANT ihm.run()
    on_btn_a = None
    on_btn_b = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._popup_event  = None    # timer d'auto-fermeture du popup
        self._last_pm10    = None    # dernière valeur PM10 (pour recalcul seuils)
        self._btn_a        = None    # objet button_a pinpong (None si absent)
        self._btn_b        = None    # objet button_b pinpong
        self._prev_a       = False   # état précédent bouton A (détection de front)
        self._prev_b       = False   # état précédent bouton B
        self._last_press_a = 0.0     # timestamp du dernier appui validé bouton A
        self._last_press_b = 0.0     # timestamp du dernier appui validé bouton B
        Window.clearcolor  = (0.82, 0.82, 0.82, 1)

    # ── Propriété lecture seule ───────────────────────────────────────────────
    @property
    def current_screen(self) -> str:
        """
        Retourne le nom de l'écran actif.
        Utilisé par le Controller pour décider où naviguer.
        """
        return self.sm.current if hasattr(self, 'sm') else 'accueil'

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        """
        Construit l'arbre de widgets Kivy.
        Appelé automatiquement par ihm.run().
        Le fichier ihm.kv est chargé explicitement pour fonctionner
        quel que soit le répertoire de travail courant.
        """
        kv_path = os.path.join(os.path.dirname(__file__), 'ihm.kv')
        Builder.load_file(kv_path)

        # ScreenManager sans transition pour un changement d'écran instantané
        self.sm = ScreenManager(transition=NoTransition())

        # Création de tous les écrans
        self.s_accueil         = AccueilScreen(name='accueil')
        self.s_seuils          = SeuilsScreen(name='seuils')
        self.s_reseau          = ReseauScreen(name='reseau')
        self.s_capteur2        = AccueilCapteur2Screen(name='capteur2')
        self.s_seuils_capteur2 = SeuilsCapteur2Screen(name='seuils_capteur2')

        for s in (self.s_accueil, self.s_seuils, self.s_reseau,
                  self.s_capteur2, self.s_seuils_capteur2):
            self.sm.add_widget(s)

        # Popup overlay positionné au centre de la fenêtre
        self._popup = PopupOverlay(
            size_hint=(0.88, None),
            height=90,
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        # FloatLayout racine : ScreenManager en dessous, popup par-dessus
        root = FloatLayout()
        root.add_widget(self.sm)
        root.add_widget(self._popup)

        # Initialisation des boutons dans le thread principal (obligatoire pour pinpong)
        self._init_buttons()
        Clock.schedule_interval(self._poll_buttons, GPIO_POLL_INTERVAL)
        Window.bind(on_key_down=self._on_key)

        # Mise à jour initiale si une mesure est arrivée avant que l'UI soit prête
        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return root

    # ── Initialisation des boutons UNIHIKER ───────────────────────────────────
    def _init_buttons(self):
        """
        Initialise les objets button_a et button_b de pinpong.
        Ces objets correspondent aux boutons physiques intégrés à la carte.
        Silencieux si pinpong est absent (mode test sur PC).
        """
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

    # ── Polling des boutons ───────────────────────────────────────────────────
    def _poll_buttons(self, dt):
        """
        Appelée par Clock.schedule_interval toutes les GPIO_POLL_INTERVAL secondes.
        S'exécute dans le thread principal Kivy → pas de problème avec les signaux.

        Logique de détection :
          - is_pressed() retourne True tant que le bouton est enfoncé.
          - On déclenche l'action uniquement sur le front montant (False → True)
            pour éviter les appuis répétés si le bouton reste enfoncé.
          - Le debounce (DEBOUNCE_DELAY) filtre les rebonds mécaniques du bouton.
        """
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

    # ── Clavier (test sur PC) ─────────────────────────────────────────────────
    def _on_key(self, window, key, *args):
        """
        Fallback clavier pour tester sans carte UNIHIKER.
        Touche 'a' (keycode 97) → simule le bouton A.
        Touche 'b' (keycode 98) → simule le bouton B.
        """
        if key == 97 and callable(self.on_btn_a):
            self.on_btn_a()
        elif key == 98 and callable(self.on_btn_b):
            self.on_btn_b()

    # ══════════════════════════════════════════════════════════════════════════
    # API PUBLIQUE — appelée par le Controller, toutes thread-safe
    # Thread-safe = passage par Clock.schedule_once pour s'exécuter dans le
    # thread UI Kivy, qui est le seul autorisé à modifier les propriétés.
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, screen_name: str):
        """
        Change l'écran affiché.

        :param screen_name: Nom de l'écran ('accueil', 'seuils', 'reseau',
                            'capteur2', 'seuils_capteur2').
        """
        Clock.schedule_once(
            lambda dt: setattr(self.sm, 'current', screen_name), 0
        )

    def update_pm10(self, pm10: float):
        """
        Met à jour la valeur PM10 sur l'écran d'accueil.
        Stocke la dernière valeur pour recalcul en cas de changement de seuils.

        :param pm10: Valeur PM10 en ug/m3.
        """
        self._last_pm10 = pm10
        if hasattr(self, 's_accueil'):
            Clock.schedule_once(
                lambda dt: self.s_accueil.update_pm10(pm10), 0
            )

    def update_tvoc_co2(self, eco2: int, tvoc: int):
        """
        Met à jour les valeurs TVOC et eCO2 sur l'écran capteur2.
        Les paramètres correspondent directement à la sortie de CCS811.read_eco2_tvoc().

        :param eco2: Valeur eCO2 en ppm.
        :param tvoc: Valeur TVOC en ppb.
        """
        if hasattr(self, 's_capteur2'):
            Clock.schedule_once(
                lambda dt: (
                    self.s_capteur2.update_tvoc(tvoc),
                    self.s_capteur2.update_co2(eco2)
                ), 0
            )

    def update_seuils(self, seuil_vert: float, seuil_orange: float):
        """
        Met à jour les seuils PM10.
        Comme seuil_vert et seuil_orange sont des NumericProperty sur l'App,
        SeuilsScreen se met à jour automatiquement via le binding KV.
        La couleur de la mesure courante est aussi recalculée.

        :param seuil_vert:   Nouveau seuil vert en ug/m3.
        :param seuil_orange: Nouveau seuil orange en ug/m3.
        """
        def _do(dt):
            self.seuil_vert   = seuil_vert
            self.seuil_orange = seuil_orange
            if self._last_pm10 is not None:
                self.s_accueil.update_pm10(self._last_pm10)
        Clock.schedule_once(_do, 0)

    def update_seuils_capteur2(self, tvoc_vert: float, tvoc_orange: float,
                                co2_vert: float, co2_orange: float):
        """
        Met à jour les seuils TVOC et eCO2.
        SeuilsCapteur2Screen se met à jour automatiquement via le binding KV.

        :param tvoc_vert:   Nouveau seuil TVOC vert en ppb.
        :param tvoc_orange: Nouveau seuil TVOC orange en ppb.
        :param co2_vert:    Nouveau seuil eCO2 vert en ppm.
        :param co2_orange:  Nouveau seuil eCO2 orange en ppm.
        """
        def _do(dt):
            self.seuil_tvoc_vert   = tvoc_vert
            self.seuil_tvoc_orange = tvoc_orange
            self.seuil_co2_vert    = co2_vert
            self.seuil_co2_orange  = co2_orange
        Clock.schedule_once(_do, 0)

    def show_popup(self, titre: str, message: str, duration: float = 4):
        """
        Affiche un popup d'alerte par-dessus l'écran actif.

        :param titre:    Titre de l'alerte, affiché en rouge.
        :param message:  Message détaillé, affiché en blanc.
        :param duration: Secondes avant fermeture automatique (0 = permanent).
        """
        Clock.schedule_once(
            lambda dt: self._do_show_popup(titre, message, duration), 0
        )

    def _do_show_popup(self, titre: str, message: str, duration: float):
        """
        Exécution réelle de l'affichage (dans le thread UI).
        Annule le timer de fermeture précédent avant d'en armer un nouveau.
        """
        if self._popup_event:
            self._popup_event.cancel()
            self._popup_event = None
        self._popup.show(titre, message)
        if duration > 0:
            self._popup_event = Clock.schedule_once(
                lambda dt: self.hide_popup(), duration
            )

    def hide_popup(self):
        """Masque le popup d'alerte. Thread-safe."""
        Clock.schedule_once(lambda dt: self._popup.hide(), 0)