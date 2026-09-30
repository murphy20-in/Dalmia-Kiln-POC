/** Display helpers for API score rows. No score formula. Gaps stay gaps. */

export const GAP_SECONDS = 600;

export function parseTs(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/.exec(value || "");
  if (!m) return null;
  const n = m.slice(1).map(Number);
  return Date.UTC(n[0], n[1] - 1, n[2], n[3], n[4], n[5]);
}

export function formatTs(ms) {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

export function addMinutes(ts, minutes) {
  const t = parseTs(ts);
  if (t == null) return null;
  return formatTs(t + minutes * 60000);
}

export function isGap(earlier, later) {
  const a = parseTs(earlier);
  const b = parseTs(later);
  if (a == null || b == null) return true;
  return (b - a) / 1000 > GAP_SECONDS;
}

/** Contiguous runs of numeric API values. Nulls and >10 min steps start a new run. Never fills. */
export function segments(rows, valueKey, gapPairs) {
  const breakAfter = new Set((gapPairs || []).map((pair) => pair[0]));
  const out = [];
  let cur = [];
  const flush = () => {
    if (cur.length) out.push(cur);
    cur = [];
  };
  for (const row of rows) {
    const t = row.timestamp;
    const raw = row[valueKey];
    if (cur.length && (breakAfter.has(cur[cur.length - 1].timestamp) || isGap(cur[cur.length - 1].timestamp, t))) {
      flush();
    }
    if (raw == null || raw === "" || Number.isNaN(Number(raw))) {
      flush();
      continue;
    }
    cur.push({ timestamp: t, y: Number(raw) });
  }
  flush();
  return out;
}

/** Keep real API points. Stride inside each segment; always keep the segment ends.
 *  ponytail: cap is about 900 points. Plot every point if a window must be read bucket by bucket. */
export function decimate(segs, maxPoints) {
  const total = segs.reduce((n, s) => n + s.length, 0);
  if (total <= maxPoints) return segs;
  const stride = Math.ceil(total / maxPoints);
  return segs.map((seg) => {
    if (seg.length <= 2) return seg.slice();
    const keep = [];
    for (let i = 0; i < seg.length; i += stride) keep.push(seg[i]);
    const last = seg[seg.length - 1];
    if (keep[keep.length - 1] !== last) keep.push(last);
    return keep;
  });
}

export function flatten(segs) {
  return segs.flat();
}

/** Fixed 0–100 scale unless an API value falls outside it. */
export function yDomain(segs) {
  let lo = 0;
  let hi = 100;
  for (const seg of segs) {
    for (const p of seg) {
      if (p.y < lo) lo = p.y;
      if (p.y > hi) hi = p.y;
    }
  }
  return [lo, hi];
}
