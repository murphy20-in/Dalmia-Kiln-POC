# Analytical semantics review

Compared with the Phase 8 / Phase 9 handoff.

- The score line is the API `empirical_risk_score`. No formula is evaluated in JavaScript.
- Gaps use the published 10-minute rule and `gaps_in_page`. A zero remains a point.
- O₂ is requested only when the toggle is on and is labelled as a sensitivity analysis. The served `variant_preference` ("neither variant is preferred until the plant explains…") is shown next to both variants and next to L07, so the primary score isn't implied to be preferred either.
- Step 9 `mle-reviewer` findings and their dispositions are in `REVIEW_LOG.md` §4.
- Periods keep `label_type` and the sentence “KPI-derived abnormal periods (not plant events)”.
- Plant events keep `event_type` from the plant. Overlap text does not merge the labels.
- Validation prints the API primary endpoint, including `NOT_SUPPORTED`, and does not rank horizons or show coverage or AUC.
- F16’s API title contains the words “Lead time”. It is shown with class BLOCKED. No lead-time number is shown.
- Reference-relative bands are not painted.

No client-side relabeling of HIGH / ELEVATED / LOW into alarm language.
