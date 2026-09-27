"""Step 6 - Lead-time estimation and false-lead analysis for every indicator.

Reads  cache/lag_analysis.parquet, cache/episode_metrics.csv, cache/features.parquet, cache/kpi_grid.parquet
Writes outputs/indicator_lead_time.csv   per indicator:
  Lead time
    discovery_lag_minutes      THE lead time: lag chosen on discovery only (smallest BH q) - pre-declared (MLE-H2)
    posthoc_best_lag_minutes   POST-HOC DESCRIPTIVE: argmax over lags of sign * rho_p in the replication months (Jun-Jul)
    posthoc_stable_lag_range   POST-HOC DESCRIPTIVE: replication lags with sign * rho_p >= 0.5 * best and CI excluding 0
    month_best_lags            best lag per month (JUN, JUL replication; AUG holdout, descriptive)
    lead_time_confidence_uncapped  HIGH / MEDIUM / LOW (see lead_confidence()); the published lead_time_confidence in
                               indicator_scores / leading_indicator_set is this value capped at the indicator confidence
    median_episode_lead_minutes new threshold crossing before independent KPI deterioration episodes (Jun-Jul; suppressed
                               when crossings are not more frequent before episodes than before matched controls)
  False leads (causal alarms: >= 30 min beyond the directional discovery threshold after >= 2 h clear), per scope
  (replication Jun-Jul = *_repl; holdout Aug = *_holdout):
    an alarm is EVALUABLE when the 12 h after it are RUNNING with >= 2/3 KPI coverage; it is a TRUE lead if the KPI rises
    by >= delta within those 12 h (delta = discovery P75 of the 12-h maximum rise); otherwise FALSE, classified as
    LOAD_TRANSITION, SHORT_LIVED, DIRECTIONAL_REVERSAL or UNEXPLAINED. Alarms with a stop / transition in the 6 h before
    or the 12 h after are SHUTDOWN_RELATED excursions (reported, not evaluable). Precision is compared with the base
    rate computed on exactly the same evaluability rule.
All thresholds are POC analytical heuristics fitted on discovery, not plant alarm limits.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p4common import (CACHE, FEED_TAG, HOLDOUT, PRIMARY, REPLICATION_MONTHS, P4Config, THRESHOLD_LABEL, log,
                      write_csv)
import analysis_context as ac
import indicator_core as ic

lg = log("evaluate_lead_time")


def lead_confidence(stable: np.ndarray, lags: np.ndarray, disc_lag: int, month_best: dict) -> str:
    """HIGH: the replication stable range is contiguous, contains the discovery lag, and both replication months' best
    lags fall inside it. MEDIUM: the stable range contains the discovery lag. LOW: otherwise (no single lead reported)."""
    if not stable.any():
        return "LOW"
    idx = np.flatnonzero(stable)
    lo, hi = lags[idx[0]], lags[idx[-1]]
    if not lo <= disc_lag <= hi:
        return "LOW"
    inside = sum(v is not None and lo <= v <= hi for m, v in month_best.items() if m in REPLICATION_MONTHS)
    return "HIGH" if np.all(np.diff(idx) == 1) and inside == len(REPLICATION_MONTHS) else "MEDIUM"


def lead_profile(lagdf: pd.DataFrame, choice: pd.DataFrame) -> pd.DataFrame:
    out = []
    for c, g in lagdf[lagdf.window.isin(["REPL", *REPLICATION_MONTHS, HOLDOUT])].groupby("indicator_id", sort=True):
        s = int(choice.sign.get(c, 0))
        rec = {"indicator_id": c}
        p = g[g.window.eq("REPL")].sort_values("lag_minutes")
        sr = s * p.rho_p.to_numpy()
        lags = p.lag_minutes.to_numpy()
        if s == 0 or not np.isfinite(sr).any():
            out.append(rec)
            continue
        i = int(np.nanargmax(sr))
        best = sr[i]
        rec["posthoc_best_lag_minutes"] = int(lags[i]) if best > 0 else np.nan
        rec["posthoc_best_rho_p"] = float(p.rho_p.iloc[i])
        sig = (s * p.ci_lo.to_numpy() > 0) & (s * p.ci_hi.to_numpy() > 0)
        stable = (sr >= 0.5 * best) & sig if best > 0 else np.zeros(len(sr), bool)
        rec["n_stable_lags"] = int(stable.sum())
        rec["lags_same_sign_share"] = float(np.mean(sr[np.isfinite(sr)] > 0))
        if stable.any():
            idx = np.flatnonzero(stable)
            rec["posthoc_stable_lag_range"] = f"{int(lags[idx[0]])}-{int(lags[idx[-1]])}"
            rec["stable_range_contiguous"] = bool(np.all(np.diff(idx) == 1))
        mb = {}
        for m in (*REPLICATION_MONTHS, HOLDOUT):
            q = g[g.window.eq(m)].sort_values("lag_minutes")
            v = s * q.rho_p.to_numpy()
            mb[m] = int(q.lag_minutes.iloc[int(np.nanargmax(v))]) if np.isfinite(v).any() and np.nanmax(v) > 0 else None
        rec["month_best_lags"] = "|".join(f"{k}:{v if v is not None else 'none'}" for k, v in mb.items())
        rec["lead_time_confidence_uncapped"] = lead_confidence(stable, lags, int(choice.lag_minutes[c]), mb)
        out.append(rec)
    return pd.DataFrame(out)


def false_leads(F: pd.DataFrame, ctx: ac.Context, choice: pd.DataFrame, thr: pd.Series, cfg: P4Config) -> pd.DataFrame:
    h = cfg.follow_h * 60 // cfg.bucket_min
    fmr = ic.future_max_rise(ctx.K_primary, ctx.running, h)
    disc = ac.discovery_rows(ctx) & np.isfinite(fmr) & (ctx.index + pd.Timedelta(hours=cfg.follow_h) <= pd.Timestamp(cfg.disc_end))
    delta = float(np.quantile(fmr[disc], 0.75))
    st = ctx.grid.bucket_state.to_numpy()
    nonrun = st != "RUNNING"
    pre = ic.buckets_in(6 * 60, cfg)
    feed = F.get(f"{FEED_TAG}|LEVEL_1H")
    dfeed = np.abs(feed.to_numpy() - ic.lagged(feed.to_numpy(), ic.buckets_in(60, cfg))) if feed is not None else np.full(len(st), np.nan)
    d_ok = ac.discovery_rows(ctx) & np.isfinite(dfeed)
    feed_thr = float(np.quantile(dfeed[d_ok], 0.95)) if d_ok.any() else np.inf
    drows = ac.discovery_rows(ctx)
    scopes = {"repl": np.isin(ctx.window, REPLICATION_MONTHS), "holdout": ctx.window == HOLDOUT}
    cs = np.concatenate([[0], np.cumsum(nonrun)])
    i_all = np.arange(len(nonrun))
    pre_nonrun = (cs[i_all] - cs[np.maximum(i_all - pre, 0)]) > 0          # any non-RUNNING bucket in [i-6 h, i)
    evaluable = {k: m & ctx.running & np.isfinite(fmr) & ~pre_nonrun for k, m in scopes.items()}
    base = {k: float(np.mean(fmr[e] >= delta)) if e.any() else np.nan for k, e in evaluable.items()}
    out = []
    for c, r in choice.iterrows():
        x = F[c].to_numpy(float)
        s = int(r.sign)
        if not np.isfinite(thr.get(c, np.nan)) or s == 0:
            continue
        on_all = ic.alarm_onsets(x, s, thr[c], cfg)
        beyond = np.where(np.isfinite(x), s * x >= s * thr[c], False)
        opp_thr = np.nanquantile(x[drows], 1 - cfg.alarm_q if s > 0 else cfg.alarm_q)
        opp = np.where(np.isfinite(x), s * x <= s * opp_thr, False)
        rec = {"indicator_id": c, "alarm_threshold": thr[c], "threshold_label": THRESHOLD_LABEL, "delta_kpi_points": delta}
        for scope, mask in scopes.items():
            b = base[scope]                                       # same evaluability rule as the alarms
            on = on_all[mask[on_all] & ctx.running[on_all]]
            cats = dict.fromkeys(["TRUE_LEAD", "SHUTDOWN_RELATED", "LOAD_TRANSITION", "SHORT_LIVED", "DIRECTIONAL_REVERSAL",
                                  "UNEXPLAINED", "NOT_EVALUABLE"], 0)
            for i in on:
                if pre_nonrun[i] or nonrun[i + 1:i + 1 + h].any():
                    cats["SHUTDOWN_RELATED"] += 1
                elif not np.isfinite(fmr[i]):
                    cats["NOT_EVALUABLE"] += 1
                elif fmr[i] >= delta:
                    cats["TRUE_LEAD"] += 1
                elif np.isfinite(dfeed[i]) and dfeed[i] >= feed_thr:
                    cats["LOAD_TRANSITION"] += 1
                elif not beyond[i + 1: i + 1 + cfg.alarm_persist_buckets].all():
                    cats["SHORT_LIVED"] += 1
                elif opp[i + 1: i + 1 + pre].any():
                    cats["DIRECTIONAL_REVERSAL"] += 1
                else:
                    cats["UNEXPLAINED"] += 1
            n_eval = sum(v for k, v in cats.items() if k not in ("NOT_EVALUABLE", "SHUTDOWN_RELATED"))
            prec = cats["TRUE_LEAD"] / n_eval if n_eval else np.nan
            run_days = float((mask & ctx.running).sum() * cfg.bucket_min / 1440)
            rec.update({f"n_alarms_{scope}": int(len(on)),
                        f"alarms_per_7_running_days_{scope}": len(on) / run_days * 7 if run_days else np.nan,
                        f"n_alarms_evaluable_{scope}": n_eval,
                        f"false_lead_rate_{scope}": (n_eval - cats["TRUE_LEAD"]) / n_eval if n_eval else np.nan,
                        f"precision_{scope}": prec, f"base_rate_{scope}": b,
                        f"precision_lift_{scope}": prec / b if n_eval and b and b > 0 else np.nan})
            rec.update({f"n_{k.lower()}_{scope}": v for k, v in cats.items()})
        out.append(rec)
    return pd.DataFrame(out)


def main():
    cfg = PRIMARY
    ctx = ac.build_context(cfg)
    F = ac.load_features()
    lagdf = ac.load_lag_table()
    choice = ac.discovery_choice(lagdf)
    em = pd.read_csv(CACHE / "episode_metrics.csv").set_index("indicator_id")
    thr = em.threshold
    lp = lead_profile(lagdf, choice)
    fl = false_leads(F, ctx, choice, thr, cfg)
    out = choice.reset_index().rename(columns={"lag_minutes": "discovery_lag_minutes", "rho_p": "disc_rho_p",
                                               "q_bh": "disc_q_bh", "ci_lo": "disc_ci_lo", "ci_hi": "disc_ci_hi",
                                               "n": "disc_n", "n_eff": "disc_n_eff", "p_eff": "disc_p_eff"})
    out = out.merge(lp, on="indicator_id", how="left").merge(fl, on="indicator_id", how="left")
    keep = [c for c in em.columns if c.endswith(("_repl", "_holdout", "_disc")) and not c.startswith("n_episodes_total")]
    out = out.merge(em[keep].reset_index(), on="indicator_id", how="left")
    out = out.rename(columns={"median_lead_min_repl": "median_episode_lead_minutes"})
    out = out.sort_values("indicator_id", kind="mergesort")
    out.to_parquet(CACHE / "lead_time.parquet", index=False)
    write_csv(out, "indicator_lead_time.csv", lg)
    s = out[out.disc_supported]
    lg.info("discovery-supported %d; lead-time confidence %s; median replication false-lead rate %.2f (base rate %.2f)",
            len(s), s.lead_time_confidence_uncapped.value_counts().to_dict(), float(s.false_lead_rate_repl.median()),
            float(s.base_rate_repl.median()))


if __name__ == "__main__":
    main()
