# Model/Ccs811.py
"""
Pilote bas niveau du capteur de qualité d'air CCS811 — partie Model MVC.

Le CCS811 est un capteur numérique qui mesure :
  - eCO2 (CO2 équivalent) en ppm
  - TVOC (composés organiques volatils totaux) en ppb
Il communique via bus I2C (adresse 0x5A par défaut).

Ce module ne contient que l'accès matériel brut.
La logique de run-in, de réinitialisation et de gestion d'erreur est
dans MesureTVOC_CO2.
"""

import time
from pinpong.board import I2C


class Ccs811:
    """
    Pilote I2C pour le capteur CCS811.

    Le bus I2C et la connexion à la carte (Board) doivent être initialisés
    AVANT d'instancier cette classe. C'est la responsabilité de
    MesureTVOC_CO2._init_hardware() qui appelle Board().begin() en amont.
    """

    # Adresse I2C par défaut du CCS811
    # (0x5B si le pont d'adresse ADD est soudé)
    CCS811_ADDR = 0x5A

    # ── Registres principaux (cf. datasheet CCS811 programming guide) ─────────
    REG_STATUS     = 0x00   # registre d'état : data_ready en bit 3
    REG_MEAS_MODE  = 0x01   # registre de configuration du mode de mesure
    REG_ALG_RESULT = 0x02   # 4 octets : [eCO2_hi, eCO2_lo, TVOC_hi, TVOC_lo]
    REG_HW_ID      = 0x20   # identifiant matériel, doit valoir 0x81
    REG_APP_START  = 0xF4   # commande de démarrage de l'application embarquée

    HW_ID_EXPECTED = 0x81   # valeur attendue dans REG_HW_ID

    def __init__(self):
        """
        Crée le bus I2C.
        Board().begin() doit avoir été appelé avant l'instanciation.
        """
        # I2C() utilise le bus par défaut du connecteur I2C de l'UNIHIKER
        self.i2c = I2C()

    # ── Primitives d'accès registres ──────────────────────────────────────────

    def read_reg(self, reg: int, length: int = 1) -> list:
        """
        Lit 'length' octets depuis le registre 'reg' du CCS811.

        :param reg:    Adresse du registre.
        :param length: Nombre d'octets à lire.
        :return:       Liste d'entiers (valeurs des octets lus).
        """
        data = self.i2c.readfrom_mem(self.CCS811_ADDR, reg, length)
        return list(data)

    def write_reg(self, reg: int, data_bytes: list):
        """
        Ecrit 'data_bytes' dans le registre 'reg' du CCS811.

        :param reg:        Adresse du registre.
        :param data_bytes: Liste d'octets à écrire.
        """
        self.i2c.writeto_mem(self.CCS811_ADDR, reg, data_bytes)

    # ── Initialisation du capteur ─────────────────────────────────────────────

    def ccs811_init(self):
        """
        Initialise le CCS811 :
          1. Vérifie la présence du capteur sur le bus I2C.
          2. Contrôle l'identifiant matériel (HW_ID).
          3. Démarre l'application embarquée du capteur.
          4. Configure le mode de mesure à 1 mesure par seconde.

        :raises RuntimeError: Si le capteur est absent ou si HW_ID est incorrect.
        """
        # Scan du bus pour vérifier la présence physique du capteur
        print("Scan I2C en cours...")
        devices = self.i2c.scan()
        print(f"Peripheriques I2C detectes : {devices}")

        if self.CCS811_ADDR not in devices:
            raise RuntimeError(
                f"CCS811 non trouve sur le bus I2C (adresse attendue : 0x{self.CCS811_ADDR:02X})."
            )

        # Verification de l'identifiant matériel
        hw_id = self.read_reg(self.REG_HW_ID, 1)[0]
        print(f"HW_ID lu = {hex(hw_id)}")
        if hw_id != self.HW_ID_EXPECTED:
            raise RuntimeError(
                f"HW_ID incorrect : {hex(hw_id)} (attendu : {hex(self.HW_ID_EXPECTED)})."
            )

        # Demarrage de l'application embarquée du CCS811
        # APP_START est une commande spéciale : écriture sans donnée
        self.i2c.writeto(self.CCS811_ADDR, [self.REG_APP_START])
        time.sleep(0.1)

        # Configuration du mode 1 : mesure toutes les secondes
        MEAS_MODE_1SEC = 0x10
        self.write_reg(self.REG_MEAS_MODE, [MEAS_MODE_1SEC])
        print("CCS811 initialise en mode mesure 1 s.")

    # ── Lecture des mesures ───────────────────────────────────────────────────

    def data_ready(self) -> bool:
        """
        Indique si une nouvelle mesure est disponible dans le registre ALG_RESULT.
        Le bit 3 du registre STATUS est mis à 1 quand une mesure est prête.

        :return: True si une mesure est prête, False sinon.
        """
        status = self.read_reg(self.REG_STATUS, 1)[0]
        return bool(status & 0x08)

    def read_eco2_tvoc(self) -> tuple:
        """
        Lit eCO2 et TVOC depuis le registre ALG_RESULT (4 octets).
        Structure : [eCO2_hi, eCO2_lo, TVOC_hi, TVOC_lo]

        :return: Tuple (eco2: int, tvoc: int) en ppm et ppb respectivement.
        """
        data = self.read_reg(self.REG_ALG_RESULT, 4)
        eco2 = (data[0] << 8) | data[1]   # reconstruction 16 bits big-endian
        tvoc = (data[2] << 8) | data[3]
        return eco2, tvoc