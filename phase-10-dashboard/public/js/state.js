import { toApiTimestamp } from "./pure/query.js";

const RANGE = "p10.range";
const ACTOR = "p10.actor";

export function readRange() {
  const params = new URLSearchParams(location.search);
  const fromUrl = pair(params.get("start"), params.get("end"));
  if (fromUrl) return fromUrl;
  try {
    return pairFrom(JSON.parse(sessionStorage.getItem(RANGE) || "null"));
  } catch {
    return null;
  }
}

function pair(start, end) {
  const a = toApiTimestamp(start);
  const b = toApiTimestamp(end);
  if (!a || !b || a >= b) return null;
  return { start: a, end: b };
}

function pairFrom(value) {
  if (!value) return null;
  return pair(value.start, value.end);
}

export function writeRange(range) {
  const valid = pair(range?.start, range?.end);
  if (!valid) {
    sessionStorage.removeItem(RANGE);
    return null;
  }
  sessionStorage.setItem(RANGE, JSON.stringify(valid));
  const url = new URL(location.href);
  url.searchParams.set("start", valid.start);
  url.searchParams.set("end", valid.end);
  history.replaceState(history.state, "", url);
  return valid;
}

export function clearRange() {
  sessionStorage.removeItem(RANGE);
  const url = new URL(location.href);
  url.searchParams.delete("start");
  url.searchParams.delete("end");
  history.replaceState(history.state, "", url);
}

export function readActor() {
  return sessionStorage.getItem(ACTOR) || "";
}

export function writeActor(actor) {
  sessionStorage.setItem(ACTOR, actor);
}
