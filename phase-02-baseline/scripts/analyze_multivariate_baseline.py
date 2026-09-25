"""Step 7c - multivariate shape of normal operation (descriptive; no predictive model).

Grain: 10-minute medians of INCLUDED values; a bucket is used only if >= 8 of its 10
minutes are INCLUDED (no filling). Buckets never mix excluded periods with valid ones.

Views:
  WITHIN_DATASET:Kiln-I   the dataset holding feed, fuel, AF, combustion, draft, burning zone
  COMPOSITE               tags from all datasets joined on the 10-minute bucket timestamp;
                          labelled POC COMPOSITE PROCESS VIEW — PLANT CONFIRMATION REQUIRED
Methods: Pearson and Spearman (rank, robust to outliers) correlation on pairwise-complete
buckets; rank-based PCA (ranks standardised, i.e. the Spearman correlation structure) on complete
buckets. Median/IQR scaling was rejected because zero-inflated tags (e.g. CO) have IQR ~ 0
and dominate the components. Descriptive only; not a model transform.
Outputs: outputs/multivariate_baseline.csv, reports/figures/corr_kiln_i.png,
         reports/figures/pca_kiln_i.png
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p2common import FIG, H, COMPOSITE_LABEL, PROCESSED, datasets, read_out, wide_included, write_csv, log

lg = log("analyze_multivariate_baseline")


def buckets(eq: str, keep: set) -> tuple[pd.DataFrame, dict]:
    w, seg, names, _ = wide_included(eq)
    w = w[[c for c in w.columns if (eq, c) in keep]]
    b = f"{H['mv_bucket_min']}min"
    cnt = w.resample(b).count()
    med = w.resample(b).median()
    return med.where(cnt >= H["mv_bucket_min_valid"]), names


def corr_rows(df: pd.DataFrame, view: str, meta: dict) -> list[dict]:
    pe = df.corr(method="pearson", min_periods=500)
    sp = df.corr(method="spearman", min_periods=500)
    nn = df.notna().astype(int)
    n = nn.T @ nn
    rows = []
    cols = list(df.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            if pd.isna(sp.loc[a, b]):
                continue
            rows.append({"view": view, "record": "CORRELATION", "var_a": a, "name_a": meta[a][0], "family_a": meta[a][1],
                         "var_b": b, "name_b": meta[b][0], "family_b": meta[b][1], "n_buckets": int(n.loc[a, b]),
                         "pearson": float(pe.loc[a, b]), "spearman": float(sp.loc[a, b]),
                         "pearson_minus_spearman": float(pe.loc[a, b] - sp.loc[a, b])})
    return rows


def pca_rows(df: pd.DataFrame, view: str, meta: dict, min_cov: float = 0.6):
    cov = df.notna().mean()
    use = [c for c in df.columns if cov[c] >= min_cov and df[c].nunique() > 5]
    X = df[use].dropna()
    use = [c for c in use if X[c].nunique() > 5]      # guard: constant within the complete-case subset
    X = X[use]
    if len(X) < 200 or len(use) < 3:
        return [], None
    # rank-based (Spearman-structure) PCA: each variable -> ranks -> standardised. Robust to spikes and
    # zero-inflated signals, which dominate a median/IQR scaling (e.g. CO with IQR ~ 0).
    R = X[use].rank(method="average")
    Z = ((R - R.mean()) / R.std(ddof=0)).to_numpy()
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    ev = S ** 2 / (S ** 2).sum()
    rows = [{"view": view, "record": "PCA_SETTINGS", "var_a": "", "n_buckets": len(X), "value": len(use),
             "detail": "rank-based PCA (ranks standardised = Spearman correlation structure); complete buckets; variables with >=60% bucket coverage"}]
    for k in range(min(6, len(ev))):
        rows.append({"view": view, "record": "PCA_EXPLAINED_VARIANCE", "var_a": f"PC{k + 1}", "value": float(ev[k]),
                     "detail": f"cumulative {ev[:k + 1].sum():.3f}"})
        top = np.argsort(-np.abs(Vt[k]))[:8]
        for j in top:
            c = use[j]
            rows.append({"view": view, "record": "PCA_LOADING", "var_a": f"PC{k + 1}", "var_b": c, "name_b": meta[c][0],
                         "family_b": meta[c][1], "value": float(Vt[k, j])})
    scores = pd.DataFrame(U[:, :2] * S[:2], index=X.index, columns=["PC1", "PC2"])
    return rows, (scores, ev)


def main():
    bs = read_out("baseline_statistics.csv")
    bsr = bs[bs.population == "BASELINE_RUNNING"]
    keep = set(zip(bsr.dataset, bsr.tag))
    fam = bsr.set_index(["dataset", "tag"])[["original_name", "process_family", "unit"]]
    rows = []
    # within Kiln-I
    k1, _ = buckets("Kiln-I", keep)
    meta = {c: (f"{fam.loc[('Kiln-I', c), 'original_name']} [{fam.loc[('Kiln-I', c), 'unit']}]", fam.loc[("Kiln-I", c), "process_family"]) for c in k1.columns}
    rows += corr_rows(k1, "WITHIN_DATASET:Kiln-I", meta)
    pr, k1_scores = pca_rows(k1, "WITHIN_DATASET:Kiln-I", meta)
    rows += pr
    # composite
    parts, cmeta = [], {}
    for eq in datasets():
        b, _ = buckets(eq, keep)
        b.columns = [f"{eq}!{c}" for c in b.columns]
        for c in b.columns:
            e, t = c.split("!")
            cmeta[c] = (f"{fam.loc[(e, t), 'original_name']} [{fam.loc[(e, t), 'unit']}]", fam.loc[(e, t), "process_family"])
        parts.append(b)
    comp = pd.concat(parts, axis=1)
    comp = comp.loc[:, comp.notna().mean() >= 0.3]
    comp = comp.loc[:, comp.nunique() > 5]
    rows += corr_rows(comp, "COMPOSITE", cmeta)
    pr, _ = pca_rows(comp, "COMPOSITE", cmeta)
    rows += pr
    out = pd.DataFrame(rows)
    out.loc[out.view == "COMPOSITE", "label"] = COMPOSITE_LABEL
    out["note"] = "Descriptive association within the baseline population; not causal; no predictive model"
    write_csv(out, "multivariate_baseline.csv", lg)
    plot(k1, meta, k1_scores)


def plot(k1, meta, scores):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sp = k1.corr(method="spearman", min_periods=500)
    fig, ax = plt.subplots(figsize=(10, 8.5))
    im = ax.imshow(sp.values, cmap="RdBu_r", vmin=-1, vmax=1)
    labels = [f"{c} {meta[c][0][:24]}" for c in sp.columns]
    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=6); ax.set_yticks(range(len(labels)), labels, fontsize=6)
    fig.colorbar(im, ax=ax, shrink=0.7, label="Spearman ρ")
    ax.set_title("Kiln-I baseline: Spearman correlation of 10-min medians (INCLUDED values)", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "corr_kiln_i.png", dpi=110); plt.close(fig)
    if scores is None:
        return
    sc, ev = scores
    rg = pd.read_parquet(PROCESSED / "regime_timeline.parquet", columns=["ts", "load_regime"]).set_index("ts").load_regime
    band = rg.reindex(sc.index)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for b in sorted(band.dropna().unique()):
        m = band == b
        ax[0].scatter(sc.PC1[m], sc.PC2[m], s=2, alpha=0.35, label=b)
    ax[0].set_xlabel(f"PC1 ({ev[0]:.1%})"); ax[0].set_ylabel(f"PC2 ({ev[1]:.1%})"); ax[0].legend(markerscale=5, fontsize=7)
    ax[0].set_title("Kiln-I baseline process space (10-min buckets)", fontsize=9)
    ax[1].bar(range(1, min(10, len(ev)) + 1), ev[:10], color="#6baed6"); ax[1].set_xlabel("component"); ax[1].set_ylabel("explained variance")
    ax[1].set_title("PCA scree (rank-based)", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "pca_kiln_i.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
