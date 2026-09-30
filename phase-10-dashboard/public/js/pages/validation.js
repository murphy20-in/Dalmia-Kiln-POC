import { dotFigure } from "../chart.js";
import { F3_GROUP, FINDINGS_NOTE, PAGE, PERIOD_LABEL } from "../copy.js";
import { h } from "../dom.js";
import { evidenceForDisplay, findingAnchor, groupFindings, plain } from "../pure/present.js";
import { chip, enumText, exact, hero, kpis, loading, section, table, to } from "../ui.js";
import { artifactVersion, loadStory, storySections, versions } from "./common.js";

const VARIANT = { PRIMARY: "Primary score", EXCLUDE_KILN_INLET_O2_ANALYSER: "O₂-excluded (sensitivity)" };
const windowLabel = (min) => (min < 60 ? `${min} min` : `${min / 60} h`);

export async function render(root, ctx) {
  root.replaceChildren(hero(PAGE.validation), loading());
  const story = await loadStory();
  const v = story.validation;
  const pe = v.primary_endpoint.by_variant.primary;
  const o2 = v.primary_endpoint.by_variant.o2_excluded;
  const verdict = plain("status", v.historical_validation_status);
  const version = artifactVersion(story.validationEnvelope);

  const horizon = v.horizon_results.map((r) => ({
    group: `${windowLabel(r.horizon_minutes)} window${r.is_primary ? " (primary)" : ""}`,
    series: r.score_variant === "PRIMARY" ? "primary" : "sensitivity",
    name: VARIANT[r.score_variant] || r.score_variant,
    value: r.median_rank_excess,
    lo: r.bootstrap_ci_low,
    hi: r.bootstrap_ci_high,
    status: r.historical_validation_status,
  })).sort((a, b) => (a.series === b.series ? 0 : a.series === "primary" ? -1 : 1));

  root.replaceChildren(
    hero(PAGE.validation),
    kpis([
      { label: "Early-warning validation", value: verdict.text, raw: verdict.raw, meaning: verdict.meaning, source: "Phase 8 · /validation/early-warning-historical", link: to("/validation", {}, "primary") },
      { label: "Evaluable periods", value: `${pe.n_evaluable_periods} of ${pe.n_periods}`, meaning: `${PERIOD_LABEL} with enough data before onset`, source: "Phase 8 · primary_endpoint", link: to("/validation", {}, "primary") },
      { label: "O₂-excluded check", value: plain("status", o2.historical_validation_status).text, raw: o2.historical_validation_status, meaning: "Analyser-dependent sensitivity analysis, not preferred", source: "Phase 8 · primary_endpoint", link: to("/validation", {}, "o2") },
      { label: "Censored onsets", value: `${v.censoring.n_onset_censored} of ${v.censoring.n_periods}`, meaning: "onsets cut off by the look-back cap", source: "Phase 8 · censoring", link: to("/validation", {}, "censoring") },
      { label: "Pipeline integrity checks", value: `${v.phase8_integrity_checks.pass} of ${v.phase8_integrity_checks.total}`, meaning: "the analysis ran correctly; this is not a favourable result", source: "Phase 8 · integrity checks", link: to("/methodology", {}, "validation") },
    ]),
    h("div", { class: "verdicts" },
      h("section", { class: "verdict", id: "primary", "aria-labelledby": "primary-h" },
        h("p", { class: "detail-kicker" }, "Primary endpoint"),
        h("h2", { id: "primary-h" }, "Early-warning validation: ", enumText("status", v.historical_validation_status)),
        h("p", {}, `Question tested: ${v.question}`),
        table("Primary endpoint, as served", ["Effect (median rank excess)", "95% interval", "Randomisation p", "Evaluable periods", "Controls"],
          [[exact(pe.effect_estimate_median_rank_excess), `${exact(pe.ci95_low)} to ${exact(pe.ci95_high)}`, exact(pe.randomisation_p_value), `${pe.n_evaluable_periods} of ${pe.n_periods}`, String(pe.n_controls)]]),
        h("p", { class: "hint" }, `Method: ${v.primary_endpoint.definition}.`),
        h("a", { class: "btn btn-secondary", href: to("/validation", {}, "censoring") }, "Why not supported?")),
      h("section", { class: "verdict verdict-secondary", id: "o2", "aria-labelledby": "o2-h" },
        h("p", { class: "detail-kicker" }, "Sensitivity analysis — not preferred"),
        h("h2", { id: "o2-h" }, "O₂-excluded variant: ", enumText("status", o2.historical_validation_status)),
        h("p", {}, `Served note: ${o2.note}.`),
        h("p", {}, `On the primary's own ${o2.like_for_like_event_set}, p = ${exact(o2.like_for_like_p_value)}. Comparable to primary: ${o2.comparable_to_primary ? "yes" : "no"}.`),
        h("a", { class: "btn btn-secondary", href: to("/history", { overlay: "o2_excluded" }) }, "Compare variants"))),
    section("Estimates by look-back window", "graph",
      dotFigure({
        title: "Median rank excess before onset, with 95% bootstrap intervals",
        description: "Each dot is a served estimate: how far the score rank sat above ordinary running in the window before a period onset. Intervals that cross zero mean no difference was shown. The primary score is the filled dot; the O₂-excluded sensitivity is the hollow dot with a dashed interval.",
        zeroLabel: "0 = same as ordinary running",
        rowTitle: "Window before onset",
        rows: horizon,
        legend: [["swatch-dot-primary", "Primary score"], ["swatch-dot-sensitivity", "O₂-excluded — sensitivity analysis, not preferred"]],
        tableHeaders: ["Window", "Variant", "Median rank excess", "95% interval", "Status"],
        footnote: `Validation ${version} · score p7-risk-1.1.0 · ${versions(story)}`,
      })),
    section("Censored onsets", "censoring",
      h("p", {}, `${v.censoring.n_onset_censored} of ${v.censoring.n_periods} onsets are censored. Served meaning: ${v.censoring.meaning}.`),
      h("details", { class: "table-toggle" }, h("summary", {}, "Censored and uncensored slices (table)"),
      table("Censored and uncensored slices, as served", ["Window", "Variant", "Slice", "Effect", "p", "Evaluable"],
        v.censoring.split.map((r) => [windowLabel(r.horizon_minutes), VARIANT[r.variant] || r.variant, plain("x", r.slice).text, exact(r.pe), exact(r.p_value), String(r.n_evaluable)])))),
    section("Negative controls", "controls",
      h("p", {}, "Checks on the historical protocol. They are not combined into an overall score."),
      h("details", { class: "table-toggle" }, h("summary", {}, "Negative controls (table)"),
      table("Negative controls, as served", ["Control", "Method", "Status", "p"],
        (v.negative_controls || []).map((r) => [r.control_id, r.method, plain("x", r.status.split(";")[0]).text, exact(r.p_value)])))),
    section("Findings", "findings",
      h("p", {}, FINDINGS_NOTE),
      h("div", { class: "findings" }, groupFindings(story.findings).map(finding))),
    ...storySections("validation", story),
  );
}

function finding(row) {
  const id = findingAnchor(row.finding_id);
  if (row.grouped) {
    return h("article", { class: "finding", id, "aria-labelledby": `${id}-h` },
      h("h3", { id: `${id}-h` }, h("span", { class: "fid" }, "F3"), " ", chip("status", row.classification), " ", F3_GROUP.title),
      h("p", { class: "hint" }, `${row.grouped.length} rule definitions, each ${plain("status", row.classification).text.toLowerCase()}. ${F3_GROUP.note}`));
  }
  const evidence = row.evidence_redacted ? "" : evidenceForDisplay(row.evidence);
  return h("article", { class: "finding", id, "aria-labelledby": `${id}-h` },
    h("h3", { id: `${id}-h` }, h("span", { class: "fid" }, row.finding_id), " ", chip("status", row.classification), " ", row.title),
    h("p", { class: "hint" }, evidence ? `Evidence: ${evidence}` : "Evidence figures withheld in this view (Phase 8 section 26)."),
    row.context_only ? h("p", { class: "hint" }, "Context only: not evidence of an effect.") : null);
}
