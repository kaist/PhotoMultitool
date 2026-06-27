from M5 import *
import M5
import time
M5.begin()
Mic.begin()
rec_data = bytearray(800)
Mic.config(noise_filter_level=5)
Mic.config(sample_rate=8000)

import struct, math

def level(buffer, little_endian=True):

    format_char = '<h' if little_endian else '>h'
    
    # Преобразуем байты в список 16-битных значений
    samples = []
    for i in range(0, len(buffer), 2):
        # Берем два байта и преобразуем в 16-битное целое число
        sample_bytes = buffer[i:i+2]
        sample_value = struct.unpack(format_char, sample_bytes)[0]
        samples.append(sample_value)
    
    # Вычисляем среднее значение (используем абсолютные значения для громкости)
    average_volume = sum(abs(sample) for sample in samples) / len(samples)
    
    return average_volume

while True:
    Mic.record(rec_data, 8000, False)
    time.sleep_ms(100)
    Mic.end()
    #print(int(level(rec_data)))
    print('#'*int(level(rec_data)/100))
    
    