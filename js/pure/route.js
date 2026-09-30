/** Every dashboard URL is parsed and built here, for path mode (local) and hash mode (GitHub Pages). */
import { buildQuery } from "./query.js";

export const PAGES = ["/", "/history", "/abnormal-periods", "/events", "/validation", "/data-quality", "/methodology"];
const PERIOD = /^\/abnormal-periods\/(P6-\d{3})$/;
const EVENT = /^\/events\/([0-9a-f-]{36})(\/edit)?$/;

/** Route path -> { page, id?, mode? }, or null for an unknown path. */
export function match(path) {
  if (PAGES.includes(path)) return { page: path };
  if (path === "/events/new") return { page: "/events", mode: "new" };
  let m = PERIOD.exec(path);
  if (m) return { page: "/abnormal-periods", id: m[1] };
  m = EVENT.exec(path);
  if (m) return { page: "/events", id: m[1], mode: m[2] ? "edit" : "detail" };
  return null;
}

/** location-like { pathname, search, hash } -> { page, id, mode, path, query, anchor, known } */
export function parseLocation(loc, hashMode) {
  let path = loc.pathname || "/";
  let search = loc.search || "";
  let anchor = (loc.hash || "").slice(1);
  if (hashMode) {
    const raw = (loc.hash || "").slice(1) || "/";
    const cut = raw.indexOf("#");
    const pathAndQuery = cut === -1 ? raw : raw.slice(0, cut);
    anchor = cut === -1 ? "" : raw.slice(cut + 1);
    const q = pathAndQuery.indexOf("?");
    path = q === -1 ? pathAndQuery : pathAndQuery.slice(0, q);
    search = q === -1 ? "" : pathAndQuery.slice(q);
    if (!path.startsWith("/")) path = `/${path}`;
  }
  const hit = match(path);
  return {
    ...(hit || { page: "/" }),
    known: Boolean(hit),
    path: hit ? path : "/",
    query: Object.fromEntries(new URLSearchParams(search)),
    anchor: safeDecode(anchor),
  };
}

/** Build an href. Hash mode prefixes "#" so the link stays on the hosted page. */
export function href(path, query = {}, anchor = "", hashMode = false) {
  const q = buildQuery(query);
  const s = `${path}${q ? `?${q}` : ""}${anchor ? `#${anchor}` : ""}`;
  return hashMode ? `#${s}` : s;
}

/** A clicked link's href (as written) -> location-like object, or null if it is not an in-app route. */
export function linkTarget(raw, hashMode) {
  if (!raw || /^[a-z]+:/i.test(raw) || raw.startsWith("//")) return null;
  if (hashMode) return raw.startsWith("#/") ? { pathname: "/", search: "", hash: raw } : null;
  if (!raw.startsWith("/")) return null;
  const url = new URL(raw, "http://dashboard.local");
  return { pathname: url.pathname, search: url.search, hash: url.hash };
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return "";
  }
}
