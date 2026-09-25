"""Shared helpers for the Phase 1 data-discovery pipeline.

Everything here is READ-ONLY with respect to the source data. Parsed sheets are
cached under phase-01-data-discovery/cache/ (outside the source tree).

Heuristic constants below are POC DATA-QUALITY HEURISTICS. They are NOT plant
engineering limits and must not be used as process thresholds.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import re
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

# --------------------------------------------------------------------------- paths
SOURCE_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia/Dalmia/Dalmia/AI Automation(Kiln)")
# Supporting material that sits next to (not inside) the data root.
SUPPORTING_ROOT = Path("/home/admin1/POPOS-DATA/Codebases/Dalmia")
PHASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PHASE_DIR / "outputs"
REPORT_DIR = PHASE_DIR / "reports"
CACHE_DIR = PHASE_DIR / "cache"
for _d in (OUT_DIR, REPORT_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------- POC DATA-QUALITY HEURISTICS
HEURISTICS = {
    "completeness_green_min_pct": 95.0,   # >= 95 % non-missing -> GREEN
    "completeness_amber_min_pct": 70.0,   # 70-95 % -> AMBER, < 70 % -> RED
    "gap_factor": 1.5,                    # interval > 1.5 x observed mode interval = gap
    "long_gap_minutes": 60,               # gap >= 60 min = long gap
    "flatline_min_samples": 60,           # >= 60 identical consecutive samples = flatline period
    "iqr_k": 1.5,
    "iqr_extreme_k": 3.0,
    "mad_z": 3.5,
    "spike_mad_z": 10.0,                  # |first difference| robust z threshold
    "unit_magnitude_ratio": 10.0,         # month-to-month median ratio flag
    "near_constant_top_share": 0.95,      # most common value covers >= 95 % of values
}

# Candidate sentinel / placeholder tokens (documented as candidates, not invalid).
SENTINEL_NUMERIC = {9999, -9999, 99999, -99999, 999999, -999999, 32767, -32768, 65535}
SENTINEL_TEXT = {"", "NA", "N/A", "#N/A", "NULL", "NAN", "*", "-", "--", "BAD", "ERROR",
                 "#VALUE!", "#DIV/0!", "#REF!", "NONE", "?"}

TS_PATTERNS = [
    (re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$"), "%d.%m.%Y %H:%M"),
    (re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}$"), "%d.%m.%Y %H:%M:%S"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$"), "ISO"),
    (re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?$"), "%d/%m/%Y %H:%M"),
]

EXPECTED_EQUIPMENT = [
    "Kiln-I", "Kiln-IA", "Kiln-II", "Kiln-III", "Kiln-IIIA", "Kiln-IIIB",
    "CBS-I", "CBS-II", "CBS-Calculation", "IKN Cooler-I",
]

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


# ------------------------------------------------------------------------ utilities
def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(SOURCE_ROOT))


def equipment_from_folder(folder_name: str) -> str:
    m = re.match(r"^\s*(\d+)\.Process Log Sheet for (.+?)\s*$", folder_name)
    return m.group(2) if m else "UNKNOWN"


def folder_index(folder_name: str) -> str:
    m = re.match(r"^\s*(\d+)\.", folder_name)
    return m.group(1) if m else ""


def month_label_from_filename(name: str) -> str:
    """Month label as written in the filename (e.g. 'Sep', 'MAY', 'april')."""
    m = re.search(r"\(?\s*([A-Za-z]+)\s*\)?\.xlsx$", name)
    return m.group(1) if m else "UNKNOWN"


def month_num_from_label(label: str) -> int | None:
    return MONTHS.get(label[:3].lower())


def source_xlsx_files() -> list[Path]:
    return sorted(p for p in SOURCE_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm", ".xls"))


def is_valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            z.namelist()
        return True
    except Exception:
        return False


def write_csv(df: pd.DataFrame, name: str) -> Path:
    p = OUT_DIR / name
    df.to_csv(p, index=False)
    print(f"  wrote {p.relative_to(PHASE_DIR)} ({len(df)} rows)")
    return p


def read_out(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT_DIR / name, low_memory=False)


def norm_token(s) -> str:
    s = "" if s is None else str(s)
    s = s.strip().lower()
    s = re.sub(r"[^0-9a-z]+", "_", s)
    return s.strip("_")


def clean_text(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def parse_ts(v):
    """Return (Timestamp|None, format_label)."""
    if v is None:
        return None, "EMPTY"
    if isinstance(v, datetime):
        return pd.Timestamp(v), "EXCEL_DATETIME"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return None, "NUMERIC_NOT_PARSED"
    s = str(v).strip()
    for rx, fmt in TS_PATTERNS:
        if rx.match(s):
            try:
                if fmt == "ISO":
                    return pd.Timestamp(s), "ISO"
                if s.count(":") == 2 and fmt.count(":") == 1:
                    fmt += ":%S"
                return pd.Timestamp(datetime.strptime(s, fmt)), fmt
            except ValueError:
                return None, "PATTERN_MATCH_BUT_INVALID"
    return None, "UNPARSED_TEXT"


# ------------------------------------------------------------------ sheet parsing
@dataclass
class ColumnMeta:
    col_index: int
    col_letter: str
    header_cells: list          # raw values of each header row (None preserved)
    header_rows: list           # 1-based row numbers of header rows
    unit_raw: str | None
    unit_cell: str | None
    original_name: str          # raw header parts joined with ' | ' (non-empty parts only)
    group_ffill_candidate: str | None   # positional forward fill of top group row (INFERRED)
    normalized_name: str
    is_timestamp_col: bool = False


@dataclass
class SheetParse:
    file_rel: str
    sheet_name: str
    sheet_index: int
    sheet_state: str
    max_row: int
    max_col: int
    kind: str                       # PROCESS_LOG_TABLE | NON_PROCESS_CONTENT | EMPTY
    title_row: int | None = None
    title_text: str | None = None
    header_rows: list = field(default_factory=list)
    unit_row: int | None = None
    unit_row_match_rate: float | None = None
    data_start_row: int | None = None
    data_end_row: int | None = None
    n_data_rows: int = 0
    trailing_rows_without_ts: int = 0
    columns: list = field(default_factory=list)   # list[ColumnMeta]
    notes: list = field(default_factory=list)


UNIT_LEXICON = {
    "hrs", "hr", "h", "tph", "tpd", "kwh/t", "kcla/kgclnkr", "kcal/kgclnkr", "kcal/kg", "lph", "a", "amps",
    "rpm", "kw", "mmwc", "deg.c", "degc", "°c", "%", "ppm", "m3/m", "m3/hr", "nm3/min", "nm3/h", "bar", "mbar",
    "kv", "ma", "kw/ton", "ton", "tons", "kg/h", "t", "m3/h", "pa", "kpa", "mm", "kg/t", "kcal/kg clinker",
}


def _is_unit_like(v) -> bool:
    s = clean_text(v)
    if s is None:
        return False
    return s.lower() in UNIT_LEXICON or (len(s) <= 12 and not re.search(r"\d{3,}", s))


def parse_sheet(ws, file_rel: str, sheet_index: int, rows: list[tuple]) -> SheetParse:
    sp = SheetParse(file_rel=file_rel, sheet_name=ws.title, sheet_index=sheet_index,
                    sheet_state=ws.sheet_state, max_row=len(rows), max_col=max((len(r) for r in rows), default=0),
                    kind="EMPTY")
    if not rows or all(all(clean_text(c) is None for c in r) for r in rows):
        return sp
    # data start = first row whose column-A value parses as a timestamp
    data_start = None
    for i, r in enumerate(rows[:50]):
        ts, _ = parse_ts(r[0] if r else None)
        if ts is not None:
            data_start = i
            break
    if data_start is None:
        sp.kind = "NON_PROCESS_CONTENT"
        sp.notes.append("No timestamp-like value found in column A within first 50 rows")
        return sp
    sp.kind = "PROCESS_LOG_TABLE"
    sp.data_start_row = data_start + 1
    hdr = rows[:data_start]
    ncol = sp.max_col
    # title row: a header row with exactly one non-empty cell containing 'page' (case-insens.)
    hdr_rows_idx = list(range(len(hdr)))
    for i in hdr_rows_idx:
        vals = [clean_text(c) for c in hdr[i]]
        nn = [v for v in vals if v]
        if len(nn) == 1 and re.search(r"page", nn[0], re.I):
            sp.title_row, sp.title_text = i + 1, nn[0]
    struct_rows = [i for i in hdr_rows_idx if (i + 1) != sp.title_row
                   and any(clean_text(c) for c in hdr[i])]
    sp.header_rows = [i + 1 for i in struct_rows]
    if struct_rows:
        u = struct_rows[-1]
        vals = [clean_text(c) for c in hdr[u][1:]]
        nn = [v for v in vals if v]
        rate = (sum(_is_unit_like(v) for v in nn) / len(nn)) if nn else 0.0
        sp.unit_row_match_rate = round(rate, 3)
        if rate >= 0.8:
            sp.unit_row = u + 1
        else:
            sp.notes.append("Last header row does not look like a unit row; units UNKNOWN")
    # trailing rows (after data) without timestamp
    last = len(rows) - 1
    while last > data_start and parse_ts(rows[last][0] if rows[last] else None)[0] is None:
        last -= 1
    sp.data_end_row = last + 1
    sp.trailing_rows_without_ts = len(rows) - 1 - last
    sp.n_data_rows = last - data_start + 1
    top = struct_rows[0] if struct_rows else None
    ffill = None
    for c in range(ncol):
        cells = [hdr[i][c] if c < len(hdr[i]) else None for i in struct_rows]
        unit_raw = None
        name_rows = struct_rows
        if sp.unit_row is not None:
            unit_raw = clean_text(hdr[sp.unit_row - 1][c] if c < len(hdr[sp.unit_row - 1]) else None)
            name_rows = [i for i in struct_rows if i + 1 != sp.unit_row]
        parts = [clean_text(hdr[i][c] if c < len(hdr[i]) else None) for i in name_rows]
        nonempty = [p for p in parts if p]
        if top is not None and top + 1 != sp.unit_row:
            v = clean_text(hdr[top][c] if c < len(hdr[top]) else None)
            if v:
                ffill = v
        letter = get_column_letter(c + 1)
        is_ts = c == 0
        original = " | ".join(nonempty) if nonempty else ("(unlabelled timestamp column)" if is_ts else "(no header text)")
        norm = f"{letter.lower()}__" + (norm_token("_".join(nonempty)) if nonempty else ("timestamp" if is_ts else "unnamed"))
        if unit_raw:
            norm += "__" + norm_token(unit_raw)
        sp.columns.append(ColumnMeta(
            col_index=c, col_letter=letter, header_cells=cells, header_rows=[i + 1 for i in struct_rows],
            unit_raw=unit_raw, unit_cell=f"{letter}{sp.unit_row}" if sp.unit_row else None,
            original_name=original,
            group_ffill_candidate=(ffill if (top is not None and not is_ts) else None),
            normalized_name=norm, is_timestamp_col=is_ts))
    return sp


def load_workbook_cached(path: Path, force: bool = False):
    """Return list of (SheetParse, raw_rows) for each sheet; None if unreadable."""
    key = hashlib.md5(rel(path).encode()).hexdigest()[:12]
    cp = CACHE_DIR / f"{key}.pkl"
    if cp.exists() and not force:
        with open(cp, "rb") as fh:
            return pickle.load(fh)
    if not is_valid_zip(path):
        return None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    result = []
    for si, ws in enumerate(wb.worksheets):
        rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
        sp = parse_sheet(ws, rel(path), si, rows)
        result.append((sp, rows))
    wb.close()
    with open(cp, "wb") as fh:
        pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return result


# ------------------------------------------------------------ dataset construction
def classify_cell(v) -> str:
    if v is None:
        return "empty"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, np.integer)):
        return "int"
    if isinstance(v, (float, np.floating)):
        return "nan" if np.isnan(v) else ("inf" if np.isinf(v) else "float")
    if isinstance(v, datetime):
        return "datetime"
    s = str(v)
    if s.strip() == "":
        return "blank_string"
    if s.strip().upper() in SENTINEL_TEXT:
        return "placeholder_text"
    try:
        float(s.strip().replace(",", ""))
        return "numeric_string"
    except ValueError:
        return "text"


def iter_process_tables():
    """Yield dicts describing each readable PROCESS_LOG_TABLE sheet."""
    for p in source_xlsx_files():
        res = load_workbook_cached(p)
        if res is None:
            continue
        folder = p.parent.name
        for sp, rows in res:
            if sp.kind != "PROCESS_LOG_TABLE":
                continue
            yield {
                "path": p, "file_rel": rel(p), "folder": folder,
                "equipment": equipment_from_folder(folder),
                "month_label": month_label_from_filename(p.name),
                "sheet": sp, "rows": rows,
            }


def table_frame(t) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Return (raw object frame of data rows incl. col A, parsed timestamp series, ts format labels)."""
    sp: SheetParse = t["sheet"]
    data = t["rows"][sp.data_start_row - 1: sp.data_end_row]
    ncol = sp.max_col
    data = [tuple(r) + (None,) * (ncol - len(r)) for r in data]
    df = pd.DataFrame(data, columns=[c.col_letter for c in sp.columns], dtype=object)
    parsed = [parse_ts(v) for v in df.iloc[:, 0]]
    ts = pd.Series([p[0] for p in parsed], dtype="datetime64[ns]")
    fmts = [p[1] for p in parsed]
    return df, ts, fmts


def numeric_series(s: pd.Series) -> pd.Series:
    """Native numeric cells only (numeric strings are NOT coerced; they are reported separately)."""
    def f(v):
        if isinstance(v, bool):
            return np.nan
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v)
        return np.nan
    return pd.to_numeric(s.map(f), errors="coerce").astype(float)


def dataset_frames():
    """Group readable tables by equipment; returns {equipment: [table dicts sorted by first ts]}."""
    out: dict[str, list] = {}
    for t in iter_process_tables():
        out.setdefault(t["equipment"], []).append(t)
    return out


def load_dataset(tables: list) -> tuple[pd.DataFrame, dict]:
    """Concatenate monthly tables of one equipment into a numeric frame indexed by row order.

    Columns are keyed by column letter. Returns (frame with 'ts','src_file' + numeric columns, colmeta)
    Column meta is taken per letter from the first file; header consistency is checked elsewhere.
    """
    key = hashlib.md5("|".join(sorted(t["file_rel"] for t in tables)).encode()).hexdigest()[:12]
    cp = CACHE_DIR / f"dataset_{key}.pkl"
    if cp.exists():
        with open(cp, "rb") as fh:
            return pickle.load(fh)
    frames = []
    meta = {}
    for t in tables:
        df, ts, _ = table_frame(t)
        num = pd.DataFrame({c: numeric_series(df[c]) for c in df.columns[1:]})
        num.insert(0, "ts", ts.values)
        num.insert(1, "src_file", t["file_rel"])
        frames.append(num)
        for c in t["sheet"].columns[1:]:
            meta.setdefault(c.col_letter, c)
    full = pd.concat(frames, ignore_index=True)
    full = full.sort_values(["ts"], kind="stable").reset_index(drop=True)
    with open(cp, "wb") as fh:
        pickle.dump((full, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    return full, meta


def jdump(o) -> str:
    return json.dumps(o, default=str, ensure_ascii=False)
