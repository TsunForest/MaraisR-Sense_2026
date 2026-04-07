import unittest
from unittest.mock import MagicMock, patch
from Ccs811 import Ccs811


class TestCcs811(unittest.TestCase):

    def setUp(self):
        self.capteur = Ccs811()
        self.capteur.i2c = MagicMock()

    def test_read_reg(self):
        self.capteur.i2c.readfrom_mem.return_value = bytes([0x81])
        resultat = self.capteur.read_reg(self.capteur.REG_HW_ID, 1)
        self.assertEqual(resultat, [0x81])
        self.capteur.i2c.readfrom_mem.assert_called_once_with(
            self.capteur.CCS811_ADDR,
            self.capteur.REG_HW_ID,
            1
        )

    def test_write_reg(self):
        self.capteur.write_reg(self.capteur.REG_MEAS_MODE, [0x10])
        self.capteur.i2c.writeto_mem.assert_called_once_with(
            self.capteur.CCS811_ADDR,
            self.capteur.REG_MEAS_MODE,
            [0x10]
        )

    def test_data_ready_true(self):
        self.capteur.read_reg = MagicMock(return_value=[0x08])
        self.assertTrue(self.capteur.data_ready())

    def test_data_ready_false(self):
        self.capteur.read_reg = MagicMock(return_value=[0x00])
        self.assertFalse(self.capteur.data_ready())

    def test_read_eco2_tvoc(self):
        self.capteur.read_reg = MagicMock(return_value=[0x04, 0xD2, 0x00, 0x64])
        eco2, tvoc = self.capteur.read_eco2_tvoc()
        self.assertEqual(eco2, 1234)
        self.assertEqual(tvoc, 100)

    @patch("time.sleep", return_value=None)
    def test_ccs811_init_ok(self, _):
        self.capteur.i2c.scan.return_value = [0x5A]
        self.capteur.read_reg = MagicMock(return_value=[0x81])
        self.capteur.write_reg = MagicMock()

        self.capteur.ccs811_init()

        self.capteur.i2c.writeto.assert_called_once_with(
            self.capteur.CCS811_ADDR,
            [self.capteur.REG_APP_START]
        )
        self.capteur.write_reg.assert_called_once_with(
            self.capteur.REG_MEAS_MODE,
            [0x10]
        )

    def test_ccs811_init_capteur_absent(self):
        self.capteur.i2c.scan.return_value = []

        with self.assertRaises(RuntimeError):
            self.capteur.ccs811_init()

    def test_ccs811_init_hw_id_incorrect(self):
        self.capteur.i2c.scan.return_value = [0x5A]
        self.capteur.read_reg = MagicMock(return_value=[0x00])

        with self.assertRaises(RuntimeError):
            self.capteur.ccs811_init()


if __name__ == "__main__":
    unittest.main()
