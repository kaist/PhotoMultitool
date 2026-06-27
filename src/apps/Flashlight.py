from M5 import *
import time
from machine import Pin
import json

led_pin = Pin(19, Pin.OUT)

class App:
    def __init__(self):
        pass
    def start(self,app):
        self.app=app

        self.app.enable_screen_sleep=False
        self.app.enable_poweroff=False
        self.app.enable_title=False
        self.on=True
        self.app.callback_table['ok']=self.onoff

        led_pin(1)
        Lcd.fillRect(0, 0, 135, 240, 0xffffff)
        Widgets.setBrightness(255)
        
    def onoff(self):
        self.on=not self.on
        if self.on:
            self.app.enable_screen_sleep=False
            self.app.enable_poweroff=False
            self.app.enable_title=False
            Lcd.fillRect(0, 0, 135, 240, 0xffffff)
            Widgets.setBrightness(255)
            led_pin(1)
        else:
            self.app.enable_screen_sleep=True
            self.app.enable_poweroff=True
            self.app.enable_title=True
            Lcd.fillRect(0, 0, 135, 240, 0x000000)
            Widgets.setBrightness(16)
            led_pin(0)           
            
        
  
        


        


            
        

    def stop(self):
        self.app.stop_app()
        self.app.gui.show_main_menu()
        
                
                
            
        
        


