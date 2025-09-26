# main_async.py
# uasyncio-driven loop for JbdBmsClient
#
# Tasks:
#   • bms_task      — drives JbdBmsClient.tick() at ~20 Hz
#   • reporter_task — reads cached values every 1 s (only when fresh)
#
# Notes:
#   • We import uasyncio as asyncio (MicroPython flavor).
#   • Avoid asyncio.gather() (not always present in uasyncio); use create_task().
#   • Keep the tick cadence 50–200 ms. 50 ms gives snappy updates without chatter.

import uasyncio as asyncio
import bluetooth
from bms_jbd import JbdBmsClient

# Change here the BMS device Bluetooth name
bms_bluetooth_name = 'BMS-BTT_JP'

async def bms_task(bms: JbdBmsClient):
    """
    Drive the client's cooperative state machine.
    Must run frequently so we:
      - drain BLE notifications,
      - schedule 0x03/0x04 polls,
      - keep reconnect logic responsive.
    """
    bms.start(scan_ms=8000)
    while True:
        bms.tick()
        await asyncio.sleep_ms(50)  # ~20 Hz tick

async def reporter_task(bms: JbdBmsClient):
    """
    Periodically read cached data. No blocking, no BLE calls here.
    We only print if the link is up and data arrived recently.
    """
    while True:
        if bms.is_connected() and bms.is_fresh(3000):
            v   = bms.get_battery_voltage()
            soc = bms.get_soc_percent()
            if (v is not None) and (soc is not None):
                print()
                print(f"Battery voltage: {v:.2f} V")
                print(f"Battery SOC: {soc:d} %")
            # You could also pull cells/temps/etc. here if desired:
            # cells = bms.get_cells()
            # temps = bms.get_temps_c()
        await asyncio.sleep_ms(1000)  # print cadence

async def main():
    # Single BLE stack instance shared with the client
    ble = bluetooth.BLE()
    bms = JbdBmsClient(
        ble=ble,
        target_name=bms_bluetooth_name,
        query_period_ms=1000,
        interleave_cells=True,
        debug=False,
    )

    # Launch tasks
    asyncio.create_task(bms_task(bms))
    asyncio.create_task(reporter_task(bms))

    # Keep the event loop alive forever
    while True:
        await asyncio.sleep(3600)

# Entry point
asyncio.run(main())
