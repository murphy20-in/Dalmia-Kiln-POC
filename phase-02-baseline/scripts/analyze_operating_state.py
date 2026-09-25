"""Step 4 - operating-state evidence and a POC PROXY — UNCONFIRMED state timeline.

Evidence, not assumption: the meaning of 'Kiln MD' (column B, unit hrs) is NOT defined
in the source. We test whether its two observed values co-occur with independent
process signals (kiln feed, kiln speed, burning-zone temperature, fuel, clinker TPH).

Composite timeline (POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED): one
state per timestamp from the 'Kiln MD' columns of all datasets that have one
(identical in Phase 1), applied to every dataset, including CBS-Calculation, which
has no 'Kiln MD'.

States (all POC PROXY — UNCONFIRMED):
  RUNNING_PROXY               Kiln MD == 0.02
  STOPPED_PROXY               Kiln MD == 0
  TRANSITION_PRE_STOP_PROXY   pre_stop_window_min before a RUNNING->STOPPED change
  TRANSITION_RAMP_PROXY       after a restart until the signal regains P25 of ITS OWN pre-stop running
                              level for 60 clock minutes (primary Kiln-I feed, secondary Kiln-IA hood
                              temperature); the search never crosses the next stop; if the level is not
                              regained the whole run is transition (censored); fallback = median of
                              uncensored ramps only when no signal exists
  STATE_CONFLICT              RUNNING while Kiln-I feed == 0 or kiln speed == 0,
                              or STOPPED while feed > 0
  UNKNOWN                     no usable Kiln MD value
Transition labels are RETROSPECTIVE (they use knowledge of the next state change).
They define the historical baseline population only and are not a real-time rule.
Outputs: data/processed/operating_state_timeline.parquet, outputs/operating_state_analysis.csv,
         outputs/operating_state_events.csv, reports/figures/operating_state_evidence.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p2common import (PROCESSED, FIG, H, PROXY_LABEL, COMPOSITE_LABEL, load_processed, datasets, read_out,
                      write_csv, log)

lg = log("analyze_operating_state")

EVIDENCE_TAGS = [("Kiln-I", "C"), ("Kiln-I", "O"), ("Kiln-I", "AF"), ("Kiln-I", "H"), ("Kiln-I", "I"), ("Kiln-I", "K"),
                 ("Kiln-I", "R"), ("Kiln-IIIA", "M"), ("Kiln-IA", "C"), ("Kiln-II", "S"), ("IKN Cooler-I", "C")]


def series(eq, col):
    d = load_processed(eq, ["ts", "source_column", "value", "value_valid", "dup_status"])
    d = d[(d.source_column == col) & d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT"])]
    s = d.set_index("ts").value.where(d.set_index("ts").value_valid)
    return s[~s.index.duplicated()].sort_index()


def main():
    contract = read_out("tag_contract.csv")
    md = contract[contract.original_name.str.lower().str.startswith("kiln md")]
    B = {r.dataset: series(r.dataset, r.source_column) for r in md.itertuples()}
    Bdf = pd.DataFrame(B)
    run_v, stop_v = H["running_B_value"], H["stopped_B_value"]
    code = Bdf.apply(lambda s: np.where(s == run_v, 1, np.where(s == stop_v, 0, np.nan)))
    code = pd.DataFrame(code, index=Bdf.index, columns=Bdf.columns)
    n_avail = code.notna().sum(axis=1)
    frac_run = code.mean(axis=1)
    state = pd.Series(np.where(n_avail == 0, "UNKNOWN", np.where(frac_run > 0.5, "RUNNING_PROXY",
                               np.where(frac_run < 0.5, "STOPPED_PROXY", "UNKNOWN"))), index=Bdf.index)
    agree = pd.Series(np.where(n_avail > 0, np.maximum(frac_run, 1 - frac_run), np.nan), index=Bdf.index)
    # other B values (neither 0 nor 0.02)
    other_vals = {eq: s[(s.notna()) & (s != run_v) & (s != stop_v)].value_counts().head(5).to_dict() for eq, s in B.items()}

    feed, speed = series("Kiln-I", "C"), series("Kiln-I", "O")
    hood = series("Kiln-IA", "C")          # feed-independent secondary signal (Kiln Hood | Temp)
    base_state = state.copy()
    idx = state.index
    fr, sp, hd = feed.reindex(idx), speed.reindex(idx), hood.reindex(idx)
    signals = {"KILN_I_FEED": fr, "KILN_IA_HOOD_TEMP": hd}

    known = base_state.isin(["RUNNING_PROXY", "STOPPED_PROXY"])
    s2 = base_state[known]
    grp = (s2 != s2.shift()).cumsum()
    runs = s2.groupby(grp).agg(["first", "size"]).rename(columns={"first": "state", "size": "minutes"})
    runs["start"] = s2.index.to_series().groupby(grp.values).first().values
    runs["end"] = s2.index.to_series().groupby(grp.values).last().values
    runs = runs.reset_index(drop=True)
    final = base_state.copy()
    pre = pd.Timedelta(minutes=H["pre_stop_window_min"])

    def ramp_end(sig: pd.Series, stop_start, restart, search_end):
        """Clock minutes from restart until sig >= P25 of its own pre-stop RUNNING level for ramp_sustain_min
        consecutive clock minutes, searching only up to search_end (never past the next stop).
        Returns (minutes | None, reference, censored). None = signal/reference unavailable."""
        lo = stop_start - pre - pd.Timedelta(days=H["ramp_ref_lookback_days"])
        hist = sig[(sig.index >= lo) & (sig.index < stop_start - pre)]
        hist = hist[base_state.reindex(hist.index) == "RUNNING_PROXY"].dropna().tail(H["ramp_ref_minutes"])
        f = sig.loc[restart:search_end]
        if len(hist) < 240 or f.notna().sum() == 0:
            return None, None, False
        ref = float(hist.quantile(H["ramp_ref_quantile"]))
        okm = (f >= ref).astype(float)
        ok = okm.rolling(f"{H['ramp_sustain_min']}min").sum() >= H["ramp_sustain_min"]   # clock-time window
        run_minutes = int((search_end - restart).total_seconds() / 60) + 1
        if not ok.any():
            return run_minutes, ref, True     # censored: level not regained before the next stop / search end
        return int((ok.idxmax() - restart).total_seconds() / 60) - H["ramp_sustain_min"] + 1, ref, False

    events = []
    for i in range(1, len(runs)):
        prev, cur = runs.iloc[i - 1], runs.iloc[i]
        if prev.state == "RUNNING_PROXY" and cur.state == "STOPPED_PROXY":
            m = (idx >= cur.start - pre) & (idx < cur.start) & (final == "RUNNING_PROXY")
            final[m] = "TRANSITION_PRE_STOP_PROXY"
            events.append({"event": "STOP", "at": cur.start, "stop_minutes": int(cur.minutes), "stop_end": cur.end,
                           "pre_stop_window_min": H["pre_stop_window_min"]})
        if prev.state == "STOPPED_PROXY" and cur.state == "RUNNING_PROXY":
            search_end = min(cur.end, cur.start + pd.Timedelta(hours=H["ramp_max_search_h"]))
            res = {name: ramp_end(sig, prev.start, cur.start, search_end) for name, sig in signals.items()}
            primary = next((n for n in signals if res[n][0] is not None), None)
            e = {"event": "RESTART", "at": cur.start, "after_stop_minutes": int(prev.minutes), "following_run_minutes": int(cur.minutes),
                 "search_end": search_end}
            for n, (mins, ref, cens) in res.items():
                e[f"ramp_min_{n}"] = mins; e[f"ref_{n}"] = ref; e[f"censored_{n}"] = cens
            e["ramp_basis"] = primary or "NONE"
            e["ramp_minutes"] = res[primary][0] if primary else None
            e["censored"] = bool(res[primary][2]) if primary else None
            events.append(e)
    uncensored = [e for e in events if e["event"] == "RESTART" and e["ramp_minutes"] is not None and not e["censored"]]
    med_ramp = int(np.median([e["ramp_minutes"] for e in uncensored])) if uncensored else 0
    for e in events:
        if e["event"] != "RESTART":
            continue
        if e["ramp_minutes"] is None:
            # never extend beyond this run (the mask must not spill into the next run)
            e["ramp_minutes_applied"] = min(med_ramp, e["following_run_minutes"])
            e["ramp_basis"] = "FALLBACK_MEDIAN_UNCENSORED_RAMP (no signal available; capped at run length)"
        else:
            e["ramp_minutes_applied"] = e["ramp_minutes"]
        m = (idx >= e["at"]) & (idx < e["at"] + pd.Timedelta(minutes=e["ramp_minutes_applied"])) & (final == "RUNNING_PROXY")
        final[m] = "TRANSITION_RAMP_PROXY"
    # conflicts with independent signals (Kiln-I, where present)
    conf = ((final == "RUNNING_PROXY") & ((fr == 0) | (sp == 0))) | ((final == "STOPPED_PROXY") & (fr > 0))
    final[conf] = "STATE_CONFLICT"
    state_basis = np.where(fr.notna(), "KILN_MD + KILN_I_FEED/SPEED", np.where(hd.notna(), "KILN_MD + KILN_IA_HOOD_TEMP (Kiln-I unavailable)",
                                                                             "KILN_MD_ONLY"))
    both_sig = [e for e in events if e["event"] == "RESTART" and e.get("ramp_min_KILN_I_FEED") is not None
                and e.get("ramp_min_KILN_IA_HOOD_TEMP") is not None and not e["censored_KILN_I_FEED"] and not e["censored_KILN_IA_HOOD_TEMP"]]
    agree_ramp = (float(np.median([abs(e["ramp_min_KILN_I_FEED"] - e["ramp_min_KILN_IA_HOOD_TEMP"]) for e in both_sig])) if both_sig else None)

    tl = pd.DataFrame({"ts": idx, "kiln_md_datasets_available": n_avail.values, "kiln_md_running_fraction": frac_run.values,
                       "kiln_md_agreement": agree.values, "state_basic": base_state.values, "operating_state": final.values,
                       "state_basis": state_basis})
    tl["label"] = PROXY_LABEL
    tl["view"] = COMPOSITE_LABEL
    tl.to_parquet(PROCESSED / "operating_state_timeline.parquet", index=False)

    rows = []
    for st, c in final.value_counts().items():
        rows.append({"section": "STATE_MINUTES", "item": st, "value": int(c), "detail": f"{c / len(final) * 100:.2f}% of composite minutes"})
    for eq in B:
        s = code[eq]
        both = s.notna() & known
        rows.append({"section": "KILN_MD_AGREEMENT_WITH_COMPOSITE", "item": eq,
                     "value": round(float(((s[both] == 1) == (base_state[both] == "RUNNING_PROXY")).mean()), 6),
                     "detail": f"{int(both.sum())} minutes compared; other values seen {other_vals[eq]}"})
    for eq, col in EVIDENCE_TAGS:
        name = contract[(contract.dataset == eq) & (contract.source_column == col)].original_name.iloc[0]
        unit = contract[(contract.dataset == eq) & (contract.source_column == col)].detected_unit.iloc[0]
        x = series(eq, col).reindex(idx)
        for st in ["RUNNING_PROXY", "STOPPED_PROXY"]:
            v = x[base_state == st]
            vv = v.dropna()
            rows.append({"section": "INDEPENDENT_SIGNAL_BY_KILN_MD_STATE", "item": f"{eq}!{col} '{name}' [{unit}] | {st}",
                         "value": float(vv.median()) if len(vv) else None,
                         "detail": (f"n={len(v)}, valid={len(vv)}, missing_share={v.isna().mean():.3f}, zero_share={(vv == 0).mean():.3f}, "
                                    f"p05={vv.quantile(.05) if len(vv) else None}, p95={vv.quantile(.95) if len(vv) else None}")})
    nres = sum(e["event"] == "RESTART" for e in events)
    rows.append({"section": "RAMP_RULE", "item": "restart ramp rule", "value": med_ramp,
                 "detail": f"ramp ends when the signal regains P{int(H['ramp_ref_quantile'] * 100)} of its own last {H['ramp_ref_minutes']} RUNNING "
                           f"minutes before that stop (<= {H['ramp_ref_lookback_days']} d back) for {H['ramp_sustain_min']} consecutive clock min; "
                           f"search stops at the next stop; "
                           f"primary Kiln-I feed, secondary Kiln-IA hood temp; {nres} restarts, "
                           f"{sum(1 for e in events if e['event'] == 'RESTART' and e.get('censored'))} censored (level not regained before next stop -> whole run is transition); "
                           f"median uncensored ramp {med_ramp} min (fallback only when no signal)"})
    rows.append({"section": "RAMP_RULE", "item": "feed vs hood ramp agreement (median |difference|, min)", "value": agree_ramp,
                 "detail": f"{len(both_sig)} restarts where both signals give an uncensored ramp"})
    for b_, c_ in pd.Series(state_basis).value_counts().items():
        rows.append({"section": "STATE_BASIS_MINUTES", "item": b_, "value": int(c_), "detail": "evidence available for the state at that minute"})
    rows.append({"section": "CONFLICTS", "item": "STATE_CONFLICT minutes", "value": int(conf.sum()),
                 "detail": "RUNNING with Kiln-I feed==0 or speed==0, or STOPPED with feed>0 (excluded from baseline)"})
    rows.append({"section": "INTERPRETATION", "item": PROXY_LABEL, "value": None,
                 "detail": "Kiln MD 0.02 co-occurs with feed/speed/fuel; 0 with absent/zero feed and speed. Consistent with a run-state "
                           "flag (0.02 h ~ one minute of run time), but the meaning is NOT CONFIRMED by the plant."})
    out = pd.DataFrame(rows)
    out["label"] = PROXY_LABEL
    write_csv(out, "operating_state_analysis.csv", lg)
    write_csv(pd.DataFrame(events), "operating_state_events.csv", lg)
    plot(idx, base_state, final, fr, sp)


def plot(idx, base_state, final, fr, sp):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(13, 7.5), sharex=True)
    ax[0].plot(fr.index, fr.values, lw=0.3, color="#1f4e79"); ax[0].set_ylabel("Kiln-I C\nKiln Feed | Pfister [TPH]")
    ax[1].plot(sp.index, sp.values, lw=0.3, color="#2e7d32"); ax[1].set_ylabel("Kiln-I O\nKiln Main Drive | Speed [RPM]")
    cmap = {"RUNNING_PROXY": 3, "TRANSITION_RAMP_PROXY": 2, "TRANSITION_PRE_STOP_PROXY": 2, "STATE_CONFLICT": 1, "STOPPED_PROXY": 0, "UNKNOWN": -1}
    ax[2].plot(idx, final.map(cmap).values, drawstyle="steps-post", lw=0.6, color="#6a1b9a")
    ax[2].set_yticks([-1, 0, 1, 2, 3], ["UNKNOWN", "STOPPED", "CONFLICT", "TRANSITION", "RUNNING"])
    ax[2].set_ylabel("state\n(POC PROXY)")
    fig.suptitle("Operating-state evidence — POC PROXY — UNCONFIRMED (composite view; plant confirmation required)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "operating_state_evidence.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
