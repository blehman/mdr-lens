# Sample Medical Data Review Plan — mdr-lens

A demonstration plan showing how this page's own §01–06 views would be
organized into a Medical Data Review (MDR, the ongoing clinical review of
incoming trial data for safety issues and data problems) cadence, from
critical-to-quality factor → the risk each existing view watches →
threshold → who would review it, and at which milestone. It reuses the
same 25/50/75/100% enrollment-milestone cuts §01's "Live study simulator"
already computes (`review_meeting_cuts`, `src/mdrlens/cuts.py`) as a
deterministic stand-in for cohort reviews and safety data review committee
meetings.

**This plan is a sample, built on public guidance as its basis. It is not
a validated or regulatory-submitted Medical Data Review Plan, and neither
this document nor any view on the mdr-lens page claims compliance with, or
certification against, any source cited below.** It also makes no
statement about any employer's internal Medical Data Review processes.

## Basis: sources (fetched from their official hosting, dated)

1. **ICH (International Council for Harmonisation) E6(R3), Good Clinical
   Practice.** Final guideline; adopted by the U.S. FDA (Food and Drug
   Administration) as final guidance, September 2025.
   <https://www.fda.gov/media/169090/download>
   (guidance page: <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/e6r3-good-clinical-practice-gcp>).
   **Fetched 2026-11-17.**
2. **ICH E8(R1), General Considerations for Clinical Studies.** Final
   guideline; adopted by the FDA as final guidance, April 2022.
   <https://www.fda.gov/media/157560/download>
   (guidance page: <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/e8r1-general-considerations-clinical-studies>).
   **Fetched 2026-11-17.**
3. **TransCelerate BioPharma Inc., Risk-Based Monitoring (RBM) initiative**
   — the industry-consortium work underlying what is now commonly called
   Risk-Based Quality Management (RBQM): the Risk Assessment and
   Categorization Tool (RACT) template/example and the Risk Indicator
   Library.
   <https://www.transceleratebiopharmainc.com/initiatives/risk-based-monitoring/>
   (initiative overview) and
   <https://www.transceleratebiopharmainc.com/rbminteractiveguide/rbm-toolbox/>
   (toolbox listing the RACT and Risk Indicator Library).
   **Fetched 2026-11-17.**
4. **FDA, "Oversight of Clinical Investigations — A Risk-Based Approach to
   Monitoring," Guidance for Industry.** August 2013.
   <https://www.fda.gov/media/116754/download>
   (guidance page: <https://www.fda.gov/regulatory-information/search-fda-guidance-documents/oversight-clinical-investigations-risk-based-approach-monitoring>).
   **Fetched 2026-11-17.**

This sample plan cites these documents as its basis; it does not claim
compliance or certification.

These four public documents are this plan's **basis** — the language
below (critical-to-quality factors, quality by design, risk-based
monitoring, quality tolerance limits, centralized monitoring, critical
data and processes) is their own vocabulary, used here to show how this
project's existing views would slot into a real program built on top of
them. See each guidance document's own text for its full, authoritative
scope; FDA guidance documents are explicitly nonbinding recommendations,
not requirements.

## How ICH E8(R1) and E6(R3) connect

ICH E8(R1) §3.2 defines **critical-to-quality (CtQ) factors** as "attributes
of a study whose integrity is fundamental to the protection of study
participants, the reliability and interpretability of the study results,
and the decisions made based on the study results," to be identified
prospectively (§3.3) and reviewed periodically (§3.3.4) as a study
progresses. §7 gives a non-exhaustive list of considerations for
identifying them — among others, that "the protocol specifies the
collection of data needed to meet the study objectives, understand the
benefit/risk of the drug, and monitor participant safety," and that "the
extent and nature of study monitoring are tailored to the specific study
design and objectives and the need to ensure participants' safety."

ICH E6(R3) §3.10 (Quality Management) then operationalizes that: sponsors
should adopt "a proportionate and risk-based approach to quality
management, which involves incorporating quality into the design of the
clinical trial (i.e., quality by design) and identifying those factors
... likely to have a meaningful impact on participants' rights, safety
and well-being, and the reliability of the results (i.e., critical to
quality factors as described in ICH E8(R1))." §3.10.1 walks through risk
identification, evaluation, control (including, "where relevant,"
prespecified **quality tolerance limits** at the trial level), communication,
review, and reporting. §3.11.4 (Monitoring) describes **centralized
monitoring** — "an evaluation of accumulated data, performed in a timely
manner" that "can identify systemic or site-specific issues" — as
complementary to on-site monitoring, with the monitoring plan itself
focused on "aspects that are critical to quality."

FDA's 2013 risk-based monitoring guidance frames the same idea
operationally: sponsors should "prospectively identify **critical data and
processes**... then perform a risk assessment... and then develop a
monitoring plan that focuses on the important and likely risks to critical
data and processes," with **centralized monitoring** techniques
"identify[ing] the great majority of on-site monitoring findings" in the
cited literature review. TransCelerate's RBM toolkit operationalizes the
same risk-assessment step further still with the RACT (a structured way to
categorize and score those risks) and a library of standard risk
indicators — the same key-risk-indicator (KRI) concept §05 of this page's
site-level view already implements (see README's "Prior art," citing
Gilead-Public/gsm).

## The plan

Six rows below map a CtQ factor (per E8(R1) §7's considerations) to the
risk it protects against, the existing mdr-lens view that watches it, that
view's own threshold (already implemented in `src/mdrlens/`), the
milestone at which it would be reviewed, and who would review it.
"Milestone" reuses §01's own 25/50/75/100% enrollment-milestone cuts
(`review_meeting_cuts`) as the deterministic stand-in for cohort reviews
and safety data review committee meetings that ICH E8(R1) §7 and FDA's
2013 guidance describe tailoring to a study's own design.

| Critical-to-quality factor (ICH E8(R1) §7) | Risk to that factor | Existing view | Threshold (as implemented) | Milestone | Reviewer |
|---|---|---|---|---|---|
| Protection of participant safety — serious hepatic injury | A drug-induced liver-injury signal (Hy's Law pattern) goes unnoticed | §04 eDISH (`src/mdrlens/hyslaw.py`) | peak transaminase (ALT or AST) ≥ 3× ULN **and** peak bilirubin ≥ 2× ULN | Every 25/50/75/100% enrollment-milestone cut, and any cut where §01's "what changed" flags a newly-met pattern | Medical monitor / safety reviewer, escalated to the safety data review committee at milestone cuts |
| Reliability of trial results — emerging signals between formal reviews | A new adverse event or lab excursion is missed between scheduled reviews | §01 "What changed since the last cut" (`src/mdrlens/cuts.py`) | New AE; new lab result ≥ 3× ULN; a subject newly meeting the potential-Hy's-Law pattern; a site newly outside its funnel-plot limit | Every monthly data cut, with emphasis at the four milestone cuts | MDR analyst at every cut; safety data review committee at milestone cuts |
| Integrity of systems and processes — site-level conduct | A site under-reports adverse events, under-collects labs, or drifts outside its visit schedule, masking a real risk or signaling an operational problem | §05 Site KRIs (`src/mdrlens/site_kri.py`, `src/mdrlens/funnel.py`) | Outside the ≈99.8% funnel-plot "alarm" band (z = 3) for AE rate, missing-lab rate, or visit out-of-window rate, sized to that site's own n | 25/50/75/100% enrollment-milestone cuts (a cohort-review cadence) | RBQM / clinical operations lead, per flagged site |
| Reliability of trial results — integrity of the records themselves | Missing required fields or duplicate records undermine any of the views above | §06 Data quality (`src/mdrlens/dataquality.py`) | A hand-picked required-field list per SDTM domain; duplicate detection on each domain's own key fields; visits outside a ±7-day window | Ongoing, reviewed at every cut | Data management / MDR analyst |
| Protection of participant safety — one subject's story must be internally consistent | A severe lab abnormality with no matching adverse event entered (or vice versa) goes unreconciled | §03 One-patient timeline (`src/mdrlens/timeline.py`), joining CRF (case report form) data (AE, visits, disposition) to the central-lab (LB) feed | Qualitative reviewer judgment — the join itself (USUBJID + study day) is what §08 Traceability documents | Triggered by any flag from the rows above, not milestone-scheduled | Medical monitor |
| Study feasibility — enrollment pace (E8(R1) §7: "the number of participants... are sufficient to support the study objective") | Enrollment falls behind the pace needed to reach a planned review on schedule | §01 Enrollment curve with review-meeting-style milestones | 25/50/75/100% of final enrollment reached | Each threshold is itself the milestone | Study team / sponsor oversight |

## What this plan is, and is not

This is a **sample** plan, written to show how critical-to-quality-factor
thinking (ICH E8(R1)) and a risk-based, proportionate approach to quality
management (ICH E6(R3), TransCelerate's RBM/RBQM toolkit, FDA's 2013
risk-based monitoring guidance) would organize a real review cadence
around mdr-lens's own existing views and their already-implemented
thresholds. Every number and threshold referenced above traces to actual
code in `src/mdrlens/` and to the machine-readable lineage in
`data/derived/lineage.json` (see §08 Traceability on the page, and
`tests/test_lineage.py`). It is not itself a validated, sponsor-approved,
or regulatory-submitted Medical Data Review Plan, and neither this
document nor any part of mdr-lens claims compliance with, or certification
against, ICH E6(R3), ICH E8(R1), TransCelerate's RBM/RBQM materials, or any
FDA guidance. It makes no statement about Roche's, Genentech's, or any
other employer's own internal Medical Data Review processes.
