# Phase 8 — Limitations

1. **No plant event ground truth.** The 12 periods are KPI-derived `EMPIRICAL_ABNORMAL_PERIODS`. Deposit / ring /
   coating / failure / maintenance early warning is BLOCKED; lead times are to a KPI-defined onset only.
2. **Circularity.** The Phase 3 KPI (which defines the periods) and the Phase 7 score are built from the same five
   family components. A pre-onset association is expected partly by construction; it measures temporal precedence
   relative to the KPI onset, not independent validity. The KPI baseline check quantifies the overlap but cannot
   remove it.
3. **Anchor definition.** T0 is the Phase 6 CUSUM onset: the last bucket before the KPI deviation starts to
   accumulate, i.e. structurally a local low of any smoothed signal. Detection (KPI ≥ P90) is structurally high.
   Neither is a plant event time; results depend on this choice, which was fixed before results.
4. **Small n.** At most 12 periods (≤ 5 per month). Confidence intervals are wide, month-level results cannot be
   SUPPORTED by design, and absent results are not evidence of absence.
5. **Trailing-window persistence.** The score is a smoothed trailing statistic; it stays elevated after periods
   (NC3), so elevation near an onset is not specific to the time before it.
6. **O₂ analyser.** Ambient-like `Kiln-I!X` readings reduce Phase 7 data-quality confidence, which makes some periods
   non-evaluable for the primary score and moves the O₂-excluded result. The cause of those readings is not known
   (plant confirmation required), so neither variant can be preferred on data grounds.
7. **Load.** The score depends on load; transition-excluded analyses keep few periods, so load dependence can only be
   bounded, not removed.
8. **Censored onsets.** Several onsets are censored (the KPI deviation was already accumulating at the start of the
   6-h look-back); their T0 is the look-back cap, so their "pre-onset" window lies inside the shift. Uncensored T0s
   are the CUSUM zero, a local low. The positive excesses come from the censored group (report §20); the endpoint
   cannot measure precedence for either group.
9. **Reference period.** The rank transform and W1–W4 thresholds use the Apr–May in-sample reference; June has no
   out-of-sample month for threshold holdout.
10. **Controls.** Ordinary running is defined by the absence of KPI-defined periods, not by plant confirmation that
    the kiln was normal (open Phase 7 plant question: which period the plant regards as normal). Excluding every
    KPI ≥ P90 candidate selects low-KPI time; excluding only the final periods (F20) and holding controls to the event
    data-quality rule (F19) are reported as sensitivities.
11. **Multiple analyses.** Many secondary / robustness analyses are reported; only the primary endpoint is
    confirmatory. Horizon SUPPORTED needs BH q; horizon WEAK uses raw p. The F2–F20 classification rules are post hoc
    (spec §16).
12. **Rank ceiling.** Summer ordinary running already ranks high against the Apr–May reference (control median ≈ 0.83),
    so a rank excess has little room (≈ 0.17) and W1 / W3 fire often in ordinary running.
13. **Regime boundary.** The first onset (P6-020, 2025-06-01 01:00) lies about an hour after the reference period;
    its look-back straddles the in-sample boundary.
14. **Contract deviations.** No month × load → load-stratum fallback (spec §5); pooled control rate in the coverage
    binomial; the ×0.5 O₂ data-quality penalty is hard-coded in Phase 7 and mirrored, not read.
