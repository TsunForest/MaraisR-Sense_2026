# tests/test_ccs811.py
"""
Tests unitaires pour Model/Ccs811.py.

Le bus I2C (pinpong.board.I2C) est entièrement simulé.
"""

import pytest
from unittest.mock import MagicMock, patch, call
import sys

# ── Stub pinpong ──────────────────────────────────────────────────────────────
mock_pinpong = MagicMock()
mock_i2c_instance = MagicMock()
mock_pinpong.board.I2C.return_value = mock_i2c_instance
sys.modules['pinpong']              = mock_pinpong
sys.modules['pinpong.board']        = mock_pinpong.board

from ..Model.Ccs811 import Ccs811  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_i2c_mock():
    """Remet le mock I2C à zéro avant chaque test."""
    mock_i2c_instance.reset_mock()
    yield


@pytest.fixture
def ccs():
    return Ccs811()


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de classe
# ─────────────────────────────────────────────────────────────────────────────

class TestConstantes:
    def test_adresse_i2c(self):
        assert Ccs811.CCS811_ADDR == 0x5A

    def test_hw_id_attendu(self):
        assert Ccs811.HW_ID_EXPECTED == 0x81

    def test_registre_status(self):
        assert Ccs811.REG_STATUS == 0x00

    def test_registre_meas_mode(self):
        assert Ccs811.REG_MEAS_MODE == 0x01

    def test_registre_alg_result(self):
        assert Ccs811.REG_ALG_RESULT == 0x02

    def test_registre_hw_id(self):
        assert Ccs811.REG_HW_ID == 0x20

    def test_registre_app_start(self):
        assert Ccs811.REG_APP_START == 0xF4


# ─────────────────────────────────────────────────────────────────────────────
# Primitives d'accès registres
# ─────────────────────────────────────────────────────────────────────────────

class TestReadReg:
    def test_lecture_1_octet(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0xAB])
        result = ccs.read_reg(0x00, 1)
        assert result == [0xAB]

    def test_lecture_4_octets(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x02, 0x58, 0x01, 0x40])
        result = ccs.read_reg(0x02, 4)
        assert result == [0x02, 0x58, 0x01, 0x40]

    def test_appel_readfrom_mem_correct(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x00])
        ccs.read_reg(0x20, 1)
        mock_i2c_instance.readfrom_mem.assert_called_once_with(0x5A, 0x20, 1)

    def test_retourne_liste(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x10, 0x20])
        result = ccs.read_reg(0x00, 2)
        assert isinstance(result, list)


class TestWriteReg:
    def test_appel_writeto_mem_correct(self, ccs):
        ccs.write_reg(0x01, [0x10])
        mock_i2c_instance.writeto_mem.assert_called_once_with(0x5A, 0x01, [0x10])

    def test_ecriture_plusieurs_octets(self, ccs):
        ccs.write_reg(0x02, [0xAA, 0xBB, 0xCC])
        mock_i2c_instance.writeto_mem.assert_called_once_with(0x5A, 0x02, [0xAA, 0xBB, 0xCC])


# ─────────────────────────────────────────────────────────────────────────────
# ccs811_init
# ─────────────────────────────────────────────────────────────────────────────

class TestCcs811Init:
    def _setup_nominal(self):
        """Configure le mock I2C pour une initialisation réussie."""
        mock_i2c_instance.scan.return_value = [0x5A]
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x81])   # HW_ID correct
        mock_i2c_instance.writeto_mem.return_value = None
        mock_i2c_instance.writeto.return_value = None

    def test_init_reussie(self, ccs):
        self._setup_nominal()
        with patch('time.sleep'):
            ccs.ccs811_init()   # ne doit pas lever d'exception

    def test_leve_si_capteur_absent(self, ccs):
        mock_i2c_instance.scan.return_value = []   # aucun périphérique détecté
        with pytest.raises(RuntimeError, match="non trouve"):
            ccs.ccs811_init()

    def test_leve_si_hw_id_incorrect(self, ccs):
        mock_i2c_instance.scan.return_value = [0x5A]
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x42])   # mauvais HW_ID
        with pytest.raises(RuntimeError, match="HW_ID incorrect"):
            ccs.ccs811_init()

    def test_app_start_envoye(self, ccs):
        self._setup_nominal()
        with patch('time.sleep'):
            ccs.ccs811_init()
        mock_i2c_instance.writeto.assert_called_with(0x5A, [0xF4])

    def test_meas_mode_configure(self, ccs):
        self._setup_nominal()
        with patch('time.sleep'):
            ccs.ccs811_init()
        mock_i2c_instance.writeto_mem.assert_called_with(0x5A, 0x01, [0x10])


# ─────────────────────────────────────────────────────────────────────────────
# data_ready
# ─────────────────────────────────────────────────────────────────────────────

class TestDataReady:
    def test_true_si_bit3_leve(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x08])   # bit 3 = 1
        assert ccs.data_ready() is True

    def test_false_si_bit3_non_leve(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x00])
        assert ccs.data_ready() is False

    def test_true_si_plusieurs_bits_leves(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0xFF])
        assert ccs.data_ready() is True

    def test_false_si_bit3_seul_absent(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0xF7])   # 0xFF ^ 0x08
        assert ccs.data_ready() is False


# ─────────────────────────────────────────────────────────────────────────────
# read_eco2_tvoc
# ─────────────────────────────────────────────────────────────────────────────

class TestReadEco2Tvoc:
    def test_decodage_eco2_et_tvoc(self, ccs):
        # eco2 = 0x0352 = 850 ppm  ; tvoc = 0x0140 = 320 ppb
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x03, 0x52, 0x01, 0x40])
        eco2, tvoc = ccs.read_eco2_tvoc()
        assert eco2 == 850
        assert tvoc == 320

    def test_eco2_zero(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x00, 0x00, 0x00, 0x64])
        eco2, tvoc = ccs.read_eco2_tvoc()
        assert eco2 == 0
        assert tvoc == 100

    def test_tvoc_zero(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x01, 0xF4, 0x00, 0x00])
        eco2, tvoc = ccs.read_eco2_tvoc()
        assert eco2 == 500
        assert tvoc == 0

    def test_valeurs_maximales(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0xFF, 0xFF, 0xFF, 0xFF])
        eco2, tvoc = ccs.read_eco2_tvoc()
        assert eco2 == 65535
        assert tvoc == 65535

    def test_lecture_depuis_bon_registre(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x00, 0x00, 0x00, 0x00])
        ccs.read_eco2_tvoc()
        mock_i2c_instance.readfrom_mem.assert_called_with(0x5A, 0x02, 4)

    def test_retourne_tuple(self, ccs):
        mock_i2c_instance.readfrom_mem.return_value = bytes([0x01, 0x2C, 0x00, 0x50])
        result = ccs.read_eco2_tvoc()
        assert isinstance(result, tuple)
        assert len(result) == 2
