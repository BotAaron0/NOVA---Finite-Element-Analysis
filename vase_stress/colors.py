"""Logarithmic blue -> cyan -> green -> yellow -> red stress colors."""
import math

STOPS = ((0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 0, 0))
NAMES = ("blue", "cyan", "green", "yellow", "red")


def stress_color(value, maximum, log_range_decades=3.0):
    if not math.isfinite(value) or not math.isfinite(maximum) or value < 0 or maximum < 0:
        raise ValueError("Stress must be finite and nonnegative")
    if not math.isfinite(log_range_decades) or not 0 < log_range_decades <= 12:
        raise ValueError("log_range_decades must be greater than 0 and at most 12")
    gain = math.expm1(log_range_decades * math.log(10))
    ratio = min(value / maximum, 1.0) if maximum else 0.0
    t = math.log1p(gain * ratio) / math.log1p(gain)
    index = min(int(t * 4), 3)
    fraction = t * 4 - index
    return [round(a + fraction * (b - a)) for a, b in zip(STOPS[index], STOPS[index + 1])] + [255]


def color_scale(maximum, log_range_decades=3.0):
    stress_color(0, maximum, log_range_decades)
    gain = math.expm1(log_range_decades * math.log(10))
    return {"type": "log1p", "log_range_decades": log_range_decades,
            "anchors_pa": {name: maximum * math.expm1(i / 4 * math.log1p(gain)) / gain
                           for i, name in enumerate(NAMES)}}
