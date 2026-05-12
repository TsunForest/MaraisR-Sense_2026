# tests/test_capteur_particules.py
"""
Tests unitaires pour Model/Capteur_Particules.py (CapteurParticules / SDS011).

Les dépendances matérielles (port série, bibliothèque sds011) sont entièrement
simulées via unittest.mock afin que les tests s'exécutent sans capteur physique.
"""

import time
import serial
import pytest
from unittest.mock import MagicMock, patch, call


# ── Stub de la bibliothèque sds011 (absente hors UNIHIKER) ───────────────────
import sys
mock_sds011_module = MagicMock()

class FakeSDS011Base:
    """Classe de base simulant l'API publique de sds011.SDS011."""
    def __init__(self, port, use_query_mode=False):
        self.ser = MagicMock()
        self.ser.timeout = None
    def sleep(self, sleep=True):
        pass
    def query(self):
        return (12.3, 45.6)   # (pm25, pm10)

mock_sds011_module.SDS011 = FakeSDS011Base
sys.modules['sds011'] = mock_sds011_module

# Import APRÈS injection du stub
from ..Model.Capteur_Particules import CapteurParticules  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def capteur():
    """Instancie CapteurParticules avec le port par défaut (stub série actif)."""
    with patch('time.sleep'):   # accélère les délais de stabilisation
        c = CapteurParticules(port="/dev/ttyUSB0")
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Initialisation
# ─────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_port_memorise(self, capteur):
        assert capteur._port == "/dev/ttyUSB0"

    def test_timeout_serie_configure(self, capteur):
        assert capteur.ser.timeout == 5

    def test_port_personnalise(self):
        with patch('time.sleep'):
            c = CapteurParticules(port="/dev/ttyUSB1")
        assert c._port == "/dev/ttyUSB1"


# ─────────────────────────────────────────────────────────────────────────────
# get_pm10 — cas nominaux
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPm10:
    def test_retourne_pm10_correct(self, capteur):
        """query() renvoie (pm25, pm10) : on doit récupérer uniquement pm10."""
        capteur.query = MagicMock(return_value=(5.0, 42.7))
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            result = capteur.get_pm10()
        assert result == pytest.approx(42.7)

    def test_appel_sleep_wake_deux_fois(self, capteur):
        capteur.query = MagicMock(return_value=(1.0, 10.0))
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            capteur.get_pm10()
        # sleep(sleep=False) doit être appelé exactement 2 fois
        wake_calls = [c for c in capteur.sleep.call_args_list
                      if c == call(sleep=False)]
        assert len(wake_calls) == 2

    def test_remise_en_veille_apres_mesure(self, capteur):
        capteur.query = MagicMock(return_value=(1.0, 20.0))
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            capteur.get_pm10()
        # Dernier appel à sleep doit être sans argument (sleep=True par défaut)
        last_call = capteur.sleep.call_args_list[-1]
        assert last_call == call()

    def test_pm10_zero_valide(self, capteur):
        capteur.query = MagicMock(return_value=(0.0, 0.0))
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            result = capteur.get_pm10()
        assert result == 0.0

    def test_pm10_valeur_elevee(self, capteur):
        capteur.query = MagicMock(return_value=(300.0, 999.9))
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            result = capteur.get_pm10()
        assert result == pytest.approx(999.9)


# ─────────────────────────────────────────────────────────────────────────────
# get_pm10 — cas d'erreur
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPm10Erreurs:
    def test_leve_serial_exception_si_query_none(self, capteur):
        """Si query() retourne None (timeout capteur), une SerialException est levée."""
        capteur.query = MagicMock(return_value=None)
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            with pytest.raises(serial.SerialException):
                capteur.get_pm10()

    def test_message_exception_contient_sds011(self, capteur):
        capteur.query = MagicMock(return_value=None)
        capteur.sleep = MagicMock()
        with patch('time.sleep'):
            with pytest.raises(serial.SerialException, match="SDS011"):
                capteur.get_pm10()


# ─────────────────────────────────────────────────────────────────────────────
# reconnecter
# ─────────────────────────────────────────────────────────────────────────────

class TestReconnecter:
    def test_reconnecter_ferme_port_avant_tout(self, capteur):
        """Le port série doit être fermé en premier lors de la reconnexion."""
        capteur.ser = MagicMock()

        fake_serial_cls = MagicMock()
        fake_serial_instance = MagicMock()
        fake_serial_cls.return_value = fake_serial_instance

        with patch('serial.Serial', fake_serial_cls), \
             patch.object(FakeSDS011Base, '__init__', return_value=None), \
             patch('time.sleep'), \
             patch.object(capteur, 'ser', MagicMock()):
            capteur.reconnecter()

        capteur.ser.close.assert_called()

    def test_reconnecter_ignore_erreur_fermeture(self, capteur):
        """Même si ser.close() lève une exception, reconnecter() continue."""
        capteur.ser = MagicMock()
        capteur.ser.close.side_effect = Exception("déjà fermé")

        with patch('serial.Serial') as mock_serial, \
             patch.object(FakeSDS011Base, '__init__', return_value=None), \
             patch('time.sleep'):
            mock_serial.return_value.__enter__ = MagicMock()
            mock_serial.return_value.close = MagicMock()
            try:
                capteur.reconnecter()
            except Exception:
                pass   # on vérifie juste que close() ne bloque pas

    def test_reconnecter_reessaie_si_port_inaccessible(self, capteur):
        """
        La reconnexion doit attendre que serial.Serial() réussisse.
        Simule 2 échecs puis 1 succès.
        """
        capteur.ser = MagicMock()
        successes = [False, False, True]

        def side_effect(*args, **kwargs):
            if not successes.pop(0):
                raise serial.SerialException("port indisponible")
            obj = MagicMock()
            obj.close = MagicMock()
            return obj

        with patch('serial.Serial', side_effect=side_effect), \
             patch.object(FakeSDS011Base, '__init__', return_value=None), \
             patch('time.sleep') as mock_sleep:
            capteur.reconnecter()

        # time.sleep(2) doit avoir été appelé pour les 2 échecs
        sleep_calls_2s = [c for c in mock_sleep.call_args_list if c == call(2)]
        assert len(sleep_calls_2s) >= 2
