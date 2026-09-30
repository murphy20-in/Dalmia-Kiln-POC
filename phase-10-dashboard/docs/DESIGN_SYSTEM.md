# Design system

Visual reference: the public Dalmia Cement site (https://www.dalmiacement.com/), used for colour and tone only. No site markup, logo file, script, or tracking tag is copied.

Tokens live in `public/css/app.css` (`:root`).

| Token | Value | Use |
|---|---|---|
| `--green-deep` | `#003a1e` | Header, buttons |
| `--green` | `#006838` | Brand and the primary score line |
| `--orange` | `#c4511a` | Header stripe only |
| `--charcoal` | `#414042` | Ink |
| `--paper` | `#f3f4f1` | Page background |
| `--series` / `--sensitivity` / `--period` / `--event` / `--gap` | green, slate, blue-grey, umber, beige | Series identity |

Green on a score line means “primary series”, not a safe state. Coverage tints use the same idea: available, reference, partial, missing. There is no red/amber/green status scale.

Type is the system UI stack. Radius is 2px. Charts are inline SVG (`viewBox` 860×360, `aspect-ratio` so the box does not collapse).

Chart decision: the repository had no chart library. The required series, gaps, and overlays fit native SVG, so no chart package was added.
