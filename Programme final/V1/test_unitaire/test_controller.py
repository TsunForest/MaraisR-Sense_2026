# tests/test_controller.py
"""
Tests unitaires pour Controller/Controller.py.

IHM (Kivy), CapteurParticules, MesureTVOC_CO2 et MQTTClient sont tous simulés.
Les threads sont testés via des mocks de threading.Timer.
"""

import serial
import threading
import pytest
from unittest.mock import MagicMock, patch, call, PropertyMock
import sys


# ── Stubs des modules matériels / IHM ─────────────────────────────────────────
def _make_ihm_mock(screen='accueil'):
    ihm = MagicMock()
    type(ihm).current_screen = PropertyMock(return_value=screen)
    return ihm


def _make_controller(
        pm10_ok=True, tvoc_ok=True,
        mqtt_ok=True, ihm_screen='accueil'):
    """
    Construit un Controller entièrement mocké.
    Retourne (ctrl, ihm_mock, mqtt_mock).
    """
    ihm_mock  = _make_ihm_mock(ihm_screen)
    mqtt_mock = MagicMock() if mqtt_ok else None

    capteur_pm10_mock = MagicMock()
    capteur_tvoc_mock = MagicMock()
    capteur_tvoc_mock.is_connected = True

    with patch('Controller.IHM',            return_value=ihm_mock), \
         patch('Controller.CapteurParticules',
               return_value=capteur_pm10_mock if pm10_ok
               else MagicMock(side_effect=serial.SerialException)), \
         patch('Controller.MesureTVOC_CO2',
               return_value=capteur_tvoc_mock if tvoc_ok
               else MagicMock(side_effect=Exception)), \
         patch('Controller.MQTTClient',
               return_value=mqtt_mock if mqtt_ok
               else MagicMock(side_effect=Exception)):
        from Controller import Controller
        ctrl = Controller()

    ctrl.ihm  = ihm_mock
    ctrl.mqtt = mqtt_mock
    return ctrl, ihm_mock, mqtt_mock


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ctrl_deux():
    """Controller avec les deux capteurs disponibles."""
    return _make_controller(pm10_ok=True, tvoc_ok=True)


@pytest.fixture
def ctrl_pm10_seul():
    """Controller avec uniquement PM10."""
    return _make_controller(pm10_ok=True, tvoc_ok=False)


@pytest.fixture
def ctrl_tvoc_seul():
    """Controller avec uniquement TVOC/CO2."""
    return _make_controller(pm10_ok=False, tvoc_ok=True)


@pytest.fixture
def ctrl_aucun():
    """Controller sans capteur détecté."""
    return _make_controller(pm10_ok=False, tvoc_ok=False)


# ─────────────────────────────────────────────────────────────────────────────
# Détection des capteurs
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectionCapteurs:
    def test_pm10_dispo_si_capteur_detecte(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        assert ctrl._pm10_dispo is True

    def test_tvoc_dispo_si_capteur_detecte(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        assert ctrl._tvoc_dispo is True

    def test_deux_capteurs_si_les_deux_ok(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        assert ctrl._deux_capteurs is True

    def test_pm10_non_dispo_si_absent(self, ctrl_tvoc_seul):
        ctrl, _, _ = ctrl_tvoc_seul
        assert ctrl._pm10_dispo is False

    def test_tvoc_non_dispo_si_absent(self, ctrl_pm10_seul):
        ctrl, _, _ = ctrl_pm10_seul
        assert ctrl._tvoc_dispo is False

    def test_deux_capteurs_false_si_pm10_absent(self, ctrl_tvoc_seul):
        ctrl, _, _ = ctrl_tvoc_seul
        assert ctrl._deux_capteurs is False

    def test_deux_capteurs_false_si_tvoc_absent(self, ctrl_pm10_seul):
        ctrl, _, _ = ctrl_pm10_seul
        assert ctrl._deux_capteurs is False


# ─────────────────────────────────────────────────────────────────────────────
# Écran initial
# ─────────────────────────────────────────────────────────────────────────────

class TestEcranInitial:
    def test_accueil_si_pm10_seul(self, ctrl_pm10_seul):
        ctrl, ihm, _ = ctrl_pm10_seul
        ihm.navigate_to.assert_any_call('accueil')

    def test_capteur2_si_tvoc_seul(self, ctrl_tvoc_seul):
        ctrl, ihm, _ = ctrl_tvoc_seul
        ihm.navigate_to.assert_any_call('capteur2')

    def test_accueil_si_deux_capteurs(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ihm.navigate_to.assert_any_call('accueil')

    def test_popup_si_aucun_capteur(self, ctrl_aucun):
        ctrl, ihm, _ = ctrl_aucun
        ihm.show_popup.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# _on_seuils_recus
# ─────────────────────────────────────────────────────────────────────────────

class TestOnSeuilsRecus:
    def test_update_seuils_appele(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ctrl._on_seuils_recus(25.0, 50.0)
        ihm.update_seuils.assert_called_with(25.0, 50.0)

    def test_valeurs_transmises_correctement(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ctrl._on_seuils_recus(10.5, 30.2)
        ihm.update_seuils.assert_called_once_with(10.5, 30.2)


# ─────────────────────────────────────────────────────────────────────────────
# Alternance automatique
# ─────────────────────────────────────────────────────────────────────────────

class TestAlternance:
    def _ctrl_avec_ecran(self, screen):
        """Crée un Controller avec two capteurs et un écran courant donné."""
        ctrl, ihm, _ = _make_controller()
        type(ihm).current_screen = PropertyMock(return_value=screen)
        ctrl.ihm = ihm
        ctrl._pm10_dispo  = True
        ctrl._tvoc_dispo  = True
        ctrl._deux_capteurs = True
        return ctrl, ihm

    def test_accueil_vers_capteur2_en_mode_mesures(self):
        ctrl, ihm = self._ctrl_avec_ecran('accueil')
        ctrl._contexte = "mesures"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('capteur2')

    def test_capteur2_vers_accueil_en_mode_mesures(self):
        ctrl, ihm = self._ctrl_avec_ecran('capteur2')
        ctrl._contexte = "mesures"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('accueil')

    def test_seuils_vers_seuils_tvoc_en_mode_seuils(self):
        ctrl, ihm = self._ctrl_avec_ecran('seuils')
        ctrl._contexte = "seuils"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('seuils_tvoc')

    def test_seuils_tvoc_vers_seuils_co2(self):
        ctrl, ihm = self._ctrl_avec_ecran('seuils_tvoc')
        ctrl._contexte = "seuils"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('seuils_co2')

    def test_seuils_co2_vers_seuils(self):
        ctrl, ihm = self._ctrl_avec_ecran('seuils_co2')
        ctrl._contexte = "seuils"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('seuils')

    def test_alterner_rearme_le_timer(self):
        ctrl, ihm = self._ctrl_avec_ecran('accueil')
        ctrl._contexte = "mesures"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ctrl._demarrer_alternance.assert_called_once()

    def test_tvoc_seul_seuils_tvoc_vers_co2(self):
        ctrl, ihm = self._ctrl_avec_ecran('seuils_tvoc')
        ctrl._pm10_dispo    = False
        ctrl._tvoc_dispo    = True
        ctrl._deux_capteurs = False
        ctrl._contexte      = "seuils"
        ctrl._demarrer_alternance = MagicMock()
        ctrl._alterner()
        ihm.navigate_to.assert_called_with('seuils_co2')


# ─────────────────────────────────────────────────────────────────────────────
# _arreter_alternance / _annuler_retour_auto
# ─────────────────────────────────────────────────────────────────────────────

class TestTimers:
    def test_arreter_alternance_annule_timer_vivant(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        mock_timer = MagicMock()
        mock_timer.is_alive.return_value = True
        ctrl._alt_timer = mock_timer
        ctrl._arreter_alternance()
        mock_timer.cancel.assert_called_once()
        assert ctrl._alt_timer is None

    def test_arreter_alternance_ignore_timer_mort(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        mock_timer = MagicMock()
        mock_timer.is_alive.return_value = False
        ctrl._alt_timer = mock_timer
        ctrl._arreter_alternance()
        mock_timer.cancel.assert_not_called()

    def test_annuler_retour_auto_annule_timer(self, ctrl_deux):
        ctrl, _, _ = ctrl_deux
        mock_timer = MagicMock()
        mock_timer.is_alive.return_value = True
        ctrl._retour_timer = mock_timer
        ctrl._annuler_retour_auto()
        mock_timer.cancel.assert_called_once()
        assert ctrl._retour_timer is None


# ─────────────────────────────────────────────────────────────────────────────
# Navigation — bouton A
# ─────────────────────────────────────────────────────────────────────────────

class TestBtnA:
    def _ctrl_mesures(self, screen='accueil'):
        ctrl, ihm, _ = _make_controller()
        type(ihm).current_screen = PropertyMock(return_value=screen)
        ctrl.ihm        = ihm
        ctrl._contexte  = "mesures"
        ctrl._pm10_dispo = True
        ctrl._tvoc_dispo = True
        ctrl._arreter_alternance  = MagicMock()
        ctrl._annuler_retour_auto = MagicMock()
        ctrl._demarrer_alternance = MagicMock()
        ctrl._armer_retour_auto   = MagicMock()
        return ctrl, ihm

    def test_contexte_devient_seuils(self):
        ctrl, ihm = self._ctrl_mesures('accueil')
        ctrl._btn_a_appuye()
        assert ctrl._contexte == "seuils"

    def test_navigate_vers_seuils_depuis_accueil(self):
        ctrl, ihm = self._ctrl_mesures('accueil')
        ctrl._btn_a_appuye()
        ihm.navigate_to.assert_called_with('seuils')

    def test_navigate_vers_seuils_tvoc_depuis_capteur2(self):
        ctrl, ihm = self._ctrl_mesures('capteur2')
        ctrl._pm10_dispo = False
        ctrl._btn_a_appuye()
        ihm.navigate_to.assert_called_with('seuils_tvoc')

    def test_retour_immediat_depuis_seuils(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._contexte = "seuils"
        ctrl._retour_mesures = MagicMock()
        ctrl._btn_a_appuye()
        ctrl._retour_mesures.assert_called_once()

    def test_retour_auto_arme_apres_entree_seuils(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._btn_a_appuye()
        ctrl._armer_retour_auto.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Navigation — bouton B
# ─────────────────────────────────────────────────────────────────────────────

class TestBtnB:
    def _ctrl_mesures(self):
        ctrl, ihm, _ = _make_controller()
        type(ihm).current_screen = PropertyMock(return_value='accueil')
        ctrl.ihm        = ihm
        ctrl._contexte  = "mesures"
        ctrl._arreter_alternance  = MagicMock()
        ctrl._annuler_retour_auto = MagicMock()
        ctrl._armer_retour_auto   = MagicMock()
        return ctrl, ihm

    def test_contexte_devient_reseau(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._btn_b_appuye()
        assert ctrl._contexte == "reseau"

    def test_navigate_vers_reseau(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._btn_b_appuye()
        ihm.navigate_to.assert_called_with('reseau')

    def test_retour_depuis_reseau(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._contexte = "reseau"
        ctrl._retour_mesures = MagicMock()
        ctrl._btn_b_appuye()
        ctrl._retour_mesures.assert_called_once()

    def test_retour_auto_arme_en_entrant_reseau(self):
        ctrl, ihm = self._ctrl_mesures()
        ctrl._btn_b_appuye()
        ctrl._armer_retour_auto.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# _retour_mesures
# ─────────────────────────────────────────────────────────────────────────────

class TestRetourMesures:
    def test_contexte_revient_a_mesures(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ctrl._contexte = "seuils"
        ctrl._retour_mesures()
        assert ctrl._contexte == "mesures"

    def test_navigate_accueil_si_pm10_dispo(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ctrl._pm10_dispo = True
        ctrl._retour_mesures()
        ihm.navigate_to.assert_called_with('accueil')

    def test_navigate_capteur2_si_pm10_absent(self, ctrl_tvoc_seul):
        ctrl, ihm, _ = ctrl_tvoc_seul
        ctrl._retour_mesures()
        ihm.navigate_to.assert_called_with('capteur2')

    def test_alternance_redemarre_si_deux_capteurs(self, ctrl_deux):
        ctrl, ihm, _ = ctrl_deux
        ctrl._demarrer_alternance = MagicMock()
        ctrl._retour_mesures()
        ctrl._demarrer_alternance.assert_called_once()

    def test_pas_d_alternance_si_un_seul_capteur(self, ctrl_pm10_seul):
        ctrl, ihm, _ = ctrl_pm10_seul
        ctrl._demarrer_alternance = MagicMock()
        ctrl._retour_mesures()
        ctrl._demarrer_alternance.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# prise_mesure_et_envoi — démarrage des threads
# ─────────────────────────────────────────────────────────────────────────────

class TestPriseMesure:
    def test_thread_pm10_demarre_si_pm10_dispo(self, ctrl_pm10_seul):
        ctrl, ihm, _ = ctrl_pm10_seul
        ihm.run.side_effect = KeyboardInterrupt   # stoppe la boucle Kivy
        with patch('threading.Thread') as MockThread:
            mock_t = MagicMock()
            MockThread.return_value = mock_t
            try:
                ctrl.prise_mesure_et_envoi()
            except SystemExit:
                pass
        # Au moins un thread créé pour PM10
        assert MockThread.called

    def test_mqtt_disconnect_dans_finally(self, ctrl_pm10_seul):
        ctrl, ihm, mqtt = ctrl_pm10_seul
        ihm.run.side_effect = KeyboardInterrupt
        with patch('threading.Thread'):
            try:
                ctrl.prise_mesure_et_envoi()
            except SystemExit:
                pass
        mqtt.disconnect.assert_called()
