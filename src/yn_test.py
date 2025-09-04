# MicroPython (ESP32) — YN360 BLE Controller: разовый scan() -> connect ко всем
# + УСТОЙЧИВЫЕ ИМЕНА ПО MAC ("01","02",...) с сохранением в app/yn360_names.json
# + on_update(devs) всегда отдаёт ТОЛЬКО подключённые устройства
import bluetooth as bt
import micropython, time
from micropython import const
import os
try:
    import ujson as json
except:
    import json

# ===== UUID =====
SRV_UUID_STR = 'f000aa60-0451-4000-b000-000000000000'
CHR_UUID_STR = 'f000aa61-0451-4000-b000-000000000000'

# ===== IRQ codes =====
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_WRITE_DONE = const(17)

# ===== AD types =====
_ADV_TYPE_SHORT_NAME = const(0x08)
_ADV_TYPE_COMPLETE_NAME = const(0x09)
_ADV_UUID16_INCOMP = const(0x02)
_ADV_UUID16_COMP   = const(0x03)
_ADV_UUID32_INCOMP = const(0x04)
_ADV_UUID32_COMP   = const(0x05)
_ADV_UUID128_INCOMP= const(0x06)
_ADV_UUID128_COMP  = const(0x07)

# ===== storage =====
_NAMES_PATH = 'apps/yn360_names.json'

# ===== utils =====
def _clamp(v, lo, hi):
    v = int(v)
    return lo if v < lo else hi if v > hi else v

def _hex_to_rgb(hexs):
    s = (hexs or '').strip()
    if s.startswith('#'): s = s[1:]
    if len(s) != 6: return (0,0,0)
    try:
        return (int(s[0:2],16), int(s[2:4],16), int(s[4:6],16))
    except: return (0,0,0)

def _adv_iter(payload):
    i, n = 0, len(payload)
    while i + 1 < n:
        L = payload[i]
        if L == 0: break
        t = payload[i+1]
        v = payload[i+2:i+1+L]
        yield (t, v)
        i += 1 + L

def _decode_field(payload, adv_type):
    i, out = 0, []
    while i + 1 < len(payload):
        ln = payload[i]
        if ln == 0: break
        if payload[i+1] == adv_type:
            out.append(payload[i+2:i+1+ln])
        i += 1 + ln
    return out

def _adv_name(payload):
    n = _decode_field(payload, _ADV_TYPE_COMPLETE_NAME) or _decode_field(payload, _ADV_TYPE_SHORT_NAME)
    try:
        return (n and n[0].decode('utf-8')) or None
    except:
        return None

def _addr_str(addr_bytes):
    # В порядке как отдаёт стек (без среза со step)
    return ":".join("{:02X}".format(b) for b in addr_bytes)

def _services_from_adv(payload):
    services = []
    for code in (_ADV_UUID16_INCOMP, _ADV_UUID16_COMP,
                 _ADV_UUID32_INCOMP, _ADV_UUID32_COMP,
                 _ADV_UUID128_INCOMP, _ADV_UUID128_COMP):
        for u in _decode_field(payload, code):
            services.append(bt.UUID(u))
    return services

def _ensure_app_dir():
    try:
        os.stat('app')
    except OSError:
        try: os.mkdir('app')
        except: pass

def _safe_read_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {}

def _safe_write_json(path, obj):
    try:
        _ensure_app_dir()
        with open(path, 'w') as f:
            json.dump(obj, f)
        return True
    except Exception as e:
        print('names save error:', e)
        return False

def _mac_key(addr_bytes):
    # ключ для JSON: "AA:BB:CC:DD:EE:FF" (как даёт стек)
    return ":".join("{:02X}".format(b) for b in addr_bytes)

# ===== основной класс =====
class YN360Controller:
    """
    Стабильные имена по MAC:
      - первое появление -> "01", далее "02", ...
      - хранится в app/yn360_names.json
    on_update(devs) — всегда только подключённые.
    """
    def __init__(self, ble=None, on_update=None, max_conns=3):
        self._ble = ble or bt.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        try:
            self._ble.config(gap_name='M5')
            self._ble.config(mtu=247)
        except: pass

        self.SRV_UUID = bt.UUID(SRV_UUID_STR)
        self.CHR_UUID = bt.UUID(CHR_UUID_STR)

        # addr(bytes(6)) -> state
        self._by_addr = {}
        # алиас -> addr
        self._name2addr = {}

        # scan/connect state
        self._scanning = False
        self._auto_connect_on_done = False
        self._connect_queue = []
        self._scheduled = False
        self._cooldown = {}  # addr -> ticks deadline
        self._max_conns = max_conns
        self._on_update = on_update

        # persist имён
        self._names = _safe_read_json(_NAMES_PATH)  # {"AA:BB:...:FF": "01", ...}

        # антидребезг уведомлений
        self._last_emit_sig = None

    # ----- публичное API -----
    def set_callback(self, cb): self._on_update = cb

    def scan(self, duration_ms=4000, active=True, auto_connect=True):
        """Разово сканируем. После окончания начнём подключения (если auto_connect=True)."""
        if self._scanning:
            try: self._ble.gap_scan(None)
            except: pass
        self._scanning = True
        self._auto_connect_on_done = auto_connect
        self._ble.gap_scan(duration_ms, 30000, 30000, active)

    def clear_discovered(self):
        """Очистить найденные (не затрагивает активные подключения)."""
        self._by_addr = {a:st for a,st in self._by_addr.items() if st.get("conn") is not None}
        self._rebuild_name_index()

    def disconnect_all(self):
        for st in self._by_addr.values():
            ch = st.get("conn")
            if ch is not None:
                try: self._ble.gap_disconnect(ch)
                except: pass

    def connected_devices(self):
        return self._snapshot_connected()

    def send_scene_by_name(self, name, scene):
        # сначала пробуем наш алиас ("01"...)
        addr = self._name2addr.get(name)
        if addr:
            return self.send_scene_by_addr(addr, scene)
        # фолбэк: по рекламному имени
        for addr, st in self._by_addr.items():
            if st.get("adv") == name and st.get("conn") is not None:
                return self.send_scene_by_addr(addr, scene)
        return False

    def send_scene_by_addr(self, addr, scene):
        st = self._by_addr.get(addr)
        if not st: return False
        frame = self._build_frame(scene, st)
        st.setdefault("txq", []).append(frame)
        if st.get("conn") is not None and st.get("ch_val") is not None and not st.get("tx_busy"):
            self._drain(addr)
        elif st.get("conn") is not None and not st.get("sv_range"):
            self._ble.gattc_discover_services(st["conn"])
        return True

    def send_scene_all(self, scene):
        ok = False
        for addr, st in self._by_addr.items():
            if st.get("conn") is not None:
                ok |= self.send_scene_by_addr(addr, scene)
        return ok

    # ----- внутреннее -----
    def _snapshot_connected(self):
        """Возвращает только подключённые устройства."""
        out = []
        for addr, st in self._by_addr.items():
            if st.get("conn") is None:
                continue
            out.append({
                "addr": addr,
                "addr_str": _addr_str(addr),
                "name": st.get("name"),   # устойчивый алиас "01"
                "adv":  st.get("adv"),    # рекламное имя
                "rssi": st.get("rssi"),
                "ready": st.get("ch_val") is not None,
            })
        return out

    def _notify(self):
        """Вызывает on_update только если список подключённых реально изменился."""
        if not self._on_update:
            return
        lst = self._snapshot_connected()

        # Подпись: список MAC+готовность, отсортированный
        sig_items = []
        for d in lst:
            mac = ":".join("{:02X}".format(b) for b in d["addr"])
            sig_items.append(mac + ("#1" if d["ready"] else "#0"))
        sig_items.sort()
        sig = tuple(sig_items)

        if sig == self._last_emit_sig:
            return  # без изменений

        self._last_emit_sig = sig
        try:
            self._on_update(lst)
        except Exception as e:
            print("on_update error:", e)

    def _rebuild_name_index(self):
        self._name2addr = {}
        for a, st in self._by_addr.items():
            alias = st.get("name")
            if alias:
                self._name2addr[alias] = a

    def _assign_alias(self, addr, adv_name=None):
        """Вернёт стабильный алиас для addr; если новый — присвоит следующий, сохранит JSON."""
        key = _mac_key(addr)
        alias = self._names.get(key)
        if alias:
            return alias
        # найти следующий свободный 01..99
        used = set(self._names.values())
        n = 1
        while True:
            cand = "{:02d}".format(n)
            if cand not in used:
                alias = cand
                break
            n += 1
        self._names[key] = alias
        _safe_write_json(_NAMES_PATH, self._names)
        return alias

    def _queue_all_candidates(self):
        self._connect_queue = []
        now = time.ticks_ms()
        for addr, st in self._by_addr.items():
            if st.get("conn") is None and not st.get("connecting"):
                if time.ticks_diff(self._cooldown.get(addr, 0), now) <= 0:
                    self._connect_queue.append(addr)

    def _schedule_connect(self):
        if not self._scheduled:
            self._scheduled = True
            micropython.schedule(self._connect_scheduler, 0)

    def _connect_scheduler(self, _):
        self._scheduled = False
        # сколько слотов занято (connected + connecting)
        busy = 0
        for st in self._by_addr.values():
            if st.get("conn") is not None or st.get("connecting"):
                busy += 1
        if busy >= self._max_conns: return

        now = time.ticks_ms()
        # выкинем те, кто в «охлаждении»
        self._connect_queue = [a for a in self._connect_queue if time.ticks_diff(self._cooldown.get(a, 0), now) <= 0]

        # достанем следующего кандидата
        cand = None
        while self._connect_queue:
            a = self._connect_queue.pop(0)
            st = self._by_addr.get(a)
            if st and st.get("conn") is None and not st.get("connecting"):
                cand = a; break
        if cand is None: return

        st = self._by_addr[cand]
        st["connecting"] = True
        try:
            self._ble.gap_connect(st["addr_type"], cand)
        except OSError as e:
            st["connecting"] = False
            err = e.args[0]
            if err == 16:  # EBUSY
                self._cooldown[cand] = time.ticks_add(now, 200)
                self._connect_queue.append(cand)
            elif err == 19:  # ENODEV — адрес устарел, дождёмся нового скана
                pass
            if self._connect_queue:
                self._schedule_connect()

    def _drain(self, addr):
        st = self._by_addr.get(addr)
        if not st or st.get("tx_busy") or st.get("ch_val") is None: return
        q = st.get("txq") or []
        if not q: return
        data = q.pop(0)
        st["tx_busy"] = True
        try:
            self._ble.gattc_write(st["conn"], st["ch_val"], data, 0)  # without response
        except OSError:
            st["tx_busy"] = False
            q.insert(0, data)
            time.sleep_ms(20)

    def _build_frame(self, scene, st):
        if (scene or {}).get("mode") == "light":
            w = _clamp(scene.get("white", 0), 0, 99)
            y = _clamp(scene.get("yellow", 0), 0, 99)
            s = w + y
            last = st.get("last_sum")
            if last == s:
                if w < 99: w += 1
                elif w > 0: w -= 1
                s = w + y
            st["last_sum"] = s
            return bytes((0xAE,0xAA,0x01,w,y,0x56))
        else:
            r,g,b = scene.get("color", (0,0,0))
            return bytes((0xAE,0xA1,_clamp(r,0,255),_clamp(g,0,255),_clamp(b,0,255),0x56))

    # ----- IRQ -----
    def _irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            addr = bytes(addr)
            try:
                if self.SRV_UUID in _services_from_adv(adv_data):
                    st = self._by_addr.get(addr)
                    adv = _adv_name(adv_data)
                    if not st:
                        alias = self._assign_alias(addr, adv)
                        st = {
                            "addr_type": addr_type,
                            "name": alias,       # устойчивый алиас "01"
                            "adv":  adv,         # рекламное имя
                            "rssi": rssi,
                            "conn": None,
                            "connecting": False,
                            "sv_range": None,
                            "ch_val": None,
                            "txq": [],
                            "tx_busy": False,
                            "last_sum": None,
                        }
                        self._by_addr[addr] = st
                        self._name2addr[alias] = addr
                    else:
                        st["rssi"] = rssi
                        if not st.get("adv") and adv:
                            st["adv"] = adv
            except Exception:
                pass

        elif event == _IRQ_SCAN_DONE:
            self._scanning = False
            if self._auto_connect_on_done:
                self._queue_all_candidates()
                self._schedule_connect()

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            addr = bytes(addr)
            st = self._by_addr.get(addr)
            if not st:
                try: self._ble.gap_disconnect(conn_handle)
                except: pass
                return
            st["conn"] = conn_handle
            st["connecting"] = False
            st["sv_range"] = None
            st["ch_val"] = None
            self._ble.gattc_discover_services(conn_handle)
            self._notify()

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            addr = bytes(addr)
            st = self._by_addr.get(addr)
            if st:
                st["conn"] = None
                st["connecting"] = False
                st["sv_range"] = None
                st["ch_val"] = None
                st["tx_busy"] = False
                self._notify()

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            if isinstance(uuid, bt.UUID) and uuid == self.SRV_UUID:
                for a, st in self._by_addr.items():
                    if st.get("conn") == conn_handle:
                        st["sv_range"] = (start_handle, end_handle)

        elif event == _IRQ_GATTC_SERVICE_DONE:
            conn_handle, status = data
            for a, st in self._by_addr.items():
                if st.get("conn") == conn_handle:
                    rng = st.get("sv_range")
                    if rng:
                        self._ble.gattc_discover_characteristics(conn_handle, rng[0], rng[1])

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, properties, uuid = data
            if isinstance(uuid, bt.UUID) and uuid == self.CHR_UUID:
                for a, st in self._by_addr.items():
                    if st.get("conn") == conn_handle:
                        st["ch_val"] = value_handle

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            conn_handle, status = data
            for a, st in self._by_addr.items():
                if st.get("conn") == conn_handle:
                    self._drain(a)
                    self._notify()

        elif event == _IRQ_GATTC_WRITE_DONE:
            conn_handle, value_handle, status = data
            for a, st in self._by_addr.items():
                if st.get("conn") == conn_handle and st.get("ch_val") == value_handle:
                    st["tx_busy"] = False
                    time.sleep_ms(8)
                    self._drain(a)


def on_update(devs):
    # name — ваш устойчивый алиас ("01"), adv — рекламное имя
    print("CONNECTED:", [(d['name'], d['adv'], d['addr_str'], 'ready' if d['ready'] else '...') for d in devs])

ctrl = YN360Controller(on_update=on_update, max_conns=4)
ctrl.scan(4000, auto_connect=True)
time.sleep(6)

# По алиасу:
#ctrl.send_scene_by_name("01", {"mode":"light","white":60,"yellow":10})
# Всем:
ctrl.send_scene_all({"mode":"color","color":(40,40,0)})
time.sleep(30)