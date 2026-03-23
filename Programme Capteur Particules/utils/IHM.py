from utils import CapteurParticules
import kivy
import time

kivy.require('2.1.0') # replace with your current kivy version !

from kivy.app import App
from kivy.uix.label import Label
from kivy.clock import Clock


class MyApp(App):

    def build(self):
        return Label(text='Hello world')
    
    def affichage_mesure(self, dt):
        event = Clock.schedule_interval(self.affichage_mesure, 1 / 30)

if __name__ == '__main__':
    MyApp().run()