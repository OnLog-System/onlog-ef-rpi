# ⚖️ onlog-ef-qw — RS232 전자저울 LoRa 연동 모듈

본 디렉터리는 **CAS QW-15 전자저울**의 RS-232 계량 데이터를  
**Raspberry Pi 5 → LoRa-E5 Dev Board → RAK7268 Gateway → ChirpStack**으로  
전송하기 위한 **엣지 노드용 브리지 모듈**입니다.

---

## 🧩 개요

| 항목     | 내용                                   |
|----------|----------------------------------------|
| 장비     | CAS QW-15 (RS232, 4800 bps)            |
| 변환     | FTDI RS232–USB (FT232)                 |
| 제어 장치| Raspberry Pi 5 (8GB)                   |
| 송신 모듈| LoRa-E5 Dev Board (CP210x UART, v4.0.11)|
| 게이트웨이| RAK7268V2 (KR920)                     |
| 네트워크 | LoRaWAN (OTAA, Class A)                |
| 서버     | ChirpStack v4 (Docker Compose)         |

---

## ⚙️ 주요 파일

| 파일명                | 설명                                 |
|-----------------------|--------------------------------------|
| `lora_scale_bridge.py`| 저울 → LoRa 송신 전체 파이프라인 구현 |
| `README.md`           | 본 문서                              |

---

## 📜 lora_scale_bridge.py 개요

```python
import serial, time

SCALE_PORT = "/dev/ttyUSB0"  # QW-15
LORA_PORT  = "/dev/ttyUSB1"  # LoRa-E5

# 저울 데이터 수집
scale = serial.Serial(SCALE_PORT, 4800, timeout=1)
LoRa 제어
lora  = serial.Serial(LORA_PORT, 9600, timeout=1)
  </code></pre>

  <h3>🧠 동작 흐름</h3>
  <ol>
    <li>저울에서 <code>ST,GS, 00091.0 g</code> 형식의 문자열 수신</li>
    <li>무게값(예: <code>91.0</code>)을 파싱</li>
    <li>값이 이전과 달라질 때만 LoRa-E5로 전송</li>
    <li>LoRa-E5는 <code>AT+MSG="91.0g"</code> 명령으로 uplink 수행</li>
    <li>Gateway → ChirpStack → MQTT → DB 로 전달</li>
  </ol>

  <h3>💡 주요 특징</h3>
  <ul>
    <li>실시간 스트림 기반 수집 (4800 8N1)</li>
    <li>중복 송신 방지 (<code>last_weight</code> 비교)</li>
    <li>AT 명령 기반 uplink (<code>AT+MSG</code>)</li>
    <li>예외 처리 및 포트 재시도 구조 포함</li>
    <li>향후 FSM(Self-Healing) 구조 확장 가능</li>
  </ul>

  <hr>

  <h2>🧩 실행 방법</h2>
  <pre><code>
#실행 전 포트 권한 부여
sudo chmod 666 /dev/ttyUSB0 /dev/ttyUSB1

#스크립트 실행
python3 lora_scale_bridge.py
  </code></pre>

  <p>출력 예시:</p>
  <pre><code>
⚖️ QW-15 → LoRa Bridge 시작
[SCALE] 91.0 g
[LORA] +MSG: Start
[LORA] +MSG: Done
  </code></pre>

  <hr>

  <h2>🧰 예시 하드웨어 연결</h2>
  <table border="1" cellspacing="0" cellpadding="6">
    <tr><th>장치</th><th>포트</th><th>비고</th></tr>
    <tr><td>QW-15 TXD(2)</td><td>FTDI RXD(2)</td><td>데이터 송신</td></tr>
    <tr><td>QW-15 GND(7)</td><td>FTDI GND(5)</td><td>공통 접지</td></tr>
    <tr><td>FTDI</td><td>USB A</td><td>Raspberry Pi 5 연결</td></tr>
    <tr><td>LoRa-E5</td><td>USB C</td><td>Raspberry Pi 5 연결</td></tr>
  </table>

  <hr>

  <h2>📡 ChirpStack 설정 요약</h2>
  <table border="1" cellspacing="0" cellpadding="6">
    <tr><th>항목</th><th>값</th></tr>
    <tr><td>Region</td><td>KR920-923</td></tr>
    <tr><td>MAC Version</td><td>1.0.3</td></tr>
    <tr><td>Regional Param</td><td>RP002-1.0.2</td></tr>
    <tr><td>Activation</td><td>OTAA (Class A)</td></tr>
    <tr><td>DevEUI</td><td>2CF7F120701006F7</td></tr>
    <tr><td>AppEUI</td><td>526973696E674846</td></tr>
    <tr><td>AppKey</td><td>2B7E151628AED2A6ABF7158809CF4F3C</td></tr>
  </table>

  <hr>

  <h2>🧪 테스트 명령 요약</h2>
  <table border="1" cellspacing="0" cellpadding="6">
    <tr><th>명령</th><th>설명</th></tr>
    <tr><td><code>AT</code></td><td>장치 연결 확인</td></tr>
    <tr><td><code>AT+MODE=LWOTAA</code></td><td>OTAA 모드 설정</td></tr>
    <tr><td><code>AT+DR=KR920</code></td><td>지역 대역 설정</td></tr>
    <tr><td><code>AT+JOIN</code></td><td>네트워크 조인</td></tr>
    <tr><td><code>AT+MSG="HELLO"</code></td><td>uplink 테스트</td></tr>
    <tr><td><code>AT+TDC=60000</code></td><td>60초 주기 자동 송신</td></tr>
  </table>

  <hr>

  <h2>🪄 향후 계획</h2>
  <ul>
    <li>Confirmed Uplink (<code>AT+CMSG</code>) 시험</li>
    <li>LoRa 송신 실패 시 로컬 SQLite 버퍼링</li>
    <li>systemd 서비스화 (<code>/etc/systemd/system/lora-scale.service</code>)</li>
  </ul>

  <hr>


</body>
</html>
