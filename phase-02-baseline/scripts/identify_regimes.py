"""Step 5 - operating-regime investigation (within RUNNING_PROXY minutes only).

Regimes are declared ONLY if the data support them. Candidate dimensions:
  load:    Kiln-I C 'Kiln Feed | Pfister' [TPH]
  AF mode: Kiln-I K 'AFR | Solid' [TPH] == 0 vs > 0 while running
Support criteria (POC ANALYTICAL HEURISTICS):
  - Gaussian-mixture BIC selects k > 1 (k = 1..4, fixed seed), fitted on 10-minute medians
    (>= 8 valid minutes) to reduce the autocorrelation of 1-minute samples
  - adjacent components that are not separated (Ashman D < threshold) are merged
  - adjacent components separated: Ashman's D >= regime_ashman_d
  - each component weight >= 5 %
  - regimes persist: median dwell >= regime_min_dwell_min, measured on a TRAILING
    30-minute median of feed (no look-ahead)
  - robustness: the fit + merge is repeated on day-block bootstrap resamples; the share of
    resamples reproducing the same number of bands is reported
Labels are descriptive data clusters (e.g. 'FEED_BAND_1'), not plant operating modes.
The mixture is fitted on the FULL supplied period (descriptive); later phases must refit on
their own training window before using bands for scoring (no reuse across evaluation periods).
Outputs: outputs/operating_regimes.csv, data/processed/regime_timeline.parquet,
         reports/figures/regimes_feed.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

from p2common import PROCESSED, FIG, H, PROXY_LABEL, COMPOSITE_LABEL, load_processed, write_csv, log

lg = log("identify_regimes")


def running_series(col: str) -> pd.Series:
    tl = pd.read_parquet(PROCESSED / "operating_state_timeline.parquet", columns=["ts", "operating_state"]).set_index("ts")
    d = load_processed("Kiln-I", ["ts", "source_column", "value", "value_valid", "dup_status", "segment_id"])
    d = d[(d.source_column == col) & d.ts.notna() & d.dup_status.isin(["UNIQUE", "DUP_KEPT"])].set_index("ts").sort_index()
    d = d[~d.index.duplicated()]
    st = tl.operating_state.reindex(d.index)
    x = d.value.where(d.value_valid & (st == "RUNNING_PROXY"))
    return x, d.segment_id


def ashman_d(m1, s1, m2, s2):
    return float(np.sqrt(2) * abs(m1 - m2) / np.sqrt(s1 ** 2 + s2 ** 2))


def main():
    rows = []
    feed, seg = running_series("C")
    v = feed.dropna()
    b10 = feed.resample("10min")
    med10 = b10.median().where(b10.count() >= 8).dropna()
    sub = med10.values.reshape(-1, 1)
    fits = {}
    for k in range(1, 5):
        g = GaussianMixture(n_components=k, random_state=H["seed"], n_init=3).fit(sub)
        fits[k] = g
        rows.append({"dimension": "LOAD (Kiln-I C Kiln Feed | Pfister, TPH)", "test": "GMM_BIC", "k": k, "value": float(g.bic(sub)),
                     "detail": f"fitted on {len(sub)} 10-minute medians"})
    best = min(fits, key=lambda k: fits[k].bic(sub))
    g = fits[best]
    order = np.argsort(g.means_.ravel())
    means = g.means_.ravel()[order]
    sds = np.sqrt(g.covariances_.ravel()[order])
    w = g.weights_[order]
    for i in range(best):
        rows.append({"dimension": "LOAD", "test": "GMM_COMPONENT", "k": best, "value": float(means[i]),
                     "detail": f"component {i + 1}: mean {means[i]:.1f} TPH, sd {sds[i]:.1f}, weight {w[i]:.3f}"})
    # merge adjacent components that are not separated (Ashman D < threshold); BIC alone over-splits
    # large autocorrelated samples. Groups are merged using mixture moments.
    groups = [[i] for i in range(best)]

    def moments(gr):
        ww = w[gr]; mm = means[gr]; ss = sds[gr]
        m = float((ww * mm).sum() / ww.sum())
        var = float((ww * (ss ** 2 + (mm - m) ** 2)).sum() / ww.sum())
        return m, np.sqrt(var), float(ww.sum())
    while len(groups) > 1:
        dd = [ashman_d(*moments(groups[i])[:2], *moments(groups[i + 1])[:2]) for i in range(len(groups) - 1)]
        j = int(np.argmin(dd))
        if dd[j] >= H["regime_ashman_d"]:
            break
        groups[j] = groups[j] + groups.pop(j + 1)
    gm = [moments(gr) for gr in groups]
    ds = [ashman_d(gm[i][0], gm[i][1], gm[i + 1][0], gm[i + 1][1]) for i in range(len(gm) - 1)]
    comp_to_group = {c: gi for gi, gr in enumerate(groups) for c in gr}
    for gi, (m, sd, wt) in enumerate(gm):
        rows.append({"dimension": "LOAD", "test": "MERGED_BAND", "k": len(gm), "value": m,
                     "detail": f"FEED_BAND_{gi + 1}: components {[c + 1 for c in groups[gi]]}, mean {m:.1f} TPH, sd {sd:.1f}, weight {wt:.3f}"})
    w_groups = np.array([x[2] for x in gm])
    # persistence on a trailing 30-min median within segments (no look-ahead)
    sm = feed.groupby(seg).transform(lambda s: s.rolling(30, min_periods=20).median())
    lab = pd.Series(np.nan, index=feed.index)
    ok = sm.notna()
    comp_sorted = order.argsort()[g.predict(sm[ok].values.reshape(-1, 1))]
    lab[ok] = [comp_to_group[c] for c in comp_sorted]
    runs = (lab != lab.shift()).cumsum()
    dwell = lab.dropna().groupby(runs[lab.notna()]).size()
    med_dwell = float(dwell.median()) if len(dwell) else 0.0
    supported = len(gm) > 1 and min(ds, default=0) >= H["regime_ashman_d"] and w_groups.min() >= 0.05 and med_dwell >= H["regime_min_dwell_min"]
    rows.append({"dimension": "LOAD", "test": "SUPPORT_DECISION", "k": best, "value": float(supported),
                 "detail": f"BIC best k={best}; after merging unseparated components {len(gm)} band(s); Ashman D between bands="
                           f"{['%.2f' % x for x in ds]} (need >= {H['regime_ashman_d']}); min band weight {w_groups.min():.3f}; median dwell {med_dwell:.0f} min (need >= {H['regime_min_dwell_min']}) -> "
                           + ("LOAD REGIMES SUPPORTED" if supported else "NO SUPPORTED LOAD REGIMES (single running-state load distribution)")})
    # bootstrap robustness of the band structure (day-block resampling of the 10-minute medians)
    rng = np.random.default_rng(H["seed"])
    days = med10.index.floor("D")
    ud = days.unique()
    ks, dmins = [], []
    for _ in range(20):
        pick = rng.choice(ud, size=len(ud), replace=True)
        xb = np.concatenate([med10.values[days == dday] for dday in pick]).reshape(-1, 1)
        fb = {kk: GaussianMixture(n_components=kk, random_state=H["seed"], n_init=1).fit(xb) for kk in range(1, 5)}
        kb = min(fb, key=lambda kk: fb[kk].bic(xb))
        gb = fb[kb]; ob = np.argsort(gb.means_.ravel())
        mb_, sb_, wb_ = gb.means_.ravel()[ob], np.sqrt(gb.covariances_.ravel()[ob]), gb.weights_[ob]
        grs = [[i] for i in range(kb)]

        def mom(gr):
            ww = wb_[gr]; mm = mb_[gr]; ss = sb_[gr]
            m = float((ww * mm).sum() / ww.sum()); return m, float(np.sqrt((ww * (ss ** 2 + (mm - m) ** 2)).sum() / ww.sum()))
        while len(grs) > 1:
            dd = [ashman_d(*mom(grs[i]), *mom(grs[i + 1])) for i in range(len(grs) - 1)]
            j = int(np.argmin(dd))
            if dd[j] >= H["regime_ashman_d"]:
                break
            grs[j] = grs[j] + grs.pop(j + 1)
        ks.append(len(grs))
        dmins.append(min([ashman_d(*mom(grs[i]), *mom(grs[i + 1])) for i in range(len(grs) - 1)], default=np.nan))
    same = float(np.mean(np.array(ks) == len(gm)))
    rows.append({"dimension": "LOAD", "test": "BOOTSTRAP_BAND_STABILITY", "k": len(gm), "value": same,
                 "detail": f"20 day-block resamples: merged band counts { {int(a): int(b) for a, b in pd.Series(ks).value_counts().items()} }; "
                           f"min Ashman D median {np.nanmedian(dmins):.2f}; share reproducing {len(gm)} bands = {same:.2f}"})
    robust = supported and same >= H["regime_bootstrap_min_share"]
    status = "ROBUST" if robust else ("TENTATIVE (supported on full data, not reproduced under resampling)" if supported else "NOT SUPPORTED")
    rows.append({"dimension": "LOAD", "test": "REGIME_STATUS", "k": len(gm), "value": float(robust),
                 "detail": f"{status}; bands are used as a secondary stratification only; primary baseline = single RUNNING population"
                           if supported else status})
    rows.append({"dimension": "LOAD", "test": "FIT_WINDOW", "k": None, "value": None,
                 "detail": f"{med10.index.min()} .. {med10.index.max()} (full supplied Kiln-I running period; descriptive; refit before any scoring use)"})
    if supported:
        mon = pd.DataFrame({"m": lab.index.to_period("M").astype(str), "b": lab.values}).dropna()
        for (mm, b), c in mon.groupby(["m", "b"]).size().items():
            rows.append({"dimension": "LOAD", "test": "BAND_SHARE_BY_MONTH", "k": len(gm), "value": float(c / (mon.m == mm).sum()),
                         "detail": f"{mm}: FEED_BAND_{int(b) + 1}"})
    # AF mode while running
    afr, aseg = running_series("K")
    a = afr.dropna()
    on = (a > 0)
    r2 = (on != on.shift()).cumsum()
    dw = on.groupby(r2).agg(["first", "size"])
    zero_share = float((~on).mean())
    af_supported = zero_share >= 0.05 and float(dw[~dw["first"]]["size"].median() if (~dw["first"]).any() else 0) >= H["regime_min_dwell_min"]
    rows.append({"dimension": "AF MODE (Kiln-I K AFR | Solid, TPH)", "test": "ZERO_WHILE_RUNNING_SHARE", "k": None, "value": zero_share,
                 "detail": f"{int((~on).sum())} of {len(on)} running minutes have AFR Solid == 0"})
    rows.append({"dimension": "AF MODE", "test": "DWELL_MEDIAN_ZERO_MIN", "k": None,
                 "value": float(dw[~dw["first"]]["size"].median()) if (~dw["first"]).any() else 0.0,
                 "detail": f"median contiguous AFR==0 run while running; longest {int(dw[~dw['first']]['size'].max()) if (~dw['first']).any() else 0} min"})
    rows.append({"dimension": "AF MODE", "test": "SUPPORT_DECISION", "k": None, "value": float(af_supported),
                 "detail": ("AFR_ZERO / AFR_POSITIVE modes are persistent; reported as a descriptive stratum only (no causal claim)"
                            if af_supported else "AFR zero periods not persistent enough to form a stratum")})
    reg = pd.DataFrame({"ts": feed.index})
    reg["load_regime"] = (lab.map(lambda x: f"FEED_BAND_{int(x) + 1}" if pd.notna(x) else None).values if supported
                          else np.where(feed.notna().values, "SINGLE_RUNNING_DISTRIBUTION", None))
    afm = pd.Series(np.where(afr > 0, "AFR_POSITIVE", np.where(afr == 0, "AFR_ZERO", None)), index=afr.index)
    reg["af_mode"] = afm.reindex(feed.index).values if af_supported else None
    reg["label"] = PROXY_LABEL
    reg["view"] = COMPOSITE_LABEL + " (Kiln-I regimes applied to other datasets by timestamp)"
    reg.to_parquet(PROCESSED / "regime_timeline.parquet", index=False)
    out = pd.DataFrame(rows)
    out["note"] = "Descriptive data clusters within RUNNING_PROXY minutes; not plant-defined operating modes"
    write_csv(out, "operating_regimes.csv", lg)
    plot(v, g, order, supported)


def plot(v, g, order, supported):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(v.values, bins=120, density=True, color="#9ecae1", edgecolor="none", label="RUNNING_PROXY minutes")
    xs = np.linspace(v.min(), v.max(), 600)
    for j, i in enumerate(order):
        m, s, w = g.means_.ravel()[i], np.sqrt(g.covariances_.ravel()[i]), g.weights_[i]
        ax.plot(xs, w * np.exp(-0.5 * ((xs - m) / s) ** 2) / (s * np.sqrt(2 * np.pi)), lw=1.2, label=f"GMM comp {j + 1}")
    ax.set_xlabel("Kiln-I C 'Kiln Feed | Pfister' [TPH]"); ax.set_ylabel("density")
    ax.set_title("Load distribution while RUNNING_PROXY — " + ("regimes supported" if supported else "no supported regimes"), fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "regimes_feed.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
