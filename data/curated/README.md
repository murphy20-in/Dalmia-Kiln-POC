# curated/

Empty. It will be populated from Phase 2 onward with analysis-ready datasets (for example a time-aligned multi-dataset table for the baseline, KPI and leading-indicator phases).

Constraints carried from Phase 1:

- Datasets can be aligned on the shared 1-minute timestamp. Kiln-I has no September 2025 and Kiln-IIIA has no April 2025, so alignment must not bridge those months.
- No event labels exist. Any label added here must come from plant-supplied records and be traceable to them.
- Each curated file needs a sidecar note naming its source files (by SHA-256 from `../raw/source_manifest.csv`), the transformation scripts, and the masking rules applied.
