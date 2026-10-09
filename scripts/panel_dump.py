"""Debug: dump both real RGB panel frame buffers (physical 320x820) and save them rotated to landscape."""
import pathlib, re, sys, time
import serial
from PIL import Image
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'build/panel')
port = serial.Serial(port=None, baudrate=115200, timeout=3); port.dtr = False; port.rts = False; port.port = 'COM7'
with port:
    time.sleep(.3); port.reset_input_buffer()
    if len(sys.argv) > 2: port.write(sys.argv[2].encode()); time.sleep(1.2)
    port.write(b'x')
    for _ in range(2):
        while True:
            m = re.match(rb'PANEL (\d) (\d+) (\d+) (\d+)', port.readline())
            if m: break
        i, w, h, size = map(int, m.groups()); data = bytearray()
        while len(data) < size: data.extend(port.read(size - len(data)))
        rgb = bytearray()
        for k in range(0, size, 2):
            v = data[k] | data[k+1] << 8
            rgb.extend((((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
        img = Image.frombytes('RGB', (w, h), bytes(rgb)).transpose(Image.ROTATE_270)
        img.save(f'{out}{i}.png'); print('saved', f'{out}{i}.png')
