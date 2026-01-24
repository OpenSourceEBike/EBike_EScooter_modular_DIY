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


def clamp(x, min_val, max_val):
    """Clamp value into range [min_val, max_val]."""
    return max(min_val, min(x, max_val))


def moving_average(samples, new_val, window=10):
    """Update a simple moving average buffer."""
    samples.append(new_val)
    if len(samples) > window:
        samples.pop(0)
    return sum(samples) / len(samples)
