"""Step 2 - Training / scoring window analysis and selection.

Reads  cache/minute_values.parquet, cache/minute_state.parquet, data/processed/regime_timeline.parquet
Writes outputs/kpi_training_windows.csv

For each candidate window (p3common.TRAINING_WINDOWS) the table reports duration, running coverage,
continuity (missing minutes, stops), load coverage (feed quantiles; share of each tentative Phase 2 feed band,
DESCRIPTIVE ONLY because those bands were fitted on the full period), month coverage and Sp.Heat level,
for both the training and the scoring side. The PRIMARY window is chosen by the documented rule below; the
other windows are sensitivity variants. Nothing here is fitted for scoring.

Selection rule (declared before scoring):
  1. training must be >= 45 days of Kiln-I data and contain >= 2 stop/restart cycles (the causal ramp rule is
     then exercised inside training);
  2. training must contain every tentative feed band with >= 5 % share (load adjustment needs the load range; the
     Phase 2 bands are full-period DESCRIPTIVE clusters, used here only as a design constant for coverage);
  3. scoring must keep >= 60 days of Kiln-I data (enough to observe persistent change);
  4. among windows that satisfy 1-3, prefer the earliest (a reference must precede what it scores).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p3common import CACHE, FEED_TAG, PROCESSED, TRAINING_WINDOWS, log, write_csv

lg = log("build_training_window")
KILN_I_END = "2025-08-31 23:59"
MIN_DAY_MINUTES = 360   # a day counts as a Sp.Heat day with >= 6 h of RUNNING minutes carrying Sp.Heat (hourly
                        # 0.0 placeholders during the late-August stop no longer count)


def describe(v: pd.DataFrame, st: pd.DataFrame, bands: pd.Series, start: str, end: str) -> dict:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    vv, ss, bb = v.loc[s:e], st.loc[s:e], bands.loc[s:e]
    cal_min = int((e - s).total_seconds() // 60) + 1
    run = ss.state_basic.eq("RUNNING_PROXY")
    stops = int((ss.state_basic.eq("STOPPED_PROXY") & ~ss.state_basic.shift().eq("STOPPED_PROXY")).sum())
    ki = (vv["Kiln-I!F"].notna() | vv["Kiln-I!G"].notna()) & run      # RUNNING minutes with a Sp.Heat value
    feed = vv[FEED_TAG].where(run)
    day_run = run.groupby(run.index.floor("D")).mean()
    b = bb[run.reindex(bb.index, fill_value=False)].value_counts(normalize=True)
    return {"start": str(s), "end": str(e), "calendar_days": round(cal_min / 1440, 2),
            "minutes_present": int(len(vv)), "minutes_missing": cal_min - int(len(vv)),
            "running_minutes": int(run.sum()), "running_share": round(float(run.mean()), 4),
            "days_with_kiln_i_sp_heat": int((ki.groupby(ki.index.floor("D")).sum() >= MIN_DAY_MINUTES).sum()),
            "effective_running_days (>=50% running)": int((day_run >= 0.5).sum()),
            "stops": stops, "months": ",".join(sorted(vv.index.to_period("M").astype(str).unique())),
            "feed_p05": feed.quantile(0.05), "feed_p50": feed.median(), "feed_p95": feed.quantile(0.95),
            "share_FEED_BAND_1": float(b.get("FEED_BAND_1", 0.0)), "share_FEED_BAND_2": float(b.get("FEED_BAND_2", 0.0)),
            "share_FEED_BAND_3": float(b.get("FEED_BAND_3", 0.0)),
            "sp_heat_F_median_running": vv["Kiln-I!F"].where(run).median(),
            "sp_heat_G_median_running": vv["Kiln-I!G"].where(run).median()}


def main():
    v = pd.read_parquet(CACHE / "minute_values.parquet", columns=["Kiln-I!F", "Kiln-I!G", FEED_TAG])
    st = pd.read_parquet(CACHE / "minute_state.parquet")
    rg = pd.read_parquet(PROCESSED / "regime_timeline.parquet", columns=["ts", "load_regime"]).set_index("ts").load_regime
    rows = []
    for wid, (ts, te, role) in TRAINING_WINDOWS.items():
        tr = describe(v, st, rg, ts, te)
        sc_start = str(pd.Timestamp(te) + pd.Timedelta(minutes=1))
        sc = describe(v, st, rg, sc_start, KILN_I_END)
        crit = {"C1_train_>=45d_and_>=2_stops": tr["days_with_kiln_i_sp_heat"] >= 45 and tr["stops"] >= 2,
                "C2_all_bands_>=5pct": min(tr["share_FEED_BAND_1"], tr["share_FEED_BAND_2"], tr["share_FEED_BAND_3"]) >= 0.05,
                "C3_scoring_>=60d": sc["days_with_kiln_i_sp_heat"] >= 60}
        rows.append({"window_id": wid, "role": role, **{f"train_{k}": x for k, x in tr.items()},
                     **{f"score_{k}": x for k, x in sc.items()}, **crit, "all_criteria": all(crit.values())})
    df = pd.DataFrame(rows)
    ok = df[df.all_criteria]
    chosen = ok.sort_values("train_start").window_id.iloc[0] if len(ok) else None
    df["selected_by_rule"] = df.window_id.eq(chosen)
    df["note"] = ("Phase 2 feed-band shares are descriptive (bands fitted on the full period, TENTATIVE). "
                  "Training data are strongly autocorrelated: effective sample size is far below the bucket count.")
    # Consistency guard (not a selection step): the configured PRIMARY window must be the one the rule selects.
    if chosen != "W_APR_MAY":
        raise SystemExit(f"selection rule chose {chosen}, but PRIMARY config uses W_APR_MAY - update p3common.PRIMARY")
    write_csv(df, "kpi_training_windows.csv", lg)
    lg.info("selected training window by rule: %s", chosen)


if __name__ == "__main__":
    main()
