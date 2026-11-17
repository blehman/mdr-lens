"""eDISH / Hy's Law liver-safety view.

eDISH = evaluation of Drug-Induced Serious Hepatotoxicity, a standard safety
graphic (see SafetyGraphics/safetyGraphics, cited in the README) that plots,
per subject, peak transaminase (ALT or AST, whichever read higher) against
peak total bilirubin, both in x ULN (times the upper limit of normal), on
log-log axes.

Hy's Law is Hyman Zimmerman's clinical observation that a drug causing pure
hepatocellular injury *and* clinically significant bilirubin elevation in
the same patient, with no other explanation, predicts a roughly 10% risk of
fatal or transplant-requiring liver failure -- the single most feared safety
signal in a clinical trial. "Potential Hy's Law" (PHL) is the lab-only proxy
used to flag candidates for clinical review, classically:

    peak (ALT or AST) >= 3 x ULN   AND   peak total bilirubin >= 2 x ULN

This module computes that per subject from the SDTM LB (laboratory test
results) domain. It does not diagnose Hy's Law -- it flags lab patterns that
a medical reviewer would then adjudicate against the rest of the chart
(other causes of liver injury, alkaline phosphatase, etc.), exactly as the
Good Statistical Monitoring (gsm) and safetyGraphics prior art describe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .uln import peak_x_uln

ALT_CODE = "ALT"
AST_CODE = "AST"
BILI_CODE = "BILI"

PHL_TRANSAMINASE_X_ULN = 3.0
PHL_BILI_X_ULN = 2.0


@dataclass
class SubjectLiverProfile:
    usubjid: str
    peak_alt_xuln: Optional[float]
    peak_ast_xuln: Optional[float]
    peak_bili_xuln: Optional[float]
    peak_transaminase_xuln: Optional[float] = field(init=False)
    hy_flag: bool = field(init=False)

    def __post_init__(self) -> None:
        vals = [v for v in (self.peak_alt_xuln, self.peak_ast_xuln) if v is not None]
        self.peak_transaminase_xuln = max(vals) if vals else None
        self.hy_flag = bool(
            self.peak_transaminase_xuln is not None
            and self.peak_bili_xuln is not None
            and self.peak_transaminase_xuln >= PHL_TRANSAMINASE_X_ULN
            and self.peak_bili_xuln >= PHL_BILI_X_ULN
        )


def _peak_for_test(lb: pd.DataFrame, usubjid: str, testcd: str) -> Optional[float]:
    sub = lb[(lb["USUBJID"] == usubjid) & (lb["LBTESTCD"] == testcd)]
    pairs = list(zip(sub["LBSTRESN"], sub["LBSTNRHI"]))
    return peak_x_uln(pairs)


def build_liver_profiles(
    lb: pd.DataFrame, subjects: Optional[list] = None
) -> list[SubjectLiverProfile]:
    """Build one SubjectLiverProfile per subject.

    `subjects` lets the caller pass the *full* study population (every
    USUBJID in the DM -- demographics -- domain), so subjects with zero LB
    records (e.g. screen failures who never had on-study labs drawn) still
    get a profile with every peak as None, rather than silently vanishing
    from the eDISH view. Defaults to the subjects actually present in `lb`
    for backward compatibility / simple unit tests.
    """
    if subjects is None:
        subjects = sorted(lb["USUBJID"].unique())
    else:
        subjects = sorted(set(subjects))
    profiles = []
    for usubjid in subjects:
        alt = _peak_for_test(lb, usubjid, ALT_CODE)
        ast = _peak_for_test(lb, usubjid, AST_CODE)
        bili = _peak_for_test(lb, usubjid, BILI_CODE)
        profiles.append(SubjectLiverProfile(usubjid, alt, ast, bili))
    return profiles
