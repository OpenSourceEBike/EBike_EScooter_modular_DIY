# import throttle as Throttle
# from configurations_escooter_fiido_q1_s import cfg

# # object for left handle bar throttle
# throttle_1 = Throttle.Throttle(
#     cfg.throttle_1_pin,
#     min = cfg.throttle_1_adc_min, # min ADC value that throttle reads, plus some margin
#     max = cfg.throttle_1_adc_max) # max ADC value that throttle reads, minus some margin

# # object for right handle bar throttle
# throttle_2 = Throttle.Throttle(
#     cfg.throttle_2_pin,
#     min = cfg.throttle_2_adc_min, # min ADC value that throttle reads, plus some margin
#     max = cfg.throttle_2_adc_max) # max ADC value that throttle reads, minus some margin

# import time

# while True:
#     print('1', throttle_1.value, throttle_1.adc_value)
#     print('2', throttle_2.value, throttle_2.adc_value)
#     time.sleep(0.33)



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
