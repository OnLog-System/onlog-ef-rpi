import serial
import time

SCALE_PORT = "/dev/ttyUSB0"   # QW-15
LORA_PORT = "/dev/ttyUSB1"    # LoRa-E5

scale = serial.Serial(
    SCALE_PORT,
    baudrate=4800,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=False,
    rtscts=False,
    timeout=1
)

lora = serial.Serial(LORA_PORT, baudrate=9600, timeout=1)

def send_to_lora(msg):
    cmd = f'AT+MSG="{msg.strip()}"\r\n'
    lora.write(cmd.encode())
    time.sleep(1)
    while lora.in_waiting:
        print("[LORA]", lora.readline().decode(errors="ignore").strip())

def read_scale():
    line = scale.readline().decode(errors="ignore").strip()
    if line.startswith("ST,GS"):
        try:
            val = line.split(",")[2].replace("g", "").strip()
            return val
        except Exception:
            return None
    return None

print("⚖️ QW-15 → LoRa Bridge 시작")
while True:
    try:
        weight = read_scale()
        if weight:
            print(f"[SCALE] {weight} g")
            send_to_lora(weight + "g")
        time.sleep(5)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("❌", e)
        time.sleep(2)
