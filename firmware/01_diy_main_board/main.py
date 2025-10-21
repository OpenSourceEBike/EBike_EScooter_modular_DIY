#############################################
#
# Choose here which EBike/EScooter model firmware to run:
model = 'escooter_fiido_q1_s'
# model = 'escooter_iscooter_i12'
# model = 'ebike_bafang_m500'
# model = 'escooter_xiaomi_m365'


if model == 'escooter_fiido_q1_s':
    import escooter_fiido_q1_s.main
elif model == 'escooter_iscooter_i12':
    import escooter_iscooter_i12.main
elif model == 'ebike_bafang_m500':
    import ebike_bafang_m500.main
elif model == 'escooter_xiaomi_m365':
    import ebike_bafang_m500.main
else:
    raise 'You need to select a valid EBike/EScooter model'
