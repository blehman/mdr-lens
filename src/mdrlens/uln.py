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

import pandas as pd


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


def peak_x_uln_by_test(lb: pd.DataFrame, subjects: list, tests: list[str]) -> list[dict]:
    """Peak x ULN per subject per lab test code -- the same `peak_x_uln`
    arithmetic mdrlens.hyslaw.build_liver_profiles uses for ALT/AST/BILI,
    generalized to any list of LBTESTCD values.

    This is the one reusable primitive mdrlens.second_study plugs a
    different SDTM study's LB (laboratory test results) domain into: a
    study whose LB domain doesn't carry one of `tests` (e.g. no BILI
    draws at all) simply yields no rows for that test, never a fabricated
    value. See mdrlens.studyconfig.StudyConfig.liver_panel_tests for how a
    study declares which tests it actually ran.
    """
    out = []
    for usubjid in sorted(set(subjects)):
        sub = lb[lb["USUBJID"] == usubjid]
        for test in tests:
            test_rows = sub[sub["LBTESTCD"] == test]
            pairs = list(zip(test_rows["LBSTRESN"], test_rows["LBSTNRHI"]))
            peak = peak_x_uln(pairs)
            if peak is not None:
                out.append({"usubjid": usubjid, "test": test, "peak_x_uln": round(peak, 4)})
    return out
