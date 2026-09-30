# Accessibility (v2, WCAG 2.2 AA target)

- One `h1` per page. Sections use `h2`. A route change focuses the `h1`; a detail panel or anchor target (`#F3`, `#L01`, `#censoring`, a coverage cell) is scrolled to, opened if inside `<details>`, and focused.
- A same-page re-render (history presets, overlay, Apply range) puts focus back on the control that caused it.
- Skip link focuses `<main>` without a route change. `nav` marks the page with `aria-current="page"`.
- The disclaimer (`role="note"`) is the only sticky element. `scroll-padding-top` follows its measured height (`--sticky`, updated by a `ResizeObserver`), so focused content and anchor targets are never hidden beneath it. Under 900 px the nav scrolls with the page.
- Focus: 3 px navy `:focus-visible` outline. SVG links use a stroke that is wider than the "highlighted period" stroke, so a highlighted band still changes when focused. Event diamonds grow when focused.
- Charts: `figure` + `figcaption` + description, SVG `role="group"` labelled by the caption, a legend that names every mark (solid, dashed, three hatch densities, diamond, gap), a "View as table" toggle, and a "List the periods and annotations in this chart" toggle of ordinary links. That list is the equivalent control for chart marks smaller than 24 px (WCAG 2.5.8). SVG links take their name from one `<title>`. Score charts add a labelled range input that steps through every plotted point; it announces the time and score through `aria-valuetext` and updates the readout, which is not a live region.
- Under 720 px charts keep a 600 px minimum width inside a focusable, labelled scroll region, so SVG text stays legible.
- The history range is set with labelled date inputs and preset buttons; drag-to-zoom is an extra, not the only way. Range errors set `aria-invalid` and are linked with `aria-describedby`.
- Annotation form: visible "(required)" labels; hints linked with `aria-describedby`; on error each field gets `aria-invalid` and is described by the `role="alert"` error line, and focus moves to the first invalid field. Server-side field errors are shown the same way.
- Hosted read-only copy: write buttons are `aria-disabled` (still focusable) and described by the visible reason "Read-only hosted copy — annotate on the local service".
- Toast is a permanent `role="status"` region; the text is cleared and re-set so repeated messages announce.
- Tables use `caption`, `scope="col"`, and a stacked layout under 720 px via `data-label`.
- Colour is never the only cue: severity is hatch density + outline weight + text; status is text in an outline chip; coverage names its state in the cell.
- `prefers-reduced-motion` disables transitions and animations.

Checked: Lighthouse Accessibility 100 on all seven pages; keyboard-only journey (a); 375 px and 720 px (200 % zoom) with no page-level horizontal overflow. No screen-reader session was run.
