# tests/test_mesure_tvoc_co2.py
"""
Tests unitaires pour Model/MesureTVOC_CO2.py.

Board et Ccs811 sont intégralement simulés.
"""

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys

# ── Stubs pinpong ─────────────────────────────────────────────────────────────
mock_pinpong = MagicMock()
sys.modules['pinpong']       = mock_pinpong
sys.modules['pinpong.board'] = mock_pinpong.board


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_mesure(connected=True, run_in_elapsed=True,
                 data_ready=True, eco2=850, tvoc=320):
    """Crée un mock Ccs811 configuré selon les paramètres."""
    mock_ccs = MagicMock()
    # Simulation de la lecture du registre STATUS (présence physique)
    mock_ccs.i2c.readfrom_mem.return_value = bytes([0x08])
    mock_ccs.data_ready.return_value = data_ready
    mock_ccs.read_eco2_tvoc.return_value = (eco2, tvoc)
    return mock_ccs


# ─────────────────────────────────────────────────────────────────────────────
# Import après stubs
# ─────────────────────────────────────────────────────────────────────────────

from MesureTVOC_CO2 import MesureTVOC_CO2  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mesure_ok():
    """
    Instance de MesureTVOC_CO2 avec CCS811 connecté et run-in écoulé.
    _init_hardware est remplacé pour ne pas toucher au matériel.
    """
    with patch('MesureTVOC_CO2.Board'), \
         patch('MesureTVOC_CO2.Ccs811') as MockCcs811:
        MockCcs811.return_value = _make_mesure()
        m = MesureTVOC_CO2()
        # Forcer le run-in écoulé
        m._reinit_time = time.time() - MesureTVOC_CO2.DUREE_RUN_IN - 1
    return m


@pytest.fixture
def mesure_absent():
    """Instance de MesureTVOC_CO2 dont l'init a échoué (capteur absent)."""
    with patch('MesureTVOC_CO2.Board'), \
         patch('MesureTVOC_CO2.Ccs811') as MockCcs811:
        MockCcs811.return_value.ccs811_init.side_effect = RuntimeError("CCS811 absent")
        m = MesureTVOC_CO2()
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

class TestConstantes:
    def test_duree_run_in(self):
        assert MesureTVOC_CO2.DUREE_RUN_IN == 30


# ─────────────────────────────────────────────────────────────────────────────
# is_connected
# ─────────────────────────────────────────────────────────────────────────────

class TestIsConnected:
    def test_true_si_ccs811_present(self, mesure_ok):
        assert mesure_ok.is_connected is True

    def test_false_si_ccs811_absent(self, mesure_absent):
        assert mesure_absent.is_connected is False


# ─────────────────────────────────────────────────────────────────────────────
# get_mesures — cas nominaux
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMesures:
    def test_retourne_tuple_eco2_tvoc(self, mesure_ok):
        result = mesure_ok.get_mesures()
        assert result is not None
        eco2, tvoc = result
        assert eco2 == 850
        assert tvoc == 320

    def test_retourne_none_si_data_not_ready(self, mesure_ok):
        mesure_ok._ccs811.data_ready.return_value = False
        assert mesure_ok.get_mesures() is None

    def test_retourne_none_pendant_run_in(self, mesure_ok):
        mesure_ok._reinit_time = time.time()   # run-in vient de démarrer
        assert mesure_ok.get_mesures() is None

    def test_retourne_none_si_capteur_absent(self, mesure_absent):
        # _ccs811 est None, _init_hardware échoue encore
        with patch.object(mesure_absent, '_init_hardware', return_value=False):
            assert mesure_absent.get_mesures() is None

    def test_detection_deconnexion_a_chaud(self, mesure_ok):
        """Si readfrom_mem lève une exception, le capteur est marqué absent."""
        mesure_ok._ccs811.i2c.readfrom_mem.side_effect = OSError("I2C error")
        result = mesure_ok.get_mesures()
        assert result is None
        assert mesure_ok._ccs811 is None

    def test_erreur_lecture_remet_capteur_none(self, mesure_ok):
        mesure_ok._ccs811.data_ready.return_value = True
        mesure_ok._ccs811.read_eco2_tvoc.side_effect = Exception("bus error")
        result = mesure_ok.get_mesures()
        assert result is None
        assert mesure_ok._ccs811 is None

    def test_reinit_auto_si_capteur_none(self, mesure_absent):
        """Si _ccs811 est None, _init_hardware est rappelée automatiquement."""
        with patch.object(mesure_absent, '_init_hardware', return_value=False) as mock_init:
            mesure_absent.get_mesures()
        mock_init.assert_called_once()

    def test_valeurs_eco2_tvoc_differentes(self, mesure_ok):
        mesure_ok._ccs811.read_eco2_tvoc.return_value = (400, 0)
        eco2, tvoc = mesure_ok.get_mesures()
        assert eco2 == 400
        assert tvoc == 0


# ─────────────────────────────────────────────────────────────────────────────
# _init_hardware
# ─────────────────────────────────────────────────────────────────────────────

class TestInitHardware:
    def test_board_init_appelee_une_seule_fois(self):
        """Board().begin() ne doit être appelé qu'une fois même si _init_hardware
        est rappelée."""
        with patch('MesureTVOC_CO2.Board') as MockBoard, \
             patch('MesureTVOC_CO2.Ccs811'):
            m = MesureTVOC_CO2()
            m._init_hardware()   # 2e appel
        # begin() appelé une seule fois (flag _board_inited)
        assert MockBoard.return_value.begin.call_count == 1

    def test_retourne_false_si_ccs811_init_echoue(self):
        with patch('MesureTVOC_CO2.Board'), \
             patch('MesureTVOC_CO2.Ccs811') as MockCcs811:
            MockCcs811.return_value.ccs811_init.side_effect = RuntimeError("absent")
            m = MesureTVOC_CO2()
            result = m._init_hardware()
        assert result is False

    def test_retourne_true_si_init_reussie(self):
        with patch('MesureTVOC_CO2.Board'), \
             patch('MesureTVOC_CO2.Ccs811'):
            m = MesureTVOC_CO2()
            result = m._init_hardware()
        assert result is True

    def test_timestamp_reinit_mis_a_jour(self):
        t_avant = time.time()
        with patch('MesureTVOC_CO2.Board'), \
             patch('MesureTVOC_CO2.Ccs811'):
            m = MesureTVOC_CO2()
        assert m._reinit_time >= t_avant
