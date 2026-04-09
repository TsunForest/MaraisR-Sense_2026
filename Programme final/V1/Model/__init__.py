# Model/__init__.py
"""
Exports publics du module Model.
Chaque classe représente une responsabilité du modèle MVC :
  - CapteurParticules : lecture du capteur SDS011 (PM10) via port série
  - Ccs811            : pilote bas niveau du capteur CCS811 via I2C
  - MesureTVOC_CO2    : couche métier autour de Ccs811 (init, run-in, lecture)
  - MQTTClient        : connexion au broker, publication et abonnement seuils
"""

from .Capteur_Particules import CapteurParticules
from .Ccs811             import Ccs811
from .MesureTVOC_CO2     import MesureTVOC_CO2
from .MQTTClient         import MQTTClient

__all__ = ['CapteurParticules', 'Ccs811', 'MesureTVOC_CO2', 'MQTTClient']