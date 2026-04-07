import unittest
from unittest.mock import Mock, patch, MagicMock
import time
# Corrigez le nom du module selon votre fichier exact
from MesureTVOC_CO2 import MesureTVOC_CO2  # ou .mesure_tvoc_co2 si renommé

class TestMesureTVOC_CO2(unittest.TestCase):

    def setUp(self):
        self.mesure = MesureTVOC_CO2()
        self.mesure.start_time = time.time()


    def test_init_hardware_success(self):
        """Test init réussie - vérifie board_inited et ccs811 créés"""
        result = self.mesure._init_hardware()
        self.assertTrue(result)
        self.assertTrue(self.mesure.board_inited)
        self.assertIsNotNone(self.mesure.ccs811)

    @patch('MesureTVOC_CO2.Board')
    @patch('MesureTVOC_CO2.Ccs811')
    def test_init_hardware_fail(self, MockCcs811, MockBoard):
        MockCcs811.side_effect = Exception("Init fail")
        result = self.mesure._init_hardware()
        self.assertFalse(result)
        self.assertIsNone(self.mesure.ccs811)

    def test_get_mesures_ccs811_none_init_success(self):
        self.mesure.ccs811 = None
        with patch.object(self.mesure, '_init_hardware', return_value=True) as mock_init:
            result = self.mesure.get_mesures()

        self.assertIsNone(result)  # Car run-in ou pas ready par défaut
        mock_init.assert_called_once()

    def test_get_mesures_i2c_fail(self):
        self.mesure.board_inited = True
        self.mesure.ccs811 = Mock()
        self.mesure.ccs811.i2c.readfrom_mem.side_effect = Exception()

        result = self.mesure.get_mesures()

        self.assertIsNone(result)
        self.assertIsNone(self.mesure.ccs811)

    @patch('time.time', return_value=1000)
    def test_get_mesures_runin_period(self, mock_time):
        self.mesure.board_inited = True
        self.mesure.ccs811 = Mock()
        self.mesure.ccs811.i2c.readfrom_mem.return_value = b'\x00'
        self.mesure.reinit_time = 990  # 10s < 30s

        result = self.mesure.get_mesures()

        self.assertIsNone(result)

    @patch('time.time', return_value=1000)
    def test_get_mesures_success(self, mock_time):
        self.mesure.board_inited = True
        self.mesure.ccs811 = Mock()
        self.mesure.ccs811.i2c.readfrom_mem.return_value = b'\x00'
        self.mesure.reinit_time = 900  # 100s > 30s
        self.mesure.ccs811.data_ready.return_value = True
        self.mesure.ccs811.read_eco2_tvoc.return_value = (1234, 56)

        result = self.mesure.get_mesures()

        self.assertEqual(result, (1234, 56))

if __name__ == '__main__':
    unittest.main()
