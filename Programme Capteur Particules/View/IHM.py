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
    ihm.update_seuils_tvoc(sv, so)
    ihm.update_seuils_co2(sv, so)
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
import time         # pour le verrou boutons (time.monotonic)
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

# Intervalle de polling des boutons physiques (secondes).
BTN_POLL_INTERVAL = 0.5

# Durée du verrou global après un appui validé (secondes).
# Pendant ce temps, tous les boutons sont ignorés.
# Cela résout à la fois les rebonds (bouton A) et les faux double-appuis.
BTN_LOCK_DELAY = 1

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
    Aucun paquet n'est envoyé : c'est une astuce pour identifier l'interface
    réseau active sans parser ifconfig.
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
        Les seuils sont lus depuis l'App ce qui permet une mise à jour immédiate
        si les seuils changent via MQTT.

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
    app.seuil_orange. La mise à jour est automatique quand ces valeurs changent.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# ECRAN 3 – Configuration réseau
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):
    """
    Affiche l'adresse IP et l'adresse MAC de la carte UNIHIKER.
    Les valeurs sont récupérées dans un thread de fond à chaque entrée dans
    l'écran pour ne pas bloquer l'UI.

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
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        """
        Récupère IP et MAC dans un thread de fond, puis reposte dans le thread UI
        via Clock.schedule_once (obligatoire pour modifier des propriétés Kivy
        depuis un thread autre que le thread principal).
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

    Propriétés bindées dans ihm.kv :
        tvoc_color      : couleur RGBA du bloc TVOC
        tvoc_val_text   : valeur TVOC affichée (ex. "320 ppb")
        tvoc_state_text : état qualitatif TVOC
        co2_color       : couleur RGBA du bloc eCO2
        co2_val_text    : valeur eCO2 affichée (ex. "850 ppm")
        co2_state_text  : état qualitatif eCO2
        time_text       : horloge
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

        :param tvoc: Valeur TVOC en ppb.
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

        :param eco2: Valeur eCO2 en ppm.
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
    Pas de propriétés propres : le KV lit directement app.seuil_tvoc_* et
    app.seuil_co2_*. La mise à jour est automatique.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# POPUP overlay
# ══════════════════════════════════════════════════════════════════════════════
class PopupOverlay(BoxLayout):
    """
    Bandeau d'alerte semi-transparent affiché par-dessus n'importe quel écran.
    La visibilité est contrôlée par is_visible qui modifie l'opacité
    sans recréer de widget.

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
    Tout widget du KV qui les référence se redessine automatiquement quand elles
    changent (binding réactif Kivy).
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
        self._popup_event = None    # timer d'auto-fermeture du popup
        self._last_pm10   = None    # dernière valeur PM10 (pour recalcul seuils)
        self._btn_a       = None    # objet button_a pinpong (None si absent)
        self._btn_b       = None    # objet button_b pinpong
        self._prev_a      = False   # état précédent bouton A (détection de front)
        self._prev_b      = False   # état précédent bouton B

        # Verrou global : timestamp jusqu'auquel tout appui est ignoré.
        # Initialisé à 0.0 → aucun verrou actif au démarrage.
        self._btn_lock_until = 0.0

        Window.clearcolor = (0.82, 0.82, 0.82, 1)

    # ── Propriété lecture seule ───────────────────────────────────────────────
    @property
    def current_screen(self) -> str:
        """Retourne le nom de l'écran actif. Utilisé par le Controller."""
        return self.sm.current if hasattr(self, 'sm') else 'accueil'

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        """
        Construit l'arbre de widgets Kivy.
        Appelé automatiquement par ihm.run().
        """
        kv_path = os.path.join(os.path.dirname(__file__), 'ihm.kv')
        Builder.load_file(kv_path)

        self.sm = ScreenManager(transition=NoTransition())

        self.s_accueil         = AccueilScreen(name='accueil')
        self.s_seuils          = SeuilsScreen(name='seuils')
        self.s_reseau          = ReseauScreen(name='reseau')
        self.s_capteur2        = AccueilCapteur2Screen(name='capteur2')
        self.s_seuils_capteur2 = SeuilsCapteur2Screen(name='seuils_capteur2')

        for s in (self.s_accueil, self.s_seuils, self.s_reseau,
                  self.s_capteur2, self.s_seuils_capteur2):
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
        Clock.schedule_interval(self._poll_buttons, BTN_POLL_INTERVAL)
        Window.bind(on_key_down=self._on_key)

        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return root

    # ── Initialisation des boutons UNIHIKER ───────────────────────────────────
    def _init_buttons(self):
        """
        Initialise les objets button_a et button_b de pinpong.
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
        Appelée par Clock.schedule_interval toutes les BTN_POLL_INTERVAL secondes.
        S'exécute dans le thread principal Kivy.

        Stratégie anti-rebond avec verrou global :
          1. Détection du front montant (False → True) sur chaque bouton.
          2. Quand un appui est validé, un verrou est posé pour BTN_LOCK_DELAY
             secondes. Pendant ce temps, aucun bouton ne peut déclencher d'action.
          3. Pendant le verrou, l'état des boutons est quand même lu et mis à jour
             dans _prev_a / _prev_b pour éviter un faux front montant à la
             levée du verrou si le bouton est encore tenu.

        Avantages par rapport à l'ancien debounce par-bouton :
          - Résout les rebonds rapides du bouton A (plusieurs fronts en < 0.35 s).
          - Résout la non-détection du bouton B (poll à 20 ms au lieu de 50 ms).
        """
        if self._btn_a is None:
            return

        now = time.monotonic()

        try:
            a = self._btn_a.is_pressed()
            b = self._btn_b.is_pressed()
        except Exception as e:
            print(f"Erreur lecture boutons : {e}")
            return

        if now < self._btn_lock_until:
            # Verrou actif : on met à jour l'état précédent sans déclencher d'action.
            # Cela évite un faux front montant si le bouton est encore pressé au
            # moment où le verrou expire.
            self._prev_a, self._prev_b = a, b
            return

        # Détection du front montant bouton A
        if a and not self._prev_a:
            self._btn_lock_until = now + BTN_LOCK_DELAY
            self._prev_a, self._prev_b = a, b
            if callable(self.on_btn_a):
                self.on_btn_a()
            return   # on traite un seul bouton par cycle

        # Détection du front montant bouton B
        if b and not self._prev_b:
            self._btn_lock_until = now + BTN_LOCK_DELAY
            self._prev_a, self._prev_b = a, b
            if callable(self.on_btn_b):
                self.on_btn_b()
            return

        self._prev_a, self._prev_b = a, b

    # ── Clavier (test sur PC) ─────────────────────────────────────────────────
    def _on_key(self, window, key, *args):
        """
        Fallback clavier pour tester sans carte UNIHIKER.
        Touche 'a' (keycode 97) → simule le bouton A.
        Touche 'b' (keycode 98) → simule le bouton B.
        Le verrou global s'applique aussi au clavier.
        """
        now = time.monotonic()
        if now < self._btn_lock_until:
            return
        if key == 97 and callable(self.on_btn_a):
            self._btn_lock_until = now + BTN_LOCK_DELAY
            self.on_btn_a()
        elif key == 98 and callable(self.on_btn_b):
            self._btn_lock_until = now + BTN_LOCK_DELAY
            self.on_btn_b()

    # ══════════════════════════════════════════════════════════════════════════
    # API PUBLIQUE — appelée par le Controller, toutes thread-safe
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, screen_name: str):
        """
        Change l'écran affiché.

        :param screen_name: Nom de l'écran cible.
        """
        Clock.schedule_once(
            lambda dt: setattr(self.sm, 'current', screen_name), 0
        )

    def update_pm10(self, pm10: float):
        """
        Met à jour la valeur PM10 sur l'écran d'accueil.

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

        :param eco2: Valeur eCO2 en ppm (premier retour de CCS811.read_eco2_tvoc).
        :param tvoc: Valeur TVOC en ppb (second retour de CCS811.read_eco2_tvoc).
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
        Met à jour les seuils PM10 et recalcule la couleur de la mesure courante.

        :param seuil_vert:   Nouveau seuil vert en ug/m3.
        :param seuil_orange: Nouveau seuil orange en ug/m3.
        """
        def _do(dt):
            self.seuil_vert   = seuil_vert
            self.seuil_orange = seuil_orange
            if self._last_pm10 is not None:
                self.s_accueil.update_pm10(self._last_pm10)
        Clock.schedule_once(_do, 0)

    def update_seuils_tvoc(self, seuil_vert: float, seuil_orange: float):
        """
        Met à jour uniquement les seuils TVOC.
        SeuilsCapteur2Screen se met à jour automatiquement via le binding KV.

        :param seuil_vert:   Nouveau seuil TVOC vert en ppb.
        :param seuil_orange: Nouveau seuil TVOC orange en ppb.
        """
        def _do(dt):
            self.seuil_tvoc_vert   = seuil_vert
            self.seuil_tvoc_orange = seuil_orange
        Clock.schedule_once(_do, 0)

    def update_seuils_co2(self, seuil_vert: float, seuil_orange: float):
        """
        Met à jour uniquement les seuils eCO2.
        SeuilsCapteur2Screen se met à jour automatiquement via le binding KV.

        :param seuil_vert:   Nouveau seuil eCO2 vert en ppm.
        :param seuil_orange: Nouveau seuil eCO2 orange en ppm.
        """
        def _do(dt):
            self.seuil_co2_vert   = seuil_vert
            self.seuil_co2_orange = seuil_orange
        Clock.schedule_once(_do, 0)

    def show_popup(self, titre: str, message: str, duration: float = 4):
        """
        Affiche un popup d'alerte par-dessus l'écran actif.

        :param titre:    Titre de l'alerte (affiché en rouge).
        :param message:  Message détaillé (affiché en blanc).
        :param duration: Secondes avant fermeture automatique (0 = permanent).
        """
        Clock.schedule_once(
            lambda dt: self._do_show_popup(titre, message, duration), 0
        )

    def _do_show_popup(self, titre: str, message: str, duration: float):
        """
        Exécution réelle de l'affichage dans le thread UI.
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