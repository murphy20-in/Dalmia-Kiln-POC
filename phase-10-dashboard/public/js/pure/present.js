/** Presenters: served value -> display text. Counting served rows is allowed; no statistic is computed here. */
import { PLAIN } from "../copy.js";

/** Drop presentation of figures Phase 8 withholds from this layer. Does not alter stored evidence. */
const WITHHELD = /\bAUC\b|lead[\s-]?time|coverage\s+[0-9]|false[- ]positive rate/i;

export function evidenceForDisplay(text) {
  if (text == null || text === "") return "";
  if (WITHHELD.test(String(text))) return "";
  return String(text);
}

/** Served enum -> { text, meaning, raw }. Unknown values are shown as served, only de-underscored. */
export function plain(kind, value) {
  const raw = value == null ? "" : String(value);
  const hit = PLAIN[kind]?.[raw];
  if (hit) return { text: hit[0], meaning: hit[1] || "", raw };
  return { text: raw ? raw.replaceAll("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "—", meaning: "", raw };
}

/** Served rows -> Map(value -> number of rows), in first-seen order. */
export function countBy(rows, key) {
  const out = new Map();
  for (const row of rows || []) {
    const value = row?.[key];
    out.set(value, (out.get(value) || 0) + 1);
  }
  return out;
}

/** "2025-06-15T17:30:00" -> "15 Jun 17:30". Plant-local naive time, never converted. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function shortStamp(ts, withYear = false) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(ts || "");
  if (!m) return "—";
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}${withYear ? ` ${m[1]}` : ""} ${m[4]}:${m[5]}`;
}
export function shortDate(ts, withYear = false) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ts || "");
  if (!m) return "—";
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}${withYear ? ` ${m[1]}` : ""}`;
}
export function monthLabel(yyyymm) {
  const m = /^(\d{4})-(\d{2})$/.exec(yyyymm || "");
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : String(yyyymm || "");
}

/** "2025-04-01..2025-09-30" -> ["2025-04", …, "2025-09"]. Calendar listing, not a statistic. */
export function monthsIn(range) {
  const m = /^(\d{4})-(\d{2})-\d{2}\.\.(\d{4})-(\d{2})-\d{2}$/.exec(range || "");
  if (!m) return [];
  const out = [];
  let y = Number(m[1]);
  let mo = Number(m[2]);
  while (y < Number(m[3]) || (y === Number(m[3]) && mo <= Number(m[4]))) {
    out.push(`${y}-${String(mo).padStart(2, "0")}`);
    mo += 1;
    if (mo > 12) { mo = 1; y += 1; }
  }
  return out;
}

/** Findings for display: F3.* warning-rule rows collapse to one row that names no rule. */
export function groupFindings(rows) {
  const out = [];
  let group = null;
  for (const row of rows || []) {
    if (/^F3\./.test(row.finding_id)) {
      if (!group) {
        group = { finding_id: "F3", grouped: [], classification: row.classification };
        out.push(group);
      }
      group.grouped.push(row);
      if (row.classification !== group.classification) group.classification = "MIXED";
      continue;
    }
    out.push(row);
  }
  return out;
}

/** Anchor for a finding id ("F3.W1_RANK" -> "F3"). */
export function findingAnchor(id) {
  return String(id || "").split(".")[0];
}

/** Forbidden UI wording. A match is allowed only in a block that denies the claim. */
export const FORBIDDEN_UI = [
  /\bpredict(ed|ion|ions|s)?\b/i,
  /\bforecast/i,
  /\bprobabilit/i,
  /\blikelihood\b/i,
  /\bchance of\b/i,
  /\balarms?\b/i,
  /\balerts?\b/i,
  /\breal[- ]time\b/i,
  /\blive\b/i,
  /\bmonitor(ing)?\b/i,
  /\bcurrent(ly)?\b/i,
  /\bnow\b/i,
  /lead[\s-]?time/i,
  /\bAUC\b/,
  /afr_context/i,
  /\bW[1-5]_[A-Z]/,
  /early[\s-]warning/i,
  /\babnormal events?\b/i,
];

const NEGATION = /\bnot\b|\bnever\b|\bwithout\b|\bno\b|prohibited|must not|does not|do not|cannot|withheld|blocked|refused/i;
/** The two permitted uses: the disclaimer and the verdict. The verdict label may stand alone ("Early-warning
 *  validation", always paired with its served status), and the endpoint path is an identifier, not a claim. */
const EARLY_WARNING_OK = /retrospective, not an early warning|early-warning validation[:\s]+(is\s+)?not supported|^\s*early-warning validation:?\s*$|\/validation\/early-warning-historical/gim;

/** True when the text block may contain a forbidden word: it states the absence of the claim. */
export function lineAllowsForbidden(text) {
  const s = String(text);
  const rest = s.replace(EARLY_WARNING_OK, "");
  if (!FORBIDDEN_UI.some((re) => re.test(rest))) return true;
  return NEGATION.test(s);
}
