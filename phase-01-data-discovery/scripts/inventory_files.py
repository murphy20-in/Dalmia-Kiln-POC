"""Objective A - recursive file inventory of the source data root (read-only).

Also lists supporting material located next to the data root (problem statement,
notes, archive) with scope=SUPPORTING so every supplied file is accounted for.
Outputs: outputs/file_inventory.csv
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from common import SOURCE_ROOT, SUPPORTING_ROOT, sha256, write_csv, equipment_from_folder, month_label_from_filename, month_num_from_label

TEMP_RX = re.compile(r"^(~\$|\.~lock|~)|\.(tmp|temp|bak|old|swp)$", re.I)
BACKUP_RX = re.compile(r"(copy|backup|bkp|\(\d+\)|_old|_v\d+)", re.I)
PERSONAL_ROOT_SKIP = {"Dalmia-Kiln-POC"}  # our own work area, not supplied data


def zip_diagnostics(p: Path) -> dict:
    """Structural check of an OOXML (zip) container without modifying it."""
    d = {"zip_valid": False, "zip_members": None, "zip_diagnostic": ""}
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            d["zip_valid"] = True
            d["zip_members"] = len(names)
            trash = [n for n in names if n.startswith("[trash]")]
            if trash:
                d["zip_diagnostic"] = f"contains {len(trash)} '[trash]' parts (Office editing residue)"
            return d
    except Exception as e:  # corrupt container: describe what is physically present
        data = p.read_bytes()
        tail_zero = len(data) - len(data.rstrip(b"\x00"))
        local = []
        for m in re.finditer(rb"PK\x03\x04", data):
            i = m.start()
            n = int.from_bytes(data[i + 26:i + 28], "little")
            local.append(data[i + 30:i + 30 + n].decode("latin-1"))
        d["zip_diagnostic"] = (
            f"{type(e).__name__}: {e}. End-of-central-directory missing; "
            f"{tail_zero:,} of {len(data):,} bytes ({tail_zero / len(data):.1%}) are trailing zero bytes; "
            f"local entries physically present: {local}. "
            "Sheet XML is truncated and xl/sharedStrings.xml (all header text) is absent -> workbook NOT READABLE; "
            "not reconstructed in Phase 1."
        )
        return d


def classify(p: Path) -> str:
    ext = p.suffix.lower()
    return {
        ".xlsx": "EXCEL_OOXML_WORKBOOK", ".xlsm": "EXCEL_MACRO_WORKBOOK", ".xls": "EXCEL_LEGACY_WORKBOOK",
        ".csv": "CSV", ".txt": "TEXT", ".pdf": "PDF", ".md": "MARKDOWN", ".zip": "ZIP_ARCHIVE",
    }.get(ext, "OTHER/UNSUPPORTED")


def record(p: Path, scope: str, base: Path) -> dict:
    st = p.stat()
    ftype = classify(p)
    r = {
        "scope": scope,
        "absolute_path": str(p),
        "relative_path": str(p.relative_to(base)),
        "parent_folder": p.parent.name,
        "filename": p.name,
        "extension": p.suffix.lower(),
        "file_size_bytes": st.st_size,
        "file_size_mb": round(st.st_size / 1e6, 3),
        "modified_time": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "file_type": ftype,
        "is_hidden": p.name.startswith("."),
        "is_empty": st.st_size == 0,
        "is_temp_candidate": bool(TEMP_RX.search(p.name)),
        "is_backup_candidate": bool(BACKUP_RX.search(p.stem)),
        "is_workbook": ftype.startswith("EXCEL"),
        "sha256": sha256(p),
        "equipment_from_folder": equipment_from_folder(p.parent.name) if scope == "SOURCE_DATA" else "",
        "month_label_in_filename": month_label_from_filename(p.name) if ftype.startswith("EXCEL") else "",
    }
    r["month_number_from_filename"] = month_num_from_label(r["month_label_in_filename"]) if r["month_label_in_filename"] else None
    if ftype.startswith("EXCEL"):
        r.update(zip_diagnostics(p))
        r["readable"] = r["zip_valid"]
    elif ftype == "ZIP_ARCHIVE":
        try:
            with zipfile.ZipFile(p) as z:
                r["zip_valid"], r["zip_members"] = True, len(z.namelist())
            r["readable"] = True
        except Exception as e:
            r["zip_valid"], r["readable"], r["zip_diagnostic"] = False, False, str(e)
    else:
        r["readable"] = True
    return r


def archive_crosscheck(zip_path: Path, df: pd.DataFrame) -> list[dict]:
    """Compare members of the supplied archive against extracted source files (hash)."""
    notes = []
    by_rel = {Path(r).as_posix(): h for r, h in zip(df.loc[df.scope == "SOURCE_DATA", "relative_path"], df.loc[df.scope == "SOURCE_DATA", "sha256"])}
    import hashlib
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            key = name.split("AI Automation(Kiln)/", 1)[1] if "AI Automation(Kiln)/" in name else None
            h = hashlib.sha256()
            with z.open(info) as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
            hx = h.hexdigest()
            same = df.loc[df.sha256 == hx, "absolute_path"].tolist()
            notes.append({"archive_member": name, "size": info.file_size, "sha256": hx,
                          "matches_extracted_source": (key in by_rel and by_rel[key] == hx) if key else None,
                          "extracted_counterpart": key or "",
                          "byte_identical_files_on_disk": "; ".join(same)})
    return notes


def main():
    rows = [record(p, "SOURCE_DATA", SOURCE_ROOT) for p in sorted(SOURCE_ROOT.rglob("*")) if p.is_file()]
    # supporting files beside the data root (excluding the source tree itself and our work area)
    for p in sorted(SUPPORTING_ROOT.rglob("*")):
        if not p.is_file():
            continue
        if SOURCE_ROOT in p.parents or any(part in PERSONAL_ROOT_SKIP for part in p.relative_to(SUPPORTING_ROOT).parts):
            continue
        rows.append(record(p, "SUPPORTING", SUPPORTING_ROOT))
    df = pd.DataFrame(rows)
    # duplicates by content hash
    dup = df.groupby("sha256")["relative_path"].transform("count")
    df["duplicate_group_size"] = dup
    df["duplicate_of"] = df.apply(lambda r: "; ".join(x for x in df.loc[df.sha256 == r.sha256, "relative_path"] if x != r.relative_path), axis=1)
    # month label vs expected set per folder
    df["processing_status"] = df.apply(
        lambda r: ("NOT_READABLE_CORRUPT" if (r.is_workbook and not r.readable) else
                   "PROCESS_LOG_WORKBOOK" if r.is_workbook and r.scope == "SOURCE_DATA" else
                   "SUPPORTING_DOCUMENT" if r.scope == "SUPPORTING" else "OTHER"), axis=1)
    # archive cross-check
    for p in df.loc[df.file_type == "ZIP_ARCHIVE", "absolute_path"]:
        members = pd.DataFrame(archive_crosscheck(Path(p), df))
        write_csv(members, "archive_member_crosscheck.csv")
        n_match = int(members.matches_extracted_source.fillna(False).sum())
        extra = members.loc[members.extracted_counterpart == "", "archive_member"].tolist()
        df.loc[df.absolute_path == p, "zip_diagnostic"] = (
            f"{len(members)} members; {n_match} byte-identical to extracted source files; "
            f"members outside data root: {extra}")
    write_csv(df, "file_inventory.csv")


if __name__ == "__main__":
    main()
