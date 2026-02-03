from unihiker import GUI
import time

#Instantiate a GUI object.
u_gui=GUI()

#Variable
button_state = "normal"

# Callback function
def A():
    global button_state
    if button_state == "normal":
        button_state = "disabled"
    else:
        button_state = "normal"

    #Move the button off the screen
    buttonB.config(x=25,text="BtnA is Clicked",state=button_state)

def B():
    #Move the button off the screen
    buttonB.config(x=240)

#Create buttons with text; set their size, location and callback functions 
buttonA = u_gui.add_button(text="State",x=25,y=100,w=190,h=40,onclick=A)
buttonB = u_gui.add_button(text="Move",x=25,y=170,w=190,h=40,onclick=B)
while True:

    #Prevent the program from exiting or getting stuck
    time.sleep(0.1)