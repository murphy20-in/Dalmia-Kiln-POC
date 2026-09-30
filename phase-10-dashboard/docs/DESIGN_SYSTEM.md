# Design system (v2)

## Source

Tokens were sampled on 2026-09-30 from the live site https://www.dalmiacement.com/, using computed styles in a Playwright browser at 1440×900. The site has rebranded to **Dalmia Bharat Cement**: navy and cyan, with Arimo type. v1's green (`#006838`) and orange (`#c4511a`) were not taken from the site, so they are retired. The fallback tokens in the rebuild prompt apply only when the site is unreachable, and it was reachable.

No logo image, site imagery, markup, script or tracking tag is copied. The header uses a text wordmark: **DALMIA CEMENT | Kiln Analytical POC**. The reference capture is `screenshots/reference-dalmiacement.png`, and the side-by-side is `screenshots/theme-side-by-side.png`.

## Tokens (`public/css/app.css`, `:root`)

| Token | Value | Sampled from | Used for |
|---|---|---|---|
| `--navy` | `#2a469c` | footer background, "Request Callback" button, heading colour | header, primary CTA, h1, KPI top rule, primary score line, focus ring |
| `--navy-deep` | `#233d8e` | darker navy panel | primary CTA hover |
| `--cyan` | `#00a8ce` | "Our Products" / "Watch Video" buttons | 4 px header stripe and section-heading rule only. It is 2.6:1 on white, so never text and never data |
| `--charcoal` | `#414142` | body text (416 elements) | ink, event diamonds, severity outlines |
| `--grey` | `#646668` | secondary text `#6d6f71`, darkened | secondary text (5.1:1 on the tint surface), the O₂ sensitivity line (dashed) |
| `--mist` | `#e7e8e9` | light rule | grid lines, disabled buttons |
| `--tint` | `#eef1f8` | navy at about 8% (derived) | info callouts, advisory, active nav |
| `--slate` | `#5b6472` | neutral (derived) | bar marks (6.0:1) |
| `--hatch` | `#7c8089` | neutral (derived) | severity hatch (4.0:1) |
| `--radius` | `5px` | button border-radius | cards, buttons, inputs |
| `--font` | `Arimo, Arial, …` | `font-family` on 754 elements | all text. Arial is metric-compatible, so no font is downloaded and the page works offline |

Buttons follow the site pattern: 5 px radius, about 10 px × 16 px padding, weight 500, 16 px. The primary button is filled navy. The secondary button is outlined navy, and a ghost button is an underlined navy link. Every button is at least 44 px tall. There is one primary CTA per action bar.

## Colour rule for data

Brand colours never encode a state. Score bands, KPI severity, validation status and coverage use a neutral ramp, and each is always paired with a text label and a pattern or weight:

- **KPI severity:** hatch density and outline weight (high: dense, 2 px; moderate: medium, 1.2 px; low: sparse, dashed 0.8 px), plus the text "High / Moderate / Low severity".
- **Validation status:** plain-English text in a charcoal outline chip ("Not supported", "Weak", "Blocked"), with the raw enum in a tooltip.
- **Coverage:** the cell text names the state ("Missing", "Partial", "Reference"…), and pattern is the second cue.
- **Gaps:** grey hatch (`#8d9096`, 3.2:1) and a break in the line. Gaps are never interpolated.
- **Series identity:** the primary score is solid navy, and the O₂-excluded sensitivity is dashed grey. They differ in greyscale (luminance 0.07 vs 0.16) and by dash, with a legend.

No red, amber, orange or traffic-light hue appears anywhere. `tests/honesty.test.mjs` checks the stylesheet.

## Checks (`dataviz` skill validator and WCAG contrast)

| Pair | Ratio | Need |
|---|---|---|
| navy on white / white on navy | 8.56 | 4.5 text |
| charcoal on white / on tint | 10.2 / 9.0 | 4.5 |
| grey on white / tint / paper | 5.8 / 5.1 / 5.3 | 4.5 |
| severity hatch, bars, gap hatch | 4.0 / 6.0 / 3.2 | 3 (marks) |
| input border | 3.2 | 3 (UI component) |

`validate_palette.js "#2a469c,#6d6f71"` passes CVD separation (ΔE 17.1 protan, 13.0 tritan) and the normal-vision floor (18.2). It flags lightness band (navy) and chroma floor (grey). Those are categorical-palette checks. Here the grey is deliberately recessive ("not preferred"), and the pair carries secondary encoding (solid vs dashed, legend, labels). Disposition: accepted.

## Layout

The header sits above a sticky disclaimer. Below them are a 232 px left nav and the main column (max 1240 px). Under 900 px the nav becomes top tabs; under 720 px tables stack and the gutter is 16 px. Every page follows the same rhythm: hero (title plus a one-sentence answer) → KPI cards → graph → insights → advisory → next steps → action bar. `prefers-reduced-motion` removes transitions and the spinner. Dark mode is out of scope.
