import { isGap } from "./pure/series.js";

class SnapshotError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** github.io has no Phase 9 process. GET reads the exported responses; writes are refused. */

const FILES = {
  "/api/v1/metadata": "metadata.json",
  "/api/v1/metadata/status": "status.json",
  "/api/v1/metadata/provenance": "provenance.json",
  "/api/v1/metadata/limitations": "limitations.json",
  "/api/v1/metadata/methodology": "methodology.json",
  "/api/v1/metadata/data-requirements": "data-requirements.json",
  "/api/v1/abnormal-periods": "periods.json",
  "/api/v1/events": "events.json",
  "/api/v1/validation/early-warning-historical": "validation.json",
  "/api/v1/findings": "findings.json",
};

const cache = new Map();

export function useSnapshot() {
  return typeof location !== "undefined" && location.hostname.endsWith("github.io");
}

export async function snapshotRequest(path, { method = "GET", signal } = {}) {
  if (method !== "GET") {
    throw new SnapshotError(405, "This hosted copy is read-only. Plant annotations are saved only on the local analytical service.");
  }
  const url = new URL(path, "http://dashboard.local");
  const name = url.pathname;
  if (name === "/api/v1/risk-scores") return scorePage("scores-primary.json", url, "empirical_risk_score", signal);
  if (name === "/api/v1/risk-scores/variant-comparison") return comparisonPage(url, signal);
  if (name.startsWith("/api/v1/events/") && name.endsWith("/audit")) return eventAudit(name, signal);
  if (name.startsWith("/api/v1/events/")) return eventOne(name, signal);
  const file = FILES[name];
  if (!file) {
    throw new SnapshotError(404, "This hosted copy does not include that request.");
  }
  const body = await load(file, signal);
  if (name === "/api/v1/abnormal-periods") return sliceRows(body, url, (row) => overlaps(row.start_time, row.end_time, url));
  if (name === "/api/v1/events") return sliceRows(body, url, (row) => eventMatch(row, url));
  if (name === "/api/v1/findings") return sliceRows(body, url, () => true);
  return body;
}

async function load(file, signal) {
  if (!cache.has(file)) {
    cache.set(file, fetch(`snapshot/${file}`, { signal }).then(async (response) => {
      if (!response.ok) throw new SnapshotError(503, "Analytical service unavailable. The exported responses could not be loaded.");
      return response.json();
    }));
  }
  return cache.get(file);
}

function sliceRows(body, url, keep) {
  const rows = (body.data || []).filter(keep);
  const paged = page(rows, url);
  return { ...body, data: paged.data, pagination: paged.pagination, query: queryObject(url) };
}

async function scorePage(file, url, key, signal) {
  const packed = await load(file, signal);
  let rows = packed.points.map(([timestamp, score]) => ({ timestamp, [key]: score }));
  const start = url.searchParams.get("start");
  const end = url.searchParams.get("end");
  if (start) rows = rows.filter((row) => row.timestamp >= start);
  if (end) rows = rows.filter((row) => row.timestamp < end);
  const paged = page(rows, url);
  const extent = { ...(packed.shell.data_extent || {}), gaps_in_page: gapPairs(paged.data) };
  return { ...packed.shell, data: paged.data, pagination: paged.pagination, data_extent: extent, query: queryObject(url) };
}

async function comparisonPage(url, signal) {
  const packed = await load("scores-comparison.json", signal);
  let rows = packed.points.map(([timestamp, primary, o2]) => ({
    timestamp,
    primary_empirical_risk_score: primary,
    o2_excluded_empirical_risk_score: o2,
  }));
  const start = url.searchParams.get("start");
  const end = url.searchParams.get("end");
  if (start) rows = rows.filter((row) => row.timestamp >= start);
  if (end) rows = rows.filter((row) => row.timestamp < end);
  const paged = page(rows, url);
  const extent = { ...(packed.shell.data_extent || {}), gaps_in_page: gapPairs(paged.data) };
  return { ...packed.shell, data: paged.data, pagination: paged.pagination, data_extent: extent, query: queryObject(url) };
}

async function eventOne(name, signal) {
  const id = name.split("/").pop();
  const body = await load("events.json", signal);
  const row = (body.data || []).find((event) => event.event_id === id);
  if (!row) throw new SnapshotError(404, "That plant annotation is not in this hosted copy.");
  return { ...body, data: row, pagination: undefined };
}

async function eventAudit(name, signal) {
  const id = name.split("/")[4];
  const audits = await load("events-audit.json", signal);
  const rows = audits[id];
  if (!rows) throw new SnapshotError(404, "That plant annotation is not in this hosted copy.");
  const body = await load("events.json", signal);
  return { ...body, data: rows, pagination: undefined };
}

function page(rows, url) {
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || rows.length || 1);
  const data = rows.slice(offset, offset + limit);
  return {
    data,
    pagination: {
      offset,
      limit,
      returned: data.length,
      total: rows.length,
      has_more: offset + data.length < rows.length,
      next_offset: offset + data.length,
    },
  };
}

function eventMatch(row, url) {
  const status = url.searchParams.get("status") || "ACTIVE";
  if (status !== "ALL" && row.status !== status) return false;
  const type = url.searchParams.get("event_type");
  if (type && row.event_type !== type) return false;
  return overlaps(row.start_time, row.end_time, url);
}

function overlaps(start, end, url) {
  const windowStart = url.searchParams.get("start") || "0000";
  const windowEnd = url.searchParams.get("end") || "9999";
  return start < windowEnd && (end ? windowStart < end : windowStart <= start);
}

function gapPairs(rows) {
  const pairs = [];
  for (let i = 1; i < rows.length; i += 1) {
    if (isGap(rows[i - 1].timestamp, rows[i].timestamp)) pairs.push([rows[i - 1].timestamp, rows[i].timestamp]);
  }
  return pairs;
}

function queryObject(url) {
  return Object.fromEntries(url.searchParams.entries());
}
