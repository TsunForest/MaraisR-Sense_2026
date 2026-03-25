import time
from pinpong.board import Board
from .Ccs811 import Ccs811

class MesureTVOC_CO2:
    def __init__(self):
        self.board_inited = False
        self.ccs811 = None
        self.reinit_time = 0
        self.start_time = time.time()
        self._init_hardware()

    def _init_hardware(self):
        if not self.board_inited:
            Board("UNIHIKER").begin()
            self.board_inited = True

        try:
            self.ccs811 = Ccs811()
            self.ccs811.ccs811_init()
            self.reinit_time = time.time()
            print("INIT - run-in 2min")
            return True
        except Exception as e:
            print("INIT ECHOUE:", e)
            self.ccs811 = None
            return False

    def get_mesures(self):
        """
        Retourne:
          - (eco2, tvoc) si mesure valide
          - None si run-in, capteur absent ou pas prêt
        """
        # Si pas d'objet, tentative de réinit
        if self.ccs811 is None:
            if not self._init_hardware():
                return None

        # Test connexion physique
        try:
            self.ccs811.i2c.readfrom_mem(0x5A, 0x00, 1)
        except Exception:
            print("CAPTEUR DECONNECTE, reinit au prochain appel")
            self.ccs811 = None
            return None

        # Run-in 2 minutes après chaque init
        if (time.time() - self.reinit_time) < 30:
            return None

        # Mesure normale
        try:
            if self.ccs811.data_ready():
                return self.ccs811.read_eco2_tvoc()
            return None
        except Exception as e:
            print("ERREUR LECTURE:", e)
            self.ccs811 = None
            return None
