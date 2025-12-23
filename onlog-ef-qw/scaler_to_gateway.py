import serial
import time
import sys
import struct

# === 설정 구간 ===
SCALE_PORT = "/dev/ttyUSB0"   # 저울 포트
LORA_PORT = "/dev/ttyUSB1"    # LoRa-E5 포트
LORA_BAUDRATE = 9600
SCALE_BAUDRATE = 4800



# [중요] ChirpStack에서 확인한 AppKey를 입력하세요 (DevEUI는 모듈 내장값 사용 권장)
APP_KEY = "2b7e151628aed2a6abf7158809cf4f3c"

def setup_serial_connection(port, baudrate, name):
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"✅ [{name}] 연결 성공: {port}")
        return ser
    except serial.SerialException as e:
        print(f"❌ [{name}] 연결 실패: {e}")
        sys.exit(1)

def send_at_cmd(ser, cmd, wait_time=0.5):
    """AT 명령어를 보내고 응답을 반환합니다."""
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait_time)
    response = ""
    while ser.in_waiting:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                response += line + "\n"
        except:
            pass
    return response.strip()

def init_lora(ser):
    """LoRa 모듈 초기화 및 네트워크 가입 (Join)"""
    print("\n📡 [LoRa] 초기화 및 네트워크 접속 시도...")

    # 1. 설정 초기화 및 주파수 설정 (한국)
    send_at_cmd(ser, "AT+FDEFAULT")      # 공장 초기화
    send_at_cmd(ser, "AT+DR=KR920")      # 한국 주파수 대역
    send_at_cmd(ser, "AT+CH=NUM,0-2")    # 채널 설정 (통신사 호환)
    send_at_cmd(ser, "AT+MODE=LWOTAA")   # OTAA 모드

    # 2. 키 설정
    send_at_cmd(ser, f'AT+KEY=APPKEY,"{APP_KEY}"')

    # 3. Join 시도
    print("⏳ [LoRa] 네트워크 가입 요청 중 (AT+JOIN)...")
    send_at_cmd(ser, "AT+JOIN")

    # Join 완료 대기 (최대 30초)
    for _ in range(30):
        response = send_at_cmd(ser, "") # 빈 명령으로 로그 읽기
        if "Network joined" in response:
            print("✅ [LoRa] 네트워크 가입 성공!")
            return True
        if "Join failed" in response:
            print("❌ [LoRa] 가입 실패. 재시도 필요.")
            send_at_cmd(ser, "AT+JOIN")
        print(".", end="", flush=True)
        time.sleep(1)

    print("\n⚠️ [LoRa] 가입 시간 초과. (Gateway 상태를 확인하세요)")
    return False

def read_scale(scale_ser):
    """저울 데이터 읽기 (이전 코드와 동일)"""
    if scale_ser.in_waiting:
        try:
            line = scale_ser.readline().decode(errors="ignore").strip()
            # 예: "ST,GS,  123.4 g" 형태 처리
            if "GS" in line and "g" in line:
                parts = line.split(",")
                # 간단한 파싱 로직 (상황에 맞춰 조정)
                for part in parts:
                    clean_part = part.replace("g", "").strip()
                    try:
                        return float(clean_part)
                    except ValueError:
                        continue
        except Exception:
            pass
    return None

def main():
    print("=== ⚖️ LoRaWAN Real-time Scale ===")

    scale = setup_serial_connection(SCALE_PORT, SCALE_BAUDRATE, "저울")
    lora = setup_serial_connection(LORA_PORT, LORA_BAUDRATE, "LoRa")

    # 1. 초기화
    if not init_lora(lora):
        return

    print("\n🚀 데이터 전송 모드 시작...\n")

    # === [수정됨] 시간 관리 변수 ===
    last_send_time = 0
    MIN_INTERVAL = 10  # 최소 전송 간격 (초 단위). 5초 이하로 줄이면 전송 실패 확률 높음.

    while True:
        try:
            # 2. 저울 값은 쉬지 않고 계속 읽습니다. (버퍼 비우기 효과)
            weight = read_scale(scale)

            # 현재 시간 확인
            current_time = time.time()

            # 3. 데이터가 있고 + 마지막 전송 후 5초가 지났다면 -> 전송!
            if weight is not None and (current_time - last_send_time > MIN_INTERVAL):

                print(f"⚖️ [실시간 측정] {weight} g")

                # 데이터 인코딩
                weight_int = int(weight * 100)
                hex_payload = "{:04X}".format(weight_int)

                # 전송 (Unconfirmed 모드로 변경 권장: 속도가 더 빠름)
                # AT+MSGHEX는 응답(ACK)을 기다리지 않아서 연속 전송에 유리함
                # Confirmed 모드로 바꾸고 싶다면 CMSGHEX 명령어 사용
                cmd = f'AT+MSGHEX="{hex_payload}"'

                print(f"📡 [전송] {hex_payload}")

                # 전송 명령
                lora.write((cmd + "\r\n").encode())

                # [중요] 전송 후 쿨타임 갱신
                last_send_time = time.time()

                # LoRa 모듈이 명령을 소화할 아주 짧은 틈은 필요함
                time.sleep(0.5)

            else:
                # 데이터를 못 읽었거나 쿨타임 중이면 아주 짧게 대기
                time.sleep(0.1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

    scale.close()
    lora.close()

if __name__ == "__main__":
    main()