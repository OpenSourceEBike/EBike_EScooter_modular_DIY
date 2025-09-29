# # espnow_tx.py
# # Envia mensagens ESP-NOW para um peer específico
# 
# import network
# import uasyncio as asyncio
# import aioespnow
# 
# CHANNEL = 1  # tem de ser o mesmo do receptor
# 
# # MAC do receptor (substitui pelo que imprimiste no RX)
# PEER_MAC = b"\x00\xb6\xb3\x01\xf7\xf3"
# 
# async def main():
#     # --- configurar WiFi STA ---
#     sta = network.WLAN(network.STA_IF)
#     sta.active(True)
# 
#     # Opcional: definir MAC do emissor
#     MY_MAC = b"\x00\xb6\xb3\x01\xf7\xf2"
#     try:
#         sta.config(mac=MY_MAC)
#     except Exception as e:
#         print("Aviso: não consegui mudar o MAC ->", e)
# 
#     print("MAC emissor:", ":".join("%02x" % b for b in sta.config("mac")))
# 
#     # Garantir que não há AP ativo
#     try:
#         ap = network.WLAN(network.AP_IF)
#         if ap.active():
#             ap.active(False)
#     except Exception:
#         pass
# 
#     # Fixar canal
#     try:
#         sta.disconnect()
#     except Exception:
#         pass
#     try:
#         sta.config(channel=CHANNEL)
#     except Exception:
#         pass
# 
#     # --- ativar ESP-NOW ---
#     esp = aioespnow.AIOESPNow()
#     esp.active(True)
# 
#     # Adicionar o receptor
#     try:
#         esp.add_peer(PEER_MAC)
#         print("Peer adicionado:", ":".join("%02x" % b for b in PEER_MAC))
#     except Exception as e:
#         print("Erro ao adicionar peer:", e)
# 
#     # --- loop de envio ---
#     count = 0
#     while True:
#         msg = "Hello %d" % count
#         ok = await esp.asend(PEER_MAC, msg.encode())
#         print("Enviado:", msg, "| OK:", ok)
#         count += 1
#         await asyncio.sleep(2)
# 
# try:
#     asyncio.run(main())
# finally:
#     pass
# 
# 




#############################################
#
# Choose here which EBike/EScooter model firmware to run:
model = 'escooter_fiido_q1_s'
# model = 'ebike_bafang_m500'
# model = 'escooter_xiaomi_m365'


if model == 'escooter_fiido_q1_s':
    import escooter_fiido_q1_s.main
elif model == 'ebike_bafang_m500':
    import ebike_bafang_m500.main
elif model == 'escooter_xiaomi_m365':
    import ebike_bafang_m500.main
else:
    raise 'You need to select a valid EBike/EScooter model'
