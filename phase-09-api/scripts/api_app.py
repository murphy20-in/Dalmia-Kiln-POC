"""Phase 9 read-only analytical service + plant event annotation API (stdlib WSGI; no framework dependency).

    ../../.venv/bin/python -B api_app.py            # serves on 127.0.0.1:8009 (DALMIA_KILN_API_HOST / _PORT)

ROUTES is the single source of truth: dispatch, the 404 / 405 split and the generated route contract
(outputs/api_contract.json, written by run_phase9.py) all read it. There is deliberately no prediction, alert, alarm,
probability, forecast or live-warning route, and no route takes a filesystem path.

Every analytical response carries `provenance` and a fixed `interpretation` block (is_prediction / is_alert /
is_probability all false). Errors are {"error": {code, message, request_id, details}} with no stack trace or path.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import parse_qsl
from wsgiref.simple_server import WSGIRequestHandler, make_server

sys.dont_write_bytecode = True

import artifact_store as ast_  # noqa: E402
import event_store as evs  # noqa: E402
from p9common import API_PREFIX, MANIFEST_FILE, VERSION, ServiceConfig, count, dumps  # noqa: E402

log = logging.getLogger("p9.api")

ERROR_CODES = {400: "INVALID_REQUEST", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT",
               413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE", 422: "VALIDATION_ERROR",
               500: "INTERNAL_ERROR", 503: "ANALYTICAL_ARTIFACT_UNAVAILABLE"}
INTERPRETATION = {"is_prediction": False, "is_alert": False, "is_probability": False, "is_live": False,
                  "is_retrospective": True, "early_warning_supported": False, "event_ground_truth_available": False}
EVENT_INTERPRETATION = {"is_plant_supplied": True, "is_analytical_label": False, "is_prediction": False,
                        "is_alert": False}
VARIANTS = {
    "primary": {"variant": "primary", "phase8_variant": "PRIMARY", "variant_status": "PRIMARY_FROZEN_SCORE",
                "is_default": True, "preferred": False},
    "o2_excluded": {"variant": "o2_excluded", "phase8_variant": "EXCLUDE_KILN_INLET_O2_ANALYSER",
                    "variant_status": "SENSITIVITY_ANALYSIS", "is_default": False, "preferred": False,
                    "attributes_not_defined": ["reference_relative_band", "confidence", "reasons", "components"]},
}
PREFERENCE_NOTE = ("Phase 8: neither variant is preferred until the plant explains the Kiln-I!X analyser; the "
                   "O2-excluded variant never substitutes for the primary score")


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: list | None = None, headers: list | None = None):
        super().__init__(message)
        self.status, self.message, self.details, self.headers = status, message, details or [], headers or []


# ============================================================================== query parameters
@dataclass(frozen=True)
class P:
    kind: str                      # ts | int | enum
    doc: str
    default: object = None
    lo: int = 0
    hi: int = 0
    values: tuple = ()


def _parse_value(raw: str, p: P):
    if p.kind == "ts":
        if msg := evs.check_ts(raw):
            raise ApiError(400, f"invalid timestamp: {msg}")
        return raw
    if p.kind == "int":
        if not re.fullmatch(r"[0-9]{1,9}", raw) or not (p.lo <= int(raw) <= p.hi):
            raise ApiError(400, f"must be an integer in [{p.lo}, {p.hi}]")
        return int(raw)
    if raw not in p.values:
        raise ApiError(400, f"must be one of {list(p.values)}")
    return raw


def parse_query(qs: str, spec: dict[str, P]) -> dict:
    """Unknown, repeated or empty parameters are errors: an invalid filter is never read as 'all'."""
    try:
        pairs = parse_qsl(qs, keep_blank_values=True, strict_parsing=bool(qs), max_num_fields=20)
    except ValueError:
        raise ApiError(400, "malformed query string")
    seen, issues = set(), []
    for k, v in pairs:
        if k not in spec:
            issues.append({"param": k[:40], "issue": "unknown parameter (not interpreted as 'all')"})
        elif k in seen:
            issues.append({"param": k, "issue": "repeated parameter"})
        elif v == "":
            issues.append({"param": k, "issue": "empty value"})
        seen.add(k)
    if issues:
        raise ApiError(400, "invalid query parameters", issues)
    given, out = dict(pairs), {}
    for k, p in spec.items():
        try:
            out[k] = _parse_value(given[k], p) if k in given else p.default
        except ApiError as e:
            raise ApiError(400, "invalid query parameters", [{"param": k, "issue": e.message}])
    if out.get("start") and out.get("end") and out["start"] >= out["end"]:
        raise ApiError(422, "start must be earlier than end", [{"param": "end", "issue": "end <= start"}])
    return out


WINDOW = {"start": P("ts", "inclusive lower bound, YYYY-MM-DDTHH:MM:SS (naive plant-local, no offset)"),
          "end": P("ts", "exclusive upper bound, YYYY-MM-DDTHH:MM:SS (naive plant-local, no offset)")}


def paging(default: int, hi: int) -> dict:
    return {"limit": P("int", f"page size (default {default}, max {hi})", default, 1, hi),
            "offset": P("int", "rows to skip (default 0)", 0, 0, 10 ** 8)}


def _pagination(q: dict, returned: int, total: int) -> dict:
    more = q["offset"] + returned < total
    return {"limit": q["limit"], "offset": q["offset"], "total": total, "returned": returned, "has_more": more,
            "next_offset": q["offset"] + returned if more else None}


GAP_RULE = ("rows exist only for operational 10-min buckets; consecutive timestamps more than 10 min apart are a "
            "gap (stop, missing data or non-operational time): break the line there, never interpolate")


def gaps(rows: list[dict]) -> list[list[str]]:
    """[previous timestamp, next timestamp] for every step > 10 min inside the returned rows."""
    from datetime import datetime as dt
    ts = [dt.fromisoformat(r["timestamp"]) for r in rows]
    return [[rows[i - 1]["timestamp"], rows[i]["timestamp"]] for i in range(1, len(ts))
            if (ts[i] - ts[i - 1]).total_seconds() > 600]


def page(rows, q) -> tuple[list, dict]:
    out = list(rows[q["offset"]:q["offset"] + q["limit"]])
    return out, _pagination(q, len(out), len(rows))


# ============================================================================== routes
@dataclass(frozen=True)
class Route:
    method: str
    template: str
    handler: str
    kind: str                      # ops | analytical | event
    summary: str
    params: dict = field(default_factory=dict)
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self):          # compiled once; matched with fullmatch (no trailing-newline match)
        object.__setattr__(self, "regex", re.compile(re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.template)))


V = API_PREFIX
ROUTES = (
    Route("GET", "/health", "health", "ops", "Process liveness only (says nothing about analytical artifacts)."),
    Route("GET", "/ready", "ready", "ops", "Analytical readiness: artifacts hash-verified and event store reachable."),
    Route("GET", f"{V}/metadata", "metadata", "analytical",
          "Project, phase, artifact versions, periods, analytical state flags and major caveats."),
    Route("GET", f"{V}/metadata/status", "status", "analytical",
          "Machine-readable analytical state, evidence status and revalidation readiness."),
    Route("GET", f"{V}/metadata/provenance", "provenance", "analytical",
          "Artifact manifest: source phase, version, SHA-256, analytical / operational status."),
    Route("GET", f"{V}/metadata/limitations", "limitations", "analytical",
          "Known data-quality and analytical limitations (none hidden)."),
    Route("GET", f"{V}/metadata/methodology", "methodology", "analytical",
          "Phase 7 score definition, reference-relative bands, feature inventory; Phase 6 / 8 definitions."),
    Route("GET", f"{V}/metadata/data-requirements", "data_requirements", "analytical",
          "Plant data still required for validation and open plant questions."),
    Route("GET", f"{V}/risk-scores", "risk_scores", "analytical",
          "Historical empirical POC risk score (operational rows only) for one explicit variant.",
          {**WINDOW, "variant": P("enum", "primary (default) | o2_excluded (sensitivity analysis)", "primary",
                                  values=("primary", "o2_excluded")),
           "operational_only": P("enum", "only 'true' is served (default true)", "true", values=("true", "false")),
           "reference_relative_band": P("enum", "primary only", values=("LOW", "ELEVATED", "HIGH")),
           "confidence_band": P("enum", "primary only", values=("LOW", "MEDIUM")),
           "score_row_status": P("enum", "primary only", values=("VALID", "VALID_REDUCED_CONFIDENCE")),
           **paging(1000, 5000)}),
    Route("GET", f"{V}/risk-scores/variant-comparison", "variant_comparison", "analytical",
          "Primary and O2-excluded historical scores side by side (explicitly labelled; no substitution).",
          {**WINDOW, **paging(1000, 5000)}),
    Route("GET", f"{V}/abnormal-periods", "abnormal_periods", "analytical",
          "The 12 Phase 6 KPI-derived empirical abnormal periods (not plant events).",
          {**WINDOW, "kpi_severity_class": P("enum", "filter", values=("LOW", "MODERATE", "HIGH")),
           **paging(100, 1000)}),
    Route("GET", f"{V}/validation/early-warning-historical", "validation", "analytical",
          "Phase 8 historical early-warning validation results (NOT_SUPPORTED); not a live warning service."),
    Route("GET", f"{V}/findings", "findings", "analytical",
          "Phase 8 findings with their evidence classifications (no aggregate score).",
          {"classification": P("enum", "filter", values=("SUPPORTED", "WEAK", "NOT_SUPPORTED", "INSUFFICIENT_DATA",
                                                          "BLOCKED")), **paging(100, 1000)}),
    Route("GET", f"{V}/events", "events_list", "event", "Plant event annotations (plant-supplied labels).",
          {**WINDOW, "event_type": P("enum", "filter", values=evs.EVENT_TYPES),
           "status": P("enum", "ACTIVE (default) | DELETED | ALL", "ACTIVE", values=("ACTIVE", "DELETED", "ALL")),
           **paging(100, 1000)}),
    Route("POST", f"{V}/events", "events_create", "event", "Create a plant event annotation (X-Actor header)."),
    Route("GET", f"{V}/events/{{event_id}}", "events_get", "event", "One plant event annotation."),
    Route("PATCH", f"{V}/events/{{event_id}}", "events_patch", "event",
          "Update an annotation; body must carry expected_version (X-Actor header)."),
    Route("DELETE", f"{V}/events/{{event_id}}", "events_delete", "event",
          "Soft-delete an annotation (X-Actor header; expected_version query required); history is kept.",
          {"expected_version": P("int", "required optimistic-concurrency check", None, 1, 10 ** 8)}),
    Route("GET", f"{V}/events/{{event_id}}/audit", "events_audit", "event",
          "Append-only audit history of one annotation."),
)


def route_contract() -> list[dict]:
    return [{"method": r.method, "path": r.template, "kind": r.kind, "summary": r.summary,
             "query_parameters": {k: {"type": p.kind, "doc": p.doc, "default": p.default,
                                      **({"values": list(p.values)} if p.values else {})}
                                  for k, p in r.params.items()}} for r in ROUTES]


# ============================================================================== request / app
@dataclass
class Req:
    method: str
    path: str
    qs: str
    environ: dict
    request_id: str
    params: dict = field(default_factory=dict)
    q: dict = field(default_factory=dict)
    log: dict = field(default_factory=dict)


class App:
    def __init__(self, cfg: ServiceConfig, manifest_path=MANIFEST_FILE):
        self.cfg = cfg
        t = time.perf_counter()
        self.store, self.store_error = None, None
        try:
            self.store = ast_.load_store(cfg.root, manifest_path)
        except ast_.ArtifactUnavailable as e:
            self.store_error = str(e)
            log.exception(json.dumps({"event": "artifacts_unavailable", "reason": self.store_error}))
        self.events = evs.EventStore(cfg.events_db)
        self.startup_seconds = time.perf_counter() - t
        log.info(json.dumps({"event": "startup", "service_version": VERSION, "startup_seconds":
                             round(self.startup_seconds, 3), "artifacts_ready": self.store is not None}))

    # ---------------------------------------------------------------- WSGI
    def __call__(self, environ, start_response):
        t0 = time.perf_counter()
        req = Req(environ.get("REQUEST_METHOD", "GET").upper(), environ.get("PATH_INFO", "") or "/",
                  environ.get("QUERY_STRING", ""), environ, uuid.uuid4().hex)
        headers = []
        try:
            status, body = self.dispatch(req)
        except ApiError as e:
            status, body, headers = e.status, self._error(e.status, e.message, req, e.details), e.headers
        except evs.EventError as e:
            status, body = e.status, self._error(e.status, e.message, req, e.details, e.code)
        except Exception:                       # noqa: BLE001  never leak a stack trace or path to the client
            log.exception(json.dumps({"event": "unhandled_error", "request_id": req.request_id}))
            status, body = 500, self._error(500, "internal error", req)
        payload = dumps(body)
        start_response(f"{status} {HTTPStatus(status).phrase}",
                       [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload))),
                        ("X-Request-ID", req.request_id), ("X-Content-Type-Options", "nosniff"),
                        ("Cache-Control", "no-store"), *headers])
        log.info(json.dumps({"event": "request", "request_id": req.request_id,
                             "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                             "method": req.method, "path": req.path[:200], "status": status,
                             "duration_ms": round((time.perf_counter() - t0) * 1000, 2), **req.log},
                            sort_keys=True))
        return [payload]

    @staticmethod
    def _error(status: int, message: str, req: Req, details: list | None = None, code: str | None = None) -> dict:
        return {"error": {"code": code or ERROR_CODES.get(status, "INVALID_REQUEST"), "message": message,
                          "request_id": req.request_id, "details": details or []}}

    def dispatch(self, req: Req) -> tuple[int, dict]:
        allowed = []
        for r in ROUTES:
            m = r.regex.fullmatch(req.path)
            if not m:
                continue
            if r.method != req.method:
                allowed.append(r.method)
                continue
            req.params = m.groupdict()
            req.q = parse_query(req.qs, r.params)
            if r.kind == "analytical" and self.store is None:
                raise ApiError(503, "analytical artifacts are unavailable or failed hash verification; see /ready")
            return getattr(self, r.handler)(req)
        if allowed:
            raise ApiError(405, "method not allowed", headers=[("Allow", ", ".join(sorted(set(allowed))))])
        raise ApiError(404, "no such endpoint (this API has no prediction, alert or probability routes)")

    # ---------------------------------------------------------------- helpers
    def _envelope(self, data, *, disclaimer: str, provenance, req: Req, pagination=None, extra=None) -> dict:
        body = {"api_version": "v1", "service_version": VERSION, "data": data, "provenance": provenance,
                "interpretation": INTERPRETATION, "disclaimer": disclaimer, "query": req.q}
        if pagination is not None:
            body["pagination"] = pagination
        return {**body, **(extra or {})}

    def _prov(self, key: str, **kw) -> dict:
        return {**self.store.provenance[key], **kw}

    def _body(self, req: Req) -> object:
        env = req.environ
        if not str(env.get("CONTENT_TYPE", "")).lower().startswith("application/json"):
            raise ApiError(415, "Content-Type must be application/json")
        raw_len = str(env.get("CONTENT_LENGTH") or "")
        if not raw_len.isdigit():
            raise ApiError(400, "Content-Length header required")
        if int(raw_len) > self.cfg.max_body_bytes:
            raise ApiError(413, f"request body exceeds {self.cfg.max_body_bytes} bytes")
        raw = env["wsgi.input"].read(int(raw_len))

        def no_dupes(pairs):
            keys = [k for k, _ in pairs]
            if len(keys) != len(set(keys)):
                raise ApiError(400, "duplicate JSON keys")
            return dict(pairs)

        def no_const(c):
            raise ApiError(400, f"non-standard JSON constant {c}")
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes, parse_constant=no_const)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise ApiError(400, "malformed JSON body")

    @staticmethod
    def _actor(req: Req) -> str:
        a = req.environ.get("HTTP_X_ACTOR")
        if not evs.valid_actor(a):
            raise ApiError(400, "X-Actor header required: 1-100 characters [A-Za-z0-9 ._@-] identifying the person "
                                "making the change (attribution only; no authentication in this POC)")
        return a

    # ---------------------------------------------------------------- ops
    def health(self, req: Req) -> tuple[int, dict]:
        return 200, {"status": "ok", "service_version": VERSION, "process": "healthy",
                     "note": "liveness only; analytical readiness is /ready"}

    def ready(self, req: Req) -> tuple[int, dict]:
        try:
            db_ok = self.events.ping()
        except Exception:                       # noqa: BLE001  reported as not ready, never raised to the client
            log.exception(json.dumps({"event": "event_store_unavailable", "request_id": req.request_id}))
            db_ok = False
        ok = self.store is not None and db_ok
        return (200 if ok else 503), {
            "ready": ok, "service_version": VERSION,
            "analytical_artifacts": "VERIFIED" if self.store is not None else "UNAVAILABLE",
            "analytical_artifacts_reason": self.store_error, "event_store": "OK" if db_ok else "UNAVAILABLE"}

    # ---------------------------------------------------------------- metadata
    def _validation_state(self) -> dict:
        v = self.store.validation["primary_endpoint"]["by_variant"]
        return {"phase8_primary_endpoint": v["primary"]["historical_validation_status"],
                "phase8_o2_excluded_variant": v["o2_excluded"]["historical_validation_status"],
                "o2_excluded_note": self.store.contract["evidence_status"]["phase8_o2_excluded_note"]}

    def metadata(self, req: Req) -> tuple[int, dict]:
        s, c = self.store, self.store.contract
        data = {"project": c["project"], "phase": c["phase"], "phase_name": c["phase_name"],
                "service_version": VERSION, "api_version": "v1",
                "artifact_versions": {a["key"]: a["version"] for a in s.manifest["artifacts"] if a["version"]},
                "periods": c["periods"], "analytical_state": c["analytical_state"],
                "validation_state": self._validation_state(),
                "event_ground_truth_status": "NOT_AVAILABLE", "alerting_status": "DISABLED",
                "prediction_status": "DISABLED",
                "major_caveats": [f"{x['topic']}: {x['detail']}" for x in c["limitations"] if x["status"] == "OPEN"],
                "endpoints": [f"{r.method} {r.template}" for r in ROUTES]}
        return 200, self._envelope(data, disclaimer=c["disclaimers"]["validation"], req=req,
                                   provenance=self._prov("analytical_contract"))

    def status(self, req: Req) -> tuple[int, dict]:
        c = self.store.contract
        counts = self.events.counts()
        data = {"analytical_state": c["analytical_state"],
                "evidence_status": {**c["evidence_status"], "from_phase8_artifacts": self._validation_state()},
                "ground_truth": {
                    "available": False,
                    "plant_annotations_recorded": counts["active_total"],
                    "plant_annotations_by_type": counts["active_by_type"],
                    "evaluable_event_count": 0,
                    "evaluable_event_count_basis": "no plant annotation has been assessed by the frozen Phase 8 "
                                                   "protocol; Phase 9 records annotations but never judges evaluability",
                    "minimum_recommended_for_revalidation":
                        c["revalidation"]["minimum_evaluable_events_for_revalidation"],
                    "threshold_meaning": c["revalidation"]["meaning"]},
                "artifacts": "VERIFIED"}
        return 200, self._envelope(data, disclaimer=c["disclaimers"]["validation"], req=req,
                                   provenance=self._prov("analytical_contract"))

    def provenance(self, req: Req) -> tuple[int, dict]:
        s = self.store
        data = {"artifacts": [{k: a[k] for k in ("key", "path", "source_phase", "version", "sha256", "bytes",
                                                 "analytical_status", "operational_status", "note",
                                                 "matches_phase8_validated_input")} for a in s.manifest["artifacts"]],
                "o2_excluded_materialisation": s.manifest["o2_excluded_materialisation"],
                "phase8_git_commit": s.manifest["phase8_git_commit"],
                "lineage": "endpoint -> artifact_store adapter -> artifact (SHA-256 above) -> producing phase",
                "path_note": "paths are repository-relative identifiers; no request can name a file"}
        return 200, self._envelope(data, disclaimer=s.contract["disclaimers"]["validation"], req=req,
                                   provenance=self._prov("analytical_contract"))

    def limitations(self, req: Req) -> tuple[int, dict]:
        s, c = self.store, self.store.contract
        rows = s.primary.rows
        data = {"limitations": c["limitations"], "missing_months": c["periods"]["missing_months"],
                "timestamp_semantics": c["periods"]["timestamp_semantics"],
                "operational_row_quality": {
                    "n_rows": len(rows),
                    "data_quality_status": count(r["data_quality"]["status"] for r in rows),
                    "o2_ambient_suspect_rows": sum(r["data_quality"]["o2_ambient_suspect"] for r in rows),
                    "confidence_band": count(r["confidence"]["band"] for r in rows)}}
        return 200, self._envelope(data, disclaimer=c["disclaimers"]["risk_score"], req=req,
                                   provenance=self._prov("analytical_contract"))

    def methodology(self, req: Req) -> tuple[int, dict]:
        keys = ("risk_score_reference", "risk_score_bands", "risk_score_feature_inventory")
        return 200, self._envelope(self.store.methodology, disclaimer=self.store.contract["disclaimers"]["risk_score"],
                                   req=req, provenance=[self._prov(k) for k in keys])

    def data_requirements(self, req: Req) -> tuple[int, dict]:
        c = self.store.contract
        data = {"plant_data_requirements": c["plant_data_requirements"],
                "plant_questions_open": c["plant_questions_open"], "prohibited_uses": c["prohibited_uses"],
                "revalidation": c["revalidation"]}
        return 200, self._envelope(data, disclaimer=c["disclaimers"]["events"], req=req,
                                   provenance=self._prov("analytical_contract"))

    # ---------------------------------------------------------------- analytical data
    def risk_scores(self, req: Req) -> tuple[int, dict]:
        q, s = req.q, self.store
        if q["operational_only"] != "true":
            raise ApiError(422, "only operational rows are served: non-operational Phase 7 rows and diagnostics "
                                "are not operational measurements",
                           [{"param": "operational_only", "issue": "must be true"}])
        variant = q["variant"]
        filters = {k: q[k] for k in ("reference_relative_band", "confidence_band", "score_row_status") if q[k]}
        if variant == "o2_excluded" and filters:
            raise ApiError(400, "filters not defined for the O2-excluded variant",
                           [{"param": k, "issue": "primary variant only"} for k in filters])
        series = s.primary if variant == "primary" else s.o2x
        rows = series.window(q["start"], q["end"])
        if filters:
            get = {"reference_relative_band": lambda r: r["reference_relative_band"],
                   "confidence_band": lambda r: r["confidence"]["band"],
                   "score_row_status": lambda r: r["score_row_status"]}
            rows = tuple(r for r in rows if all(get[k](r) == v for k, v in filters.items()))
        data, pg = page(rows, q)
        key = "risk_scores" if variant == "primary" else "o2_excluded_scores"
        supporting = ("risk_score_components", "risk_score_confidence", "risk_score_reasons") \
            if variant == "primary" else ("p8_o2_sensitivity",)
        req.log.update(artifact_version=s.provenance[key]["artifact_version"], variant=variant,
                       query_window=[q["start"], q["end"]], result_count=len(data))
        return 200, self._envelope(
            data, req=req, pagination=pg,
            disclaimer=s.contract["disclaimers"]["risk_score" if variant == "primary" else "o2_excluded"],
            provenance=self._prov(key, variant=variant, supporting_artifacts=[self._prov(k) for k in supporting]),
            extra={"variant": {**VARIANTS[variant], "preference_note": PREFERENCE_NOTE},
                   "window_semantics": "start <= timestamp < end; timestamp = 10-min bucket end, naive plant-local; "
                                       "no resampling, interpolation or gap filling",
                   "data_extent": {"first_timestamp": series.ts[0], "last_timestamp": series.ts[-1],
                                "n_rows": len(series.ts), "not_scored": s.contract["periods"]["missing_months"],
                                "gap_rule": GAP_RULE, "gaps_in_page": gaps(data)}})

    def variant_comparison(self, req: Req) -> tuple[int, dict]:
        q, s = req.q, self.store
        o2 = {r["timestamp"]: r["empirical_risk_score"] for r in s.o2x.window(q["start"], q["end"])}
        rows = tuple({"timestamp": r["timestamp"], "primary_empirical_risk_score": r["empirical_risk_score"],
                      "o2_excluded_empirical_risk_score": o2.get(r["timestamp"])}
                     for r in s.primary.window(q["start"], q["end"]))
        data, pg = page(rows, q)
        req.log.update(variant="primary+o2_excluded", query_window=[q["start"], q["end"]], result_count=len(data))
        summary = [x for x in s.validation["o2_excluded_sensitivity"]
                   if x["metric"] in ("score_rank_correlation_operational_buckets", "primary_endpoint_status",
                                      "primary_endpoint_PE_60min")]
        return 200, self._envelope(
            data, req=req, pagination=pg, disclaimer=s.contract["disclaimers"]["o2_excluded"],
            provenance=[self._prov("risk_scores", variant="primary"),
                        self._prov("o2_excluded_scores", variant="o2_excluded"), self._prov("p8_o2_sensitivity")],
            extra={"variants": {k: {**v, "preference_note": PREFERENCE_NOTE} for k, v in VARIANTS.items()},
                   "phase8_o2_sensitivity_summary": summary,
                   "window_semantics": "start <= timestamp < end; rows keyed on primary operational timestamps",
                   "data_extent": {"gap_rule": GAP_RULE, "gaps_in_page": gaps(data)}})

    def abnormal_periods(self, req: Req) -> tuple[int, dict]:
        q, s = req.q, self.store
        rows = tuple(p for p in s.periods
                     if evs.overlaps(p["start_time"], p["end_time"], q["start"] or "0000", q["end"] or "9999")
                     and (not q["kpi_severity_class"] or p["kpi_severity_class"] == q["kpi_severity_class"]))
        data, pg = page(rows, q)
        req.log.update(artifact_version=s.provenance["abnormal_episodes"]["artifact_version"],
                       query_window=[q["start"], q["end"]], result_count=len(data))
        return 200, self._envelope(data, req=req, pagination=pg,
                                   disclaimer=s.contract["disclaimers"]["abnormal_periods"],
                                   provenance=self._prov("abnormal_episodes"),
                                   extra={"window_semantics": "periods [start_time, end_time) overlapping [start, end)",
                                          "label_type": ast_.LABEL_TYPE,
                                          "time_fields_note": "onset_time = Phase 8 T0 (CUSUM onset, 6 of 12 "
                                                              "censored); start_time / end_time = the KPI-derived "
                                                              "period; detection_time = first KPI >= P90 bucket. "
                                                              "Plot the period as start_time..end_time."})

    def validation(self, req: Req) -> tuple[int, dict]:
        s = self.store
        req.log.update(artifact_version=s.provenance["p8_summary"]["artifact_version"])
        keys = ("p8_summary", "p8_horizon", "p8_controls", "p8_negative_controls", "p8_o2_sensitivity",
                "p8_load_sensitivity", "p8_gates")
        return 200, self._envelope(s.validation, req=req, disclaimer=s.contract["disclaimers"]["validation"],
                                   provenance=[self._prov(k) for k in keys])

    def findings(self, req: Req) -> tuple[int, dict]:
        q, s = req.q, self.store
        rows = tuple(f for f in s.findings if not q["classification"] or f["classification"] == q["classification"])
        data, pg = page(rows, q)
        req.log.update(artifact_version=s.provenance["p8_summary"]["artifact_version"], result_count=len(data))
        return 200, self._envelope(data, req=req, pagination=pg, disclaimer=s.contract["disclaimers"]["validation"],
                                   provenance=self._prov("p8_summary"),
                                   extra={"aggregate_score": None,
                                          "note": "each finding keeps its own Phase 8 class; classes are not "
                                                  "summed or scored; context_only findings are not evidence of "
                                                  "an effect"})

    # ---------------------------------------------------------------- plant events
    def _event_out(self, e: dict) -> dict:
        """Stored annotation + read-only analytical context computed on read (never stored, never sets a label)."""
        ctx = None
        if self.store is not None:
            ctx = {"overlapping_kpi_derived_abnormal_periods": [
                p["period_id"] for p in self.store.periods
                if evs.overlaps(p["start_time"], p["end_time"], e["start_time"], e["end_time"])],
                "note": "computed on read for future revalidation; never stored and never used to set event_type"}
        return {**e, "analytical_label": None, "analytical_context": ctx}

    def _ev_envelope(self, data, req, pagination=None) -> dict:
        body = {"api_version": "v1", "service_version": VERSION, "data": data,
                "interpretation": EVENT_INTERPRETATION, "query": req.q,
                "provenance": {"source": "PLANT_SUPPLIED_ANNOTATION", "store": "phase-09 SQLite event store",
                               "plant_supplied": True, "analytical_status": "NOT_ANALYTICAL"},
                "disclaimer": ("Plant event annotations are plant-supplied ground-truth candidates, independent of "
                               "the analytical labels.")}
        if pagination is not None:
            body["pagination"] = pagination
        return body

    def events_list(self, req: Req) -> tuple[int, dict]:
        q = req.q
        rows, total = self.events.list(status=q["status"], event_type=q["event_type"], start=q["start"],
                                       end=q["end"], limit=q["limit"], offset=q["offset"])
        req.log.update(result_count=len(rows))
        return 200, self._ev_envelope([self._event_out(e) for e in rows], req, _pagination(q, len(rows), total))

    def events_create(self, req: Req) -> tuple[int, dict]:
        actor = self._actor(req)
        e = self.events.create(self._body(req), actor)
        req.log.update(event_id=e["event_id"], operation="CREATE")
        return 201, self._ev_envelope(self._event_out(e), req)

    def events_get(self, req: Req) -> tuple[int, dict]:
        return 200, self._ev_envelope(self._event_out(self.events.get(req.params["event_id"])), req)

    def events_patch(self, req: Req) -> tuple[int, dict]:
        actor = self._actor(req)
        e = self.events.update(req.params["event_id"], self._body(req), actor)
        req.log.update(event_id=e["event_id"], operation="UPDATE")
        return 200, self._ev_envelope(self._event_out(e), req)

    def events_delete(self, req: Req) -> tuple[int, dict]:
        actor = self._actor(req)
        if req.q["expected_version"] is None:
            raise ApiError(422, "expected_version query parameter is required for DELETE",
                           [{"param": "expected_version", "issue": "required (optimistic concurrency)"}])
        e = self.events.delete(req.params["event_id"], actor, req.q["expected_version"])
        req.log.update(event_id=e["event_id"], operation="DELETE")
        return 200, self._ev_envelope(self._event_out(e), req)

    def events_audit(self, req: Req) -> tuple[int, dict]:
        return 200, self._ev_envelope(self.events.audit(req.params["event_id"]), req)


class QuietHandler(WSGIRequestHandler):
    timeout = 30                             # a stalled client cannot hold the single-threaded server forever

    def log_message(self, *args):            # request logging is the structured JSON log above
        pass


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    cfg = ServiceConfig.from_env()
    app = App(cfg)
    # ponytail: single-threaded wsgiref, fine for a POC analyst tool; put a WSGI server in front for concurrent use
    with make_server(cfg.host, cfg.port, app, handler_class=QuietHandler) as httpd:
        log.info(json.dumps({"event": "listening", "host": cfg.host, "port": cfg.port}))
        httpd.serve_forever()


if __name__ == "__main__":
    serve()
