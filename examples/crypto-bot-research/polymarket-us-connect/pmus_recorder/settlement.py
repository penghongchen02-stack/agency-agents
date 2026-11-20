"""Settlement math for Polymarket US crypto Up/Down markets.

Per docs.polymarket.us (Crypto FAQs): the open and close values are each the simple
average of the 60 BRTI prices published in [T - 60 s, T), rounded to 2 dp (or the
market's priceDecimals). The long (Up) side pays $1 when close >= open; ties go Up.
"""

from __future__ import annotations

from collections.abc import Mapping


def outcome(price_to_beat: float, settlement_price: float) -> str:
    return "UP" if settlement_price >= price_to_beat else "DOWN"


def window_average(ticks: Mapping[int, float], t_end: int, decimals: int = 2) -> tuple[float | None, int]:
    """Average of 1-second index closes in [t_end - 60, t_end). Returns (avg, n_ticks)."""
    vals = [ticks[t] for t in range(t_end - 60, t_end) if t in ticks]
    if not vals:
        return None, 0
    return round(sum(vals) / len(vals), decimals), len(vals)


def projected_close(ticks: Mapping[int, float], t_end: int, now: int) -> float | None:
    """Estimate of the settlement average at time `now` (< t_end).

    Seconds of [t_end-60, t_end) already elapsed use their recorded ticks; the
    remaining seconds are filled with the latest known price (driftless assumption).
    Before the averaging window starts, this is simply the latest price.
    """
    known = [t for t in ticks if t <= now]
    if not known:
        return None
    latest = ticks[max(known)]
    start = t_end - 60
    if now < start:
        return latest
    fixed = [ticks[t] for t in range(start, min(now + 1, t_end)) if t in ticks]
    remaining = 60 - len(fixed)
    return (sum(fixed) + latest * remaining) / 60


def taker_fee(price: float, contracts: float = 1.0, theta: float = 0.095) -> float:
    """Polymarket US standard taker fee: theta * C * p * (1 - p). Tier 1 theta = 0.095."""
    return theta * contracts * price * (1 - price)
