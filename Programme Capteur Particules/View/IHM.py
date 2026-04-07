# View/IHM.py
"""
Vue MVC de l'application — logique pure, tout le layout est dans ihm.kv.

Rôle : afficher les données fournies par le Controller, gérer les entrées
physiques (boutons A/B) et exposer une API publique thread-safe.

Propriétés Kivy sur l'App (accessibles dans ihm.kv via 'app.xxx') :
    seuil_vert, seuil_orange          — seuils PM10   (µg/m³)
    seuil_tvoc_vert, seuil_tvoc_orange — seuils TVOC  (ppb)  [non utilisés]
    seuil_co2_vert,  seuil_co2_orange  — seuils CO2   (ppm)  [non utilisés]

Callbacks à brancher depuis le Controller AVANT ihm.run() :
    ihm.on_btn_a = callable()
    ihm.on_btn_b = callable()

API publique (toutes thread-safe) :
    ihm.navigate_to(name)
    ihm.update_pm10(pm10)
    ihm.update_tvoc_co2(tvoc, co2)         [non utilisé pour l'instant]
    ihm.update_seuils(sv, so)
    ihm.update_seuils_capteur2(sv, so, cv, co)  [non utilisé pour l'instant]
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
Config.set('graphics', 'rotation',   '90')    # rotation → paysage effectif 320×240
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
from kivy.properties         import (BooleanProperty, ListProperty, NumericProperty, StringProperty)
from kivy.uix.floatlayout    import FloatLayout
from kivy.uix.boxlayout      import BoxLayout
from kivy.uix.screenmanager  import ScreenManager, Screen, NoTransition

# ── Constantes ────────────────────────────────────────────────────────────────
# Intervalle de polling des boutons physiques (secondes)
GPIO_POLL_INTERVAL = 0.05

# Délai minimum entre deux appuis acceptés (anti-rebond logiciel)
DEBOUNCE_DELAY = 0.35

# Seuils par défaut utilisés si aucun message MQTT n'est reçu
SEUIL_VERT_DEFAUT         = 25.0    # PM10  µg/m³
SEUIL_ORANGE_DEFAUT       = 50.0    # PM10  µg/m³
SEUIL_TVOC_VERT_DEFAUT    = 220.0   # TVOC  ppb
SEUIL_TVOC_ORANGE_DEFAUT  = 660.0   # TVOC  ppb
SEUIL_CO2_VERT_DEFAUT     = 800.0   # CO2   ppm
SEUIL_CO2_ORANGE_DEFAUT   = 1200.0  # CO2   ppm

# Couleurs RGBA (listes car Kivy utilise des listes pour ListProperty)
C_VERT   = [0.13, 0.86, 0.13, 1]   # vert  : qualité bonne
C_ORANGE = [1.00, 0.60, 0.00, 1]   # orange : qualité moyenne
C_ROUGE  = [0.95, 0.15, 0.15, 1]   # rouge  : mauvaise qualité
C_DARK   = [0.35, 0.35, 0.35, 1]   # gris foncé : état initial (pas de mesure)


# ── Helpers réseau (exécutés dans un thread de fond pour ne pas bloquer l'UI) ─
def _get_ip() -> str:
    """
    Retourne l'adresse IP locale en tentant une connexion UDP vers 8.8.8.8.
    Aucun paquet n'est envoyé, c'est juste un trick pour connaître l'interface
    réseau active sans avoir besoin de parser ifconfig/ip.
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
    Retourne l'adresse MAC de l'interface principale sous forme
    xx:xx:xx:xx:xx:xx via uuid.getnode().
    """
    try:
        n = uuid.getnode()
        return ':'.join(f'{(n >> (8 * i)) & 0xff:02x}' for i in range(5, -1, -1))
    except Exception:
        return "Non disponible"


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 1 – Accueil PM10
# ══════════════════════════════════════════════════════════════════════════════
class AccueilScreen(Screen):
    """
    Écran principal : affiche la mesure PM10 avec un fond coloré selon le seuil
    et une horloge temps réel.

    Propriétés bindées dans ihm.kv :
        pm10_color  : couleur du fond du bloc mesure
        val_text    : valeur affichée (ex. "42.3 µg/m³")
        state_text  : état qualitatif (ex. "Qualité moyenne")
        time_text   : horloge (ex. "07/04  14:32:05")
    """
    pm10_color = ListProperty(C_DARK)
    val_text   = StringProperty('-- µg/m³')
    state_text = StringProperty('En attente de la première mesure…')
    time_text  = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Mise à jour de l'horloge chaque seconde via Clock
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        """Appelée par Clock toutes les secondes pour rafraîchir l'horloge."""
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_pm10(self, pm10: float):
        """
        Met à jour la valeur affichée et la couleur de fond selon les seuils actifs.
        Les seuils sont lus depuis l'instance App (App.get_running_app()).
        """
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
# ÉCRAN 2 – Seuils PM10
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsScreen(Screen):
    """
    Écran des seuils PM10.
    Pas de propriétés propres : le KV lit directement app.seuil_vert et
    app.seuil_orange, ce qui assure une mise à jour automatique lors d'un
    changement de seuils via MQTT.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 3 – Configuration réseau
# ══════════════════════════════════════════════════════════════════════════════
class ReseauScreen(Screen):
    """
    Écran réseau : affiche l'IP et la MAC de la carte.
    Les valeurs sont récupérées dans un thread de fond à chaque entrée dans
    l'écran pour ne pas bloquer l'UI pendant la résolution réseau.

    Propriétés bindées dans ihm.kv :
        ip_text  : adresse IP (ex. "192.168.1.42")
        mac_text : adresse MAC (ex. "62:03:57:41:38:23")
    """
    ip_text  = StringProperty('…')
    mac_text = StringProperty('…')

    def on_enter(self, *args):
        """Déclenché automatiquement par Kivy à chaque affichage de l'écran."""
        self.ip_text  = '…'
        self.mac_text = '…'
        # Lancement dans un thread pour ne pas bloquer l'UI
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        """Récupère IP et MAC dans le thread de fond, puis repasse sur le thread UI."""
        ip, mac = _get_ip(), _get_mac()
        # Clock.schedule_once est obligatoire pour toucher les propriétés Kivy
        # depuis un thread autre que le thread principal
        Clock.schedule_once(lambda dt: self._set(ip, mac), 0)

    def _set(self, ip: str, mac: str):
        """Met à jour les labels (appelé dans le thread UI via Clock)."""
        self.ip_text  = ip
        self.mac_text = mac


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 4 – Accueil TVOC + CO2  (NON UTILISÉ POUR L'INSTANT)
# ══════════════════════════════════════════════════════════════════════════════
class AccueilCapteur2Screen(Screen):
    """
    Écran d'accueil pour les capteurs de qualité d'air intérieur (TVOC + CO2).
    Deux blocs colorés empilés, un par capteur.
    NON UTILISÉ POUR L'INSTANT — en attente d'intégration du capteur physique.

    Propriétés bindées dans ihm.kv :
        tvoc_color      : couleur du fond du bloc TVOC
        tvoc_val_text   : valeur TVOC affichée (ex. "320 ppb")
        tvoc_state_text : état qualitatif TVOC
        co2_color       : couleur du fond du bloc CO2
        co2_val_text    : valeur CO2 affichée (ex. "850 ppm")
        co2_state_text  : état qualitatif CO2
        time_text       : horloge partagée
    """
    tvoc_color      = ListProperty(C_DARK)
    tvoc_val_text   = StringProperty('-- ppb')
    tvoc_state_text = StringProperty('En attente…')
    co2_color       = ListProperty(C_DARK)
    co2_val_text    = StringProperty('-- ppm')
    co2_state_text  = StringProperty('En attente…')
    time_text       = StringProperty('--:--:--')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Horloge partagée avec AccueilScreen (même format)
        Clock.schedule_interval(self._tick, 1)

    def _tick(self, dt):
        """Mise à jour de l'horloge chaque seconde."""
        self.time_text = datetime.now().strftime('%d/%m  %H:%M:%S')

    def update_tvoc(self, tvoc: float):
        """
        Met à jour l'affichage TVOC selon les seuils actifs.
        Les seuils sont lus depuis app.seuil_tvoc_vert / seuil_tvoc_orange.
        """
        app = App.get_running_app()
        sv  = app.seuil_tvoc_vert
        so  = app.seuil_tvoc_orange

        self.tvoc_val_text = f'{tvoc:.0f} ppb'

        if tvoc < sv:
            self.tvoc_color      = C_VERT
            self.tvoc_state_text = f'Bon  (< {sv:.0f} ppb)'
        elif tvoc < so:
            self.tvoc_color      = C_ORANGE
            self.tvoc_state_text = f'Moyen  ({sv:.0f}–{so:.0f} ppb)'
        else:
            self.tvoc_color      = C_ROUGE
            self.tvoc_state_text = f'Mauvais  (≥ {so:.0f} ppb) !'

    def update_co2(self, co2: float):
        """
        Met à jour l'affichage CO2 selon les seuils actifs.
        Les seuils sont lus depuis app.seuil_co2_vert / seuil_co2_orange.
        """
        app = App.get_running_app()
        sv  = app.seuil_co2_vert
        so  = app.seuil_co2_orange

        self.co2_val_text = f'{co2:.0f} ppm'

        if co2 < sv:
            self.co2_color      = C_VERT
            self.co2_state_text = f'Bon  (< {sv:.0f} ppm)'
        elif co2 < so:
            self.co2_color      = C_ORANGE
            self.co2_state_text = f'Moyen  ({sv:.0f}–{so:.0f} ppm)'
        else:
            self.co2_color      = C_ROUGE
            self.co2_state_text = f'Mauvais  (≥ {so:.0f} ppm) !'


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRAN 5 – Seuils TVOC + CO2  (NON UTILISÉ POUR L'INSTANT)
# ══════════════════════════════════════════════════════════════════════════════
class SeuilsCapteur2Screen(Screen):
    """
    Écran des seuils pour TVOC et CO2.
    Comme SeuilsScreen, pas de propriétés propres : le KV lit directement
    app.seuil_tvoc_* et app.seuil_co2_*.
    NON UTILISÉ POUR L'INSTANT.
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# POPUP overlay
# ══════════════════════════════════════════════════════════════════════════════
class PopupOverlay(BoxLayout):
    """
    Bandeau d'alerte semi-transparent affiché par-dessus n'importe quel écran.
    Rendu visible/invisible via la BooleanProperty is_visible, ce qui modifie
    simplement l'opacité sans recréer de widgets.

    Propriétés bindées dans ihm.kv :
        is_visible : contrôle l'opacité (True = affiché, False = invisible)
        titre      : titre de l'alerte (affiché en rouge)
        message    : message détaillé (affiché en blanc)
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

    Propriétés Kivy déclarées ici pour être accessibles dans ihm.kv via 'app.xxx'.
    Elles sont observables : tout widget du KV qui les référence se met à jour
    automatiquement lorsqu'elles changent.
    """

    # ── Seuils PM10 ───────────────────────────────────────────────────────────
    seuil_vert   = NumericProperty(SEUIL_VERT_DEFAUT)
    seuil_orange = NumericProperty(SEUIL_ORANGE_DEFAUT)

    # ── Seuils TVOC (non utilisés pour l'instant) ─────────────────────────────
    seuil_tvoc_vert   = NumericProperty(SEUIL_TVOC_VERT_DEFAUT)
    seuil_tvoc_orange = NumericProperty(SEUIL_TVOC_ORANGE_DEFAUT)

    # ── Seuils CO2 (non utilisés pour l'instant) ──────────────────────────────
    seuil_co2_vert   = NumericProperty(SEUIL_CO2_VERT_DEFAUT)
    seuil_co2_orange = NumericProperty(SEUIL_CO2_ORANGE_DEFAUT)

    # Callbacks branchés par le Controller AVANT ihm.run()
    # Rester à None tant qu'ils ne sont pas branchés
    on_btn_a = None
    on_btn_b = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._popup_event  = None    # référence au timer d'auto-fermeture du popup
        self._last_pm10    = None    # dernière valeur PM10 reçue (pour recalcul seuils)
        self._btn_a        = None    # objet button_a pinpong (None si absent)
        self._btn_b        = None    # objet button_b pinpong
        self._prev_a       = False   # état précédent du bouton A (détection de front)
        self._prev_b       = False   # état précédent du bouton B
        self._last_press_a = 0.0     # timestamp du dernier appui validé (debounce)
        self._last_press_b = 0.0
        Window.clearcolor  = (0.82, 0.82, 0.82, 1)   # fond gris cohérent avec les écrans

    # ── Propriété lecture seule ───────────────────────────────────────────────
    @property
    def current_screen(self) -> str:
        """Retourne le nom de l'écran actif. Utilisé par le Controller."""
        return self.sm.current if hasattr(self, 'sm') else 'accueil'

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(self):
        """
        Point d'entrée Kivy. Construit l'arbre de widgets et configure les écrans.
        Appelé automatiquement par ihm.run().
        """
        # Chargement explicite du KV depuis le même dossier que ce fichier
        # (robuste quel que soit le répertoire de travail courant)
        kv_path = os.path.join(os.path.dirname(__file__), 'ihm.kv')
        Builder.load_file(kv_path)

        # ── Création du ScreenManager (NoTransition = changement instantané) ──
        self.sm = ScreenManager(transition=NoTransition())

        # Écrans actifs
        self.s_accueil = AccueilScreen(name='accueil')
        self.s_seuils  = SeuilsScreen(name='seuils')
        self.s_reseau  = ReseauScreen(name='reseau')

        # Écrans préparés mais non accessibles (pas de navigation vers eux)
        self.s_capteur2       = AccueilCapteur2Screen(name='capteur2')
        self.s_seuils_capteur2 = SeuilsCapteur2Screen(name='seuils_capteur2')

        # Ajout de tous les écrans au gestionnaire
        for s in (self.s_accueil, self.s_seuils, self.s_reseau,
                  self.s_capteur2, self.s_seuils_capteur2):
            self.sm.add_widget(s)

        # ── Popup overlay ─────────────────────────────────────────────────────
        self._popup = PopupOverlay(
            size_hint=(0.88, None),
            height=90,
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        # ── FloatLayout racine : ScreenManager + popup par-dessus ─────────────
        # FloatLayout permet de superposer le popup au-dessus des écrans
        root = FloatLayout()
        root.add_widget(self.sm)
        root.add_widget(self._popup)

        # ── Boutons physiques UNIHIKER ────────────────────────────────────────
        # Doit être dans build() car pinpong doit s'initialiser dans le thread principal
        self._init_buttons()

        # Polling des boutons via Clock (thread principal → pas d'erreur signal)
        Clock.schedule_interval(self._poll_buttons, GPIO_POLL_INTERVAL)

        # Fallback clavier pour tests sur PC
        Window.bind(on_key_down=self._on_key)

        # Si une mesure PM10 a été stockée avant que l'UI soit prête
        if self._last_pm10 is not None:
            self.s_accueil.update_pm10(self._last_pm10)

        return root

    # ── Initialisation boutons UNIHIKER ───────────────────────────────────────
    def _init_buttons(self):
        """
        Initialise les objets button_a et button_b de la bibliothèque pinpong.
        Ces objets représentent les boutons physiques intégrés à la carte.
        Silencieux si pinpong est absent (mode test PC).
        """
        try:
            from pinpong.board import Board
            from pinpong.extension.unihiker import button_a, button_b
            Board().begin()
            self._btn_a = button_a
            self._btn_b = button_b
            print("Boutons A/B UNIHIKER initialisés")
        except ImportError:
            print("pinpong absent — mode PC, utilisez les touches [a] et [b]")
        except Exception as e:
            print(f"Erreur initialisation boutons : {e}")

    # ── Polling boutons ───────────────────────────────────────────────────────
    def _poll_buttons(self, dt):
        """
        Appelée par Clock.schedule_interval toutes les GPIO_POLL_INTERVAL secondes.
        Tournant dans le thread principal Kivy → pas de problème avec les signaux.

        Logique de détection :
          - is_pressed() retourne True tant que le bouton est enfoncé
          - On déclenche l'action uniquement sur le FRONT MONTANT (False → True)
            pour éviter les appuis répétés si le bouton reste enfoncé
          - Le debounce (DEBOUNCE_DELAY) empêche les double-appuis dus aux rebonds
            mécaniques du bouton
        """
        if self._btn_a is None:
            return   # pinpong non disponible, rien à faire
        try:
            now = time.monotonic()   # horloge monotone, non affectée par les changements système
            a   = self._btn_a.is_pressed()
            b   = self._btn_b.is_pressed()

            # Bouton A : front montant + debounce
            if a and not self._prev_a and now - self._last_press_a >= DEBOUNCE_DELAY:
                self._last_press_a = now
                if callable(self.on_btn_a):
                    self.on_btn_a()   # délègue la décision de navigation au Controller

            # Bouton B : front montant + debounce
            if b and not self._prev_b and now - self._last_press_b >= DEBOUNCE_DELAY:
                self._last_press_b = now
                if callable(self.on_btn_b):
                    self.on_btn_b()

            # Mémorisation de l'état pour le prochain tick
            self._prev_a, self._prev_b = a, b

        except Exception as e:
            print(f"Erreur lecture boutons : {e}")

    # ── Clavier (test PC) ─────────────────────────────────────────────────────
    def _on_key(self, window, key, *args):
        """
        Fallback clavier pour tester sans carte UNIHIKER.
        Touche 'a' (keycode 97) → simule le bouton A
        Touche 'b' (keycode 98) → simule le bouton B
        """
        if key == 97 and callable(self.on_btn_a):
            self.on_btn_a()
        elif key == 98 and callable(self.on_btn_b):
            self.on_btn_b()

    # ══════════════════════════════════════════════════════════════════════════
    # API PUBLIQUE — appelée par le Controller, toutes thread-safe
    # Thread-safe = utilise Clock.schedule_once pour repasser dans le thread UI
    # ══════════════════════════════════════════════════════════════════════════

    def navigate_to(self, screen_name: str):
        """
        Change l'écran affiché.
        Thread-safe : l'assignation réelle est postée dans la file Kivy.
        """
        Clock.schedule_once(lambda dt: setattr(self.sm, 'current', screen_name), 0)

    def update_pm10(self, pm10: float):
        """
        Met à jour la valeur PM10 affichée sur l'écran d'accueil.
        Stocke aussi la dernière valeur pour recalcul si les seuils changent.
        """
        self._last_pm10 = pm10
        if hasattr(self, 's_accueil'):
            Clock.schedule_once(lambda dt: self.s_accueil.update_pm10(pm10), 0)

    def update_tvoc_co2(self, tvoc: float, co2: float):
        """
        Met à jour les valeurs TVOC et CO2 sur l'écran capteur2.
        NON UTILISÉ POUR L'INSTANT — préparé pour l'intégration future.
        """
        if hasattr(self, 's_capteur2'):
            Clock.schedule_once(
                lambda dt: (self.s_capteur2.update_tvoc(tvoc),
                            self.s_capteur2.update_co2(co2)), 0
            )

    def update_seuils(self, seuil_vert: float, seuil_orange: float):
        """
        Met à jour les seuils PM10.
        Comme seuil_vert et seuil_orange sont des NumericProperty sur l'App,
        tous les widgets du KV qui les référencent (SeuilsScreen) se
        mettent à jour automatiquement.
        Recalcule aussi la couleur de la mesure actuelle.
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
        Met à jour les seuils TVOC et CO2.
        NON UTILISÉ POUR L'INSTANT — préparé pour l'intégration future.
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
        duration : secondes avant fermeture automatique (0 = permanent).
        Thread-safe.
        """
        Clock.schedule_once(
            lambda dt: self._do_show_popup(titre, message, duration), 0
        )

    def _do_show_popup(self, titre: str, message: str, duration: float):
        """
        Exécution réelle de l'affichage du popup (dans le thread UI).
        Annule un éventuel timer de fermeture précédent avant d'en armer un nouveau.
        """
        if self._popup_event:
            self._popup_event.cancel()
            self._popup_event = None
        self._popup.show(titre, message)
        if duration > 0:
            # Arme la fermeture automatique après 'duration' secondes
            self._popup_event = Clock.schedule_once(
                lambda dt: self.hide_popup(), duration
            )

    def hide_popup(self):
        """Masque le popup. Thread-safe."""
        Clock.schedule_once(lambda dt: self._popup.hide(), 0)