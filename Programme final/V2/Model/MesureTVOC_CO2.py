# Model/MesureTVOC_CO2.py
"""
Couche métier pour le capteur CCS811 — partie Model MVC.

Gere :
  - L'initialisation de la carte UNIHIKER et du capteur CCS811.
  - La période de run-in (chauffe) de 30 secondes après chaque init.
  - La détection de déconnexion physique et la réinitialisation automatique.
  - La remontée des mesures eCO2 et TVOC au Controller.
"""

import time
from pinpong.board import Board
from .Ccs811 import Ccs811


class MesureTVOC_CO2:
    """
    Wrapper autour du pilote Ccs811.

    Cette classe gere le cycle de vie complet du capteur :
    initialisation, période de run-in, lecture, et reconnexion après
    un débranchement. Elle ne décide pas de la fréquence de lecture ;
    c'est la responsabilité du Controller.
    """

    # Duree de la période de run-in après chaque initialisation (secondes).
    # Pendant ce temps, les mesures ne sont pas encore fiables.
    DUREE_RUN_IN = 30

    def __init__(self):
        """
        Initialise la carte UNIHIKER et tente de connecter le CCS811.
        Ne lève pas d'exception si le capteur est absent : la propriété
        is_connected permet au Controller de connaitre l'état.
        """
        self._board_inited = False    # True après Board().begin() réussi
        self._ccs811       = None     # instance Ccs811, None si absent
        self._reinit_time  = 0.0      # timestamp de la dernière init réussie

        self._init_hardware()

    # ── Propriété publique ────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """
        Retourne True si le CCS811 a été initialisé avec succès et est
        présent sur le bus I2C. Le Controller utilise cette propriété pour
        décider quelle page afficher au démarrage.
        """
        return self._ccs811 is not None

    # ── Initialisation matérielle ─────────────────────────────────────────────

    def _init_hardware(self) -> bool:
        """
        Initialise la carte UNIHIKER puis le capteur CCS811.
        En cas d'echec, self._ccs811 reste None (is_connected retourne False).

        :return: True si l'initialisation a réussi, False sinon.
        """
        # Board().begin() est idempotent : sans effet si déjà appelé
        if not self._board_inited:
            Board("UNIHIKER").begin()
            self._board_inited = True

        try:
            ccs = Ccs811()
            ccs.ccs811_init()
            self._ccs811      = ccs
            self._reinit_time = time.time()
            print(f"CCS811 initialise — run-in {self.DUREE_RUN_IN} s")
            return True
        except Exception as e:
            print(f"Initialisation CCS811 echouee : {e}")
            self._ccs811 = None
            return False

    # ── Lecture des mesures ───────────────────────────────────────────────────

    def get_mesures(self):
        """
        Retourne les mesures eCO2 et TVOC si disponibles.

        Cas de retour None (sans erreur critique) :
          - Capteur absent ou non initialisé (tentative de réinit automatique).
          - Periode de run-in non écoulée.
          - Mesure pas encore prête (bit data_ready pas levé).

        :return: Tuple (eco2: int, tvoc: int) ou None.
                 eco2 en ppm, tvoc en ppb.
        """
        # Si pas d'objet capteur, tentative de reinitialisation
        if self._ccs811 is None:
            if not self._init_hardware():
                return None   # toujours absent, on réessaiera au prochain appel

        # Verification de la présence physique du capteur sur le bus I2C
        # (détecte un débranchement à chaud)
        try:
            self._ccs811.i2c.readfrom_mem(0x5A, 0x00, 1)
        except Exception:
            print("CCS811 deconnecte, reinitialisation au prochain appel")
            self._ccs811 = None
            return None

        # Période de run-in : les mesures ne sont pas fiables juste après l'init
        if (time.time() - self._reinit_time) < self.DUREE_RUN_IN:
            temps_restant = self.DUREE_RUN_IN - (time.time() - self._reinit_time)
            print(f"Run-in en cours, encore {temps_restant:.0f} s")
            return None

        # Lecture normale
        try:
            if self._ccs811.data_ready():
                eco2, tvoc = self._ccs811.read_eco2_tvoc()
                return eco2, tvoc
            return None   # mesure pas encore prête ce cycle
        except Exception as e:
            print(f"Erreur lecture CCS811 : {e}")
            self._ccs811 = None
            return None