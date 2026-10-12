# Mind Map Explorer

An MCP server over the Tokenomics mind map plus a minimal chat interface,
demoed live at the Definitions WG call on 2026-10-06. It is the Sprint 2 "MCP
unifying the underlying sources" item (see the WG summary from 2026-09-29): a
person describes an idea in their own words, the agent searches the map, and
answers with the term name, its breadcrumb (where it sits under Production,
Consumption, or Value), and the map's own definition. Every term it cites links
to its page in `terminology.html`.

## What is in here

| File | Role |
|---|---|
| `server.py` | One process, three surfaces: the MCP endpoint, the chat page, and two JSON APIs |
| `index.html` | The chat page (vanilla JS, TF dark theme, model picker) |
| `requirements.txt` | Python deps (`uv venv && uv pip install -r requirements.txt`) |

## Architecture (the 30-second version)

MCP is a client/server protocol. An agent (Claude Desktop, Claude Code, or any
MCP-capable client) is the client; this process is the server. The client asks
"what tools do you have?", sees four typed functions, and the model decides
which to call. The server never talks to a model itself; a model calling these
tools could be running on someone's laptop or in a data center.

```
                 ┌────────────────────────── one process ──────────────────────────┐
 browser ──────► │ /            chat page (index.html)                             │
                 │ /api/chat    POST {messages, model?}                            │
 WG member ─────►│                │                                                │
 own agent ────► │ /mcp           ▼                                                │
 (Streamable      │   tool loop ──► local OpenAI-compatible endpoint              │
  HTTP)           │   (≤6 rounds)     (:30001 Gemma, :30000 Qwen, or Claude via    │
                 │        │            an OpenAI-compatible gateway)               │
                 │        ▼                                                       │
                 │   MCP tools  ── search_concepts / get_concept /                │
                 │                 list_branches / list_kpis                      │
                 │        ▼                                                       │
                 │   pinned data/v0.0.2/tokenomics_mindmap.yaml (read-only,       │
                 │   in memory: 823 terms, BM25 search, slugs shared with         │
                 │   terminology.html so links line up)                           │
                 └────────────────────────────────────────────────────────────────┘
```

Key properties, all deliberate for the working-group demo:

- **One YAML, pinned.** The server loads the same versioned data file as the
  glossary and kiosk views (`data/<version>/tokenomics_mindmap.yaml`, never a
  live branch). Slugs are computed exactly as `terminology.html` computes them,
  so agent answers deep-link into the glossary at `/terminology/<slug>`.
- **Read-only tools.** Search by phrase or plain-language description (BM25
  ranking), fetch one term with breadcrumb/parent/siblings/children, list
  branches, list KPIs (filterable by branch). Nothing writes.
- **The chat page is just another MCP client.** `/api/chat` drives a real
  in-process MCP session against the same tools external agents use, so what
  the page demonstrates is exactly what a member's own agent would do. The
  side panel shows every tool call with its result.
- **Model-agnostic chat.** The model is chosen per request from any
  OpenAI-compatible `/v1/models` endpoint; the page lists what the local
  endpoints are serving right now and offers "Compare all side by side"
  (same question to every model, each answer stamped with time, tool calls,
  and tokens).
- **The MCP endpoint itself needs no model and no key.** That half can be
  hosted anywhere; model choice and keys stay on the client side.

## Running it

```bash
uv venv && uv pip install --python .venv/bin/python -r explorer/requirements.txt
.venv/bin/python explorer/server.py          # http://localhost:8789
```

Environment: `MCP_DEMO_PORT` (8789), `LLM_BACKENDS` (comma-separated
OpenAI-compatible base URLs, default `http://127.0.0.1:30001/v1,
http://127.0.0.1:30000/v1`), `LLM_MODEL` (default model id; unknown names fall
back), `GLOSSARY_PORT` (8788, used only to build term links in the page).

## Using it from your own agent

Streamable HTTP, no auth (LAN demo): endpoint `http://<host>:8789/mcp`.

```json
{ "mcpServers": { "tokenomics-mindmap": { "type": "http", "url": "http://<host>:8789/mcp" } } }
```

## Not on GitHub Pages (and why)

`/mcp`, `/api/chat`, and model keys require a server process; Pages serves
static files only. The static glossary/kiosk pages stay on Pages; the Explorer
needs the small always-on host (same box and pattern as the terminology demo
on :8788). A Pages-only variant that calls a model API from the browser is
possible but would ship the MCP tool logic to the browser and any visitor's
key with it; a gated demo mode (server-hosted, small per-member tokens) is the
next step tracked for Sprint 2.

## License

Code MIT (repo LICENSE); mind map content CC BY 4.0, Tokenomics Foundation.
