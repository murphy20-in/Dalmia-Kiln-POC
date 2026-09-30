# UX semantics

The shell always shows **Retrospective, not an early warning** and the sentence that this view does not provide live alarms, predictions, probabilities, or validated detection.

Labels that must stay distinct:

| Thing | Wording |
|---|---|
| Score | Empirical risk score (primary). Magnitude, not an alarm band |
| O₂ series | O₂-excluded sensitivity. `preferred = false`. Not a corrected score |
| Phase 6 rows | KPI-derived abnormal periods (not plant events) |
| Plant rows | Plant-supplied event. Type is whatever the plant entered |
| Overlap | Shown as overlap of two labels, never as “detected coating” |
| Validation | `NOT_SUPPORTED` for the primary endpoint. The O₂ block is “Sensitivity analysis” |
| Bands | Not painted. The methodology page says they are reference-relative, not limits |
| Gaps | Empty spans. A zero score is a point on the axis |

The status pill says “Retrospective analytical POC”.

`X-Actor` is labelled **Actor**, with the note that it is attribution only and this POC has no login.
