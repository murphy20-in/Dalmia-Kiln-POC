const TS = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

/** datetime-local or API stamp -> YYYY-MM-DDTHH:MM:SS. Rejects offsets. */
export function toApiTimestamp(value) {
  if (value == null || value === "") return "";
  const text = String(value).trim();
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) return null;
  const m = TS.exec(text);
  if (!m) return null;
  const sec = m[6] ?? "00";
  const stamp = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${sec}`;
  const dt = new Date(`${stamp}Z`);
  if (Number.isNaN(dt.getTime())) return null;
  const p = (n) => String(n).padStart(2, "0");
  const roundtrip = `${dt.getUTCFullYear()}-${p(dt.getUTCMonth() + 1)}-${p(dt.getUTCDate())}T${p(dt.getUTCHours())}:${p(dt.getUTCMinutes())}:${p(dt.getUTCSeconds())}`;
  return roundtrip === stamp ? stamp : null;
}

export function toLocalInput(stamp) {
  return stamp ? stamp.slice(0, 16) : "";
}

export function buildQuery(params) {
  const parts = [];
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.join("&");
}
