"""Step 2 - AFR / fuel signal inventory and the fuel-data requirements register.

Reads  phase-01 process_tag_inventory.csv / alternative_fuel_inventory.csv, phase-02 column_holds.csv,
       data/processed/kiln_i.parquet (fuel columns H..M only, read-only)
Writes outputs/afr_inventory.csv          every fuel-firing tag found in the supplied data + every searched-for fuel
                                          property that is NOT in the supplied data (NOT_AVAILABLE)
       outputs/afr_data_requirements.csv  prioritised plant data needed before stronger AFR conclusions are possible

Tags are taken only from the Phase 1 inventory (exact original_name, unit, dataset); nothing is inferred from a tag name.
Fraction denominators: one row per supplied Kiln-I minute (2025-04-01 .. 2025-08-31), identical duplicate copies removed.
MISSING (empty / NaN) is never counted as ZERO; a present value that Phase 2 marks invalid (or negative) is INVALID.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from af_core import AFR, AFR_LIQUID, CONTROL_INPUTS, P1_OUT, P2_OUT, PRIMARY, classify, log, write_csv
from p3common import processed_path

lg = log("build_afr_inventory")

FUEL_TAGS = {  # tag -> (fuel_category, analysis_status, reason)
    AFR: ("ALTERNATIVE_FUEL_SOLID", "ANALYSED", ""),
    AFR_LIQUID: ("ALTERNATIVE_FUEL_LIQUID", "INSUFFICIENT_DATA", ""),          # reason filled from the data below
    "Kiln-I!H": ("CONVENTIONAL_COAL_KILN", "CO_MANIPULATED_COVARIATE",
                 "used only as a co-manipulated fuel-input covariate / co-movement target, never as a process outcome"),
    "Kiln-I!I": ("CONVENTIONAL_COAL_PC", "CO_MANIPULATED_COVARIATE",
                 "used only as a co-manipulated fuel-input covariate / co-movement target, never as a process outcome"),
    "Kiln-I!J": ("CONVENTIONAL_COAL_HAG", "NOT_ANALYSED",
                 "HAG abbreviation undefined in source; zero in most minutes; not used as kiln-line firing context"),
    "Kiln-I!M": ("CONVENTIONAL_DIESEL", "NOT_ANALYSED", "near-constant (zero in most minutes)"),
}
LIQUID_MIN_PRESENT = 0.5      # POC heuristic: a signal needs >= 50 % present minutes to be analysed (Phase 4 C7 analogue)

REQUIREMENTS = [  # (item, priority, why_needed, enables, unblocks_finding, effort)
    ("sp_heat_definition", 1, "Sp.Heat F / G definitions (formula, and the heat factor used for AFR) are not confirmed",
     "deciding whether AFR-Sp.Heat and AFR-KPI links are arithmetic or process evidence; choosing the authoritative Sp.Heat",
     "F5, F6", "LOW (formula from the DCS / plant engineer)"),
    ("AFR_firing_setpoint", 1, "Kiln-I!K may be a set-point, a feeder demand or a measurement - not documented",
     "correct separation of control input from delivered fuel; operator vs controller attribution", "F1, F2, F7",
     "LOW (tag documentation)"),
    ("AFR_operating_log", 1, "reasons for AFR starts / stops / ramps (feeder trips, stock-outs, operator choice) are unknown",
     "separating operator response from process response in AFR transition episodes", "F2, F4, F6, F7",
     "LOW-MEDIUM (shift log / DCS event export)"),
    ("calorific_value", 1, "AFR mass flow (TPH) says nothing about the heat it supplies",
     "energy-based AFR share and substitution metrics; fuel-energy-adjusted Sp.Heat comparisons", "F3, F4, F5, F6",
     "MEDIUM (lab results per AFR lot)"),
    ("moisture", 1, "wet AFR absorbs heat and changes gas volume; mass flow alone cannot separate this",
     "net-heat estimates; interpretation of O2 / temperature patterns with AFR", "F3, F4", "MEDIUM (lab results)"),
    ("AFR_actual_measurement", 2, "no weighed / metered delivered-AFR signal distinct from Kiln-I!K is supplied",
     "delivered-vs-demanded fuel checks; calibration of the TPH values", "F1, F2", "MEDIUM (additional tag export)"),
    ("fuel_lab_timestamp", 2, "lab results must be time-aligned to the minute process data",
     "joining any fuel property above to process behaviour without leakage", "all fuel-property uses",
     "LOW (with the lab data)"),
    ("fuel_mix", 2, "the composition of 'AFR | Solid' (RDF, biomass, industrial waste ...) is unknown and may change",
     "stratified analysis by AFR type; interpretation of month-to-month drift", "drift in §6-7", "MEDIUM"),
    ("chlorine", 2, "chlorine and alkali circulation are the main AFR-related deposit / ring mechanisms",
     "any study of AFR and deposit / coating / ring risk", "none yet (future deposit work)", "MEDIUM (lab)"),
    ("clinker_quality", 2, "no free lime / LSF / clinker chemistry in the supplied data",
     "checking whether AFR-associated process changes matter for product quality", "none yet", "LOW-MEDIUM (QC lab)"),
    ("RDF_fraction", 3, "no RDF split in the supplied data", "RDF-specific relationships", "none yet", "MEDIUM"),
    ("plastic_fraction", 3, "no plastic share in the supplied data", "chlorine / volatile-related behaviour studies",
     "none yet", "MEDIUM"),
    ("ash", 3, "AFR ash enters the clinker and changes the melt", "clinker-chemistry and coating studies", "none yet",
     "MEDIUM (lab)"),
    ("liquid_AFR_valid_record", 3, "Kiln-I!L is 91.7 % empty and bimodal (~4 vs ~1,000-1,600 LPH) with a 10,000 value",
     "any liquid-AFR analysis (currently INSUFFICIENT_DATA)", "Liquid AFR (excluded)", "LOW-MEDIUM (re-export)"),
]


def fuel_minutes() -> pd.DataFrame:
    cols = sorted({t.split("!")[1] for t in FUEL_TAGS})
    d = pd.read_parquet(processed_path("Kiln-I"), columns=["ts", "source_column", "value", "value_valid", "dup_status"],
                        filters=[("source_column", "in", cols)])
    d = d[d.ts.notna() & ~d.dup_status.eq("DUP_IDENTICAL_COPY")].drop_duplicates(["source_column", "ts"])
    return d.assign(tag="Kiln-I!" + d.source_column.astype(str))


def main():
    inv1 = pd.read_csv(P1_OUT / "process_tag_inventory.csv").assign(tag=lambda d: d.dataset + "!" + d.source_column)
    inv1 = inv1.set_index("tag")
    af1 = pd.read_csv(P1_OUT / "alternative_fuel_inventory.csv")
    holds = pd.read_csv(P2_OUT / "column_holds.csv").assign(tag=lambda h: h.dataset + "!" + h.source_column)
    held = holds.groupby("tag").hold.apply(lambda s: "|".join(sorted(set(s)))).to_dict()
    conf = af1.dropna(subset=["source_column"]).assign(tag=lambda d: d.source.astype(str) + "!" + d.source_column)
    conf = conf.drop_duplicates("tag").set_index("tag").classification_confidence
    d = fuel_minutes()
    rows = []
    for t, (cat, status, reason) in FUEL_TAGS.items():
        if t not in inv1.index:
            raise SystemExit(f"{t} not in the Phase 1 inventory - Phase 5 never invents AFR tags")
        g = d[d.tag == t]
        v = g.value.to_numpy(float)
        c = classify(np.where(g.value_valid.to_numpy(bool) | np.isnan(v), v, -1.0), PRIMARY.zero_cut)
        n = len(g)
        present = g.ts[np.isfinite(v)]
        frac = {k: float((c == k).sum() / n) for k in ("MISSING", "ZERO", "NONZERO", "INVALID")}
        if t == AFR_LIQUID:
            by_m = pd.Series(np.isfinite(v), index=g.ts.to_numpy()).groupby(g.ts.dt.month.to_numpy()).mean()
            reason = (f"LIQUID_AFR_ANALYSIS = INSUFFICIENT_DATA: {1 - frac['MISSING']:.1%} present minutes < "
                      f"{LIQUID_MIN_PRESENT:.0%} POC minimum; present share by month "
                      + ", ".join(f"M{m:02d} {s:.1%}" for m, s in by_m.items())
                      + f"; values bimodal (~4 vs ~1,000-1,600 LPH), maximum {np.nanmax(v):,.0f}; "
                      f"Phase 2 hold {held.get(t, '')}")
            if 1 - frac["MISSING"] >= LIQUID_MIN_PRESENT:
                status, reason = "ANALYSED", ""
        r1 = inv1.loc[t]
        rows.append({"indicator_id": t, "original_name": r1.original_name, "dataset": r1.dataset, "unit": r1.detected_unit,
                     "fuel_category": cat, "signal_type": r1.inferred_category,
                     "control_or_measurement": CONTROL_INPUTS[t],
                     "coverage_start": present.min(), "coverage_end": present.max(),
                     "valid_observations": int((c == "ZERO").sum() + (c == "NONZERO").sum()),
                     "missing_fraction": frac["MISSING"], "zero_fraction": frac["ZERO"],
                     "nonzero_fraction": frac["NONZERO"], "invalid_fraction": frac["INVALID"],
                     "health_class": r1.health_class, "unit_confidence": conf.get(t, r1.confidence),
                     "phase2_hold": held.get(t, ""), "analysis_status": status, "exclusion_reason": reason,
                     "classification_evidence": ("FUEL_CONTROL_INPUT per Phase 4 handoff (fuel firing tags are set-points); "
                                                 "plant confirmation of set-point vs measurement PENDING")})
    for r in af1[af1.found.str.startswith("NOT FOUND")].itertuples():
        rows.append({"indicator_id": f"NOT_AVAILABLE:{r.parameter}", "original_name": "", "dataset": "", "unit": "",
                     "fuel_category": "FUEL_PROPERTY_OR_COMPOSITION", "signal_type": "", "control_or_measurement": "",
                     "coverage_start": "", "coverage_end": "", "valid_observations": 0, "missing_fraction": 1.0,
                     "zero_fraction": np.nan, "nonzero_fraction": np.nan, "invalid_fraction": np.nan, "health_class": "",
                     "unit_confidence": "", "phase2_hold": "", "analysis_status": "NOT_AVAILABLE",
                     "exclusion_reason": "not present in any supplied workbook (Phase 1 alternative_fuel_inventory)",
                     "classification_evidence": ""})
    write_csv(pd.DataFrame(rows), "afr_inventory.csv", lg)
    req = pd.DataFrame(REQUIREMENTS, columns=["item", "priority", "why_needed", "enables", "unblocks_finding", "effort"])
    req["status"] = "REQUIRED_FUTURE_DATA"
    req["currently_available"] = False
    write_csv(req.sort_values(["priority", "item"], kind="mergesort"), "afr_data_requirements.csv", lg)


if __name__ == "__main__":
    main()
