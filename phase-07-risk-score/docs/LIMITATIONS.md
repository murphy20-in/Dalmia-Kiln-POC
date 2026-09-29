# Phase 7 Limitations

Each limitation is stated with its consequence for anyone who reads or consumes the score. The quantitative evidence is in the outputs and the report.

## Scientific

1. **No event ground truth.**
   - There are no coating, ring, deposit, cleaning, maintenance, failure or shutdown-reason records.
   - The score is therefore **not** a deposit, ring or failure probability, and has no validated operational meaning.
   - Any "risk" is resemblance to reference-relative abnormal process behaviour.
2. **Only 12 empirical abnormal periods, and they are circular.**
   - Phase 6 found them from the same Phase 3 components with the same P90 family rule.
   - High coverage is expected by construction and is not evidence of detection skill. It was not used to choose the design.
   - The 10 Apr–May calibration-only periods are in-sample.
3. **Reference dependence.**
   - Band levels (the share of time in HIGH) change materially with the reference window. April-only and May-only references give very different HIGH shares, and band agreement drops to about 0.55 with April only.
   - Rank ordering is stable (median Spearman ≈ 0.97).
   - A band is only meaningful together with its `reference_version`.
4. **Drift is uncertain, and much of it depends on one analyser.**
   - Against the Apr–May reference, the share of HIGH time is higher in August than in June. That difference has a block CI that excludes zero, and it holds in every robustness variant.
   - The month-to-month steps are **not** separable: the monthly CIs overlap, and the path is not monotone in every variant.
   - The jump from the 10 % reference level to June mixes in-sample optimism with drift.
   - Excluding the kiln-inlet O₂ analyser (limitation 16) roughly halves the June → August rise.
   - The plant has not confirmed which of these it reflects: real deterioration, a changed operating regime (for example the lower Sp.Heat, AFR or feed pattern of Jun–Aug), an analyser artefact, or a reference that is not representative.
5. **Load confounding.**
   - The score is higher in low-feed and load-change periods.
   - The Phase 3 tags are load-adjusted within the training load range, but low loads are rare in the reference, and load-band anchors change the score materially (ρ ≈ 0.65).
   - As in Phase 6, the score is **not load-independent**. The `LOAD_ASSOCIATED_CONDITION` context code flags it.
6. **The relationship with Phase 6 severity is inconclusive.**
   - With n = 12, the Spearman CI spans from negative to strongly positive, and class medians are not monotone.
   - This is underpowered, not evidence of no relationship.
   - Score magnitude must not be read as a severity grade.
   - The AFR / Phase 4 inclusion tests are likewise biased toward exclusion: they measure gain on circular coverage.
7. **The 0.50 / 0.25 / 0.25 weights are a declared design choice, not a fit.** The rank is insensitive to them; the bands are moderately sensitive (see robustness).
8. **Families are not fully independent evidence.**
   - STABILITY is built from tags of other families.
   - Phase 3 dimensions share the feed-conditional reference.
   - The maximum reference correlation is low (|ρ| ≈ 0.29), but they are all process-deviation views of one kiln.

## Data

9. **Partial baseline.**
   - No Phase 2 family is READY, and baseline readiness is PARTIAL.
   - Tag-level confidence is static full-period metadata (disclosed).
   - The reference is in-sample for Phase 3, so the band edges are optimistic.
10. **Unconfirmed operating-state proxy.** The meaning of `Kiln MD` is unconfirmed, so STOPPED / TRANSITION / RUNNING and the restart settling ramp are POC proxies.
11. **Unconfirmed equipment identity.** The folders are assumed to be pages of one kiln line, and the composite view is unconfirmed.
12. **Unresolved Sp.Heat definition.**
    - The two definitions (F and G) differ by about 60 kcal/kg.
    - Phase 5 found Sp.Heat reproducible from the firing inputs, so it may be calculated rather than measured.
    - The efficiency family therefore partly reflects firing decisions.
13. **Missing periods.** Kiln-I September is missing, so there is no numeric score in September. Kiln-IIIA April is missing (it affects clinker context only).
14. **Missing measurements.** There are no fuel properties (calorific value, moisture, RDF / plastic split, ash / chlorine), no clinker quality, no kiln shell temperature, no measured CO₂ and no labelled ID fan. None of these is invented or imputed.
15. **Missing data: the bias is downward, and dropout can move the score either way.**
    - Missing *families* can never raise the score (fixed denominator), but they bias it **downward**. Absence of evidence scores as normal, so confidence is LOW for an incomplete family set below HIGH.
    - A trailing median of fewer buckets, or a family average over fewer tags (Phase 3 averages the available tags), can move either way. Both are quantified in G7.
    - Tag dropout is value-related (MNAR): for example, the O₂ analyser drops out after high readings.
16. **Kiln-inlet O₂ analyser (`Kiln-I!X`).**
    - It often reads near ambient air (up to about 21 %, a hard ceiling) while the kiln is running, which suggests a purge / calibration cycle or a sample-line fault.
    - These readings are valid upstream, so they raise the combustion and stability families. They are more frequent in August.
    - Phase 7 does not modify upstream masking and has no plant-confirmed threshold. It therefore flags these buckets in confidence (heuristic: bucket median ≥ 15 %) and quantifies their effect with an exact no-analyser robustness variant, but does not remove them from the primary score.
17. **Retrospective context labels.** Phase 5 AFR transition labels and Phase 1 DQ windows are detected with hindsight. They are used only as context (AFR), or only after the window has ended (DQ confidence), and never as score inputs.

## Operational

18. **Confidence is internal consistency, not accuracy.** It is capped at MEDIUM because there is no ground truth, the state proxy is unconfirmed and the equipment mapping is unconfirmed.
19. **No early-warning claim.** Pre-onset scores are descriptive. Early warning is Phase 8's question and must be judged against the same frozen reference.
20. **Nothing here is a plant limit, alarm, set-point or control recommendation,** and nothing should drive an operating action without the plant's own review.
