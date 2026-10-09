"""Finds the VibeHUD board on USB and streams snapshots to it."""
from __future__ import annotations
import serial
from serial.tools import list_ports

ESP32S3_VID, ESP32S3_PID = 0x303A, 0x1001     # Espressif USB-serial/JTAG (the board's native USB)

def find_port() -> str | None:
    for p in list_ports.comports():
        if p.vid == ESP32S3_VID and p.pid == ESP32S3_PID:
            return p.device
    return None

class Device:
    def __init__(self, port: str | None = None):
        self.port_name = port
        self.serial: serial.Serial | None = None

    def connected(self) -> bool:
        return self.serial is not None and self.serial.is_open

    def connect(self) -> bool:
        name = self.port_name or find_port()
        if not name:
            return False
        try:
            ser = serial.Serial(port=None, baudrate=115200, write_timeout=2)
            ser.dtr = False; ser.rts = False        # asserting these on this chip resets it
            ser.port = name
            ser.open()
        except (serial.SerialException, OSError):
            return False
        self.serial = ser
        return True

    def send(self, payload: bytes) -> bool:
        if not self.connected():
            return False
        try:
            self.serial.write(payload)
            self.serial.reset_input_buffer()        # board logs are not needed; keep the OS buffer small
            return True
        except (serial.SerialException, OSError):
            self.close()
            return False

    def close(self):
        if self.serial:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
