# Tested with MicroPython 1.26.1 sources and with added CAN TWAI driver,
# on ESP32-S3 Zero WaveShare board.

import time
from can import CAN

# --- Configuration ---
BAUDRATE = 125000    # Adjust to match your bus speed
TX_PIN   = 5
RX_PIN   = 6

# Initialize CAN interface
MODE = getattr(CAN, "NORMAL", 0)  # Use CAN.LISTEN_ONLY if available for passive sniffing
bus = CAN(tx=TX_PIN, rx=RX_PIN, baudrate=BAUDRATE, mode=MODE)

print("📡 Listening for CAN messages...\n")

# --- Main loop ---
while True:
    try:
        msg = bus.recv()  # Non-blocking: returns None or raises ETIMEDOUT when no frame is available
        if not msg:
            time.sleep_ms(10)
            continue

        mid, is_ext, rtr, data = msg
        dlc = len(data) if data else 0
        id_str = f"0x{mid:08X}" if is_ext else f"0x{mid:03X}"
        hexdata = " ".join(f"{b:02X}" for b in data) if data else ""

        print(f"RX  ID={id_str}  ext={bool(is_ext)}  rtr={bool(rtr)}  dlc={dlc}  data={hexdata}")

    except OSError as e:
        # ETIMEDOUT (116) means no frame was available during the internal timeout window
        if e.args and e.args[0] == 116:
            time.sleep_ms(5)
        else:
            print("⚠️ RX OSError:", e)
            time.sleep_ms(20)
    except Exception as e:
        print("⚠️ RX error:", e)
        time.sleep_ms(50)

