# Accessibility review

| Check | Result |
|---|---|
| Semantic regions | Header, nav, main, footer. One h1 per page |
| Disclaimer | Sticky, in the shell, not only the footer |
| Focus | `:focus-visible` outline |
| Forms | Labels on actor, times, type, source, description |
| Charts | Title, description, legend with stroke names, data table, keyboard slider |
| Colour | Series identity is also named. No red/amber/green band scale |
| Tables | Scroll inside `.table-wrap` on desktop; stacked `data-label` rows under 720px |
| 390px | Page `scrollWidth` equals `clientWidth`. Nav links scroll horizontally |

No screen-reader session and no Lighthouse score were run.
