# mdr-lens

A small, local portfolio project: Medical Data Review (MDR, the ongoing clinical
review of incoming trial data for safety issues and data problems) views built on
one public, already-finished clinical trial dataset. Built to show interest and
some of the underlying skills for Real-Time Visual Analytics (RVA) / Medical Data
Review roles that build dashboards for safety signal detection and Risk-Based
Quality Management (RBQM) — not to claim real clinical-trial experience. Everything
here is local and was never deployed, pushed, or made public.

Data: the long-standing CDISC (Clinical Data Interchange Standards Consortium)
Pilot Project study, redistributed as SDTM (Study Data Tabulation Model) tables by
the pharmaverse community's [pharmaverse/pharmaversesdtm](https://github.com/pharmaverse/pharmaversesdtm)
package (Apache-2.0 license). It is a public, synthetic/anonymized teaching dataset
used across the industry for exactly this kind of tooling practice: 306 subjects,
17 sites, 1,191 adverse events, 59,580 lab results. No data here comes from any
real patient, and none of it is related to any employer's systems.

## What it is

One static HTML page (`web/index.html`, D3 + Observable Plot, both vendored so the
page runs fully offline with no network calls) plus a small Python package that
computes everything the page shows. The page is built "monad"-style: it starts
with one patient, then widens to the whole study, then to the 17 sites, then to
the data itself — never a dashboard grid of unrelated tiles.

1. **One patient** — a single subject's adverse events, lab results, visits, and
   disposition (discontinuation/completion) on one time axis, the way a reviewer
   would actually read a case before looking at aggregates.
2. **Whole study — eDISH** (evaluation of Drug-Induced Serious Hepatotoxicity) —
   peak liver enzyme (ALT/AST) vs. peak bilirubin, both in × ULN (upper limit of
   normal: a lab result ÷ that lab's own normal-range ceiling, so different labs'
   units are comparable), log–log, with Hy's Law reference lines. Hy's Law is
   Hyman Zimmerman's observation that enzyme elevation *and* bilirubin elevation in
   the same patient predicts serious liver injury; "potential Hy's Law" is the
   lab-only screening pattern used here (≥3× ULN enzyme and ≥2× ULN bilirubin) to
   flag candidates for a reviewer, not a diagnosis.
3. **Whole study — adverse-event explorer** — every AE (adverse event), filterable
   by severity and MedDRA (Medical Dictionary for Regulatory Activities) body
   system, with the one-patient subject highlighted in context.
4. **Sites — RBQM-style key risk indicators (KRIs)** — per site: AE reporting rate,
   missing-lab rate, and visit out-of-window rate, each checked against a
   funnel-plot band that widens for small sites (gsm-style, see Prior art), with
   site size (n) shown beside every flag.
5. **Data quality** — missing required fields, duplicate records, and
   out-of-window visits, per SDTM domain.

## What each view answers for a reviewer

- *Is any subject showing the lab pattern that predicts serious drug-induced liver
  injury?* — the eDISH view.
- *What happened to this subject, in order, across every data source at once?* —
  the one-patient timeline.
- *What adverse events has the study seen, and does this one look unusual for its
  body system or severity?* — the AE explorer.
- *Is any site behaving differently enough from the rest of the study to warrant a
  closer look — accounting for the fact that a 1-subject site and a 51-subject
  site can't be held to the same bar?* — the site KRI view.
- *Can the numbers above even be trusted, given what's missing or duplicated in the
  source data?* — the data-quality view.

## CRF vs. non-CRF data

A CRF (case report form) is the form — paper or electronic — a trial site fills
out to record a subject's visit: adverse events, concomitant medications, physical
exam findings. Non-CRF data arrives by other routes: central lab results, ECG
(electrocardiogram) readings, imaging — typically a data feed from a vendor rather
than something a site coordinator types in. A real Medical Data Review workflow
reconciles both: a lab value from the non-CRF feed and an adverse event the site
entered on a CRF should tell a consistent story (e.g. a severe lab abnormality
with no matching AE entered is itself a data-quality flag). This project's SDTM
domains already carry that distinction (LB is lab, i.e. non-CRF data; AE is
CRF-entered) but doesn't reconcile the two against each other end to end — a real
EDC (Electronic Data Capture) system and query workflow would.

## Prior art (read and cited; no code copied)

- [Gilead-Public/gsm](https://github.com/Gilead-Public/gsm) (Good Statistical
  Monitoring, Apache-2.0) — the RBQM key-risk-indicator and funnel-plot method the
  site view here follows.
- [pharmaverse/teal](https://github.com/insightsengineering/teal) — Roche/Genentech's
  open-source clinical data exploration framework.
- [SafetyGraphics/safetyGraphics](https://github.com/SafetyGraphics/safetyGraphics)
  — the eDISH / Hy's Law graphic convention this project's liver-safety view
  follows.

## Honesty about the statistics

17 sites is a thin population for process-control rules, and this study's sites
range from 1 subject to 51 — a single fixed cutoff applied to a raw rate would be
meaningless for the small ones. Every KRI limit here is a funnel-plot band (normal
approximation: a pooled study-wide rate ± 2 or 3 standard errors, with the standard
error shrinking as a site's own denominator grows) so the band narrows for big
sites and flares open for small ones, and every flag in the page and the table is
shown next to that site's **n**. A flag on a 3-subject site is a prompt to look
closer, not a finding. This is also a normal-approximation shortcut, not the exact
binomial/Poisson method or the multiplicity correction a real RBQM program (e.g.
gsm) would use — see Limits below.

This is a look back at **one already-completed pilot study**, not a live feed —
nothing on the page is real-time, and the page says so.

## What a real trial would add

- A live EDC/CRF feed, refreshing continuously, instead of one static,
  already-closed dataset.
- The EX (drug exposure) domain for real dosing dates, instead of the DM
  (demographics) domain's reference start/end dates used here as a stand-in for
  exposure duration.
- A published protocol visit schedule with real visit windows, instead of the
  ±7-day window around each visit's study-wide median day used here as a proxy.
- A query workflow — raising a data query against a site, tracking it to
  resolution, and re-running these KRIs — which this static page has no mechanism
  for.
- Formal validation against a define.xml and the study's own CDISC conformance
  rules, not the hand-picked "required field" list used here.
- Exact (not normal-approximation) funnel limits, multiplicity correction across
  many simultaneous KRIs, and clinical adjudication of every flag by a reviewer.

## How to run it

```sh
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# one command: fetch the public data, rebuild every derived number, re-run every
# check (including an independent recount of the headline numbers straight from
# the raw tables, in tests/test_independent_recount.py)
uv run python scripts/fetch_data.py && uv run python scripts/build.py && uv run pytest
```

Then open `web/index.html` directly in a browser — no server, no network
connection needed. `scripts/fetch_data.py` downloads the five SDTM domains used
here (`dm`, `ae`, `lb`, `sv`, `ds`) to `data/raw/` (gitignored) and records the
source URL and a sha256 of every file in `data/manifest.json`. `scripts/build.py`
computes every number on the page from those raw files and writes the small
derived JSON in `data/derived/` plus `web/data.js` (the bundle the page actually
loads).

## QA

`tests/` is plain pytest (`uv run pytest`), including hand-checked × ULN math
against real values from one subject, and the independent recount above. The page
was opened in Playwright under Chromium (1440×900) and WebKit/iPhone 14 (390×844);
screenshots are in `docs/screenshots/`, zero browser console errors on either.

## Limits

- Teaching dataset, not a live trial: nothing here is real-time, and the
  "real-time" dashboards an RVA role actually builds would look structurally
  different (continuous refresh, query workflow, access control, validation).
- The "required field" list per domain, the ±7-day visit window, and the KRI
  thresholds are reasonable choices for a demo, not a validated clinical
  monitoring plan.
- No claim of real clinical-trial experience: this is a skills demonstration on
  public data, built to close a specific gap, not a substitute for it.
