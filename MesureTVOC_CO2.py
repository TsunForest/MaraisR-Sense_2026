import time

class MesureTVOC_CO2:
    def __init__(self):
        self.i2c = None
        self.mqtt = None
        self.ccs811 = None  # Référence capteur
        self.last_scan = 0
        self.capteur_present = True

    def check_capteur(self):
        """Hotplug: rescan toutes 30s."""
        now = time.time()

        # RESCAN PERIODIQUE (30s)
        if now - self.last_scan > 30:
            self.last_scan = now
            try:
                devices = self.i2c.scan()
                nouveau_present = 0x5A in devices
                if nouveau_present != self.capteur_present:
                    if nouveau_present:
                        print("CAPTEUR RECONNECTÉ → re-init")
                        self.reinit_capteur()
                    else:
                        print("CAPTEUR DÉBRANCHÉ")
                    self.capteur_present = nouveau_present
            except:
                pass

        if not self.capteur_present:
            return False

        try:
            # Check data_ready SANS ERROR bit
            if self.ccs811 and self.ccs811.data_ready():
                return True
            return True  # Toujours OK si présent
        except:
            return self.capteur_out()

    def reinit_capteur(self):
        """Re-init complète après reconnexion."""
        try:
            self.ccs811.ccs811_init()
            print("RE-INIT OK")
        except:
            print("RE-INIT ÉCHOUÉE")

    def capteur_out(self):
        self.capteur_present = False
        if self.mqtt:
            self.mqtt.publish_measure(-999, -999)
        return False
