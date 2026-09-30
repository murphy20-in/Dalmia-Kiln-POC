import { buildQuery } from "./pure/query.js";

export class ApiError extends Error {
  constructor(status, body) {
    super(publicMessage(status, body));
    this.status = status;
    this.body = body;
    this.code = body?.error?.code || "";
  }
}

function publicMessage(status, body) {
  const raw = body?.error?.message || "";
  if (/traceback|\/home\/|sqlite|\.parquet|events\.sqlite/i.test(raw)) {
    return "The analytical service could not complete this request.";
  }
  if (status === 503 || body?.error?.code === "ANALYTICAL_SERVICE_UNAVAILABLE") {
    return "Analytical service unavailable. Check that the Phase 9 service is running.";
  }
  if (status === 409) return raw || "The record changed before this update was saved.";
  if (raw) return raw;
  return "The analytical service could not complete this request.";
}

export function logClientError(kind, err) {
  const status = err?.status || "";
  const code = err?.code || "";
  console.error("[dashboard]", kind, status, code);
}

export async function api(path, { method = "GET", body, actor, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (body != null) headers["Content-Type"] = "application/json";
  if (actor) headers["X-Actor"] = actor;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body != null ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    logClientError("network", err);
    throw new ApiError(503, { error: { code: "ANALYTICAL_SERVICE_UNAVAILABLE", message: "Analytical service unavailable" } });
  }
  const text = await response.text();
  let parsed = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      logClientError("parse", { status: response.status });
      throw new ApiError(response.status, { error: { message: "The analytical service returned an unreadable response." } });
    }
  }
  if (!response.ok) {
    const error = new ApiError(response.status, parsed);
    logClientError("api", error);
    throw error;
  }
  return parsed;
}

export async function getAll(path, params, { signal, pageLimit = 5000, maxRows = 12000 } = {}) {
  const rows = [];
  const gaps = [];
  let offset = 0;
  let envelope = null;
  while (rows.length < maxRows) {
    const query = buildQuery({ ...params, limit: pageLimit, offset });
    const page = await api(`${path}?${query}`, { signal });
    envelope = page;
    rows.push(...(page.data || []));
    gaps.push(...(page.data_extent?.gaps_in_page || []));
    if (!page.pagination?.has_more) break;
    offset = page.pagination.next_offset;
  }
  return { rows, gaps, envelope };
}
