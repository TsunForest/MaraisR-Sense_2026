#  -*- coding: UTF-8 -*-

# MindPlus
# Python
from pinpong.extension.unihiker import *
from pinpong.board import Board,Pin
from unihiker import Audio
from unihiker import GUI

Board().begin()

# Instantiate object
audio = Audio()
gui = GUI()
gui.draw_text(text="Noise Monitor",x=120,y=50,font_size=20, color="#0000FF", origin="center")
sound_text = gui.draw_text(text="",x=120,y=170,font_size=55, color="#0000FF", origin="center")

while True:
    # Update the displayed sound value
    sound_value = audio.sound_level()
    sound_text.config(text=sound_value)

    # Noise detection
    if (sound_value > 30):
        buzzer.pitch(392)
        time.sleep(0.1)
        buzzer.stop()