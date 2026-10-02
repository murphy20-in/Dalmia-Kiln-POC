// One tooltip layout for every chart: title, optional subtitle, labelled rows, optional note.
// Deep Forest shell (theme.ts → chart.tooltip) with a short Emerald rule under the title.
// ECharts injects formatter output as HTML, so every string is escaped here, including colours.
import { chart, colors } from "../theme";

const esc = (s: string | number) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export interface TipRow { label: string; value: string; color?: string }

const t = chart.tooltip;

export function tip({ title, sub, rows = [], note }: { title: string; sub?: string; rows?: TipRow[]; note?: string }): string {
  const head = `<div style="font-weight:600;color:${t.title};font-size:13px;letter-spacing:-0.005em">${esc(title)}</div>`
    + (sub ? `<div style="color:${t.text};margin-top:2px;font-size:11px;letter-spacing:0.04em;text-transform:uppercase">${esc(sub)}</div>` : "")
    + `<div style="width:24px;height:2px;border-radius:2px;background:${colors.emerald};margin-top:7px"></div>`;
  const body = rows.map((r) =>
    `<div style="display:flex;align-items:center;gap:8px;margin-top:6px">`
    + (r.color ? `<span style="width:8px;height:8px;border-radius:2px;background:${esc(r.color)};box-shadow:0 0 0 1px ${t.border};flex:none"></span>` : "")
    + `<span style="color:${t.text};flex:1">${esc(r.label)}</span>`
    + `<span style="font-weight:600;color:${t.title};font-variant-numeric:tabular-nums">${esc(r.value)}</span></div>`).join("");
  const foot = note ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid ${t.rule};color:${t.text};font-size:11px">${esc(note)}</div>` : "";
  return head + (body ? `<div style="margin-top:2px">${body}</div>` : "") + foot;
}
