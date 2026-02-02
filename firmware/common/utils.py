# utils.py

def map_range(x, in_min, in_max, out_min, out_max, clamp=False):
  """Map x from one range to another.

  Args:
    x: input value
    in_min, in_max: input range
    out_min, out_max: output range
    clamp: if True, clip output to [out_min, out_max]
  """
  if in_max == in_min:
    raise ValueError("in_min and in_max cannot be equal")

  result = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

  if clamp:
    if out_min < out_max:
      result = max(min(result, out_max), out_min)
    else:
      result = max(min(result, out_min), out_max)

  return result


