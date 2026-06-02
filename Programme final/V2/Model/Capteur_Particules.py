# Model/Capteur_Particules.py
"""
Modèle du capteur de particules fines SDS011 — partie Model MVC.

Le SDS011 est un capteur laser qui mesure les particules PM2.5 et PM10
en µg/m³. Il communique via port série USB (UART).

Ce module étend la classe SDS011 de la bibliothèque sds011 pour ajouter :
  - Une séquence de mesure adaptée (wake-up + stabilisation + sleep)
  - Une procédure de reconnexion automatique en cas de débranchement
"""

from sds011 import SDS011
import time
import serial


class CapteurParticules(SDS011):
    """
    Encapsule le capteur SDS011 avec une logique de mesure périodique et
    de reconnexion automatique.

    Héritage de SDS011 : donne accès aux méthodes sleep(), query(), etc.
    et à l'attribut self.ser (objet serial.Serial sous-jacent).
    """

    def __init__(self, port="/dev/ttyUSB0"):
        """
        Initialise la connexion série avec le capteur SDS011.

        :param port: Port série USB (valeur par défaut adaptée à l'UNIHIKER).
        :raises serial.SerialException: Si le port n'est pas accessible.
        :raises OSError: Si le périphérique est introuvable.
        """
        self._port = port   # conservé pour la méthode reconnecter()
        super().__init__(port, use_query_mode=True)
        # Timeout série de 5 s : évite un blocage infini si le capteur ne répond pas
        self.ser.timeout = 5

    def get_pm10(self) -> float:
        
        # Appel sleep(False)
        for _ in range(2):
            self.sleep(sleep=False)

        # Stabilisation des mesures
        time.sleep(30)

        # Requête de mesure
        result = self.query()

        if result is None:
            # Aucune réponse dans le délai timeout : capteur probablement débranché
            raise serial.SerialException("Pas de réponse du capteur SDS011")

        _, pm10 = result   # on ignore pm2.5, on ne garde que pm10

        # Remise en veille du capteur pour économiser la durée de vie du laser
        self.sleep()

        return pm10

    def reconnecter(self):
        """
        Procédure de reconnexion automatique après un débranchement USB.

        Étapes :
          1. Fermeture propre du port série pour libérer le verrou système
          2. Attente active que le port soit accessible (USB ré-inséré)
          3. Réinitialisation de l'objet SDS011 sur le même port

        Cette méthode est bloquante : elle ne retourne que lorsque
        le capteur est reconnecté et opérationnel.
        """
        print("Attente de reconnexion du capteur sur", self._port)

        # ── Étape 1 : fermeture du port ───────────────────────────────────────
        # Nécessaire pour libérer le verrou /dev/ttyUSB0 côté système
        try:
            self.ser.close()
        except Exception:
            pass   # on ignore si déjà fermé ou si l'attribut n'existe plus

        # ── Étape 2 : attente que le port soit physiquement accessible ─────────
        # On essaie d'ouvrir brièvement le port série en boucle jusqu'au succès
        while True:
            try:
                s = serial.Serial(self._port, baudrate=9600, timeout=1)
                s.close()
                break   # succès : le port existe et est accessible
            except (serial.SerialException, OSError):
                print("Port non accessible, nouvelle tentative dans 2 s")
                time.sleep(2)

        print("Port accessible, tentative de reconnexion du capteur…")

        # ── Étape 3 : réinitialisation de l'objet SDS011 ──────────────────────
        # On appelle __init__ de la classe parente pour recréer la connexion série
        # et re-flasher le mode query si nécessaire
        while True:
            try:
                super().__init__(self._port, use_query_mode=True)
                self.ser.timeout = 5
                print("Capteur SDS011 reconnecté avec succès")
                return
            except serial.SerialException as e:
                print(f"Reconnexion échouée : {e} — nouvelle tentative dans 2 s")
                time.sleep(2)