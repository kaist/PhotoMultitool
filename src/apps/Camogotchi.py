import time
import random
import json
import os
import gc
from M5 import *
from hardware import Timer
SAVE_PATH = "apps/camagochi.json"

# ===== ⚙️ БАЛАНС =====
BASE_BREAKAGE_CHANCE = 0.0003
HOURS_PER_SIMULATION = 8
SESSION_EFFICIENCY_MIN = 0.4
SESSION_EFFICIENCY_MAX = 0.7

REPAIR_COST = 80
BATTERY_COST = 150
LIFE_EXPENSE_MIN = 5
LIFE_EXPENSE_MAX = 25
LIFE_EXPENSE_CHANCE = 0.5

MOOD_DECAY_HOURS = 12
MOOD_EFFECT = 0.15


sad_camera_icon_32x32 = [
# 32 ряда по 32 пикселя: 0 — черный, 1 — белый
[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
[0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0],
[0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0],
[0,0,1,1,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,1,1,0,0,0,0,0,0,0],
[0,1,1,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,1,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,1,1,1,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0],
[0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0],
[0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
[0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0],
[0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0],
[0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0],
# оставшиеся ряды пустые для выравнивания 32x32
] + [[0]*32 for _ in range(32-20)]

# ===== ПРОФЕССИОНАЛИЗМ =====
PRO_LEVELS = [{"level": i+1, "value": 0.5 + i*0.05, "cost": 100*(2**i)} for i in range(10)]

# ===== ОБЪЕКТИВЫ =====
LENSES = [
    {"name": name, "value": val, "reliability": rel, "cost": cost}
    for name, val, rel, cost in [
        ("Kit Lens", 10, 1.0, 0),
        ("Portrait 50mm", 25, 0.95, 200),
        ("Telephoto 200mm", 40, 0.9, 400),
        ("Macro Lens", 55, 0.85, 700),
        ("Wide 24mm", 70, 0.9, 900),
        ("Prime 85mm", 90, 0.88, 1100),
        ("Vintage Lens", 110, 0.75, 1400),
        ("Pro Zoom 24–70", 140, 0.95, 1800),
        ("Cinematic Lens", 180, 0.85, 2500),
        ("Legendary Prime", 250, 1.1, 3500),
    ]
]

# ===== КЛАССЫ =====
class Lens:
    def __init__(self, name="Kit Lens", value=10, reliability=1.0):
        self.name = name
        self.value = value
        self.reliability = reliability

class CameraState:
    def __init__(self):
        self.money = 0.0
        self.professionalism = 0.5
        self.pro_level = 1
        self.batteries = 1
        self.battery_capacity = 10
        self.memory_capacity = 32
        self.lens = Lens()
        self.broken = False
        self.last_visit = time.time()
        self.used_memory = 0
        self.mood = 1.0  # 0..1

class DeltaState:
    def __init__(self):
        self.sessions = 0
        self.money_earned = 0
        self.memory_used = 0
        self.batteries_used = 0
        self.broken = False

class IdleCameraGame:
    def __init__(self):
        self.state = self._load_state()
        self.delta = DeltaState()

    # ===== Сохранение / Загрузка =====
    def _save_state(self):
        try:
            os.makedirs("/".join(SAVE_PATH.split("/")[:-1]), exist_ok=True)
        except:
            pass
        data = {
            "money": self.state.money,
            "professionalism": self.state.professionalism,
            "pro_level": self.state.pro_level,
            "batteries": self.state.batteries,
            "battery_capacity": self.state.battery_capacity,
            "memory_capacity": self.state.memory_capacity,
            "lens": {"name": self.state.lens.name, "value": self.state.lens.value, "reliability": self.state.lens.reliability},
            "broken": self.state.broken,
            "last_visit": self.state.last_visit,
            "used_memory": self.state.used_memory,
            "mood": self.state.mood,
        }
        with open(SAVE_PATH, "w") as f:
            f.write(json.dumps(data))

    def _load_state(self):
        try:
            with open(SAVE_PATH, "r") as f:
                data = json.loads(f.read())
            state = CameraState()
            state.money = data.get("money",0)
            state.professionalism = data.get("professionalism",0.5)
            state.pro_level = data.get("pro_level",1)
            state.batteries = data.get("batteries",1)
            state.battery_capacity = data.get("battery_capacity",10)
            state.memory_capacity = data.get("memory_capacity",32)
            lens_data = data.get("lens",{})
            state.lens = Lens(lens_data.get("name","Kit Lens"), lens_data.get("value",10), lens_data.get("reliability",1.0))
            state.broken = data.get("broken",False)
            state.last_visit = data.get("last_visit",time.time())
            state.used_memory = data.get("used_memory",0)
            state.mood = data.get("mood",1.0)
            return state
        except:
            return CameraState()

    # ===== Основной idle =====
    def on_enter(self):
        now = time.time()
        hours_passed = (now - self.state.last_visit) / 3600
        self.delta = DeltaState()
        if hours_passed <= 0:
            return

        if self.state.broken:
            self.delta.broken = True
            self.state.last_visit = now
            self._save_state()
            return

        # настроение
        mood_drop = min(1.0, hours_passed / MOOD_DECAY_HOURS * 0.15)
        self.state.mood = max(0.5, self.state.mood - mood_drop)

        # сессии
        max_sessions = self.state.batteries * self.state.battery_capacity
        available_memory = max(0, self.state.memory_capacity - self.state.used_memory)
        possible_sessions = min(max_sessions, available_memory)

        session_count = int(possible_sessions * random.uniform(SESSION_EFFICIENCY_MIN,SESSION_EFFICIENCY_MAX) * hours_passed / HOURS_PER_SIMULATION)

        effective_skill = self.state.professionalism * (0.8 + self.state.mood * MOOD_EFFECT)
        successful_sessions = 0
        for _ in range(session_count):
            if random.random() < effective_skill:
                successful_sessions +=1

        income = successful_sessions * self.state.lens.value
        self.state.money += income
        self.state.used_memory += session_count

        self.delta.sessions = successful_sessions
        self.delta.money_earned = income
        self.delta.memory_used = session_count

        self._drain_batteries(session_count)
        self._check_breakage(session_count)
        self._life_expenses()

        self.state.last_visit = now
        self._save_state()

    # ===== Вспомогательные =====
    def _check_breakage(self, session_count):
        if session_count==0 or self.state.broken:
            return
        chance = BASE_BREAKAGE_CHANCE / self.state.lens.reliability
        total_chance = 1 - (1 - chance) ** session_count
        if random.random() < total_chance:
            self.state.broken = True
            self.delta.broken = True

    def _drain_batteries(self, sessions):
        per_battery = self.state.battery_capacity
        drained = sessions // per_battery
        drained = min(drained,self.state.batteries)
        self.state.batteries -= drained
        self.delta.batteries_used = drained
        if self.state.batteries <= 0:
            self.state.broken = True
            self.delta.broken = True

    def _life_expenses(self):
        if random.random() < LIFE_EXPENSE_CHANCE:
            expense = random.uniform(LIFE_EXPENSE_MIN,LIFE_EXPENSE_MAX)
            self.state.money = max(0,self.state.money - expense)

    # ===== Действия =====
    def repair(self):
        if self.state.money >= REPAIR_COST:
            self.state.money -= REPAIR_COST
            self.state.broken = False
            self.state.mood = min(1.0,self.state.mood + 0.2)
            self._save_state()
            return True
        return False

    def upgrade_professionalism(self):
        current_level = self.state.pro_level
        if current_level >= len(PRO_LEVELS):
            return False
        next_level = PRO_LEVELS[current_level]
        if self.state.money >= next_level["cost"]:
            self.state.money -= next_level["cost"]
            self.state.professionalism = next_level["value"]
            self.state.pro_level = next_level["level"]
            self._save_state()
            return True
        return False

    def buy_lens(self,name):
        for lens in LENSES:
            if lens["name"]==name and self.state.money >= lens["cost"]:
                self.state.money -= lens["cost"]
                self.state.lens = Lens(lens["name"],lens["value"],lens["reliability"])
                self._save_state()
                return True
        return False

    # ===== Summary =====
    def summary(self):
        return {
            "money": round(self.state.money,2),
            "professionalism": round(self.state.professionalism,2),
            "level": self.state.pro_level,
            "batteries": self.state.batteries,
            "memory": "{}/{}".format(self.state.used_memory,self.state.memory_capacity),
            "lens": self.state.lens.name,
            "mood": round(self.state.mood,2),
            "broken": self.state.broken,
            # Дельта с последнего захода
            "delta_sessions": self.delta.sessions,
            "delta_money": round(self.delta.money_earned,2),
            "delta_memory": self.delta.memory_used,
            "delta_batteries": self.delta.batteries_used,
            "delta_broken": self.delta.broken,
        }
    


class App:
    def __init__(self):
        pass

        
    def start(self,app):
        self.app=app
        #self.app.callback_table['ok']=self.shoot
        #self.app.callback_table['right']=self.minus_timer
        #self.app.callback_table['left']=self.plus_timer       
        #self.app.callback_table_long['left']=self.start_pair
        #self.app.callback_table_long['ok']=self.change_mode
        self.draw()
        
        self.timer=Timer(3)
        self.timer.init(mode=Timer.PERIODIC, period=1000, callback=self.timer_callback)

        

                

            
    def timer_callback(self,event=None):
        self.draw()    
   
    def draw_icon_scaled(self,x0, y0, icon, scale=3, color=1):
        """
        Рисует битовую иконку на дисплее с увеличением каждого пикселя.
        
        x0, y0 — верхний левый угол на дисплее
        icon — список списков 32x32 (0/1)
        scale — размер одного пикселя (3x3)
        color — цвет (1 — белый, 0 — черный)
        """
        height = len(icon)
        width = len(icon[0])
        
        for y in range(height):
            for x in range(width):
                if icon[y][x]:  # если пиксель белый
                    Lcd.fillRect(x0 + x*scale, y0 + y*scale, scale, scale, 0xFFFFFF)
   
    def draw(self):
        gc.collect()
        
        icon=sad_camera_icon_32x32
        
        self.draw_icon_scaled(10,50,icon)
        

 
    def stop(self):
        self.app.stop_app()
