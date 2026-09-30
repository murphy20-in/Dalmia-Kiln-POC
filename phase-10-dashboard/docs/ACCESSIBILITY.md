# Accessibility

- One `h1` per page. Sections use `h2`.
- Skip link, `nav` with `aria-current="page"`, sticky disclaimer with `role="note"`.
- Visible `:focus-visible` outline in brand green.
- Form fields have labels. Validation text sits in a `role="alert"` or `role="status"` line.
- Charts: `role="img"`, title, description, legend that names the stroke (solid, dashed, hatch, diamond, gap), a data table of plotted points, and a range control that announces a timestamp and score.
- Tables use `caption`, `scope="col"`, and a stacked layout under 720px via `data-label`.
- Score meaning does not depend on colour. The legend names each mark.
- KPI severity class is text, not a colour.

Checked in the browser: keyboard focus ring is CSS-visible; the historical chart exposes the table and the inspect slider; the event form labels are associated with controls. No automated screen-reader pass was run.
