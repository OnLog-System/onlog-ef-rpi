import serial
import time

# === 포트 설정 ===
SCALE_PORT = "/dev/ttyUSB0"   # 저울
LORA_PORT = "/dev/ttyUSB1"    # LoRa-E5

# === 시리얼 초기화 ===
scale = serial.Serial(SCALE_PORT, baudrate=9600, timeout=1)
lora = serial.Serial(LORA_PORT, baudrate=9600, timeout=1)

def send_to_lora(message: str):
    """LoRa-E5로 AT+MSG 명령 전송"""
    cmd = f'AT+MSG="{message.strip()}"\r\n'
    lora.write(cmd.encode())
    time.sleep(1)
    while lora.in_waiting:
        print("[LORA]", lora.readline().decode(errors="ignore").strip())

def read_scale():
    """저울에서 한 줄 데이터 읽기"""
    line = scale.readline().decode(errors="ignore").strip()
    if line.startswith("ST,GS"):  # 정상 계량값 패턴
        try:
            value = line.split(",")[2].replace("g", "").strip()
            return value
        except Exception:
            return None
    return None

print("📡 LoRa-Scale Bridge Started")
while True:
    try:
        weight = read_scale()
        if weight:
            print(f"[SCALE] {weight} g")
            send_to_lora(f"{weight}g")
        time.sleep(5)  # 5초마다 전송
    except KeyboardInterrupt:
        print("\n🛑 종료됨")
        break
    except Exception as e:
        print("❌ Error:", e)
        time.sleep(2)
