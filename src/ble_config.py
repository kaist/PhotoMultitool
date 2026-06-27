import bluetooth
import json
import time
from micropython import const

# UUID сервиса и характеристик
SERVICE_UUID = bluetooth.UUID("6f2b3c1a-8d4f-4e2b-a1c3-9f0b12345678")
CHAR_RX_UUID = bluetooth.UUID("6f2b3c1a-8d4f-4e2b-a1c3-9f0b12345679")  # клиент → сервер
CHAR_TX_UUID = bluetooth.UUID("6f2b3c1a-8d4f-4e2b-a1c3-9f0b1234567a")  # сервер → клиент

# Флаги
FLAG_READ = const(0x0002)
FLAG_WRITE = const(0x0008)
FLAG_NOTIFY = const(0x0010)

# --- формирование рекламного пакета ---
def advertising_payload(name=None, services=None):
    payload = bytearray()
    if name:
        name_bytes = name.encode("utf-8")
        payload.extend(bytearray([len(name_bytes) + 1, 0x09]))  # Complete Local Name
        payload.extend(name_bytes)
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 16:
                payload.extend(bytearray([17, 0x07]))  # 128-bit UUID
                payload.extend(b)
            elif len(b) == 2:
                payload.extend(bytearray([3, 0x03]))   # 16-bit UUID
                payload.extend(b)
    return payload


class BLEConfigServer:
    def __init__(self, name="ESP32-BLE",iam=None, config=None,message_callback=None):
        self.name = name
        self.config = config
        self.message_callback=message_callback
        self.iam=iam

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.tx_handle = None
        self.rx_handle = None

        self._connections = set()
        self._rx_buffer = b""
        self._msg_queue = []

        self._register()
        self._advertise()

    # --- регистрация сервиса и характеристик ---
    def _register(self):
        services = (
            (SERVICE_UUID, (
                (CHAR_TX_UUID, FLAG_READ | FLAG_NOTIFY),
                (CHAR_RX_UUID, FLAG_WRITE),
            )),
        )
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services(services)
        print("[BLE] Service registered")

    # --- реклама BLE устройства ---
    def _advertise(self):
        payload = advertising_payload(name=self.name, services=[SERVICE_UUID])
        self.ble.gap_advertise(100, bytes(payload))
        print(f"[BLE] Advertising as {self.name}")

    # --- IRQ обработчик ---
    def _irq(self, event, data):
        if event == 1:  # подключение
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            print("[BLE] Connected", conn_handle)
        elif event == 2:  # отключение
            conn_handle, _, _ = data
            self._connections.discard(conn_handle)
            print("[BLE] Disconnected", conn_handle)
            self._advertise()
        elif event == 3:  # write к RX
            conn_handle, value_handle = data
            if value_handle == self.rx_handle:
                chunk = self.ble.gatts_read(self.rx_handle) or b""
                self._rx_buffer += chunk

                # Буферируем сообщения и обрабатываем в основном цикле
                if b"\n" in self._rx_buffer:
                    lines = self._rx_buffer.split(b"\n")
                    for line in lines[:-1]:
                        self._msg_queue.append(line)
                    self._rx_buffer = lines[-1]  # остаток

    # --- основной цикл обработки сообщений ---
    def process_messages(self):
        while self._msg_queue:
            line = self._msg_queue.pop(0)
            try:
                msg = json.loads(line.decode().strip())
                print("[BLE] Received JSON:", msg)
                self._handle_message(msg)
            except Exception as e:
                print("[BLE] JSON error:", e)

    # --- обработка команд ---
    def _handle_message(self, msg):
        if "get" in msg:
            if msg['get']=='whoareyou':
                self.send_hello()     
        elif "set" in msg:
            self.message_callback(msg['set'])




    # --- безопасная отправка JSON чанками ---
    def send_hello(self):
        data={'iam':self.iam,'config':self.config}
        self.send_data(json.dumps(data)+'\n')
        
    def send_data(self,data):
        for conn in self._connections:
            for i in range(0, len(data), 20):
                chunk = data[i:i+20]
                print(chunk)
                self.ble.gatts_notify(conn, self.tx_handle, chunk)
        print("[BLE] Config sent:", data)