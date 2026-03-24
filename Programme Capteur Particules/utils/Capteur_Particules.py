from sds011 import SDS011
import time
import serial

class CapteurParticules(SDS011):
    def __init__(self, port="/dev/ttyUSB0"):
        self._port = port
        super().__init__(port, use_query_mode=True)
        self.ser.timeout = 5
    
    def get_pm10(self):
        for i in range(2):
            self.sleep(sleep=False)
        time.sleep(15)

        result = self.query()
        
        if result is None:
            raise serial.SerialException("Pas de réponse du capteur (débranché ?)")

        _, pm10 = result
        self.sleep()
        time.sleep(44)
        
        return pm10

    def reconnecter(self):
        # Ferme proprement le port puis attend la reconnexion.
        print("Attente du capteur sur /dev/ttyUSB0")

        # Forcer la fermeture pour libérer le verrou
        try:
            self.ser.close()
        except Exception:
            pass

        # Attendre que le port soit réellement accessible
        while True:
            try:
                s = serial.Serial(self._port, baudrate=9600, timeout=1)
                s.close()
                break
            except (serial.SerialException, OSError):
                print("Port non accessible, nouvelle tentative dans 2s")
                time.sleep(2)

        print("Port accessible, reconnexion en cours")
        while True:
            try:
                super().__init__(self._port, use_query_mode=True)
                self.ser.timeout = 5
                print("Capteur reconnecté")
                return
            except serial.SerialException as e:
                print(f"Reconnexion échouée : {e} nouvelle tentative dans 2s")
                time.sleep(2)