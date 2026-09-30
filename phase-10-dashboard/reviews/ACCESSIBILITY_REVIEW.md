# Accessibility review (v2)

The `a11y-architect` review of v2 against WCAG 2.2 AA found 3 HIGH, 6 MEDIUM and 5 LOW issues. They are listed in `REVIEW_LOG.md` §2 (A1–A14). All are fixed, except two parts that were accepted with a reason: A6 has no computed chart summary, because client-side statistics are forbidden, and A9 uses one error line that names each field. `docs/ACCESSIBILITY.md` describes what the dashboard does now.

| Check | Result |
|---|---|
| Lighthouse Accessibility | 100 on all seven pages (`E2E_LOG.md`) |
| Keyboard only | Journey (a) passes. Focus returns to the history preset after a re-render, and the chart slider steps through every plotted point |
| Focus not obscured | The sticky disclaimer height feeds `scroll-padding-top`, and the nav is not sticky at 900 px and below |
| Read-only reasons | Hosted mode: every write control is `aria-disabled` and described by its reason (headless Chrome, `tests/e2e/capture.mjs hosted`) |
| 375 px / 720 px | No page-level horizontal overflow on any page (`capture.mjs shots` reports overflow 0) |

No screen-reader session was run.
