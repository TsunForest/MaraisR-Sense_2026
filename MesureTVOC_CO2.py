class MesureTVOC_CO2:
    def __init__(self):
        self.i2c = None
        self.mqtt = None

    def check_capteur(self):
        """Check MINIMAL: juste I2C vivant."""
        try:
            # Test ultra-rapide: juste scan
            devices = self.i2c.scan()
            if 0x5A in devices:
                return True
            return self.capteur_out()
        except:
            return self.capteur_out()

    def capteur_out(self):
        """VRAIE panne seulement."""
        print(" CAPTEUR ABSENT")

        if self.mqtt:
            self.mqtt.publish_measure(-999, -999)

        return False
