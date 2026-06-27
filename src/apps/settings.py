import machine
from M5 import *
from ble_config import BLEConfigServer
import json

class App:
    def __init__(self):
        self.name = 'settings'
        self.icon = 'settings.bmp'
    def save_config(self,config):
        with open('config.json', "w") as f:
            json.dump(config['settings'],f)
        machine.reset()


    def start(self, app):
        self.app = app
        self.app.ble.active(True)
        with open('config.json', "r") as f:
            conf=json.loads(f.read())
        self.config=BLEConfigServer(name=conf['name'],iam='main_settings',config=conf,message_callback=self.save_config)

        self.app.loop_callback = self.config.process_messages
        Lcd.setFont(Widgets.FONTS.DejaVu12)
        Lcd.setTextColor(0xffffff, 0x000000)
        w = Lcd.textWidth('Open in browser')           
        x = (125 - w) // 2+5
        y = 50                            
        Lcd.drawString('Open in browser', x, y)
        Lcd.setFont(Widgets.FONTS.DejaVu18)
        w = Lcd.textWidth("m5.i-app.ru")           
        x = (125 - w) // 2+5
        y = 70                          
        Lcd.drawString("m5.i-app.ru", x, y)
        Lcd.drawQR('https://m5.i-app.ru', 22, 120, 90, 1)

    def stop(self):
        try:
            if self.portal:
                self.portal.stop()
        except:
            pass
        self.app.loop_callback = None
        self.app.stop_app()
        self.app.gui.show_main_menu()
