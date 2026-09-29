"""Falsification / robustness checks of the primary endpoint (spec section 11). Each row answers one attempt to
disprove the early-warning hypothesis; `survives` = PE > 0 and p < 0.10 (secondary, exploratory).

BLOCK_LENGTH_*            bootstrap block 3 / 6 / 12 (declared) / 24 h
EXCLUDE_CENSORED_ONSETS   onsets whose CUSUM never returned to 0 in the 6-h look-back (shift began earlier)
VALID_ONLY                drop VALID_REDUCED_CONFIDENCE periods
REFERENCE_FREE_ROLLING    7-day rolling rank instead of the Apr-May reference rank (reference artefact / drift)
CONTROLS_EXCLUDE_FINAL_PERIODS_ONLY  controls not filtered on the other KPI >= P90 candidates (selection circularity)
CONTROLS_SAME_DQ_RULE_AS_EVENTS      the event POOR-share / stop-transition rule applied to control windows too
KPI_BASELINE              the Phase 3 KPI ranked against its own Apr-May values (is it just KPI persistence?)
DETECTION_ANCHOR          anchored at KPI >= P90 detection instead of onset: CIRCULARITY ILLUSTRATION (mechanical)
LOEO                      PE with each period left out (single-period dominance)
SEVERITY_*                PE within Phase 6 severity strata (context metadata only, never a target)
PHASE4_INDICATOR_CONTEXT  Phase 4 Kiln-I!I|ROC_1H trailing-2h activation at T0 vs controls (historical sensitivity)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import build_controls as bc
import temporal_validation as tv
import warning_metrics as wm
from p8common import CFG, P8Config


def _row(check: str, r: dict, note: str = "", cfg: P8Config = CFG, status: str | None = None) -> dict:
    return {"section": "ROBUSTNESS", "check": check, **tv.summarise(r),
            "status": status or (tv.secondary_status(r, r["p_value"], cfg) if np.isfinite(r.get("p_value", np.nan))
                                 else "REPORTED"), "survives": bool(r["pe"] > 0 and r["p_value"] < 0.10), "note": note}


def kpi_rank(B: dict) -> np.ndarray:
    k = B["s"].kpi_value.to_numpy(float)
    ref = np.sort(k[B["ref_mask"] & np.isfinite(k)])
    return wm.ecdf(ref, np.where(B["oper"], k, np.nan))


def phase4_context(B: dict, cfg: P8Config = CFG) -> dict:
    act = B["s"].phase4_context.fillna("").str.startswith("ACTIVE").to_numpy()
    ev = B["events"]
    ok = ev.evaluable.to_numpy()
    p0 = ev.pos_T0.to_numpy()[ok]
    elig = B["elig"][cfg.primary_h]
    obs = float(act[p0].mean())
    rng = np.random.default_rng(tv.seed_of("PHASE4", cfg))
    pools = {m: np.flatnonzero(elig & (B["month"] == m)) for m in sorted(set(ev.month[ok]))}
    null = np.array([np.mean([act[rng.choice(pools[m])] for m in ev.month[ok]]) for _ in range(cfg.n_null)])
    return {"obs": obs, "control": float(act[elig].mean()), "p": float((1 + np.sum(null >= obs)) / (1 + null.size))}


def run(sig: dict, B: dict, cfg: P8Config = CFG) -> tuple[pd.DataFrame, np.ndarray]:
    x, h, ev = sig["rank"], cfg.primary_h, B["events"]
    rows = [_row(f"BLOCK_LENGTH_{bh}H", tv.endpoint(x, B, h, f"PRIMARY|h{h}", cfg, block_hours=bh),
                 "declared" if bh == cfg.block_hours else "sensitivity only") for bh in cfg.block_sensitivity]
    rows.append(_row("EXCLUDE_CENSORED_ONSETS", tv.endpoint(x, B, h, "R_CENS", cfg,
                                                            ev_mask=~ev.onset_censored.to_numpy(bool))))
    rows.append(_row("VALID_ONLY", tv.endpoint(x, B, h, "R_VALID", cfg,
                                               ev_mask=ev.data_quality_status.eq("VALID").to_numpy())))
    rows.append(_row("REFERENCE_FREE_ROLLING_RANK", tv.endpoint(sig["rank_roll"], B, h, "R_ROLL", cfg),
                     "rank of the score within its own trailing 7 days (excluding the last 24 h)"))
    rows.append(_row("KPI_BASELINE", tv.endpoint(kpi_rank(B), B, h, "R_KPI", cfg),
                     "Phase 3 KPI (context only in Phase 7) ranked against its Apr-May values: how much of the "
                     "pre-onset elevation the KPI itself already carries"))
    el_final = bc.eligible(bc.final_only_clean(B["ix"], ev, cfg), B["oper"], B["dq"], h)
    rows.append(_row("CONTROLS_EXCLUDE_FINAL_PERIODS_ONLY", tv.endpoint(x, B, h, "R_CFINAL", cfg, elig=el_final),
                     "controls may include the other KPI >= P90 candidate extents (control-selection circularity)"))
    rows.append(_row("CONTROLS_SAME_DQ_RULE_AS_EVENTS", tv.endpoint(x, B, h, "R_CDQ", cfg,
                                                                    ctrl_mask=bc.event_dq_rule(B["s"], h)),
                     "control windows also need POOR share <= 0.5 and no STOPPED / TRANSITION_CONTEXT bucket"))
    rows.append(_row("DETECTION_ANCHOR (CIRCULARITY_ILLUSTRATION)", tv.endpoint(x, B, h, "R_DET", cfg,
                                                                                 anchor="pos_det"),
                     "anchored at KPI >= P90 detection: the window lies inside the shift the period is built from",
                     status="CIRCULAR_BY_CONSTRUCTION"))
    lo = tv.loeo(x, B, h, "PRIMARY", cfg)
    fin = lo[np.isfinite(lo)]
    rows.append({"section": "ROBUSTNESS", "check": "LEAVE_ONE_EVENT_OUT", "horizon_minutes": h,
                 "n_evaluable": int(fin.size), "pe": float(np.min(fin)) if fin.size else np.nan,
                 "status": "REPORTED", "survives": bool(fin.size and fin.min() > 0),
                 "note": f"pe = minimum PE over {fin.size} leave-one-out fits; range "
                         f"[{fin.min():+.3f}, {fin.max():+.3f}]; {int((fin > 0).sum())} of {fin.size} > 0"})
    for sev in ("HIGH", "MODERATE", "LOW"):
        rows.append(_row(f"SEVERITY_{sev} (context only)", tv.endpoint(x, B, h, f"R_SEV{sev}", cfg,
                                                                        ev_mask=ev.severity.eq(sev).to_numpy())))
    p4 = phase4_context(B, cfg)
    rows.append({"section": "ROBUSTNESS", "check": "PHASE4_INDICATOR_CONTEXT (historical sensitivity only)",
                 "horizon_minutes": h, "median_event": p4["obs"], "median_control": p4["control"],
                 "pe": p4["obs"] - p4["control"], "p_value": p4["p"], "status": "REPORTED",
                 "survives": bool(p4["obs"] > p4["control"] and p4["p"] < 0.10),
                 "note": "share of periods with Kiln-I!I|ROC_1H active in the trailing 2 h at T0 vs control share; "
                         "never a production feature"})
    return pd.DataFrame(rows), lo


def censored_split(sig: dict, B: dict, cfg: P8Config = CFG) -> pd.DataFrame:
    """PE at every horizon for censored onsets (T0 = the look-back cap; the KPI shift had already begun) and for
    uncensored onsets (T0 = CUSUM zero, a local low) separately. p only (no bootstrap)."""
    cen = B["events"].onset_censored.to_numpy(bool)
    rows = []
    for h in cfg.horizons:
        for grp, m in (("CENSORED", cen), ("UNCENSORED", ~cen)):
            r = tv.endpoint(sig["rank"], B, h, f"{sig['name']}|CENS_SPLIT|{grp}|h{h}", cfg, ev_mask=m, boot=False)
            rows.append({"section": "CENSORED_SPLIT", "variant": sig["name"], "slice": grp, **tv.summarise(r)})
    return pd.DataFrame(rows)
