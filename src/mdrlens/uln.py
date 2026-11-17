"""The one piece of arithmetic everything else here leans on: x ULN.

ULN = upper limit of normal. Lab results in clinical trials are read relative
to the normal range for the specific lab that ran the test, not an absolute
number, because normal ranges differ slightly lab to lab (see LBSTNRHI in
the SDTM LB domain, which is 34, 43, 35 or 32 for ALT across the four labs in
this study). "x ULN" means (result / upper limit of normal) -- a result of
3 x ULN is three times the top of that lab's normal range, independent of
which lab or which unit was used, which is why eDISH (evaluation of Drug-
Induced Serious Hepatotoxicity) plots and Hy's Law criteria are always
written in x ULN rather than raw units.
"""

from __future__ import annotations

import math
from typing import Optional


def x_uln(value: Optional[float], uln: Optional[float]) -> Optional[float]:
    """Return value / uln, or None if either input is missing/non-positive.

    None propagates deliberately: a missing result or a missing/zero normal
    range must never silently become a number (e.g. a 0 or a 1.0 "looks
    normal" value), because that is exactly the kind of silent data problem
    a medical data reviewer is paid to catch.
    """
    if value is None or uln is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(uln, float) and math.isnan(uln):
        return None
    if uln <= 0:
        return None
    return value / uln


def peak_x_uln(records: list[tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    """Peak (maximum) x ULN across a subject's records for one lab test.

    `records` is a list of (result, uln) pairs, e.g. every ALT draw for one
    subject across every visit. Returns None if no record yields a valid
    ratio (e.g. the subject has no results for that test at all).
    """
    ratios = [r for r in (x_uln(v, u) for v, u in records) if r is not None]
    if not ratios:
        return None
    return max(ratios)
