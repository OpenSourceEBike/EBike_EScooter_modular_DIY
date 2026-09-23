"""Allocation-light helpers for operational dual-motor telemetry."""

def select_wheel_speed(rear_speed, rear_fresh,
                       front_speed=0, front_fresh=False):
  """Prefer rear speed, falling back to a fresh front-wheel value."""
  if rear_fresh:
    return rear_speed
  if front_fresh:
    return front_speed
  return 0


def clear_stale_status_1(data):
  """Expire motion telemetry and force a speed calculation on recovery."""
  data.speed_erpm = 0
  data.wheel_speed = 0
  data.wheel_speed_last_erpm = None
  data.motor_current_x10 = 0


def refresh_wheel_speed(data):
  """Calculate wheel speed when ERPM changes or stale telemetry recovers."""
  if data.speed_erpm == data.wheel_speed_last_erpm:
    return
  data.wheel_speed_last_erpm = data.speed_erpm

  # 2*pi ≈ 6.28318
  perimeter = 6.28318 * data.cfg.wheel_radius  # meters
  motor_rpm = data.speed_erpm / max(1, data.cfg.poles_pair)
  data.wheel_speed = (perimeter * motor_rpm * 60.0) / 1000.0  # km/h

  # Small symmetric dead-zone near zero; preserve reverse motion.
  if abs(data.wheel_speed) < 1.0:
    data.wheel_speed = 0.0


def clear_stale_status_4(data, temperature_unavailable_x10):
  """Clear Status-4 values without turning unavailable temperatures into 0 C."""
  data.battery_current_x10 = 0
  data.vesc_temperature_x10 = temperature_unavailable_x10
  data.motor_temperature_x10 = temperature_unavailable_x10


def aggregate_battery_status(rear_voltage_x10, rear_current_x10, rear_fresh,
                             front_voltage_x10=0, front_current_x10=0,
                             front_fresh=False):
  """Aggregate only fresh branches for the operational Display status."""
  total_current_x10 = 0
  voltage_sum_x10 = 0
  voltage_count = 0
  voltage_weight_x10 = 0
  weighted_voltage_numerator = 0

  if rear_fresh:
    total_current_x10 += rear_current_x10
    voltage_sum_x10 += rear_voltage_x10
    voltage_count += 1
    weight = abs(rear_current_x10)
    voltage_weight_x10 += weight
    weighted_voltage_numerator += rear_voltage_x10 * weight

  if front_fresh:
    total_current_x10 += front_current_x10
    voltage_sum_x10 += front_voltage_x10
    voltage_count += 1
    weight = abs(front_current_x10)
    voltage_weight_x10 += weight
    weighted_voltage_numerator += front_voltage_x10 * weight

  if voltage_count == 0:
    voltage_x10 = 0
  elif voltage_weight_x10:
    voltage_x10 = weighted_voltage_numerator // voltage_weight_x10
  else:
    voltage_x10 = voltage_sum_x10 // voltage_count
  return voltage_x10, total_current_x10
