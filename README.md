# tokenomics_landscape_ui

Various visualization layers using the mindmap data (and optionally joining
additional data sources). Each page is a flat view or kiosk view of the same
YAML the mind map viewer uses.

## Pages

| Page | What it is |
|---|---|
| `terminology.html` | Every node as a readable, searchable glossary with a KPI toggle (same file, `?mode=kpi` opens KPI mode). Deep links: `?term=<slug>` anywhere, `/terminology/<slug>` where a host rewrites it. |
| `kiosk.html` | Portrait 1080x1920 event kiosk (from the `kiosk-mode` branch of `tokenomics_mindmap`). Loads the pinned data version and reads node `Type`. |
| `explorer/` | Mind Map Explorer: an MCP server over the pinned mind map plus a chat page where an agent places plain-language descriptions in the map. Needs a server process; not a GitHub Pages page. See `explorer/README.md`. |

## Data versioning

`tokenomics_mindmap` is referenced only by named version. The YAML is vendored
under `data/<version>/tokenomics_mindmap.yaml` and pages load that path, never
a live branch:

    data/v0.0.3/tokenomics_mindmap.yaml   # sha256 0ce6e8d0a4cd9d58...3f8f9c91, tag v0.0.3
    data/v0.0.2/tokenomics_mindmap.yaml   # sha256 472b6feb8463a153...cfb835a3d, tag v0.0.2

To pick up a new data release:

    git -C ../tokenomics_mindmap show v0.0.4:tokenomics_mindmap.yaml > data/v0.0.4/tokenomics_mindmap.yaml

then bump `DATA_VERSION` in `terminology.html` (rebuild `kpis.html`) and
`DEFAULT_FILE` in `kiosk.html`. Keep released versions immutable; a booth
kiosk only changes when you deliberately point it at a new version.

`?data=<url>` overrides the pinned file for reviewing an unreleased YAML.
Opened from a network share or disk (file://), auto-load is blocked by the
browser and the page falls back to a one-time YAML file picker.

## WordPress

`terminology.html` and `kpis.html` follow the TF dual-role contract: the
`<div id="te-terminology">` block (ID-scoped CSS + one IIFE, zero external
requests besides the pinned YAML fetch) pastes into a Custom HTML block on a
`te_page`. One WordPress page hosts the view; the 827 individual terms each
get a URL via `?term=<slug>` rather than 827 uploaded pages. The glossary and
KPI views are the same tool in two modes, so they can share one WP page or use
two with the mode pinned.

## SEO: URL scheme for the 827 terms

No query strings anywhere in the page's links. Canonical scheme:

    /terminology          glossary index
    /terminology/<slug>   one term
    /kpi                  KPI index
    /kpi/<slug>           one KPI

One HTML file serves all four; the host rewrite (WordPress rule, nginx
`try_files`, or the repo demo server) maps every path to it and the page
reads the slug/mode from the path. `scripts/serve_demo.py` (kept in sync
with the host copy) is the reference rewriter.

Open caveat (unchanged from the 2026-10-06 SEO review): term content still
arrives via XHR/JS, so Google indexes it after a render delay and non-JS
scrapers see a shell. Path URLs fix the canonicalization side; if per-term
SEO gets serious the escalation is a static build emitting real pages from
the pinned YAML. Not needed while the map is draft.

On file:// (opened from the network share), links degrade to `#<slug>`
within the page and the toggle switches modes in place.

## Editing

- `terminology.html` is the only edit surface for the glossary/KPI views
  (one file, toggle + `?mode=kpi`; there is no separate kpis.html).
- `kiosk.html` is a copy of the mindmap repo's kiosk; changes intended to be
  permanent should be sent back to `tokenomics_mindmap` before re-copying.
- `vendor/` holds d3, js-yaml, qrcode locally so pages run with no CDN.

## License

CC BY 4.0, Tokenomics Foundation.
