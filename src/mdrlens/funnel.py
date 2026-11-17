"""Funnel-plot control limits for small, unequal-sized groups (sites).

This study has 17 sites ranging from 1 subject to 51 (see data/manifest.json
after a fetch, or just `dm$SITEID` value counts). A fixed z-score cutoff
applied to a raw rate is the wrong tool here: a site with 1 subject and one
adverse event has a "rate" of 100%, which is not evidence of a problem, it
is a sample size of one. Risk-Based Quality Management (RBQM) tooling such
as Gilead-Public/gsm (Good Statistical Monitoring, cited in the README)
handles this with funnel plots: control limits computed from each site's
own denominator, so the limits widen automatically for small sites and
tighten for large ones, and a site is only flagged if it sits outside those
widened limits.

The method here is the standard normal approximation to a funnel plot
(used for a first-pass portfolio view, not a regulatory submission):

    p0 = overall rate across all sites combined (pooled numerator / pooled
         denominator)
    se_i = sqrt(p0 * (1 - p0) / n_i)      for a proportion-style rate, or
    se_i = sqrt(p0 / n_i)                  for a count-per-exposure rate
    limits_i = p0 +/- z * se_i

Two bands are drawn, as gsm and most funnel-plot RBQM tools do: a 95%-ish
"watch" band (z=2) and a 99.8%-ish "alarm" band (z=3). A site outside the
alarm band for a given KRI (key risk indicator) is flagged for review --
always shown next to its n, never on its own, because a flag on an n of 1
or 3 means "look at this with the right amount of salt," not "this site has
a problem."

Honesty note: this is a teaching-grade approximation. A real RBQM program
(e.g. gsm) also considers exact binomial/Poisson limits, multiplicity
across many simultaneous KRIs, and the direction of risk (too high AND too
low can both matter). None of that is implemented here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

RateKind = Literal["proportion", "rate"]


@dataclass
class FunnelLimits:
    n: int
    center: float
    watch_lower: float
    watch_upper: float
    alarm_lower: float
    alarm_upper: float


def funnel_limits(
    n: int,
    pooled_rate: float,
    kind: RateKind = "proportion",
    z_watch: float = 2.0,
    z_alarm: float = 3.0,
) -> FunnelLimits:
    """Control limits for one group of size n against a pooled rate.

    kind="proportion": pooled_rate in [0, 1], standard error uses
      p(1-p)/n (binomial funnel), clipped to [0, 1] at the edges since a
      rate cannot leave that range.
    kind="rate": pooled_rate is a count-per-unit-exposure (e.g. AEs per
      subject-day), standard error uses pooled_rate / n (Poisson funnel),
      clipped at 0.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if kind == "proportion":
        se = math.sqrt(max(pooled_rate * (1 - pooled_rate), 0.0) / n)
        lo_clip, hi_clip = 0.0, 1.0
    elif kind == "rate":
        se = math.sqrt(max(pooled_rate, 0.0) / n)
        lo_clip, hi_clip = 0.0, math.inf
    else:  # pragma: no cover
        raise ValueError(f"unknown kind {kind!r}")

    return FunnelLimits(
        n=n,
        center=pooled_rate,
        watch_lower=max(pooled_rate - z_watch * se, lo_clip),
        watch_upper=min(pooled_rate + z_watch * se, hi_clip),
        alarm_lower=max(pooled_rate - z_alarm * se, lo_clip),
        alarm_upper=min(pooled_rate + z_alarm * se, hi_clip),
    )


def funnel_curve(
    pooled_rate: float,
    kind: RateKind,
    n_max: int,
    n_min: int = 1,
    n_points: int = 60,
    z_watch: float = 2.0,
    z_alarm: float = 3.0,
) -> list[dict]:
    """Sample funnel_limits across n=n_min..n_max for drawing the funnel
    bands as smooth curves behind the per-site dots (the classic funnel-plot
    picture: narrow at the big-n end, flared open at the small-n end).

    n_min should be the smallest denominator any real group in the plot
    actually has (not 1 by default): extrapolating the band down to n=1
    when every real site has, say, n>=200 both overstates what the curve
    means and -- for a proportion/rate far from the band's plotted range --
    can blow the limits up to values that sit way outside the chart's own
    axis, which is a real rendering hazard, not just a cosmetic one.
    """
    n_max = max(n_max, n_min + 1)
    out = []
    seen = set()
    for i in range(n_points):
        # denser sampling at small n, where the curve bends fastest
        frac = i / (n_points - 1)
        n = max(n_min, round(n_min + (n_max - n_min) * frac**2))
        if n in seen:
            continue
        seen.add(n)
        lim = funnel_limits(n=n, pooled_rate=pooled_rate, kind=kind, z_watch=z_watch, z_alarm=z_alarm)
        out.append(
            {
                "n": n,
                "watch_lower": lim.watch_lower,
                "watch_upper": lim.watch_upper,
                "alarm_lower": lim.alarm_lower,
                "alarm_upper": lim.alarm_upper,
            }
        )
    out.sort(key=lambda r: r["n"])
    return out


def flag_outlier(observed: float, limits: FunnelLimits) -> Optional[str]:
    """Return 'high', 'low', or None, based on the alarm (z=3) band."""
    if observed > limits.alarm_upper:
        return "high"
    if observed < limits.alarm_lower:
        return "low"
    return None
