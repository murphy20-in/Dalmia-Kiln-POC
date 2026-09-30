"""Plant event annotation store (SQLite, stdlib) with an append-only audit trail.

Plant annotations are PLANT_SUPPLIED ground-truth candidates. They are kept apart from every analytical label: no
column here is ever written from the risk score or the Phase 6 periods, and the analytical layer never sets
event_type. The database enforces what it can (enums, timestamp format, start < end, label origin, immutable identity
and creation fields, version + 1 per update, no resurrection, no hard delete or REPLACE, append-only audit);
validate() enforces the rest before anything reaches SQL. Every mutation and its audit row share one transaction.

Timestamps: event start / end are timezone-naive plant-local times in the historian clock (YYYY-MM-DDTHH:MM:SS). An
offset or 'Z' is rejected, never converted. created_at / updated_at / audit times are server UTC with 'Z'.

Interval rule (one rule everywhere, see overlaps()): an annotation with an end_time is the half-open interval
[start_time, end_time); one without end_time is the instant start_time.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVENT_TYPES = ("COATING", "RING", "DEPOSIT", "CLEANING", "MAINTENANCE", "STOPPAGE", "FEED_REDUCTION",
               "ANALYSER_CALIBRATION", "PROCESS_UPSET", "OTHER")
SOURCES = ("PLANT_LOG", "SHIFT_REPORT", "MAINTENANCE_RECORD", "INSPECTION", "OPERATOR_RECALL", "OTHER")
SEVERITIES = ("MINOR", "MODERATE", "MAJOR")
CONFIRMATIONS = ("CONFIRMED", "PROBABLE", "UNCONFIRMED")
TIME_PRECISIONS = ("EXACT", "WITHIN_HOUR", "WITHIN_SHIFT", "WITHIN_DAY")
TIME_BASES = ("OBSERVED", "ESTIMATED_ONSET", "REPORTED")
ENTRY_KINDS = ("CONTEMPORANEOUS", "RETROSPECTIVE")
STATUSES = ("ACTIVE", "DELETED")
ENUMS = {"event_type": EVENT_TYPES, "source": SOURCES, "severity": SEVERITIES, "plant_confirmation": CONFIRMATIONS,
         "time_precision": TIME_PRECISIONS, "time_basis": TIME_BASES, "entry_kind": ENTRY_KINDS}
MUTABLE = ("event_type", "start_time", "end_time", "equipment", "description", "source", "source_reference",
           "severity", "plant_confirmation", "time_precision", "time_basis", "entry_kind",
           "annotator_viewed_risk_score")
REQUIRED = ("event_type", "start_time", "description", "source")
MAX_LEN = {"description": 2000, "equipment": 100, "source_reference": 200}
TS_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}")
TS_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
ACTOR_RE = re.compile(r"[A-Za-z0-9 ._@-]{1,100}")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TIMESTAMP_BASIS = "PLANT_LOCAL_NAIVE (same clock as the historian export; no timezone)"
LABEL_ORIGIN = "PLANT_SUPPLIED"
SCHEMA_VERSION = 1


def _enum(xs) -> str:
    return ",".join(f"'{x}'" for x in xs)


def _opt_enum(col: str) -> str:
    return f"{col} TEXT CHECK ({col} IS NULL OR {col} IN ({_enum(ENUMS[col])}))"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS plant_events (
  event_id          TEXT PRIMARY KEY,
  event_type        TEXT NOT NULL CHECK (event_type IN ({_enum(EVENT_TYPES)})),
  start_time        TEXT NOT NULL CHECK (start_time GLOB '{TS_GLOB}'),
  end_time          TEXT CHECK (end_time IS NULL OR (end_time GLOB '{TS_GLOB}' AND end_time > start_time)),
  timestamp_basis   TEXT NOT NULL,
  equipment         TEXT,
  description       TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
  source            TEXT NOT NULL CHECK (source IN ({_enum(SOURCES)})),
  source_reference  TEXT,
  {_opt_enum("severity")},
  {_opt_enum("plant_confirmation")},
  {_opt_enum("time_precision")},
  {_opt_enum("time_basis")},
  {_opt_enum("entry_kind")},
  annotator_viewed_risk_score INTEGER CHECK (annotator_viewed_risk_score IS NULL OR annotator_viewed_risk_score IN (0, 1)),
  label_origin      TEXT NOT NULL CHECK (label_origin = '{LABEL_ORIGIN}'),
  status            TEXT NOT NULL CHECK (status IN ({_enum(STATUSES)})),
  version           INTEGER NOT NULL CHECK (version >= 1),
  created_at        TEXT NOT NULL,
  created_by        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  updated_by        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_plant_events_window ON plant_events (status, start_time, end_time);
CREATE INDEX IF NOT EXISTS ix_plant_events_type ON plant_events (status, event_type, start_time);
CREATE TABLE IF NOT EXISTS plant_event_audit (
  audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id   TEXT NOT NULL REFERENCES plant_events (event_id),
  operation  TEXT NOT NULL CHECK (operation IN ('CREATE', 'UPDATE', 'DELETE')),
  at         TEXT NOT NULL,
  actor      TEXT NOT NULL,
  old_value  TEXT,
  new_value  TEXT
);
CREATE INDEX IF NOT EXISTS ix_plant_event_audit_event ON plant_event_audit (event_id, audit_id);
CREATE TRIGGER IF NOT EXISTS audit_append_only_u BEFORE UPDATE ON plant_event_audit
  BEGIN SELECT RAISE(ABORT, 'plant_event_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_append_only_d BEFORE DELETE ON plant_event_audit
  BEGIN SELECT RAISE(ABORT, 'plant_event_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_soft_delete_only BEFORE DELETE ON plant_events
  BEGIN SELECT RAISE(ABORT, 'plant_events are soft-deleted only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_replace BEFORE INSERT ON plant_events
  WHEN EXISTS (SELECT 1 FROM plant_events WHERE event_id = NEW.event_id)
  BEGIN SELECT RAISE(ABORT, 'plant_events rows are never replaced'); END;
CREATE TRIGGER IF NOT EXISTS events_update_guard BEFORE UPDATE ON plant_events
  WHEN NEW.event_id IS NOT OLD.event_id OR NEW.created_at IS NOT OLD.created_at
    OR NEW.created_by IS NOT OLD.created_by OR NEW.timestamp_basis IS NOT OLD.timestamp_basis
    OR OLD.status = 'DELETED' OR NEW.version IS NOT OLD.version + 1
  BEGIN SELECT RAISE(ABORT, 'immutable field, resurrection or version skip on plant_events'); END;
"""


class EventError(Exception):
    """A client-safe error: status 404 / 409 / 422 / 503, message, details, optional error code override."""

    def __init__(self, status: int, message: str, details: list | None = None, code: str | None = None):
        super().__init__(message)
        self.status, self.message, self.details, self.code = status, message, details or [], code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def check_ts(v) -> str | None:
    """Exact YYYY-MM-DDTHH:MM:SS, calendar-valid, no offset. Returns an issue string or None. Never corrects."""
    if not isinstance(v, str):
        return "must be a string YYYY-MM-DDTHH:MM:SS"
    if not TS_RE.fullmatch(v):
        if TS_RE.match(v) and v[19:].startswith(("Z", "+", "-")):
            return "timezone offsets are not accepted: give naive plant-local time (the historian clock has no timezone)"
        return "must be YYYY-MM-DDTHH:MM:SS"
    try:
        datetime.fromisoformat(v)
    except ValueError:
        return "not a valid calendar date / time"
    return None


def overlaps(s1: str, e1: str | None, s2: str, e2: str | None) -> bool:
    """[s, e) intervals; e None = the instant s. Instants overlap an interval if s <= t < e, and each other if equal."""
    return (s1 < e2 if e2 else s1 <= s2) and (s2 < e1 if e1 else s2 <= s1)


# the same rule in SQL for a stored row against bound (:s, :e); :e may be NULL (an instant)
SQL_OVERLAP = ("((:e IS NOT NULL AND start_time < :e) OR (:e IS NULL AND start_time <= :s)) AND "
               "((end_time IS NOT NULL AND :s < end_time) OR (end_time IS NULL AND :s <= start_time))")


def valid_actor(a) -> bool:
    return isinstance(a, str) and bool(ACTOR_RE.fullmatch(a)) and a.strip() == a


def validate(payload, current: dict | None = None) -> dict:
    """Create (current None) or PATCH (merged onto current). Returns the full validated field set."""
    if not isinstance(payload, dict):
        raise EventError(422, "request body must be a JSON object")
    allowed = set(MUTABLE) | ({"expected_version"} if current is not None else set())
    issues = [{"field": k, "issue": "unknown or server-controlled field"} for k in sorted(set(payload) - allowed)]
    rec = {k: (current or {}).get(k) for k in MUTABLE}
    rec.update({k: v for k, v in payload.items() if k in MUTABLE})
    for k in REQUIRED:
        if rec.get(k) in (None, ""):
            issues.append({"field": k, "issue": "required"})
    for k, vals in ENUMS.items():
        if rec.get(k) is not None and rec[k] not in vals:
            issues.append({"field": k, "issue": f"must be one of {list(vals)}"})
    v = rec.get("annotator_viewed_risk_score")
    if v is not None and not isinstance(v, bool):
        issues.append({"field": "annotator_viewed_risk_score", "issue": "must be true, false or null"})
    for k in ("description", "equipment", "source_reference"):
        v = rec.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            issues.append({"field": k, "issue": "must be a string"})
        elif not v.strip() or len(v) > MAX_LEN[k]:
            issues.append({"field": k, "issue": f"must be 1-{MAX_LEN[k]} characters and not blank"})
        elif CTRL_RE.search(v) or (k != "description" and any(ch in v for ch in "\n\t\r")):
            issues.append({"field": k, "issue": "control characters are not allowed"})
    for k in ("start_time", "end_time"):
        if rec.get(k) is not None and (msg := check_ts(rec[k])):
            issues.append({"field": k, "issue": msg})
    if not issues and rec.get("end_time") is not None and rec["end_time"] <= rec["start_time"]:
        issues.append({"field": "end_time", "issue": "must be later than start_time (not corrected)"})
    if current is not None:
        ev = payload.get("expected_version")
        if ev is None:
            issues.append({"field": "expected_version", "issue": "required for PATCH (optimistic concurrency)"})
        elif not isinstance(ev, int) or isinstance(ev, bool):
            issues.append({"field": "expected_version", "issue": "must be an integer"})
        elif not issues and all(rec[k] == current.get(k) for k in MUTABLE):
            issues.append({"field": "*", "issue": "no field changes: nothing to update"})
    if issues:
        raise EventError(422, "event annotation failed validation", issues)
    return rec


def _db(v):
    return int(v) if isinstance(v, bool) else v


def _out(row: dict) -> dict:
    v = row.get("annotator_viewed_risk_score")
    return {**row, "annotator_viewed_risk_score": None if v is None else bool(v)}


class EventStore:
    """One short-lived connection per operation: no shared mutable connection state between requests."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._conn()
        try:
            found = c.execute("PRAGMA user_version").fetchone()[0]
            if found > SCHEMA_VERSION:
                raise RuntimeError(f"event store schema v{found} is newer than this code (v{SCHEMA_VERSION})")
            c.executescript(SCHEMA)          # v0 -> v1; future versions add numbered migrations here
            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            c.execute("PRAGMA journal_mode = WAL")
        finally:
            c.close()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    @contextlib.contextmanager
    def _session(self, write: bool):
        """One connection and one transaction (BEGIN IMMEDIATE serialises writers). Lock timeouts become 503."""
        c = None
        try:
            c = self._conn()
            c.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield c
                c.execute("COMMIT")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    c.execute("ROLLBACK")
                raise
        except sqlite3.OperationalError as e:
            raise EventError(503, "event store busy or unavailable; retry", code="EVENT_STORE_UNAVAILABLE") from e
        finally:
            if c is not None:
                c.close()

    def ping(self) -> bool:
        with self._session(False) as c:
            return c.execute("SELECT 1").fetchone() is not None

    def get(self, event_id: str) -> dict:
        row = None
        if ID_RE.fullmatch(event_id or ""):
            with self._session(False) as c:
                row = c.execute("SELECT * FROM plant_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise EventError(404, "event not found")
        return _out(dict(row))

    def list(self, *, status: str, event_type: str | None, start: str | None, end: str | None, limit: int,
             offset: int) -> tuple[list[dict], int]:
        """Annotations overlapping the query window [start, end) under overlaps(). Stable order; one snapshot."""
        where, args = [], {"lim": limit, "off": offset}
        if status != "ALL":
            where.append("status = :status")
            args["status"] = status
        if event_type:
            where.append("event_type = :type")
            args["type"] = event_type
        if end:
            where.append("start_time < :qe")
            args["qe"] = end
        if start:
            where.append("((end_time IS NOT NULL AND end_time > :qs) OR start_time >= :qs)")
            args["qs"] = start
        w = f"WHERE {' AND '.join(where)}" if where else ""
        with self._session(False) as c:
            total = c.execute(f"SELECT count(*) FROM plant_events {w}", args).fetchone()[0]
            rows = c.execute(f"SELECT * FROM plant_events {w} ORDER BY start_time, event_id LIMIT :lim OFFSET :off",
                             args).fetchall()
        return [_out(dict(r)) for r in rows], total

    def audit(self, event_id: str) -> list[dict]:
        self.get(event_id)
        with self._session(False) as c:
            rows = c.execute("SELECT audit_id, event_id, operation, at, actor, old_value, new_value "
                             "FROM plant_event_audit WHERE event_id = ? ORDER BY audit_id", (event_id,)).fetchall()
        return [{**dict(r), "old_value": json.loads(r["old_value"]) if r["old_value"] else None,
                 "new_value": json.loads(r["new_value"]) if r["new_value"] else None} for r in rows]

    def counts(self) -> dict:
        with self._session(False) as c:
            by = c.execute("SELECT event_type, count(*) FROM plant_events WHERE status = 'ACTIVE' "
                           "GROUP BY event_type ORDER BY event_type").fetchall()
        return {"active_total": sum(n for _, n in by), "active_by_type": {t: n for t, n in by}}

    @staticmethod
    def _conflicts(c, rec: dict, exclude: str | None) -> list[str]:
        """Likely duplicate entries: ACTIVE annotations of the same type, equipment (case- and space-insensitive) and
        source whose windows overlap. A second source for the same event (e.g. an inspection confirming a shift
        report) is allowed."""
        rows = c.execute(
            f"SELECT event_id FROM plant_events WHERE status = 'ACTIVE' AND event_type = :t AND source = :src AND "
            f"lower(trim(COALESCE(equipment, ''))) = lower(trim(COALESCE(:eq, ''))) AND event_id != :x AND "
            f"{SQL_OVERLAP} ORDER BY event_id",
            {"t": rec["event_type"], "src": rec["source"], "eq": rec.get("equipment"), "x": exclude or "",
             "s": rec["start_time"], "e": rec.get("end_time")})
        return [r[0] for r in rows]

    @staticmethod
    def _audit(c, event_id, op, actor, at, old, new) -> None:
        c.execute("INSERT INTO plant_event_audit (event_id, operation, at, actor, old_value, new_value) "
                  "VALUES (?, ?, ?, ?, ?, ?)",
                  (event_id, op, at, actor, json.dumps(_out(old), sort_keys=True) if old else None,
                   json.dumps(_out(new), sort_keys=True) if new else None))

    def create(self, payload, actor: str) -> dict:
        rec = {k: _db(v) for k, v in validate(payload).items()}
        at = _now()
        row = {"event_id": str(uuid.uuid4()), **rec, "timestamp_basis": TIMESTAMP_BASIS, "label_origin": LABEL_ORIGIN,
               "status": "ACTIVE", "version": 1, "created_at": at, "created_by": actor, "updated_at": at,
               "updated_by": actor}
        with self._session(True) as c:
            if dup := self._conflicts(c, rec, None):
                raise EventError(409, "an active annotation of the same type, equipment and source overlaps this "
                                      "window", [{"conflicting_event_ids": dup}])
            c.execute(f"INSERT INTO plant_events ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                      list(row.values()))
            self._audit(c, row["event_id"], "CREATE", actor, at, None, row)
        return _out(row)

    def _mutate(self, event_id: str, actor: str, payload: dict | None, expected) -> dict:
        """payload None = soft delete. Both need the caller's expected_version."""
        if not ID_RE.fullmatch(event_id or ""):
            raise EventError(404, "event not found")
        at = _now()
        with self._session(True) as c:
            r = c.execute("SELECT * FROM plant_events WHERE event_id = ?", (event_id,)).fetchone()
            if r is None:
                raise EventError(404, "event not found")
            old = dict(r)
            if old["status"] == "DELETED":
                raise EventError(409, "event is deleted; deleted annotations are not modified")
            if payload is not None:
                rec = {k: _db(v) for k, v in validate(payload, _out(old)).items()}
                expected = payload["expected_version"]
            else:
                rec = {"status": "DELETED"}
            if expected != old["version"]:
                raise EventError(409, "version conflict: the event changed since it was read",
                                 [{"current_version": old["version"]}])
            if payload is not None and (dup := self._conflicts(c, rec, event_id)):
                raise EventError(409, "an active annotation of the same type, equipment and source overlaps this "
                                      "window", [{"conflicting_event_ids": dup}])
            new = {**old, **rec, "version": old["version"] + 1, "updated_at": at, "updated_by": actor}
            sets = [k for k in new if k != "event_id"]
            c.execute(f"UPDATE plant_events SET {', '.join(f'{k} = ?' for k in sets)} WHERE event_id = ?",
                      [new[k] for k in sets] + [event_id])
            self._audit(c, event_id, "UPDATE" if payload is not None else "DELETE", actor, at, old, new)
        return _out(new)

    def update(self, event_id: str, payload, actor: str) -> dict:
        return self._mutate(event_id, actor, payload, None)

    def delete(self, event_id: str, actor: str, expected_version: int) -> dict:
        return self._mutate(event_id, actor, None, expected_version)
