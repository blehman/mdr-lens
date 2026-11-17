/* mdr-lens — client-side rendering. All data comes from window.MDR_DATA
 * (see mdrlens/build.py). No network calls at runtime: this is a static,
 * offline file meant to be opened directly in a browser.
 */
(function () {
  "use strict";

  var DATA = window.MDR_DATA;
  var SUMMARY = DATA.study_summary;
  var PROTAGONIST = SUMMARY.protagonist_usubjid;

  // ---- palette (mirrors the CSS custom properties in index.html; Plot
  // needs literal color strings, not var(), to stay reliable across
  // browsers/rendering paths). ----
  var COLORS = {
    ink: "#0b0b0b", ink2: "#52514e", muted: "#898781",
    grid: "#e1e0d9", baseline: "#c3c2b7",
    blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", yellow: "#c98500", magenta: "#e87ba4",
    seq250: "#5a93d6", seq450: "#2a78d6", seq650: "#104281",
    good: "#0ca30c", warning: "#c98500", serious: "#ec835a", critical: "#d03b3b",
    gold: "#8a6a10", goldFill: "#e3b23c"
  };
  var LAB_TEST_COLOR_DOMAIN = ["ALT", "AST", "BILI", "ALP", "GGT"];
  var LAB_TEST_COLOR_RANGE = [COLORS.blue, COLORS.orange, COLORS.aqua, COLORS.yellow, COLORS.magenta];
  var SEVERITY_COLOR = { MILD: COLORS.seq250, MODERATE: COLORS.seq450, SEVERE: COLORS.seq650 };

  // Fix 4 (PA direction 2026-11-17): the registry's phase field is a raw
  // enum (PHASE1 / PHASE2); a study registered in both is bucketed once by
  // mdrlens.registry.phase_bucket_key as "PHASE1_PHASE2" server-side
  // (never double-counted into both PHASE1 and PHASE2). This mirrors that
  // same bucket->label mapping client-side so no screen ever shows a raw
  // enum.
  var PHASE_LABELS = { PHASE1: "Phase 1", PHASE2: "Phase 2", PHASE1_PHASE2: "Phase 1/2", UNKNOWN: "Unknown phase" };
  var PHASE_ORDER = ["PHASE1", "PHASE1_PHASE2", "PHASE2"];
  var PHASE_COLOR = { PHASE1: COLORS.blue, PHASE1_PHASE2: COLORS.orange, PHASE2: COLORS.aqua };
  function phaseLabel(raw) { return PHASE_LABELS[raw] || raw; }
  // Same bucketing as mdrlens.registry.phase_bucket_key, for a raw phases
  // array straight off one study record (e.g. the timeline tooltip) rather
  // than an already-bucketed server-side key.
  function phasesLabel(phases) {
    var set = {};
    (phases || []).forEach(function (p) { set[p] = true; });
    if (set.PHASE1 && set.PHASE2) return PHASE_LABELS.PHASE1_PHASE2;
    if (set.PHASE1) return PHASE_LABELS.PHASE1;
    if (set.PHASE2) return PHASE_LABELS.PHASE2;
    return PHASE_LABELS.UNKNOWN;
  }

  var fmtInt = d3.format(",");
  var fmtPct1 = d3.format(".1%");
  var fmtPct0 = d3.format(".0%");
  function fmtX(v) { return v == null ? "—" : v.toFixed(2) + "×"; }
  function dayLabel(v) { return v == null ? "—" : (v > 0 ? "+" : "") + v; }

  var redrawFns = [];
  function onResize(fn) { redrawFns.push(fn); }
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { redrawFns.forEach(function (fn) { fn(); }); }, 150);
  });

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function widthOf(el) { return Math.max(el.clientWidth || 0, 280); }

  // ================= HERO STATS =================
  function renderHeroStats() {
    var el = document.getElementById("hero-stats");
    var nFlaggedSites = DATA.site_kri.filter(function (s) {
      return s.ae_flag || s.missing_lab_flag || s.visit_oow_flag;
    }).length;
    var tiles = [
      { label: "Subjects", value: fmtInt(SUMMARY.n_subjects), note: SUMMARY.n_sites + " sites" },
      { label: "Adverse events", value: fmtInt(SUMMARY.n_ae), note: "AE domain" },
      { label: "Lab results", value: fmtInt(SUMMARY.n_lb), note: "LB domain" },
      {
        label: "Potential Hy's Law", value: SUMMARY.n_potential_hys_law + " / " + SUMMARY.n_subjects,
        note: "≥3× ULN enzyme &amp; ≥2× ULN bilirubin".replace("&amp;", "&")
      },
      { label: "Sites flagged on ≥1 KRI", value: nFlaggedSites + " / " + SUMMARY.n_sites, note: "funnel-plot screen, see §03" }
    ];
    clear(el);
    tiles.forEach(function (t) {
      var d = document.createElement("div");
      d.className = "stat-tile";
      d.innerHTML = '<div class="label">' + t.label + '</div><div class="value">' + t.value + '</div><div class="note">' + t.note + '</div>';
      el.appendChild(d);
    });
  }

  // ================= 01 STUDY IN FLIGHT =================
  function renderStudyInFlight() {
    var SIF = DATA.study_in_flight;
    var perCut = SIF.per_cut;
    var state = { idx: SIF.current_cut_index };

    function fmtUtc(iso) { return iso.slice(0, 16).replace("T", " ") + " UTC"; }
    function metaBlock(k, v) { return '<div class="m"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>'; }

    // B2 fix (PA direction 2026-11-17): the cut this simulator lands on by
    // default only cycles over cuts (cycle_start_index+1) through n_cuts --
    // from the 25% enrollment milestone. The full cut 1..n_cuts range stays
    // reachable one at a time via the stepper below.
    var cycleFirstCutOfN = (SIF.cycle_start_index + 1) + " of " + SIF.n_cuts;

    var milestonesEl = document.getElementById("inflight-milestones");
    milestonesEl.innerHTML =
      metaBlock("First Patient In (FPI)", SIF.first_patient_in) +
      metaBlock("Full replay", SIF.n_cuts + " monthly cuts") +
      metaBlock("Cycle window", "cut " + cycleFirstCutOfN + " onward") +
      metaBlock("Cycle started", SIF.cycle_epoch) +
      metaBlock("Last refresh", fmtUtc(SIF.last_refresh_utc));

    document.getElementById("inflight-cycle-note").textContent =
      "The simulator's current cut advances one cut per day and loops over cuts " +
      (SIF.cycle_start_index + 1) + "\u2013" + SIF.n_cuts + " (from the 25% enrollment milestone); after cut " +
      SIF.n_cuts + " it wraps back to cut " + (SIF.cycle_start_index + 1) + ". The cycle started on " +
      SIF.cycle_epoch + ". This build's current cut is #" + (SIF.current_cut_index + 1) + " of " +
      SIF.n_cuts + " (" + SIF.current_cut + "), computed for run date " + SIF.run_date +
      ". Every cut from #1 is still reachable with the stepper below.";

    var enrollContainer = document.getElementById("inflight-enrollment-chart");
    function drawEnrollment() {
      clear(enrollContainer);
      var width = widthOf(enrollContainer);
      var curve = SIF.enrollment_curve;
      var reviews = SIF.review_meeting_cuts;
      var plot = Plot.plot({
        width: width,
        height: 260,
        marginLeft: 48,
        marginRight: 16,
        marginTop: 22,
        marginBottom: 36,
        style: { fontFamily: "inherit", fontSize: "12px" },
        // Fix 6: Plot's default x-axis label position ("right", flush with
        // the last tick) collided with the 2015 end-of-study tick. Centering
        // the label under the axis keeps it clear of every tick regardless
        // of chart width.
        x: { label: "Data cut", type: "utc", labelAnchor: "center" },
        y: { label: "Cumulative subjects enrolled", grid: true },
        marks: [
          Plot.areaY(curve, { x: function (d) { return new Date(d.cut); }, y: "cumulative_subjects", fill: COLORS.grid, fillOpacity: 0.6, curve: "step-after" }),
          Plot.lineY(curve, { x: function (d) { return new Date(d.cut); }, y: "cumulative_subjects", stroke: COLORS.blue, strokeWidth: 2, curve: "step-after" }),
          Plot.ruleX([new Date(perCut[state.idx].cut)], { stroke: COLORS.ink2, strokeDasharray: "3,2" }),
          Plot.dot(reviews, { x: function (d) { return new Date(d.cut); }, y: "cumulative_subjects", r: 5.5, fill: COLORS.goldFill, stroke: COLORS.gold, strokeWidth: 1.5 }),
          Plot.text(reviews, {
            x: function (d) { return new Date(d.cut); }, y: "cumulative_subjects",
            text: function (d) { return fmtPct0(d.threshold); }, dy: -10, fontSize: 11, fontWeight: 700, fill: COLORS.gold
          }),
          Plot.tip(reviews, Plot.pointer({
            x: function (d) { return new Date(d.cut); }, y: "cumulative_subjects",
            title: function (d) { return fmtPct0(d.threshold) + " enrollment milestone — cut " + d.cut + " — " + d.cumulative_subjects + " subjects"; }
          }))
        ]
      });
      enrollContainer.appendChild(plot);
    }
    onResize(drawEnrollment);

    var slider = document.getElementById("inflight-slider");
    slider.max = String(perCut.length - 1);
    var prevBtn = document.getElementById("inflight-prev");
    var nextBtn = document.getElementById("inflight-next");
    var jumpBtn = document.getElementById("inflight-jump-current");
    var cutLabel = document.getElementById("inflight-cut-label");
    var statsEl = document.getElementById("inflight-cut-stats");
    var changedBody = document.getElementById("inflight-changed-body");

    function renderCut() {
      var c = perCut[state.idx];
      cutLabel.textContent = "Cut " + (state.idx + 1) + " / " + perCut.length + " — " + c.cut +
        (state.idx === SIF.current_cut_index ? " (current)" : "");
      prevBtn.disabled = state.idx === 0;
      nextBtn.disabled = state.idx === perCut.length - 1;
      slider.value = String(state.idx);

      clear(statsEl);
      [
        { label: "Subjects enrolled", value: fmtInt(c.n_subjects), note: "as of this cut" },
        { label: "AEs recorded", value: fmtInt(c.n_ae), note: "cumulative" },
        { label: "Lab results", value: fmtInt(c.n_lb), note: "cumulative" },
        { label: "Potential Hy's Law", value: fmtInt(c.n_potential_hys_law), note: "subjects flagged" },
        { label: "Sites flagged", value: fmtInt(c.n_sites_flagged), note: "on ≥1 KRI" }
      ].forEach(function (t) {
        var d = document.createElement("div");
        d.className = "stat-tile";
        d.innerHTML = '<div class="label">' + t.label + '</div><div class="value">' + t.value + '</div><div class="note">' + t.note + '</div>';
        statsEl.appendChild(d);
      });

      if (!c.what_changed) {
        changedBody.innerHTML = '<p class="caption">Cut 1 of this replay — First Patient In, with no earlier cut to compare against.</p>';
      } else {
        var wc = c.what_changed;
        function section(title, n, items, renderItem) {
          var body = items.length
            ? ("<ul>" + items.map(renderItem).join("") + "</ul>")
            : '<p class="caption" style="margin:4px 0 0;">None.</p>';
          return "<h4>" + title + " (" + fmtInt(n) + ")</h4>" + body;
        }
        changedBody.innerHTML =
          section("New adverse events", wc.n_new_ae, wc.new_ae, function (a) {
            return "<li>" + a.usubjid + " — " + a.term.toLowerCase() + " (day " + dayLabel(a.day) + ")</li>";
          }) +
          section("New lab excursions ≥3× ULN", wc.n_new_lab_excursions, wc.new_lab_excursions, function (l) {
            return "<li>" + l.usubjid + " — " + l.test + " " + fmtX(l.x_uln) + " (day " + dayLabel(l.day) + ")</li>";
          }) +
          section("Newly flagged potential Hy's Law", wc.newly_hy_flagged.length, wc.newly_hy_flagged, function (s) {
            return "<li>" + s + "</li>";
          }) +
          section("Sites newly outside a funnel limit", wc.newly_flagged_sites.length, wc.newly_flagged_sites, function (s) {
            return "<li>Site " + s.site + " — " + s.kri.replace("_flag", "") + " flagged " + s.flag + "</li>";
          });
      }
      drawEnrollment();
    }

    prevBtn.addEventListener("click", function () { if (state.idx > 0) { state.idx--; renderCut(); } });
    nextBtn.addEventListener("click", function () { if (state.idx < perCut.length - 1) { state.idx++; renderCut(); } });
    jumpBtn.addEventListener("click", function () { state.idx = SIF.current_cut_index; renderCut(); });
    slider.addEventListener("input", function () { state.idx = parseInt(slider.value, 10); renderCut(); });

    renderCut();
  }

  // ================= 02 LIVE REGISTRY =================
  function renderRegistry() {
    var REG = DATA.registry_summary;
    var card = document.getElementById("registry-fetch-card");
    if (!REG) {
      card.innerHTML = '<p class="caption">Registry snapshot not fetched for this build — run <code>scripts/fetch_registry.py</code>.</p>';
      return;
    }
    var fetchedAt = new Date(REG.fetched_at_utc);
    card.innerHTML =
      '<span class="registry-badge">● live fetch</span> &nbsp;<strong>' + fmtInt(REG.total_studies) + '</strong> studies — ' +
      'public ClinicalTrials.gov registry records as of <strong>' + fetchedAt.toISOString().slice(0, 16).replace("T", " ") + ' UTC</strong>. ' +
      'Source: <a href="' + REG.source_url + '" target="_blank" rel="noopener">' + REG.source_url + '</a>. ' +
      'Lead sponsor "Hoffmann-La Roche": ' + fmtInt(REG.per_sponsor_counts["Hoffmann-La Roche"] || 0) + '. ' +
      'Lead sponsor "Genentech": ' + fmtInt(REG.per_sponsor_counts["Genentech"] || 0) + '.';

    var statusPhaseRows = [];
    Object.keys(REG.status_phase_counts).forEach(function (status) {
      Object.keys(REG.status_phase_counts[status]).forEach(function (phase) {
        statusPhaseRows.push({ status: status.replace(/_/g, " ").toLowerCase(), phase: phaseLabel(phase), n: REG.status_phase_counts[status][phase] });
      });
    });
    var statusContainer = document.getElementById("registry-status-phase-chart");
    function drawStatusPhase() {
      clear(statusContainer);
      var width = widthOf(statusContainer);
      var plot = Plot.plot({
        width: width,
        height: 220,
        marginLeft: 160,
        marginRight: 20,
        marginTop: 10,
        marginBottom: 34,
        style: { fontFamily: "inherit", fontSize: "12px" },
        x: { label: "Studies", grid: true },
        y: { label: null },
        color: {
          domain: PHASE_ORDER.map(phaseLabel),
          range: PHASE_ORDER.map(function (p) { return PHASE_COLOR[p]; }),
          legend: true
        },
        marks: [
          Plot.barX(statusPhaseRows, { x: "n", y: "status", fill: "phase", sort: { y: "x", reverse: true } }),
          Plot.ruleX([0], { stroke: COLORS.baseline })
        ]
      });
      statusContainer.appendChild(plot);
    }
    drawStatusPhase();
    onResize(drawStatusPhase);

    // Fix 5 (PA direction 2026-11-17): "No MeSH category" always sorts
    // last, after every named category -- by count, highest first, like
    // the rest -- rather than wherever its count happens to land it. Its
    // own count still renders (the Plot.text label below), it is just
    // never mixed in among the named categories.
    var NO_MESH_LABEL = "No MeSH category";
    var meshRowsNamed = Object.keys(REG.mesh_categories)
      .filter(function (k) { return k !== NO_MESH_LABEL; })
      .map(function (k) { return { category: k, n: REG.mesh_categories[k] }; })
      .sort(function (a, b) { return b.n - a.n; });
    var meshRowsNoCategory = Object.keys(REG.mesh_categories)
      .filter(function (k) { return k === NO_MESH_LABEL; })
      .map(function (k) { return { category: k, n: REG.mesh_categories[k] }; });
    var meshRows = meshRowsNamed.concat(meshRowsNoCategory);
    var meshCategoryOrder = meshRows.map(function (r) { return r.category; });
    var meshContainer = document.getElementById("registry-mesh-chart");
    function drawMesh() {
      clear(meshContainer);
      var width = widthOf(meshContainer);
      var plot = Plot.plot({
        width: width,
        height: Math.max(meshRows.length * 26, 160),
        marginLeft: 180,
        marginRight: 40,
        marginTop: 10,
        marginBottom: 30,
        style: { fontFamily: "inherit", fontSize: "12px" },
        x: { label: "Studies", grid: true },
        // Explicit y domain in our own (named-categories-first, "No MeSH
        // category" last) order -- NOT Plot's own by-value sort, which
        // would otherwise reorder by count and could put "No MeSH
        // category" anywhere among the named ones.
        y: { label: null, domain: meshCategoryOrder },
        marks: [
          Plot.barX(meshRows, { x: "n", y: "category", fill: COLORS.blue }),
          Plot.text(meshRows, { x: "n", y: "category", text: "n", dx: 6, textAnchor: "start", fill: COLORS.ink2, fontSize: 11 }),
          Plot.ruleX([0], { stroke: COLORS.baseline })
        ]
      });
      meshContainer.appendChild(plot);
    }
    drawMesh();
    onResize(drawMesh);

    var STATUS_COLOR = {
      RECRUITING: COLORS.aqua, ACTIVE_NOT_RECRUITING: COLORS.blue,
      NOT_YET_RECRUITING: COLORS.yellow, ENROLLING_BY_INVITATION: COLORS.magenta
    };
    var timelineRows = REG.timeline_recruiting_or_active.filter(function (r) { return r.start_date && r.primary_completion_date; });
    var timelineContainer = document.getElementById("registry-timeline-chart");
    function drawTimeline() {
      clear(timelineContainer);
      var width = widthOf(timelineContainer);
      var sorted = timelineRows.slice().sort(function (a, b) { return new Date(a.start_date) - new Date(b.start_date); });
      var plot = Plot.plot({
        width: width,
        height: Math.max(sorted.length * 6.5, 200),
        marginLeft: 16,
        marginRight: 16,
        marginTop: 10,
        marginBottom: 34,
        style: { fontFamily: "inherit", fontSize: "11px" },
        x: { label: "Registered start → primary completion", type: "utc" },
        y: { axis: null },
        marks: [
          Plot.ruleY(sorted, {
            x1: function (d) { return new Date(d.start_date); },
            x2: function (d) { return new Date(d.primary_completion_date); },
            y: function (d, i) { return i; },
            stroke: function (d) { return STATUS_COLOR[d.overall_status] || COLORS.muted; },
            strokeWidth: 3,
            title: function (d) {
              return d.nct_id + " — " + d.brief_title + "\n" + d.overall_status + " — " + phasesLabel(d.phases) +
                "\n" + d.start_date + " → " + d.primary_completion_date;
            }
          })
        ]
      });
      timelineContainer.appendChild(plot);
    }
    drawTimeline();
    onResize(drawTimeline);

    var legendEl = document.getElementById("registry-timeline-legend");
    clear(legendEl);
    Object.keys(STATUS_COLOR).forEach(function (status) {
      var item = document.createElement("span");
      item.className = "item";
      item.innerHTML = '<span class="swatch" style="background:' + STATUS_COLOR[status] + '"></span>' + status.replace(/_/g, " ").toLowerCase();
      legendEl.appendChild(item);
    });
  }

  // ================= 03 PATIENT =================
  function renderPatientSummary() {
    var t = DATA.patient_timeline;
    var edishRow = DATA.edish.filter(function (r) { return r.usubjid === PROTAGONIST; })[0];
    var el = document.getElementById("patient-summary");
    clear(el);

    var left = document.createElement("div");
    left.style.minWidth = "220px";
    left.innerHTML =
      '<span class="patient-id-badge"><span class="dot"></span>Subject ' + t.usubjid + '</span>' +
      '<div class="patient-meta">' +
      metaBlock("Site", t.site) +
      metaBlock("Arm", t.arm) +
      metaBlock("Age / sex", Math.round(t.age) + " / " + t.sex) +
      '</div>';
    el.appendChild(left);

    var right = document.createElement("div");
    right.style.flex = "1 1 280px";
    var baselineDay = d3.min(t.lab_spikes.filter(function (s) { return s.baseline; }), function (s) { return s.day; });
    var baselineRows = t.lab_spikes.filter(function (s) { return s.baseline && s.day === baselineDay; });
    var baselineText = baselineRows.length
      ? baselineRows.map(function (s) { return s.test + " " + fmtX(s.x_uln); }).join(", ")
      : null;
    var armNote = baselineText
      ? " This subject is on " + t.arm + " (not an active-drug arm). The liver panel was already elevated " +
        "before randomization, at the day " + dayLabel(baselineDay) + " baseline draw (" + baselineText +
        " ULN) — a pre-existing elevation on placebo points away from a drug-induced injury, which is " +
        "exactly why a lab-pattern flag needs a reviewer's context, not automatic action."
      : "";
    var phlText = edishRow && edishRow.hy_flag
      ? "Peak ALT/AST " + fmtX(edishRow.peak_transaminase_xuln) + " ULN and peak total bilirubin " +
        fmtX(edishRow.peak_bili_xuln) + " ULN — meets the potential Hy's Law lab pattern (≥" +
        SUMMARY.hys_law_transaminase_threshold_x_uln + "× / ≥" + SUMMARY.hys_law_bili_threshold_x_uln + "×). " +
        "This is a lab-pattern flag for review, not a diagnosis." + armNote
      : "This subject does not meet the potential Hy's Law lab pattern.";
    right.innerHTML = '<div class="phl-callout"><strong>eDISH screen:</strong> ' + phlText + '</div>';
    el.appendChild(right);

    function metaBlock(k, v) {
      return '<div><div class="k">' + k + '</div><div class="v">' + v + '</div></div>';
    }
  }

  function renderPatientTimeline() {
    var container = document.getElementById("patient-timeline-chart");
    var t = DATA.patient_timeline;

    function draw() {
      clear(container);
      var width = widthOf(container);

      var labs = t.lab_spikes;
      var visits = t.visits.filter(function (v) { return v.day != null; });
      var ae = t.ae_events.filter(function (a) { return a.start_day != null; });
      var dispRaw = t.disposition.filter(function (d) { return d.day != null; });
      // merge same-day disposition events into one label (e.g. two events
      // recorded on the discontinuation visit) so they don't stack/overlap
      var dispByDay = d3.rollup(dispRaw, function (v) { return v.map(function (d) { return d.event; }).join(", "); }, function (d) { return d.day; });
      var disp = Array.from(dispByDay, function (kv) { return { day: kv[0], event: titleCaseLocal(kv[1]) }; });

      var yMax = d3.max(labs, function (d) { return d.x_uln; }) || 2;
      var yTop = Math.max(yMax * 1.35, 2.5);
      var labelY = yMax * 1.18;

      // all days actually plotted, used to decide which side a label should
      // grow toward so it never runs off the edge of the chart
      var allDays = labs.map(function (d) { return d.day; })
        .concat(visits.map(function (d) { return d.day; }))
        .concat(ae.map(function (d) { return d.start_day; }))
        .concat(disp.map(function (d) { return d.day; }));
      var dayMin = d3.min(allDays), dayMax = d3.max(allDays);
      var midDay = (dayMin + dayMax) / 2;
      function titleCaseLocal(s) { return (s || "").toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
      // Plot's textAnchor/dx are constant options, not per-datum channels --
      // a function value there silently breaks layout (NaN transforms). So
      // split each label set into "grows left" / "grows right" groups up
      // front and render each with its own constant anchor instead.
      function splitBySide(arr, dayOf) {
        var left = [], right = [];
        arr.forEach(function (d) { (dayOf(d) > midDay ? right : left).push(d); });
        return { left: left, right: right };
      }
      var aeSides = splitBySide(ae, function (d) { return d.start_day; });
      var dispSides = splitBySide(disp, function (d) { return d.day; });

      var plot = Plot.plot({
        width: width,
        height: 340,
        marginLeft: 44,
        marginRight: 20,
        marginTop: 34,
        marginBottom: 46,
        style: { fontFamily: "inherit", fontSize: "12px", background: "transparent" },
        x: { label: "Study day (0 = reference start date)", grid: false },
        y: { label: "× upper limit of normal (ULN)", domain: [0, yTop], grid: true },
        color: { domain: LAB_TEST_COLOR_DOMAIN, range: LAB_TEST_COLOR_RANGE, legend: false },
        marks: [
          Plot.ruleX(visits, { x: "day", stroke: COLORS.grid, strokeWidth: 1 }),
          Plot.ruleY([1], { stroke: COLORS.baseline, strokeDasharray: "2,3" }),
          Plot.text([{ x: d3.min(labs, function (d) { return d.day; }), y: 1 }],
            { x: "x", y: "y", text: ["ULN = 1×"], dx: 2, dy: -6, fill: COLORS.muted, fontSize: 11, textAnchor: "start" }),
          // Straight segments between observed points only -- never a
          // smoothed curve, which would visually imply trend data across
          // gaps (e.g. the ~3-week stretch with no draws between the
          // day -5 baseline and day 16) that was never actually collected.
          Plot.line(labs, { x: "day", y: "x_uln", stroke: "test", strokeWidth: 2, curve: "linear" }),
          Plot.dot(labs, { x: "day", y: "x_uln", r: 4, fill: "test" }),
          Plot.ruleX(ae, {
            x: "start_day", stroke: function (d) { return SEVERITY_COLOR[d.severity] || COLORS.ink2; },
            strokeWidth: 2, strokeDasharray: "3,2",
            title: function (d) { return "AE: " + titleCaseLocal(d.term) + " (" + d.severity + (d.serious ? ", SERIOUS" : "") + ") — day " + dayLabel(d.start_day); }
          }),
          Plot.text(aeSides.left, {
            x: "start_day", y: labelY, text: function (d) { return "AE: " + d.term.toLowerCase(); },
            dx: 6, dy: -6, fontSize: 11, fontWeight: 700, textAnchor: "start",
            fill: function (d) { return SEVERITY_COLOR[d.severity] || COLORS.ink2; }
          }),
          Plot.text(aeSides.right, {
            x: "start_day", y: labelY, text: function (d) { return "AE: " + d.term.toLowerCase(); },
            dx: -6, dy: -6, fontSize: 11, fontWeight: 700, textAnchor: "end",
            fill: function (d) { return SEVERITY_COLOR[d.severity] || COLORS.ink2; }
          }),
          Plot.ruleX(disp, {
            x: "day", stroke: COLORS.ink2, strokeDasharray: "4,2", strokeWidth: 1.25,
            title: function (d) { return d.event + " — day " + dayLabel(d.day); }
          }),
          Plot.text(dispSides.left, {
            x: "day", y: yTop, text: "event", dx: 4, dy: 10, fontSize: 10.5, fill: COLORS.ink2,
            textAnchor: "start", rotate: -24
          }),
          Plot.text(dispSides.right, {
            x: "day", y: yTop, text: "event", dx: -4, dy: 10, fontSize: 10.5, fill: COLORS.ink2,
            textAnchor: "end", rotate: -24
          }),
          Plot.tip(labs, Plot.pointer({
            x: "day", y: "x_uln",
            title: function (d) {
              return d.test + " — day " + dayLabel(d.day) + "\n" + d.value + " " + (d.unit || "") +
                " = " + d.x_uln.toFixed(2) + "× ULN";
            }
          }))
        ]
      });
      container.appendChild(plot);

      // custom legend (kept outside Plot so colors/labels stay in our control)
      var legendEl = document.getElementById("patient-timeline-legend");
      clear(legendEl);
      LAB_TEST_COLOR_DOMAIN.forEach(function (test, i) {
        var item = document.createElement("span");
        item.className = "item";
        item.innerHTML = '<span class="swatch" style="background:' + LAB_TEST_COLOR_RANGE[i] + '"></span>' + test;
        legendEl.appendChild(item);
      });
      ["AE onset (dashed, colored by severity)", "Disposition event (dashed gray)", "Visit (thin gray line)"].forEach(function (label) {
        var item = document.createElement("span");
        item.className = "item";
        item.textContent = label;
        legendEl.appendChild(item);
      });
    }
    draw();
    onResize(draw);
  }

  // ================= 04 WHOLE STUDY: eDISH =================
  function renderEdish() {
    var container = document.getElementById("edish-chart");
    var all = DATA.edish.filter(function (r) { return r.peak_transaminase_xuln != null && r.peak_bili_xuln != null; });
    var others = all.filter(function (r) { return !r.protagonist; });
    var mine = all.filter(function (r) { return r.protagonist; });
    var nMissing = DATA.edish.length - all.length;

    document.getElementById("edish-note").textContent =
      all.filter(function (r) { return r.hy_flag; }).length + " of " + all.length +
      " subjects with on-study liver labs fall in the potential Hy's Law zone (both peak transaminase ≥ " +
      SUMMARY.hys_law_transaminase_threshold_x_uln + "× ULN and peak bilirubin ≥ " +
      SUMMARY.hys_law_bili_threshold_x_uln + "× ULN). " + nMissing +
      " subjects have no on-study ALT/AST/bilirubin results (e.g. screen failures) and are excluded from this view.";

    var LOG_TICKS = [0.25, 0.5, 1, 2, 3, 5];
    var LOG_TICK_LABELS = { "0.25": "0.25", "0.5": "0.5", "1": "1", "2": "2", "3": "3", "5": "5" };
    function logTickFormat(d) { return LOG_TICK_LABELS[String(d)] || d; }

    function draw() {
      clear(container);
      var width = widthOf(container);
      var side = Math.min(width, 560);
      // Label sits just left of the gold point, at the same height, ending
      // at x=2.6 -- short of the 3x ULN rule at x=3 -- so it never crosses
      // that line regardless of chart width. No connecting line needed: a
      // short, consistent spacing at the same y as the dot, in a color used
      // nowhere else on this chart, reads as attached without one.
      var LABEL_X = 2.6;
      var labelPoint = mine.map(function (d) {
        return { x: LABEL_X, y: d.peak_bili_xuln, usubjid: d.usubjid };
      });
      var plot = Plot.plot({
        width: width,
        height: Math.max(side * 0.82, 360),
        marginLeft: 50,
        marginBottom: 42,
        marginTop: 26,
        marginRight: 20,
        style: { fontFamily: "inherit", fontSize: "12px" },
        x: { type: "log", label: "Peak ALT or AST (× ULN, log scale)", domain: [0.2, 6], ticks: LOG_TICKS, tickFormat: logTickFormat },
        y: { type: "log", label: "Peak total bilirubin (× ULN, log scale)", domain: [0.2, 6], ticks: LOG_TICKS, tickFormat: logTickFormat },
        marks: [
          Plot.ruleX([SUMMARY.hys_law_transaminase_threshold_x_uln], { stroke: COLORS.ink2, strokeDasharray: "3,3" }),
          Plot.ruleY([SUMMARY.hys_law_bili_threshold_x_uln], { stroke: COLORS.ink2, strokeDasharray: "3,3" }),
          Plot.text([{ x: SUMMARY.hys_law_transaminase_threshold_x_uln, y: SUMMARY.hys_law_bili_threshold_x_uln }], {
            x: "x", y: "y", text: ["Hy's Law zone →"], dx: -6, dy: -8,
            fill: COLORS.ink2, fontSize: 11, textAnchor: "end"
          }),
          Plot.dot(others, { x: "peak_transaminase_xuln", y: "peak_bili_xuln", r: 4, fill: COLORS.muted, fillOpacity: 0.55, stroke: "none" }),
          Plot.dot(mine, { x: "peak_transaminase_xuln", y: "peak_bili_xuln", r: 8, fill: COLORS.goldFill, stroke: COLORS.gold, strokeWidth: 2 }),
          Plot.text(labelPoint, {
            x: "x", y: "y", text: function (d) { return "Subject " + d.usubjid; },
            dx: -2, textAnchor: "end", fontSize: 11.5, fontWeight: 700, fill: COLORS.gold
          }),
          Plot.tip(all, Plot.pointer({
            x: "peak_transaminase_xuln", y: "peak_bili_xuln",
            title: function (d) {
              return d.usubjid + " (site " + d.site + ")" +
                "\nPeak ALT/AST: " + d.peak_transaminase_xuln.toFixed(2) + "× ULN" +
                "\nPeak bilirubin: " + d.peak_bili_xuln.toFixed(2) + "× ULN" +
                (d.hy_flag ? "\nPotential Hy's Law" : "");
            }
          }))
        ]
      });
      container.appendChild(plot);
    }
    draw();
    onResize(draw);
  }

  // ================= 04 WHOLE STUDY: AE explorer =================
  function renderAEExplorer() {
    var events = DATA.ae_events;
    var severities = ["MILD", "MODERATE", "SEVERE"];
    var bodySystems = Array.from(new Set(events.map(function (e) { return e.body_system; }))).sort();

    var sevFilterEl = document.getElementById("severity-filter");
    var state = { severity: "ALL", bodysys: "ALL", seriousOnly: false };

    function sevChip(label, value) {
      var b = document.createElement("button");
      b.className = "chip";
      b.type = "button";
      b.textContent = label;
      b.setAttribute("aria-pressed", String(state.severity === value));
      b.addEventListener("click", function () {
        state.severity = value;
        Array.from(sevFilterEl.children).forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        renderTable();
      });
      return b;
    }
    sevFilterEl.appendChild(sevChip("All severities", "ALL"));
    severities.forEach(function (s) { sevFilterEl.appendChild(sevChip(s, s)); });

    var bodysysEl = document.getElementById("bodsys-filter");
    var optAll = document.createElement("option");
    optAll.value = "ALL"; optAll.textContent = "All body systems";
    bodysysEl.appendChild(optAll);
    bodySystems.forEach(function (bs) {
      var o = document.createElement("option");
      o.value = bs; o.textContent = bs;
      bodysysEl.appendChild(o);
    });
    bodysysEl.addEventListener("change", function () { state.bodysys = bodysysEl.value; renderTable(); });

    var seriousEl = document.getElementById("serious-filter");
    seriousEl.addEventListener("change", function () { state.seriousOnly = seriousEl.checked; renderTable(); });

    var tbody = document.getElementById("ae-table-body");
    var countNote = document.getElementById("ae-count-note");

    function renderTable() {
      var rows = events.filter(function (e) {
        if (state.severity !== "ALL" && e.severity !== state.severity) return false;
        if (state.bodysys !== "ALL" && e.body_system !== state.bodysys) return false;
        if (state.seriousOnly && !e.serious) return false;
        return true;
      });
      countNote.textContent = "Showing " + fmtInt(rows.length) + " of " + fmtInt(events.length) + " adverse events";
      clear(tbody);
      var frag = document.createDocumentFragment();
      rows.forEach(function (e) {
        var tr = document.createElement("tr");
        if (e.usubjid === PROTAGONIST) tr.className = "is-protagonist";
        var dayText = dayLabel(e.start_day) + (e.end_day != null ? "–" + dayLabel(e.end_day) : (e.start_day != null ? " (ongoing)" : ""));
        tr.innerHTML =
          "<td>" + e.usubjid + (e.usubjid === PROTAGONIST ? ' <span class="badge protagonist">★</span>' : "") + "</td>" +
          "<td>" + e.site + "</td>" +
          "<td>" + titleCase(e.term) + "</td>" +
          "<td>" + titleCase(e.body_system) + "</td>" +
          '<td><span class="badge sev-' + e.severity + '">' + e.severity + "</span></td>" +
          "<td>" + (e.serious ? '<span class="badge serious">serious</span>' : "—") + "</td>" +
          "<td>" + titleCase(e.outcome || "") + "</td>" +
          '<td class="num">' + dayText + "</td>";
        frag.appendChild(tr);
      });
      tbody.appendChild(frag);
    }
    function titleCase(s) {
      return (s || "").toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    }
    renderTable();
  }

  // ================= 05 SITES =================
  function flagColor(flag) {
    if (flag === "high") return COLORS.critical;
    if (flag === "low") return COLORS.serious;
    return COLORS.muted;
  }
  function flagBadge(flag) {
    if (flag === "high") return '<span class="badge flag-high">high</span>';
    if (flag === "low") return '<span class="badge flag-low">low</span>';
    return '<span class="badge flag-none">—</span>';
  }

  function buildFunnelChart(container, opts) {
    function draw() {
      clear(container.el);
      var width = widthOf(container.el);
      var sites = DATA.site_kri.map(function (s) {
        return { site: s.site, n: opts.nAccessor(s), rate: opts.rateAccessor(s), flag: opts.flagAccessor(s) };
      });
      var flagged = sites.filter(function (s) { return s.flag; });
      var yTickFormat = opts.percent ? (function (d) { return fmtPct0(d); }) : (function (d) { return d.toFixed(1); });

      // headroom so a flagged-site label never collides with the top of
      // the frame; explicit opts.yDomain (e.g. the percent charts) wins
      var yDomain = opts.yDomain;
      if (!yDomain) {
        var yMax = d3.max(sites.map(function (s) { return s.rate; }).concat(opts.curve.map(function (c) { return c.alarm_upper; })));
        yDomain = [0, Math.max(yMax * 1.3, 1)];
      }

      var MARGIN_LEFT = 46, MARGIN_RIGHT = 14, MARGIN_TOP = 26, MARGIN_BOTTOM = 36;

      // Dodge overlapping flagged-site labels: two sites close together in
      // both x (n) and y (rate) -- e.g. two small, nearby sites like 706
      // and 711 -- get their labels stacked at increasing heights instead
      // of drawn on top of each other. Both axes here are plain linear, so
      // pixel position is computed directly from the same domains Plot
      // will use, without needing to introspect the rendered scale.
      var xDomain = d3.extent(opts.curve, function (c) { return c.x; });
      var plotW = width - MARGIN_LEFT - MARGIN_RIGHT, plotH = 270 - MARGIN_TOP - MARGIN_BOTTOM;
      function px(n) { return MARGIN_LEFT + ((n - xDomain[0]) / (xDomain[1] - xDomain[0])) * plotW; }
      function py(rate) { return MARGIN_TOP + (1 - (rate - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH; }
      var dodged = flagged.slice().sort(function (a, b) { return px(a.n) - px(b.n); });
      var placed = []; // {pxX, pxY, bucket}
      dodged.forEach(function (d) {
        var bucket = 0;
        var collides;
        do {
          var labelY = py(d.rate) - 10 - bucket * 14;
          collides =
            placed.some(function (p) {
              return p.bucket === bucket && Math.abs(p.pxX - px(d.n)) < 34 && Math.abs(p.pxY - py(d.rate)) < 22;
            }) ||
            // also dodge away from any OTHER site's plain dot, flagged or
            // not -- a label floating next to an unrelated grey dot reads
            // as if it belongs to that dot too
            sites.some(function (s) {
              return s !== d && Math.abs(px(s.n) - px(d.n)) < 16 && Math.abs(py(s.rate) - labelY) < 12;
            });
          if (collides) bucket++;
        } while (collides && bucket < 6);
        d._labelBucket = bucket;
        placed.push({ pxX: px(d.n), pxY: py(d.rate), bucket: bucket });
      });
      var labelBuckets = d3.groups(flagged, function (d) { return d._labelBucket || 0; });

      var plot = Plot.plot({
        width: width,
        height: 270,
        marginLeft: MARGIN_LEFT,
        marginBottom: MARGIN_BOTTOM,
        marginTop: MARGIN_TOP,
        marginRight: MARGIN_RIGHT,
        style: { fontFamily: "inherit", fontSize: "12px" },
        x: { label: opts.xLabel, grid: false },
        y: { label: opts.yLabel, grid: true, tickFormat: yTickFormat, domain: yDomain },
        marks: [
          Plot.areaY(opts.curve, { x: "x", y1: "alarm_lower", y2: "alarm_upper", fill: COLORS.grid, fillOpacity: 0.7 }),
          Plot.areaY(opts.curve, { x: "x", y1: "watch_lower", y2: "watch_upper", fill: COLORS.baseline, fillOpacity: 0.45 }),
          Plot.ruleY([opts.pooledRate], { stroke: COLORS.ink2, strokeDasharray: "2,2" }),
          Plot.dot(sites, { x: "n", y: "rate", r: 5.5, fill: function (d) { return flagColor(d.flag); }, stroke: COLORS.surface || "#fff", strokeWidth: 1 }),
        ].concat(
          // one Plot.text per collision "bucket" (dy is a constant option,
          // not a per-datum channel, so overlapping labels are separated
          // by rendering each stacked height as its own mark rather than
          // by a per-row dy function)
          labelBuckets.map(function (entry) {
            var bucket = entry[0], rows = entry[1];
            return Plot.text(rows, {
              x: "n", y: "rate", text: "site", dy: -10 - bucket * 14, fontSize: 11, fontWeight: 700,
              textAnchor: "middle", fill: function (d) { return flagColor(d.flag); }
            });
          })
        ).concat([
          Plot.tip(sites, Plot.pointer({
            x: "n", y: "rate",
            title: function (d) {
              return "Site " + d.site + " (n=" + fmtInt(d.n) + ")" +
                "\nRate: " + (opts.percent ? fmtPct1(d.rate) : d.rate.toFixed(2)) +
                "\n" + (d.flag ? "Flagged: " + d.flag : "Within funnel limits");
            }
          }))
        ])
      });
      container.el.appendChild(plot);
    }
    draw();
    onResize(draw);
  }

  function renderSiteFunnels() {
    var grid = document.getElementById("funnel-charts");
    clear(grid);

    var defs = [
      {
        key: "ae", title: "AE reporting rate", xLabel: "Exposure days at site",
        yLabel: "AE per 100 subject-days", percent: false,
        nAccessor: function (s) { return s.exposure_days; },
        rateAccessor: function (s) { return s.ae_per_100_subject_days; },
        flagAccessor: function (s) { return s.ae_flag; }
      },
      {
        key: "missing_lab", title: "Missing-lab rate", xLabel: "Lab records at site",
        yLabel: "Missing-lab rate", percent: true, yDomain: [0, 0.08],
        nAccessor: function (s) { return s.n_lb_records; },
        rateAccessor: function (s) { return s.missing_lab_rate; },
        flagAccessor: function (s) { return s.missing_lab_flag; }
      },
      {
        key: "visit_oow", title: "Visit out-of-window rate", xLabel: "Visits evaluated at site",
        yLabel: "Out-of-window rate", percent: true, yDomain: [0, 0.5],
        nAccessor: function (s) { return s.n_visits; },
        rateAccessor: function (s) { return s.visit_oow_rate; },
        flagAccessor: function (s) { return s.visit_oow_flag; }
      }
    ];

    defs.forEach(function (def) {
      var card = document.createElement("div");
      card.className = "card";
      card.innerHTML = '<h3>' + def.title + '</h3>' +
        '<div class="chart-fig" id="funnel-' + def.key + '"></div>' +
        '<div class="legend">' +
        '<span class="item"><span class="swatch" style="background:' + COLORS.baseline + '"></span>approx. 95% "watch" band (normal approximation)</span>' +
        '<span class="item"><span class="swatch" style="background:' + COLORS.grid + '"></span>approx. 99.8% "alarm" band (normal approximation)</span>' +
        '<span class="item"><span class="swatch" style="background:' + COLORS.critical + '"></span>flagged high</span>' +
        '<span class="item"><span class="swatch" style="background:' + COLORS.serious + '"></span>flagged low</span>' +
        '</div>';
      grid.appendChild(card);
      var el = document.getElementById("funnel-" + def.key);
      var funnel = DATA.site_kri_funnel[def.key];
      buildFunnelChart({ el: el }, {
        curve: funnel.curve,
        pooledRate: funnel.pooled_rate,
        xLabel: def.xLabel,
        yLabel: def.yLabel,
        percent: def.percent,
        yDomain: def.yDomain,
        nAccessor: def.nAccessor,
        rateAccessor: def.rateAccessor,
        flagAccessor: def.flagAccessor
      });
    });
  }

  function renderSiteTable() {
    var tbody = document.getElementById("site-table-body");
    clear(tbody);
    var rows = DATA.site_kri.slice().sort(function (a, b) {
      function nFlags(s) { return [s.ae_flag, s.missing_lab_flag, s.visit_oow_flag].filter(Boolean).length; }
      var d = nFlags(b) - nFlags(a);
      return d !== 0 ? d : (a.site > b.site ? 1 : -1);
    });
    var frag = document.createDocumentFragment();
    rows.forEach(function (s) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + s.site + "</td>" +
        '<td class="num">' + s.n_subjects + "</td>" +
        '<td class="num">' + s.ae_per_100_subject_days.toFixed(2) + "</td>" +
        "<td>" + flagBadge(s.ae_flag) + "</td>" +
        '<td class="num">' + fmtPct1(s.missing_lab_rate) + "</td>" +
        "<td>" + flagBadge(s.missing_lab_flag) + "</td>" +
        '<td class="num">' + fmtPct1(s.visit_oow_rate) + "</td>" +
        "<td>" + flagBadge(s.visit_oow_flag) + "</td>";
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);
  }

  // ================= 06 DATA QUALITY =================
  function renderDataQuality() {
    var dq = DATA.data_quality;
    var domains = ["dm", "ae", "lb", "sv", "ds"];
    var domainLabels = { dm: "DM — demographics", ae: "AE — adverse events", lb: "LB — labs", sv: "SV — visits", ds: "DS — disposition" };

    var barData = domains.map(function (dom) {
      var d = dq.per_domain[dom];
      var totalRequired = d.n_records * Object.keys(d.missing_required).length;
      var totalMissing = Object.values(d.missing_required).reduce(function (a, b) { return a + b; }, 0);
      return { domain: domainLabels[dom], rate: totalRequired ? totalMissing / totalRequired : 0, n: d.n_records };
    });

    var container = document.getElementById("dq-chart");
    function draw() {
      clear(container);
      var width = widthOf(container);
      var plot = Plot.plot({
        width: width,
        height: 220,
        marginLeft: 150,
        marginRight: 50,
        marginTop: 10,
        marginBottom: 30,
        style: { fontFamily: "inherit", fontSize: "12px" },
        x: { label: "Share of required-field values missing", tickFormat: fmtPct0, domain: [0, Math.max(0.02, d3.max(barData, function (d) { return d.rate; }) * 1.3)] },
        y: { label: null },
        marks: [
          Plot.barX(barData, { x: "rate", y: "domain", fill: COLORS.blue, sort: { y: "x", reverse: true } }),
          Plot.text(barData, { x: "rate", y: "domain", text: function (d) { return fmtPct1(d.rate); }, dx: 6, textAnchor: "start", fill: COLORS.ink2, fontSize: 11.5 }),
          Plot.ruleX([0], { stroke: COLORS.baseline })
        ]
      });
      container.appendChild(plot);
    }
    draw();
    onResize(draw);

    var card = document.getElementById("dq-summary-card");
    var html = "<h3>Per-domain ledger</h3>";
    domains.forEach(function (dom) {
      var d = dq.per_domain[dom];
      var missingEntries = Object.entries(d.missing_required).filter(function (e) { return e[1] > 0; });
      html += '<p style="margin-top:12px; font-size:13px;"><strong>' + domainLabels[dom] + "</strong> — " +
        fmtInt(d.n_records) + " records, " + d.n_duplicates + " duplicate" + (d.n_duplicates === 1 ? "" : "s") + ".";
      if (missingEntries.length) {
        html += " Missing: " + missingEntries.map(function (e) { return e[0] + " (" + fmtInt(e[1]) + ")"; }).join(", ") + ".";
      } else {
        html += " No missing required fields.";
      }
      html += "</p>";
    });
    html += '<p style="margin-top:14px; font-size:13px; border-top:1px solid var(--grid); padding-top:10px;">' +
      "<strong>Visit out-of-window:</strong> " + fmtInt(dq.visit_out_of_window.n_out_of_window) + " of " +
      fmtInt(dq.visit_out_of_window.n_visits_evaluated) + " evaluated visits (" +
      fmtPct1(dq.visit_out_of_window.rate) + ") fall outside a ±" + dq.visit_out_of_window.window_days +
      "-day window around that visit's study-wide median day.</p>";
    card.innerHTML = html;
  }

  // ================= 07 MDR PLAN =================
  // Sample plan content, not derived data -- same reason the footer's
  // "How the simulator works" lists are static prose, not JS over JSON:
  // a plan is a claim about intent and basis (see docs/MDR_PLAN.md and
  // the Basis card above), not a statistic computed from SDTM records.
  var MDR_PLAN_ROWS = [
    {
      factor: "Protection of participant safety — serious hepatic injury",
      risk: "A drug-induced liver-injury signal (Hy's Law pattern) goes unnoticed",
      view: "§04 eDISH",
      threshold: "peak transaminase (ALT or AST) ≥ 3× ULN and peak bilirubin ≥ 2× ULN",
      milestone: "Every 25/50/75/100% enrollment-milestone cut, and any cut flagged by §01's \"what changed\"",
      reviewer: "Medical monitor / safety reviewer; safety data review committee at milestone cuts"
    },
    {
      factor: "Reliability of trial results — emerging signals between reviews",
      risk: "A new adverse event or lab excursion is missed between scheduled reviews",
      view: "§01 \"What changed since the last cut\"",
      threshold: "New AE; new lab result ≥ 3× ULN; a subject newly meeting the potential-Hy's-Law pattern; a site newly outside its funnel limit",
      milestone: "Every monthly data cut, with emphasis at the four milestone cuts",
      reviewer: "MDR analyst every cut; safety data review committee at milestone cuts"
    },
    {
      factor: "Integrity of systems and processes — site-level conduct",
      risk: "A site under-reports AEs, under-collects labs, or drifts outside its visit schedule",
      view: "§05 Site KRIs",
      threshold: "Outside the ≈99.8% funnel-plot alarm band (z=3) for AE rate, missing-lab rate, or visit out-of-window rate",
      milestone: "25/50/75/100% enrollment-milestone cuts",
      reviewer: "RBQM / clinical operations lead, per flagged site"
    },
    {
      factor: "Reliability of trial results — integrity of the records themselves",
      risk: "Missing required fields or duplicate records undermine any view above",
      view: "§06 Data quality",
      threshold: "Hand-picked required-field list per SDTM domain; duplicate keys; visits outside a ±7-day window",
      milestone: "Ongoing, reviewed at every cut",
      reviewer: "Data management / MDR analyst"
    },
    {
      factor: "Protection of participant safety — one subject's story must be internally consistent",
      risk: "A severe lab abnormality with no matching AE entered (or vice versa) goes unreconciled",
      view: "§03 One-patient timeline (CRF ↔ central-lab join)",
      threshold: "Reviewer judgment — the join itself (USUBJID + study day) is documented at §08",
      milestone: "Triggered by any flag above, not milestone-scheduled",
      reviewer: "Medical monitor"
    },
    {
      factor: "Study feasibility — enrollment pace",
      risk: "Enrollment falls behind the pace needed to reach a planned review on schedule",
      view: "§01 Enrollment curve",
      threshold: "25/50/75/100% of final enrollment reached",
      milestone: "Each threshold is itself the milestone",
      reviewer: "Study team / sponsor oversight"
    }
  ];

  function renderMdrPlan() {
    var tbody = document.getElementById("mdrplan-table-body");
    clear(tbody);
    var frag = document.createDocumentFragment();
    MDR_PLAN_ROWS.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + r.factor + "</td>" +
        "<td>" + r.risk + "</td>" +
        "<td>" + r.view + "</td>" +
        "<td>" + r.threshold + "</td>" +
        "<td>" + r.milestone + "</td>" +
        "<td>" + r.reviewer + "</td>";
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);
  }

  // ================= 08 TRACEABILITY / LINEAGE =================
  // badge class per source kind: non-CRF (central-lab feed) reuses the
  // "flag-low" badge color, CRF (site-entered) reuses "flag-none" -- an
  // informational distinction, not a data-quality flag, but the same
  // pill styling already defined in index.html's CSS.
  var SOURCE_KIND_BADGE_CLASS = { "non-CRF (central-lab feed)": "flag-low", "CRF (site-entered)": "flag-none" };
  function renderLineageTable(tbodyId, rows, withSection) {
    var tbody = document.getElementById(tbodyId);
    clear(tbody);
    var frag = document.createDocumentFragment();
    rows.forEach(function (r) {
      var domains = (r.domains.length ? r.domains.join(", ").toUpperCase() : "—");
      var kinds = r.source_kinds && r.source_kinds.length
        ? Array.from(new Set(r.source_kinds)).map(function (k) {
            var cls = SOURCE_KIND_BADGE_CLASS[k] || "flag-none";
            return '<span class="badge ' + cls + '">' + k + "</span>";
          }).join(" ")
        : "—";
      var tr = document.createElement("tr");
      var cells = "<td>" + r.label + "</td>";
      if (withSection) cells += "<td>§" + r.page_section + "</td>";
      cells +=
        "<td>" + domains + "</td>" +
        "<td>" + r.variables.join(", ") + "</td>";
      if (withSection) cells += "<td>" + kinds + "</td>";
      cells += "<td>" + r.join + "</td>";
      tr.innerHTML = cells;
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);
  }

  function renderLineage() {
    renderLineageTable("lineage-table-body", DATA.lineage, true);
  }

  // ================= 09 REUSABLE TEMPLATE: SECOND SDTM DATASET =================
  function renderSecondStudy() {
    var summaryCard = document.getElementById("template-summary-card");
    var summary = DATA.second_study_summary;
    if (!summary) {
      summaryCard.innerHTML =
        '<p class="caption">Reusable-template demo not generated for this build — run ' +
        '<code>scripts/fetch_second_study.py</code> then <code>scripts/build_second_study.py</code>.</p>';
      document.getElementById("template-labs-table-body").innerHTML = "";
      document.getElementById("template-lineage-table-body").innerHTML = "";
      return;
    }
    var domainsText = Object.keys(summary.domains_used).map(function (d) {
      return d.toUpperCase() + " → " + summary.domains_used[d] + ".rda";
    }).join(", ");
    summaryCard.innerHTML =
      '<h3>' + summary.display_name + '</h3>' +
      '<p class="caption" style="margin-top:8px;">' + summary.enables + '</p>' +
      '<div class="patient-meta" style="margin-top:12px;">' +
      metaBlock("Subjects", fmtInt(summary.n_subjects)) +
      metaBlock("Lab records", fmtInt(summary.n_lb)) +
      metaBlock("Liver-panel tests run", summary.liver_panel_tests.join(", ")) +
      metaBlock("Domains used", domainsText) +
      '</div>' +
      '<p class="figure-note" style="margin-top:10px;">Source: <a href="' + summary.source_repo +
      '" target="_blank" rel="noopener">' + summary.source_repo + '</a>, commit ' +
      '<code>' + summary.source_commit.slice(0, 12) + '</code> — the same pinned commit §01–06 use (see Methods).</p>';

    function metaBlock(k, v) {
      return '<div><div class="k">' + k + '</div><div class="v" style="font-size:13px;">' + v + '</div></div>';
    }

    var labsBody = document.getElementById("template-labs-table-body");
    clear(labsBody);
    var frag = document.createDocumentFragment();
    (DATA.second_study_labs || []).forEach(function (r) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + r.usubjid + "</td>" +
        "<td>" + r.site + "</td>" +
        "<td>" + r.test + "</td>" +
        '<td class="num">' + fmtX(r.peak_x_uln) + "</td>";
      frag.appendChild(tr);
    });
    labsBody.appendChild(frag);

    renderLineageTable("template-lineage-table-body", DATA.second_study_lineage || [], false);
  }

  // ================= GLOSSARY =================
  function renderGlossary() {
    var terms = [
      ["RVA — Real-Time Visual Analytics", "the interactive, study-level dashboards this kind of role builds for ongoing trials, refreshed to milestones like First Patient In, cohort reviews, and safety data review committee meetings. §01 of this page is a simulator built on that workflow: one completed public study, replayed by data cut — and §02 adds a live public-registry fetch, both refreshed on a schedule (see Methods)."],
      ["MDR — Medical Data Review", "the clinical review of incoming trial data for safety issues and data problems."],
      ["RBQM — Risk-Based Quality Management", "monitoring trial conduct by watching a handful of quantitative risk indicators continuously, instead of relying only on periodic full on-site reviews."],
      ["CtQ — critical-to-quality (factor)", "an attribute of a trial (per ICH E8(R1)) whose integrity is fundamental to participant protection and the reliability of trial results — the organizing idea behind §07's sample Medical Data Review plan."],
      ["KRI — key risk indicator", "one of those quantitative metrics, e.g. the adverse-event reporting rate at a site."],
      ["eDISH — evaluation of Drug-Induced Serious Hepatotoxicity", "the liver-safety scatterplot in section 02: peak transaminase vs. peak bilirubin, both in × ULN."],
      ["Hy's Law", "Hyman Zimmerman's clinical observation that a drug causing both liver-enzyme elevation and bilirubin elevation in the same patient predicts a serious risk of liver failure. “Potential Hy's Law” is the lab-only screening pattern used here to flag candidates for review."],
      ["ULN — upper limit of normal", "the top of a lab's own normal range for a test. “× ULN” means result ÷ that limit, so results from different labs can be compared on one scale."],
      ["SDTM — Study Data Tabulation Model", "the CDISC standard table layout this project's data ships in (its DM, AE, LB, SV and DS domains)."],
      ["CDISC — Clinical Data Interchange Standards Consortium", "the nonprofit standards body behind SDTM."],
      ["CRF — case report form", "the form, paper or electronic, a trial site uses to record a subject's data."],
      ["EDC — Electronic Data Capture", "the software a site uses to enter CRF data into the sponsor's systems. This project has none — it reads one static public file."],
      ["AE — adverse event", "any unfavorable medical occurrence in a subject during the trial, whether or not thought related to treatment."],
      ["MedDRA — Medical Dictionary for Regulatory Activities", "the standard vocabulary used to code each AE term into a body system (system organ class)."]
    ];
    var dl = document.getElementById("glossary");
    var html = "";
    terms.forEach(function (t) {
      html += "<dt>" + t[0] + "</dt><dd>" + t[1] + "</dd>";
    });
    dl.innerHTML = html;
  }

  // ================= init =================
  renderHeroStats();
  renderStudyInFlight();
  renderRegistry();
  renderPatientSummary();
  renderPatientTimeline();
  renderEdish();
  renderAEExplorer();
  renderSiteFunnels();
  renderSiteTable();
  renderDataQuality();
  renderMdrPlan();
  renderLineage();
  renderSecondStudy();
  renderGlossary();
})();
