import time
from pinpong.board import Board, I2C

class Ccs811:
    # --- Initialisation de la carte et du bus I2C ---
    Board("UNIHIKER").begin()  # auto-détection du port série de l'UNIHIKER
    i2c = I2C()                # bus I2C par défaut (lié au connecteur I2C de l'UNIHIKER)

    CCS811_ADDR = 0x5A  # Adresse I2C par défaut du CCS811 (0x5B si pont d'adresse soudé)

    # Registres principaux CCS811 (cf. datasheet/programming guide)
    REG_STATUS        = 0x00
    REG_MEAS_MODE     = 0x01
    REG_ALG_RESULT    = 0x02
    REG_HW_ID         = 0x20
    REG_APP_START     = 0xF4  # registre "mailbox" spécial (write sans data)

    HW_ID_EXPECTED    = 0x81  # valeur attendue dans HW_ID pour un CCS811 valide

    def read_reg(self, reg, length=1):
        """Lecture 'length' octets à partir d'un registre CCS811."""
        data = self.i2c.readfrom_mem(self.CCS811_ADDR, reg, length)
        return list(data)

    def write_reg(self, reg, data_bytes):
        """Écriture de data_bytes (liste d'octets) dans un registre CCS811."""
        self.i2c.writeto_mem(self.CCS811_ADDR, reg, data_bytes)

    def ccs811_init(self):
        """Initialisation du CCS811."""
        print("Scan I2C en cours...")
        devices = self.i2c.scan()
        print("Périphériques I2C détectés :", devices)
        if self.CCS811_ADDR not in devices:
            raise RuntimeError("CCS811 non trouvé sur le bus I2C (attendu à 0x5A ou 0x5B).")

        hw_id = self.read_reg(self.REG_HW_ID, 1)[0]
        print("HW_ID lu =", hex(hw_id))
        if hw_id != self.HW_ID_EXPECTED:
            raise RuntimeError("HW_ID incorrect (attendu 0x81).")

        self.i2c.writeto(self.CCS811_ADDR, [self.REG_APP_START])
        time.sleep(0.1)

        MEAS_MODE_1SEC = 0x10
        self.write_reg(self.REG_MEAS_MODE, [MEAS_MODE_1SEC])
        print("CCS811 initialisé en mode mesure 1m.")

    def data_ready(self):
        """Retourne True si nouvelle mesure prête."""
        status = self.read_reg(self.REG_STATUS, 1)[0]
        return (status & 0x08) != 0

    def read_eco2_tvoc(self):
        """Lit eCO2 et TVOC."""
        data = self.read_reg(self.REG_ALG_RESULT, 4)
        eco2 = (data[0] << 8) | data[1]
        tvoc = (data[2] << 8) | data[3]
        return eco2, tvoc
