import board
import time
import supervisor
import array
import simpleio
import asyncio
import ebike_data
import vesc
import busio

# Tested on a ESP32-S3-DevKitC-1-N8R2

ebike = ebike_data.EBike()
vesc = vesc.Vesc(
    board.IO13, # UART TX pin that connect to VESC
    board.IO14, # UART RX pin that connect to VESC
    ebike) #VESC data object to hold the VESC data

dashboard = busio.UART(
            board.IO12,
            board.IO11,
            baudrate = 115200, # VESC UART baudrate
            timeout = 0.005, # 5ms is enough for reading the UART
            receiver_buffer_size = 512) # VESC PACKET_MAX_PL_LEN = 512
        

async def task_vesc_heartbeat():
    while True:
        # VESC heart beat must be sent more frequently than 1 second, otherwise the motor will stop
        vesc.send_heart_beat()
        
        # ask for VESC latest data
        vesc.refresh_data()

        # idle 500ms
        await asyncio.sleep(0.5)

async def task_dashboard():
    while True:
        response = dashboard.read(32)
        if response is not None:
            # print(",".join(["{}".format(i) for i in response]))
            print("")
            to_print = False
            for index, data in enumerate(response):
                if data == 255:
                    if index < (len(response) - 1):
                       if response[index + 1] == 85:
                           to_print = True

                if to_print:    
                    print(str(index) + ": " + str(data))
        
        
        # idle 500ms
        await asyncio.sleep(1)

async def main():

    print("starting")

    vesc_heartbeat_task = asyncio.create_task(task_vesc_heartbeat())
    dashboard_task = asyncio.create_task(task_dashboard())

    await asyncio.gather(vesc_heartbeat_task, dashboard_task)

asyncio.run(main())
