import serial
import time
import sys
import struct
import traceback

# =========================
# Configuration
# =========================
SCALE_PORT = "/dev/ttyUSB0"
LORA_PORT  = "/dev/ttyUSB1"

SCALE_BAUDRATE = 4800
LORA_BAUDRATE  = 9600

APP_KEY = "2b7e151628aed2a6abf7158809cf4f3c"

MIN_TX_INTERVAL = 10       # seconds (LoRa duty protection)
JOIN_RETRY_WAIT = 60       # seconds
SERIAL_RETRY_WAIT = 5      # seconds


# =========================
# Utilities
# =========================
def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def open_serial(port, baud, name):
    while True:
        try:
            ser = serial.Serial(port, baudrate=baud, timeout=1)
            log(f"✅ {name} serial connected ({port})")
            return ser
        except serial.SerialException as e:
            log(f"⚠️ {name} serial open failed: {e}")
            time.sleep(SERIAL_RETRY_WAIT)


def send_at(ser, cmd, wait=0.5):
    try:
        ser.write((cmd + "\r\n").encode())
        time.sleep(wait)
        resp = ""
        while ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                resp += line + "\n"
        return resp.strip()
    except Exception:
        return ""


# =========================
# LoRa Handling
# =========================
def lora_join(ser):
    log("📡 LoRa init + join start")

    send_at(ser, "AT+FDEFAULT")
    send_at(ser, "AT+DR=KR920")
    send_at(ser, "AT+CH=NUM,0-2")
    send_at(ser, "AT+MODE=LWOTAA")
    send_at(ser, f'AT+KEY=APPKEY,"{APP_KEY}"')

    send_at(ser, "AT+JOIN")

    for _ in range(30):
        resp = send_at(ser, "", wait=1)
        if "Network joined" in resp:
            log("✅ LoRa network joined")
            return True
        if "Join failed" in resp:
            log("❌ Join failed (retrying)")
            send_at(ser, "AT+JOIN")
        time.sleep(1)

    log("⚠️ Join timeout")
    return False


def lora_send(ser, payload_hex):
    try:
        cmd = f'AT+MSGHEX="{payload_hex}"'
        ser.write((cmd + "\r\n").encode())
        return True
    except Exception:
        return False


# =========================
# Scale Handling
# =========================
def read_scale(ser):
    try:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            # Example: "ST,GS,  123.4 g"
            if "GS" in line and "g" in line:
                parts = line.replace("g", "").split(",")
                for p in parts:
                    try:
                        return float(p.strip())
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


# =========================
# Main FSM Loop
# =========================
def main():
    log("⚖️ Scale → LoRa Edge Sender starting")

    scale_ser = None
    lora_ser  = None
    joined    = False
    last_tx   = 0

    while True:
        try:
            # --- Ensure scale serial ---
            if scale_ser is None or not scale_ser.is_open:
                scale_ser = open_serial(SCALE_PORT, SCALE_BAUDRATE, "Scale")

            # --- Ensure LoRa serial ---
            if lora_ser is None or not lora_ser.is_open:
                lora_ser = open_serial(LORA_PORT, LORA_BAUDRATE, "LoRa")
                joined = False

            # --- Ensure joined ---
            if not joined:
                joined = lora_join(lora_ser)
                if not joined:
                    time.sleep(JOIN_RETRY_WAIT)
                continue

            # --- Read scale continuously ---
            weight = read_scale(scale_ser)
            now = time.time()

            if weight is not None and (now - last_tx) >= MIN_TX_INTERVAL:
                weight_int = int(weight * 100)
                payload = f"{weight_int:04X}"

                ok = lora_send(lora_ser, payload)
                if ok:
                    log(f"📤 Sent weight: {weight} g ({payload})")
                    last_tx = now
                else:
                    log("⚠️ LoRa send failed → force rejoin")
                    joined = False
                    time.sleep(2)

            time.sleep(0.1)

        except serial.SerialException:
            log("⚠️ Serial disconnected → reset")
            try:
                if scale_ser:
                    scale_ser.close()
                if lora_ser:
                    lora_ser.close()
            except Exception:
                pass
            scale_ser = None
            lora_ser  = None
            joined = False
            time.sleep(SERIAL_RETRY_WAIT)

        except Exception as e:
            log("🔥 Unexpected error")
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main()
