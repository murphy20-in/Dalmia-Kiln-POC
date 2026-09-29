"""Load analyses (spec section 10). Phase 7: the score is higher at low feed and during load changes.

A RAW                  the endpoint as declared
B LOAD_ADJUSTED        rank minus the median rank of ordinary-running buckets in the same load stratum
                       (load_band x load_context; retrospective adjustment over Jun-Aug ordinary running, event zones
                       excluded)
C MATCHED_LOAD         controls matched on month x load stratum at the anchor (and on stratum across months)
D TRANSITION_EXCLUDED  events / controls whose window has any LOAD_ASSOCIATED, post-restart-settling or
                       non-operational bucket are dropped
E LOW_FEED_EXCLUDED    events / controls at TENTATIVE_LOW feed at the anchor dropped (reported, not a preferred result)
Verdict (pre-declared): ROBUST_TO_LOAD if raw > 0 and B, C (month x stratum), D all > 0 with p < 0.10;
ATTENUATED if all > 0 but some p >= 0.10; NOT_ROBUST if any <= 0; NOT_APPLICABLE if raw <= 0;
INSUFFICIENT_DATA if any analysis has < min_events_secondary evaluable periods.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import build_controls as bc
import temporal_validation as tv
from p8common import CFG, P8Config, nb


def load_adjusted(x: np.ndarray, strat: np.ndarray, ordinary: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for g in sorted(set(strat.tolist())):
        m = strat == g
        ref = x[m & ordinary & np.isfinite(x)]
        if ref.size:
            out[m] = x[m] - np.median(ref)
    return out


def steady_window(B: dict, h: int) -> np.ndarray:
    s = B["s"]
    steady = B["oper"] & s.load_context.eq("STEADY_LOAD").to_numpy() & ~bc.settling(s)
    return bc.all_in_window(steady, nb(h))


def analyses(x: np.ndarray, B: dict, h: int, label: str, cfg: P8Config = CFG, boot: bool = True) -> dict:
    strat = bc.load_stratum(B["s"])
    mkey = np.array([f"{m}|{g}" for m, g in zip(B["month"], strat)], dtype=object)
    steady = steady_window(B, h)
    p0 = B["events"].pos_T0.to_numpy()
    low = B["s"].load_band.eq("TENTATIVE_LOW").to_numpy()
    ep = lambda lab, **kw: tv.endpoint(kw.pop("x", x), B, h, f"{label}|{lab}|h{h}", cfg, boot=boot, **kw)  # noqa: E731
    return {"RAW": ep("RAW"),
            "LOAD_ADJUSTED": ep("ADJ", x=load_adjusted(x, strat, B["elig"][0])),
            "MATCHED_LOAD": ep("ML", key=mkey),
            "MATCHED_LOAD_ANY_MONTH": ep("MLA", key=strat),
            "TRANSITION_EXCLUDED": ep("TX", ev_mask=steady[p0], ctrl_mask=steady),
            "LOW_FEED_EXCLUDED": ep("LF", ev_mask=~low[p0], ctrl_mask=~low)}


def verdict(r: dict, cfg: P8Config = CFG) -> str:
    keys = ("LOAD_ADJUSTED", "MATCHED_LOAD", "TRANSITION_EXCLUDED")
    if any(r[k]["n_evaluable"] < cfg.min_events_secondary for k in ("RAW",) + keys):
        return "INSUFFICIENT_DATA"
    if not r["RAW"]["pe"] > 0:
        return "NOT_APPLICABLE"
    if any(not r[k]["pe"] > 0 for k in keys):
        return "NOT_ROBUST"
    return "ROBUST_TO_LOAD" if all(r[k]["p_value"] < 0.10 for k in keys) else "ATTENUATED"


def table(x: np.ndarray, B: dict, label: str, cfg: P8Config = CFG) -> tuple[pd.DataFrame, dict]:
    rows, keep = [], {}
    for h in cfg.horizons:
        r = analyses(x, B, h, label, cfg, boot=h == cfg.primary_h)
        keep[h] = r
        row = {"score_variant": label, "analysis": f"PRE_ONSET_RANK_EXCESS_{h}MIN", "horizon_minutes": h,
               "raw_effect": r["RAW"]["pe"], "load_adjusted_effect": r["LOAD_ADJUSTED"]["pe"],
               "matched_load_effect": r["MATCHED_LOAD"]["pe"],
               "matched_load_any_month_effect": r["MATCHED_LOAD_ANY_MONTH"]["pe"],
               "transition_excluded_effect": r["TRANSITION_EXCLUDED"]["pe"],
               "low_feed_excluded_effect": r["LOW_FEED_EXCLUDED"]["pe"]}
        for k, v in r.items():
            row[f"{k.lower()}_p"] = v["p_value"]
            row[f"{k.lower()}_n_events"] = v["n_evaluable"]
        row["status"] = verdict(r, cfg)
        rows.append(row)
    return pd.DataFrame(rows), keep
