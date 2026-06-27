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
        self.app.loop_callback = self.loop
        self.app.enable_screen_sleep=False
        self.app.enable_poweroff=False
        self.app.enable_title=False
        self.app.callback_table['left'] = self.change_speed
        self.app.callback_table['ok'] = self.change_mode
        self.app.callback_table_long['ok']=self.change_imu
        self.mode=0
        self.speed=200
        self.imu_enable=True
        self.tick_ms=time.ticks_ms()
        self.onoff=True
        self.imu_state=False
        self.last_imu_state=False
        try:
            with open('apps/look_me.json','r') as f:
                d=json.load(f)
                self.speed=d['speed']
                self.mode=d['mode']
                self.imu_enable=d['imu']
        except:pass
        
    def save_json(self):
        open('apps/look_me.json','w').write(json.dumps({'speed':self.speed,'mode':self.mode,'imu':self.imu_enable}))
        
        
    def change_imu(self):
        self.imu_enable=not self.imu_enable
        Lcd.setFont(Widgets.FONTS.DejaVu18)
        Lcd.fillRect(0, 0, 135, 240, 0x000000)
        led_pin(0)
        Widgets.setBrightness(255)
        Lcd.setTextColor(0xffffff, 0x000000)
        text='GYRO ON' if self.imu_enable else 'GYRO OFF'
        w = Lcd.textWidth(text)
        x = (125 - w) // 2 + 5
        y = 100
        Lcd.drawString(text, x, y)
        self.save_json()
        time.sleep(1)
        Lcd.fillRect(0, 0, 135, 240, 0x000000)
        
        
    def change_speed(self):
        self.speed-=100
        if self.speed<100:
            self.speed=700
        self.save_json()
        
    def change_mode(self):
        self.mode+=1
        if self.mode>5:self.mode=0
        self.save_json()
            
        
    def loop(self):
        if self.imu_enable:
            i=Imu.getAccel()
            self.imu_state=False
            if i[1]>0.7 or i[0]>0.7 or i[0]<-0.7:
                self.imu_state=True
        else:
            self.imu_state=True
            self.last_imu_state=True
            
        if not self.imu_state and self.last_imu_state:
            Lcd.fillRect(0, 0, 135, 240, 0x000000)
            led_pin(0)
            Widgets.setBrightness(0)
        self.last_imu_state=self.imu_state
            
            
            
        
        if (time.ticks_ms()-self.tick_ms)>self.speed and self.imu_state:
            self.tick_ms=time.ticks_ms()
            self.onoff=not self.onoff
            if self.onoff:
                if self.mode==0:
                    Lcd.fillRect(0, 0, 135, 240, 0xff0000)
                elif self.mode==1:
                    Lcd.fillRect(0, 0, 135, 240, 0xffffff)
                elif self.mode==2:
                    Lcd.fillTriangle(0,140,130,140,67, 230, 0xff0000)
                    Lcd.fillRect(30,10,75,130, 0xff0000)
                elif self.mode==3:
                    Lcd.fillTriangle(0,140,130,140,67, 230, 0xffffff)
                    Lcd.fillRect(30,10,75,130, 0xffffff)
                elif self.mode==4:
                    Lcd.fillCircle(135//2,240//2,135//2-10,0xff0000)
                elif self.mode==5:
                    Lcd.fillCircle(135//2,240//2,135//2-10,0xffffff)       
                   
                led_pin(1)
                Widgets.setBrightness(255)
            else:
                Lcd.fillRect(0, 0, 135, 240, 0x000000)
                led_pin(0)
                Widgets.setBrightness(0)
    def stop(self):
        self.app.stop_app()
        self.app.gui.show_main_menu()
        
                
                
            
        
        

