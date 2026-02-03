#  -*- coding: UTF-8 -*-

# MindPlus
# Python
from pinpong.extension.unihiker import *
from pinpong.board import Board,Pin
from unihiker import GUI
import time

# Event callback function
def button_click1():
    buzzer.pitch(262,1)
    text.config(text="C4")
def button_click2():
    buzzer.pitch(294,1)
    text.config(text="D4")
def button_click3():
    buzzer.pitch(330,1)
    text.config(text="E4")
def button_click4():
    buzzer.pitch(349,1)
    text.config(text="F4")
def button_click5():
    buzzer.pitch(392,1)
    text.config(text="G4")
def button_click6():
    buzzer.pitch(440,1)
    text.config(text="A4")
def button_click7():
    buzzer.pitch(494,1)
    text.config(text="B4")
def button_click8():
    buzzer.pitch(277,1)
    text.config(text="C#4")
def button_click9():
    buzzer.pitch(311,1)
    text.config(text="D#4")
def button_click10():
    buzzer.pitch(370,1)
    text.config(text="F#4")
def button_click11():
    buzzer.pitch(415,1)
    text.config(text="G#4")
def button_click12():
    buzzer.pitch(466,1)
    text.config(text="A#4")


u_gui=GUI()
Board().begin()

bg=u_gui.fill_rect(x=0,y=0,w=240,h=320,color="#CCCCFF")
text = u_gui.draw_text(x=185,y=160,text="Musical Scale",origin="center",font_size=30,angle=270)
do=u_gui.fill_rect(x=0,y=3,w=130,h=43,color="#FFFFFF",onclick=button_click1)
re=u_gui.fill_rect(x=0,y=48,w=130,h=43,color="#FFFFFF",onclick=button_click2)
mi=u_gui.fill_rect(x=0,y=93,w=130,h=43,color="#FFFFFF",onclick=button_click3)
fa=u_gui.fill_rect(x=0,y=138,w=130,h=43,color="#FFFFFF",onclick=button_click4)
so=u_gui.fill_rect(x=0,y=183,w=130,h=43,color="#FFFFFF",onclick=button_click5)
la=u_gui.fill_rect(x=0,y=228,w=130,h=43,color="#FFFFFF",onclick=button_click6)
xi=u_gui.fill_rect(x=0,y=273,w=130,h=43,color="#FFFFFF",onclick=button_click7)
bian1=u_gui.fill_rect(x=50,y=32,w=80,h=30,color="#000000",onclick=button_click8)
bian2=u_gui.fill_rect(x=50,y=77,w=80,h=30,color="#000000",onclick=button_click9)
bian3=u_gui.fill_rect(x=50,y=167,w=80,h=30,color="#000000",onclick=button_click10)
bian4=u_gui.fill_rect(x=50,y=212,w=80,h=30,color="#000000",onclick=button_click11)
bian5=u_gui.fill_rect(x=50,y=257,w=80,h=30,color="#000000",onclick=button_click12)


while True:
    time.sleep(1)