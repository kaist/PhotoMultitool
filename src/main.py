import os, sys, time, machine, esp32, ubluetooth as bt, gc, json
from M5 import *

buzzer = machine.PWM(machine.Pin(2))
buzzer.duty(0)
nvs = esp32.NVS('appsets')

def load_module(path, name):
    ns = {'__name__': name, '__file__': path, '__package__': None}
    sys.modules[name] = ns
    code = compile(open(path).read(), path, 'exec')
    exec(code, ns, ns)
    C = type('M', (), {})  # lightweight module holder
    m = C()
    for k, v in ns.items(): setattr(m, k, v)
    sys.modules[name] = m
    gc.collect()
    return m

def load_apps(folder):
    return [{'name':f[:-3],'path':folder+'/'+f,'icon':f[:-3]+'.bmp'}
            for f in os.listdir(folder) if f.endswith('.py')]

class Colors: bg=0x000000; main=0xffffff
color = Colors()

def play_tone(freq, dur):
    buzzer.freq(freq); buzzer.duty(512); time.sleep_ms(dur); buzzer.duty(0)
play_tone(250,50); time.sleep_ms(50); play_tone(250,50)

class Waiter:
    def __init__(self, app): self.app=app
    def start(self, title):
        self.old_cl=self.app.callback_table; self.old_cl_long=self.app.callback_table_long
        self.app.callback_table={'left':None,'right':None,'ok':None}
        self.app.callback_table_long={'left':None,'right':None,'ok':None}
        Lcd.fillRect(0,31,135,209,color.bg)
        x=(Lcd.width()-32)//2; y=(Lcd.height()-32)//2
        Lcd.drawImage('apps/wait.bmp',x,y)
        Lcd.setFont(Widgets.FONTS.DejaVu18); Lcd.setTextColor(color.main,color.bg)
        w=Lcd.textWidth(title); Lcd.drawString(title,(125-w)//2+5,160)
    def stop(self):
        self.app.callback_table=self.old_cl; self.app.callback_table_long=self.old_cl_long
        gc.collect(); Lcd.fillRect(0,31,135,209,color.bg)

class Menu:
    def __init__(self, items, app, x=5, y=40, h=26, maxv=7, callback=None):
        self.callback=callback; self.app=app
        self.old_cl=self.app.callback_table; self.old_cl_long=self.app.callback_table_long
        self.items=items; self.cur=0; self.off=0; self.maxv=maxv; self.x=x; self.y=y; self.h=h; self.w=Lcd.width()-10
        Lcd.fillRect(0,31,135,209,color.bg); self.draw()
    def draw(self):
        Lcd.setFont(Widgets.FONTS.DejaVu24)
        for i in range(self.maxv):
            idx=self.off+i
            if idx>=len(self.items): break
            y=self.y+i*self.h
            sel=(idx==self.cur)
            Lcd.fillRect(self.x,y,self.w,self.h,color.main if sel else color.bg)
            Lcd.setTextColor(color.bg if sel else color.main, color.main if sel else color.bg)
            Lcd.drawString(self.items[idx], self.x+5, y+2)
    def up(self):
        if self.cur>0:
            self.cur-=1
            if self.cur<self.off: self.off-=1
        self.draw()
    def down(self):
        if self.cur<len(self.items)-1:
            self.cur+=1
            if self.cur>=self.off+self.maxv: self.off+=1
        self.draw()
    def select(self):
        self.app.callback_table=self.old_cl; self.app.callback_table_long=self.old_cl_long
        self.callback(self.cur); gc.collect()

class MainMenu:
    def __init__(self, apps, app):
        self.app=app; self.apps=apps
        try: self.current=app.current_app
        except: self.current=0
        self.draw()
    def draw(self):
        Lcd.fillRect(0,31,135,209,color.bg)
        x=(Lcd.width()-64)//2; y=(Lcd.height()-64)//2
        Lcd.drawImage(f"apps/{self.apps[self.current]['icon']}",x,y)
        Lcd.setFont(Widgets.FONTS.DejaVu24); Lcd.setTextColor(color.main,color.bg)
        t=self.apps[self.current]['name']; w=Lcd.textWidth(t)
        Lcd.drawString(t,(125-w)//2+5,200)
    def up(self):
        self.current=(self.current-1)%len(self.apps); self.draw()
        nvs.set_i32('cur_menu',self.current); nvs.commit()
    def down(self):
        self.current=(self.current+1)%len(self.apps); self.draw()
        nvs.set_i32('cur_menu',self.current); nvs.commit()
    def select(self):
        Lcd.fillRect(0,31,135,209,color.bg)
        self.app.current_app=self.current; gc.collect()
        self.app.gui.title_text=self.app.apps[self.current]['name']; self.app.gui.update_title()
        mod=load_module(self.apps[self.current]['path'],'RunCurrent')
        self.app.callback_table={'left':None,'right':None,'ok':None}
        self.app.callback_table_long={'right':None,'left':None,'ok':None}
        self.app.run=getattr(mod,'App')(); self.app.run.start(self.app)
        self.app.callback_table_long['right']=self.app.run.stop; gc.collect()

class Gui:
    def __init__(self):
        self.app=None; self.title_text=None; self.power_led_on=False; self.waiter=None
        Lcd.fillRect(0,31,135,209,color.bg); self.update_title()
    def update_title(self):
        gc.collect()
        Lcd.fillRect(5,5,125,25,color.bg); Lcd.drawLine(5,30,130,30,0xcecece)
        Lcd.setCursor(10,11); Lcd.setFont(Widgets.FONTS.DejaVu12)
        try: Lcd.print((self.title_text or self.app.config['name'][:10]), color.main)
        except: pass
        lev=Power.getBatteryLevel(); ce=0x00ff00 if lev>80 else (color.main if lev>30 else 0xff0000)
        Lcd.fillRect(100,8,25,18,color.main); Lcd.fillRect(97,12,5,9,color.main)
        Lcd.fillRect(102,10,21,14,color.bg)
        d=17-int(lev/100*17)
        Lcd.fillRect(104+d,12,17-d,10,ce)
        if lev<20:
            self.power_led_on=not self.power_led_on; Power.setLed(255 if self.power_led_on else 0)
        else: Power.setLed(0)
        gc.collect()
    def show_list(self, data=[], current=0, callback=None):
        gc.collect()
        m=Menu(data, app=self.app, callback=callback)
        self.app.callback_table={'left':m.up,'right':m.down,'ok':m.select}
        self.app.callback_table_long={'left':None,'right':None,'ok':m.down}
    def show_main_menu(self):
        gc.collect()
        m=MainMenu(self.app.apps,self.app)
        self.app.callback_table={'left':m.up,'right':m.down,'ok':m.select}
        self.app.callback_table_long={'left':None,'right':None,'ok':m.down}

class App:
    def __init__(self):
        self.run=None; self.play_tone=play_tone
        try: self.config=json.loads(open('config.json').read())
        except: self.config={'brightness':100,'autooff_min':5,'name':'M5','sound':1}
        Widgets.setBrightness(int(self.config['brightness']/100*255))
        self.loop_callback=None
        self.ble=bt.BLE(); self.ble.active(True)
        self.gui=Gui(); self.auto_off=time.time()
        try: self.current_app=int(nvs.get_i32('cur_menu'))
        except: self.current_app=0
        self.apps=load_apps('apps')
        self.callback_table={'left':None,'right':None,'ok':None}
        self.callback_table_long={'left':None,'right':None,'ok':None}
        self.upd_time=0
        self.buttons_state={'ok':0,'left':0,'right':0}
        BtnA.setCallback(type=BtnA.CB_TYPE.WAS_PRESSED,  cb=lambda s:self._press('ok',1))
        BtnB.setCallback(type=BtnB.CB_TYPE.WAS_PRESSED,  cb=lambda s:self._press('left',1))
        BtnPWR.setCallback(type=BtnPWR.CB_TYPE.WAS_PRESSED,cb=lambda s:self._press('right',1))
        BtnA.setCallback(type=BtnA.CB_TYPE.WAS_RELEASED, cb=lambda s:self._press('ok',0))
        BtnB.setCallback(type=BtnB.CB_TYPE.WAS_RELEASED, cb=lambda s:self._press('left',0))
        BtnPWR.setCallback(type=BtnPWR.CB_TYPE.WAS_RELEASED,cb=lambda s:self._press('right',0))
        self.gui.app=self; self.gui.waiter=Waiter(self)
    def save_set(self,name,data,typ):
        (nvs.set_i32 if typ=='int' else nvs.set_blob)(name,data); nvs.commit()
    def get_set(self,name,typ,default):
        try:
            return int(nvs.get_i32(name)) if typ=='int' else str(nvs.get_blob(name))
        except: return default
    def start(self): self.gui.show_main_menu()
    def _press(self,btn,flag):
        self.auto_off=time.time()
        Widgets.setBrightness(int(self.config['brightness']/100*255))
        if flag: self.buttons_state[btn]=time.ticks_ms()
        else:
            df=time.ticks_ms()-self.buttons_state[btn]
            if df>1000: return
            self.click(btn, df>300)
    def click(self,btn,is_long):
        if not is_long:
            if self.config['sound']: play_tone(300,10)
            f=self.callback_table.get(btn)
        else:
            if self.config['sound']: play_tone(400,10); time.sleep_ms(20); play_tone(200,10)
            f=self.callback_table_long.get(btn)
        if f: f()
    def stop_app(self):
        self.gui.waiter.start('wait...'); machine.reset()
    def second_updater(self):
        if self.config['autooff_min'] and (time.time()-self.auto_off)>60*self.config['autooff_min']: Power.powerOff()
        if (time.time()-self.auto_off)>10: Widgets.setBrightness(16)
        self.gui.update_title()
    def loop(self):
        update()
        if (time.time()-self.upd_time)>=1:
            self.second_updater(); self.upd_time=time.time()
        if self.loop_callback: self.loop_callback()

begin()
Widgets.setRotation(0); Widgets.fillScreen(color.bg)
app=App()
if __name__=='__main__':
    app.start()
    try:
        while True: app.loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print('please update to latest firmware')
