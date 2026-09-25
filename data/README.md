# Data

Data layers for the Dalmia Kiln POC. The facts below come from Phase 1 (`phase-01-data-discovery/`). Nothing here is assumed.

## Source (read-only, not copied)

```text
/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)
```

- 60 monthly `.xlsx` process-log workbooks (277 MB), 10 equipment folders (`01`–`06`, `08`–`11`; folder `07` is absent), April–September 2025.
- One process-log sheet per workbook. Timestamps are text `dd.mm.yyyy HH:MM` in unlabelled column A, with an observed 1-minute interval and no timezone in the source.
- Header layout: an optional title row, a group row, a parameter row and a unit row. Group labels are not merged cells. The data start row differs per dataset (3, 4 or 5); see `raw/source_manifest.csv`.
- The source must never be modified. `raw/source_manifest.csv` holds a SHA-256 for every file so later phases can confirm they read the same data.

## Layers

| Folder | Content | Produced by | Status |
|---|---|---|---|
| `raw/` | Reference manifest of the source files (no copies) and the dataset registry | Phase 1 `export_data_manifest.py` | Populated |
| `processed/` | Parsed, typed, time-indexed data with masking applied | Phase 2 | Empty |
| `curated/` | Analysis-ready datasets for baseline / KPI / indicators | Phase 2+ | Empty |

## Files to use and exclude

`raw/source_manifest.csv` column `status`:

| Status | Files | Reason |
|---|---|---|
| `USE` | 58 | readable, month matches data |
| `EXCLUDE_UNREADABLE` | `01.Process Log Sheet for Kiln-I (Sep).xlsx` | truncated XLSX; Kiln-I has no September |
| `EXCLUDE_DUPLICATE_CONTENT` | `05.Process Log Sheet for Kiln-IIIA(April).xlsx` | contains May data identical to the May file; Kiln-IIIA has no April |

## Known data constraints (see `phase-01-data-discovery/outputs/dq_issue_register.csv`)

- No coating / ring / deposit / cleaning / shutdown / maintenance event records (EVENT GROUND TRUTH NOT FOUND IN SUPPLIED DATA).
- AF data: only `AFR | Solid` (TPH) and `Liquid` (LPH, 92% empty) in Kiln-I. RDF split, calorific value, moisture and fuel mix are not found.
- Folders named Kiln-IA … IIIB carry sheet titles `KILN PAGE-1A … 3B` and an identical `Kiln MD` column. They may be display pages of one kiln system. This is **not confirmed**.
- Candidates needing masking decisions in Phase 2: sentinel `99999` / `9999`, `-273` Deg.C, text `Error 6`, duplicate timestamps, the frozen window 2025-05-06 11:50–21:50, gaps, and the hourly CBS-II sampling on 1–10 June 2025.
- 9 columns have label/unit mismatches (UNIT CONSISTENCY REVIEW REQUIRED). No unit conversions have been applied anywhere.

## Rules for every layer

- Never write into the source directory.
- Keep the original header text (`original_name`) next to any normalised name.
- Record every transformation (script + parameters) so outputs can be regenerated.
- Data files are git-ignored. Only READMEs and manifests are tracked.

Regenerate `raw/`: `cd phase-01-data-discovery/scripts && python3 run_phase1.py`.
