"""USB mock controls and device-rendered RGB565 capture. Requires pyserial; capture also Pillow."""
import argparse, pathlib, re, time
import serial
p=argparse.ArgumentParser()
p.add_argument('--port', default='COM7')
p.add_argument('--command', default='', help='p page; m mode; t training; s sleeping footer; f full; r running; h stalled; d done; e error')
p.add_argument('--capture', type=pathlib.Path)
p.add_argument('--seconds', type=float, default=6)
args=p.parse_args()
port=serial.Serial(port=None,baudrate=115200,timeout=2)
port.dtr=False; port.rts=False
port.port=args.port
with port:
    time.sleep(.3);port.reset_input_buffer()
    if args.command:
        port.write(args.command.encode('ascii'));time.sleep(.5)
    if args.capture:
        from PIL import Image
        port.write(b'c')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            line=port.readline()
            m=re.match(rb'FRAME (\d+) (\d+) (\d+)',line)
            if m: break
            print(line.decode(errors='replace').strip())
        else: raise RuntimeError('No framebuffer header received')
        w,h,size=map(int,m.groups());data=bytearray()
        port.timeout=5
        while len(data)<size:
            chunk=port.read(size-len(data))
            if not chunk: raise RuntimeError(f'Truncated frame: {len(data)}/{size}')
            data.extend(chunk)
        if size!=w*h*2: raise RuntimeError('Expected RGB565 frame')
        rgb=bytearray()
        for i in range(0,size,2):
            v=data[i]|data[i+1]<<8
            rgb.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
        args.capture.parent.mkdir(parents=True,exist_ok=True)
        Image.frombytes('RGB',(w,h),bytes(rgb)).save(args.capture)
        print(f'Saved device rendering to {args.capture}')
    else:
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            line=port.readline()
            if line: print(line.decode(errors='replace').strip())
