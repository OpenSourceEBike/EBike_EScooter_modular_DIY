def map_value(x, in_min, in_max, out_min, out_max):
    # Prevent division by zero
    if in_min == in_max:
        raise ValueError("Input range cannot be zero (in_min == in_max)")

    # Clamp input
    if in_min < in_max:
        x = max(min(x, in_max), in_min)
    else:
        x = max(min(x, in_min), in_max)

    # Map value
    result = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    # Clamp output
    if out_min < out_max:
        result = max(min(result, out_max), out_min)
    else:
        result = max(min(result, out_min), out_max)

    return result
