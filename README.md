# tokenomics_landscape_ui

Various visualization layers using the mindmap data (and optionally joining
additional data sources). Each page is a flat view or kiosk view of the same
YAML the mind map viewer uses.

## Pages

| Page | What it is |
|---|---|
| `terminology.html` | Every node as a readable, searchable glossary with a KPI toggle in one self-contained file (data inlined as JSON, zero external requests). Deep links are hashes: `#<slug>` for a term, `#kpi` / `#kpi/<slug>` for KPI mode. Works identically hosted, on `file://`, and pasted into WordPress. |
| `kiosk.html` | Portrait 1080x1920 event kiosk (from the `kiosk-mode` branch of `tokenomics_mindmap`). Loads the pinned data version and reads node `Type`. |
| `explorer/` | Mind Map Explorer: an MCP server over the pinned mind map plus a chat page where an agent places plain-language descriptions in the map. Needs a server process; not a GitHub Pages page. See `explorer/README.md`. |

## Data versioning

`tokenomics_mindmap` is referenced only by named version. Released YAMLs are
vendored under `data/<version>/tokenomics_mindmap.yaml`; released versions
stay immutable, and a booth kiosk only changes when you deliberately point it
at a new version:

    data/v0.0.3/tokenomics_mindmap.yaml   # sha256 0ce6e8d0a4cd9d58...3f8f9c91, tag v0.0.3
    data/v0.0.2/tokenomics_mindmap.yaml   # sha256 472b6feb8463a153...cfb835a3d, tag v0.0.2

To pick up a new data release, vendor it, then re-pin the pages:

    git -C ../tokenomics_mindmap show v0.0.3:tokenomics_mindmap.yaml > data/v0.0.3/tokenomics_mindmap.yaml
    scripts/pin_data.py v0.0.3

`scripts/pin_data.py <version>` is a one-off maintenance helper, not a page
build. It converts the vendored YAML to JSON and rewrites only the
`#tfg-data` block, the `DATA_VERSION` constant, and the version notes in the
`terminology.html` header comment. The second run with the same version
reports identical and writes nothing; the conversion refuses em/en dashes
(house rules). `terminology.html` stays the complete, hand-editable artifact:
per the TF Mini-Tool Guide there is no build step and no fork. Also bump
`DEFAULT_FILE` in `kiosk.html` when pinning a new version there.

## terminology.html: one file, three consumers

The file is a TF HTML mini-tool (see the HTML Mini-Tool Development Guide):
one self-contained fragment, no doctype/html/head/body, zero external
requests, ID-scoped CSS (`#te-terminology`, `tfg-` classes), one guarded ES5
IIFE. The pinned mind map rides inside as JSON in
`<script type="application/json" id="tfg-data">`, so nothing is fetched and
js-yaml is not needed. It serves three consumers with no variants:

- **WordPress (the draft target):** paste the entire file into one Custom
  HTML block on a `te_page`. This is a Working Group draft: the page carries
  a visible "Working Group draft · mind map v0.0.3" label.
- **Offline review:** open the file directly (`file://`, network share, no
  network). Same hash links, same behavior, still 827 terms.
- **Repo demo server:** `python3 scripts/serve_demo.py` (port 8788) serves
  the clean paths below and doubles as the reference rewrite rule for a
  future host-side rule. Optional; the page does not need it.

There is no separate kpis.html: Glossary and KPI are two modes of this one
file, switched by the toggle or `#kpi`.

## Links and URL scheme

WordPress has no rewrite rules, so every generated link is a hash and the
app never leaves the page:

    #/              glossary
    #<slug>         one term, focused and highlighted
    #kpi            KPI cards
    #kpi/<slug>     one KPI, focused and highlighted

Back/forward work via `hashchange`. A host that does serve the file at the
clean paths (`/terminology`, `/terminology/<slug>`, `/kpi`, `/kpi/<slug>`),
like `scripts/serve_demo.py`, is honoured on load: the mode/slug is read
from the path when the URL carries no hash yet. Links are never emitted as
paths, so nothing 404s on WordPress.

SEO caveat (unchanged from the 2026-10-06 review): term content arrives via
JS, so crawlers index it only after render, and hash URLs are not per-term
canonical URLs. Fine for an internal WG draft; if per-term SEO gets serious
the escalation is a static build emitting real pages from the pinned YAML,
behind a host rewrite.

## Editing

- `terminology.html` is the only edit surface for the glossary/KPI views
  (one file, data inlined; there is no separate kpis.html and no dist twin).
  Verify edits with the structural checker:
  `python3 ~/skills/productivity/tf-html-artifact-authoring/scripts/tf_html_check.py terminology.html`
  must exit 0.
- `kiosk.html` is a copy of the mindmap repo's kiosk; changes intended to be
  permanent should be sent back to `tokenomics_mindmap` before re-copying.
- `vendor/` holds d3, js-yaml, qrcode locally for the kiosk and explorer.
  `terminology.html` no longer uses js-yaml (data ships as JSON).

## License

CC BY 4.0, Tokenomics Foundation.
