#############################################
#
# Choose here which EBike/EScooter model firmware to run:
from configurations_escooter_fiido_q1_s import model
# from configurations_escooter_iscooter_i12 import model
# from configurations_escooter_xiaomi_m365 import model

print('EBike/EScooter model:')
print(model)
print()

if model == 'escooter_fiido_q1_s':
    import escooter_fiido_q1_s.main
elif model == 'escooter_iscooter_i12':
    import escooter_fiido_q1_s.main # the same code as Fiido Q1S
elif model == 'ebike_bafang_m500':
    import ebike_bafang_m500.main
elif model == 'escooter_xiaomi_m365':
    import ebike_bafang_m500.main
else:
    raise 'You need to select a valid EBike/EScooter model'
