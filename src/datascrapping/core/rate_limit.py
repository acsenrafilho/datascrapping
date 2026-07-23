from __future__ import annotations

import random
import time


def polite_sleep(delay_min: float, delay_max: float) -> float:
    """Sleep a random interval between delay_min and delay_max seconds."""
    low = max(0.0, min(delay_min, delay_max))
    high = max(delay_min, delay_max)
    if high <= 0:
        return 0.0
    waited = random.uniform(low, high)
    time.sleep(waited)
    return waited
