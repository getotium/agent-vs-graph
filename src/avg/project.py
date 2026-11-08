"""From a few hundred measured items to a monthly and annual budget.

The projection is volume × the mean cost per item. The interval around it is a bootstrap over
the measured items: it says how sure we are of that mean from this sample, not how much a real
month will vary (with 100,000 items, sampling noise in the total is negligible; what moves a
real bill is the mix of work, which no sample of ours can know). The per-item tail (p95, max) is
reported beside it, because it is what makes one shape of work predictable and another not.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Projection:
    items: int  # measured items behind the projection
    mean: float  # USD per item
    low: float  # 5th percentile of the bootstrapped mean
    high: float  # 95th percentile of the bootstrapped mean
    p95: float  # USD, the 95th-percentile item
    max: float

    def at(self, volume: int) -> tuple[float, float, float]:
        """USD for `volume` items: (estimate, low, high)."""
        return self.mean * volume, self.low * volume, self.high * volume


def quantile(xs: list[float], q: float) -> float:
    """Linear-interpolated quantile, q in [0, 1]."""
    if not xs:
        raise ValueError("no values")
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def project(costs: list[float], rounds: int = 2000, seed: int = 1) -> Projection:
    """Bootstrap the mean of per-item costs. Seeded, so a report regenerates identically."""
    if not costs:
        raise ValueError("no items to project from")
    n = len(costs)
    mean = sum(costs) / n
    if n == 1:
        return Projection(1, mean, mean, mean, mean, mean)
    rng = random.Random(seed)
    means = [sum(rng.choices(costs, k=n)) / n for _ in range(rounds)]
    return Projection(
        items=n,
        mean=mean,
        low=quantile(means, 0.05),
        high=quantile(means, 0.95),
        p95=quantile(costs, 0.95),
        max=max(costs),
    )
