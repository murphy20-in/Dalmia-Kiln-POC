// One tooltip layout for every chart: title, optional subtitle, labelled rows, optional note.
// ECharts injects formatter output as HTML, so every string is escaped here.
import { brand } from "../theme";

const esc = (s: string | number) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export interface TipRow { label: string; value: string; color?: string }

export function tip({ title, sub, rows = [], note }: { title: string; sub?: string; rows?: TipRow[]; note?: string }): string {
  const head = `<div style="font-weight:600;color:${brand.navyInk};font-size:13px">${esc(title)}</div>`
    + (sub ? `<div style="color:${brand.muted};margin-top:1px">${esc(sub)}</div>` : "");
  const body = rows.map((r) =>
    `<div style="display:flex;align-items:center;gap:8px;margin-top:6px">`
    + (r.color ? `<span style="width:8px;height:8px;border-radius:2px;background:${esc(r.color)};flex:none"></span>` : "")
    + `<span style="color:${brand.muted};flex:1">${esc(r.label)}</span>`
    + `<span style="font-weight:600;color:${brand.navyInk};font-variant-numeric:tabular-nums">${esc(r.value)}</span></div>`).join("");
  const foot = note ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid ${brand.line};color:${brand.muted};font-size:11px">${esc(note)}</div>` : "";
  return head + (body ? `<div style="margin-top:4px">${body}</div>` : "") + foot;
}
