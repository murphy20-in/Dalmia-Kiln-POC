"""Step - AFR vs combustion behaviour (families: COMBUSTION).

Reads  cache/buckets.parquet, cache/kpi_grid.parquet, cache/bands.json, cache/episodes.csv, cache/episode_controls.csv
Writes outputs/afr_combustion_relationships.csv  (schema af_core.REL_COLUMNS + negative-control / diagnostic columns)

Correlation engine, band contrasts and transition-episode responses: see af_context. Every row is AFR-ASSOCIATED
evidence at most - never AFR-caused - and implies no set-point, limit or operating action.
"""
from __future__ import annotations

from af_context import run_families
from af_core import log

lg = log("analyze_afr_combustion")


def main():
    run_families(["COMBUSTION"], "afr_combustion_relationships.csv", lg)


if __name__ == "__main__":
    main()
