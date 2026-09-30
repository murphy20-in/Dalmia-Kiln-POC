# Browser journeys

Run in the IDE browser against `http://127.0.0.1:8010` with Phase 9 on port 8009. Playwright is not installed; these are the executed journeys.

| Journey | Result |
|---|---|
| Overview | Disclaimer, retrospective pill, `NOT_SUPPORTED`, `NOT_AVAILABLE`, 9,557 rows, 12 periods |
| Historical risk | Chart, two gaps in the default window, `preferred = false` |
| O₂ overlay | Sensitivity polyline added; sentence and `preferred = false` shown |
| Abnormal periods | 12 period ids; P6-020 detail with the KPI-derived sentence and a score trajectory |
| Plant events | XSS description stored as text (no extra script or image). Edit saved. Stale version returned 409 and left the text unchanged. Soft delete shows DELETED |
| Validation | `NOT_SUPPORTED`, exact primary figures, sensitivity label. No AUC or coverage figure in the page text |
| Data quality | Kiln-I September, Kiln-IIIA April, O₂ question, coverage months |
| Methodology | Boundary stated as “is not a prediction system” and “is not an alarm system” |
| Responsive | 390px: no horizontal page scroll (`scrollWidth === clientWidth`). Nav becomes a horizontal list. Chart stays inside the column |

Console: no failed API responses observed during these journeys. `console.error` is used only when a request fails.
