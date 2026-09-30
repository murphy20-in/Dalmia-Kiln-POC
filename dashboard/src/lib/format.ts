// Timestamps are naive historian-clock strings ("2025-06-15T11:30"). They are parsed and
// printed as UTC so the plant clock is shown unchanged in any browser timezone.
export const toMs = (t: string) => Date.parse(t + ":00Z");
export const fromMs = (ms: number) => new Date(ms).toISOString().slice(0, 16);

const dt = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const d = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
const mon = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", month: "short" });

const day = (t: string) => toMs(t.length === 10 ? t + "T00:00" : t);
export const fmtDateTime = (t: string) => dt.format(toMs(t)).replace(",", " ·");
export const fmtDate = (t: string) => d.format(day(t));
export const fmtMonth = (ym: string) => mon.format(toMs(ym + "-01T00:00"));

export const fmtInt = (n: number) => Math.round(n).toLocaleString("en-IN");
export const fmt1 = (n: number | null | undefined) => (n == null ? "–" : n.toFixed(1));
export const fmtPct = (share: number, digits = 0) => `${(share * 100).toFixed(digits)}%`;
export const fmtSigned = (n: number, digits = 0) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(digits)}`;

export function fmtDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

// Indian number system for rupees: lakh (1e5) and crore (1e7).
export function fmtRupees(n: number): string {
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)} lakh`;
  return `₹${fmtInt(n)}`;
}
