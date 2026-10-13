#!/usr/bin/env python3
"""Tokenomics mind map MCP server + minimal chat explorer (host: agent@, port 8789).

Wraps the pinned mind map v0.0.3 (same file the :8788 terminology demo serves)
as an MCP server, per the Definitions WG Sprint 2 discussion (2026-09-29):
an agent takes a plain-language description and places it in the map
(breadcrumb + neighbours), linking to the glossary page for each term.

    /mcp              MCP endpoint (Streamable HTTP) for any MCP client
    /                 chat explorer UI (index.html)
    /api/chat         POST {messages:[...], model?} -> {reply, trace, model,
                      elapsed_s, usage}; the agent's tools are called through
                      a real MCP client session
    /api/info         models available now + data version + tool list
    /assets/*         logo/icon

Env: MCP_DEMO_PORT (8789),
     LLM_BACKENDS (comma list, default :30001 Gemma, :30000 Qwen; models are
                   discovered live from each /v1/models),
     LLM_MODEL (default model id), GLOSSARY_PORT (8788).
"""
import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

import httpx
import uvicorn
import yaml
from mcp import Client
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

ROOT = Path(__file__).resolve().parent
DATA_VERSION = "v0.0.3"
def _find(rel: str) -> Path:
    """Look in the app dir, then one level up: the standalone host demo
    vendors data/ and assets/ inside explorer/, the repo copy shares the
    landscape_ui pins (data/, assets/ at repo root)."""
    for base in (ROOT, ROOT.parent):
        p = base / rel
        if p.exists():
            return p
    raise FileNotFoundError(rel)


YAML_PATH = _find(f"data/{DATA_VERSION}/tokenomics_mindmap.yaml")
PORT = int(os.environ.get("MCP_DEMO_PORT", "8789"))
LLM_BACKENDS = [u.strip().rstrip("/") for u in os.environ.get(
    "LLM_BACKENDS", "http://127.0.0.1:30001/v1,http://127.0.0.1:30000/v1").split(",") if u.strip()]
LLM_MODEL = os.environ.get("LLM_MODEL", "")  # default pick; else first backend's model
GLOSSARY_PORT = os.environ.get("GLOSSARY_PORT", "8788")
MAX_TOOL_ROUNDS = 6

# --------------------------------------------------------------------------
# Data: flatten exactly like terminology.html so slugs match /terminology/<slug>
# --------------------------------------------------------------------------

def slugify(s: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


def _get(d, key):
    if not isinstance(d, dict):
        return None
    for k in (key, key.lower(), key.upper()):
        if k in d:
            return d[k]
    return None


TERMS: list[dict] = []
BY_SLUG: dict[str, dict] = {}


def _flatten(name, node, path, parent):
    rec = {
        "name": name,
        "path": path,
        "branch": path.split(" > ")[1] if " > " in path else path,
        "type": str(_get(node, "Type") or "Concept"),
        "description": str(_get(node, "Description") or ""),
        "links": list(_get(node, "Links") or []),
        "slug": slugify(path.replace(" > ", " ")),
        "parent": parent,
        "children": [],
    }
    TERMS.append(rec)
    BY_SLUG[rec["slug"]] = rec
    ch = _get(node, "children") or {}
    if isinstance(ch, dict):
        for k, v in ch.items():
            rec["children"].append(_flatten(str(k), v, f"{path} > {k}", rec["slug"])["slug"])
    return rec


def load():
    doc = yaml.safe_load(YAML_PATH.read_text())
    (root_name, root_node), = doc.items()
    _flatten(str(root_name), root_node, str(root_name), None)


load()

# ---- tiny BM25 over name/path/description --------------------------------
_STOP = set("a an and are as at be by for from how in into is it its of on or that the this to with what which who does do i we our my".split())


def _tok(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", s.lower()):
        if w in _STOP:
            continue
        for suf in ("ing", "ies", "es", "s", "ed"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.append(w)
    return out


_DOCS = []
for t in TERMS:
    name_toks = _tok(t["name"])
    body = _tok(t["description"]) + _tok(t["path"])
    _DOCS.append((t, Counter(name_toks * 3 + body), len(name_toks) * 3 + len(body)))
_N = len(_DOCS)
_AVG = sum(d[2] for d in _DOCS) / _N
_DF = Counter(w for _, tf, _ in _DOCS for w in tf)


def _search(query: str, limit: int, kind: str | None):
    q = _tok(query)
    ql = query.lower().strip()
    scored = []
    for t, tf, ln in _DOCS:
        if kind and t["type"].lower() != kind.lower():
            continue
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (_N - _DF[w] + 0.5) / (_DF[w] + 0.5))
                s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * ln / _AVG))
        if ql and ql == t["name"].lower():
            s += 25
        elif ql and ql in t["name"].lower():
            s += 8
        if s > 0:
            scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def _brief(t: dict) -> dict:
    return {"name": t["name"], "slug": t["slug"], "type": t["type"], "path": t["path"],
            "description": t["description"], "glossary_path": f"/terminology/{t['slug']}"}


def _resolve(ref: str) -> dict | None:
    ref = ref.strip()
    if ref in BY_SLUG:
        return BY_SLUG[ref]
    s = slugify(ref.replace(" > ", " "))
    if s in BY_SLUG:
        return BY_SLUG[s]
    exact = [t for t in TERMS if t["name"].lower() == ref.lower()]
    if exact:
        return exact[0]
    hits = _search(ref, 1, None)
    return hits[0][1] if hits else None


# --------------------------------------------------------------------------
# MCP server
# --------------------------------------------------------------------------
mcp = MCPServer(
    name="tokenomics-mindmap",
    title="Tokenomics Mind Map",
    version=DATA_VERSION,
    instructions=(
        "Read-only access to the Tokenomics Foundation concept map "
        f"(mind map {DATA_VERSION}, {len(TERMS)} terms under Production, Consumption, Value). "
        "Use search_concepts to find candidates for a plain-language description, then "
        "get_concept to place a term in the map (breadcrumb, parent, siblings, children). "
        "Definitions are the map's own text; do not invent terms that are not in the map."
    ),
)


@mcp.tool(description="List the map's top-level branches (Production, Consumption, Value) and their first-level categories.")
def list_branches() -> dict:
    root = TERMS[0]
    return {
        "map_version": DATA_VERSION,
        "root": _brief(root),
        "branches": [
            {**_brief(BY_SLUG[b]), "categories": [BY_SLUG[c]["name"] for c in BY_SLUG[b]["children"]]}
            for b in root["children"]
        ],
    }


@mcp.tool(description=(
    "Search the mind map for terms matching a word, phrase, or plain-language description "
    "of an idea. Returns ranked candidates with breadcrumb path and definition. "
    "Optional kind filters by entry type: 'Concept' or 'KPI'."))
def search_concepts(query: str, limit: int = 8, kind: str | None = None) -> dict:
    limit = max(1, min(int(limit), 25))
    hits = _search(query, limit, kind)
    return {"query": query, "count": len(hits),
            "results": [{**_brief(t), "score": round(s, 2)} for s, t in hits]}


@mcp.tool(description=(
    "Get one term by slug, exact name, or breadcrumb path ('Tokenomics > Consumption > ...'). "
    "Returns its definition, links, breadcrumb, parent, siblings, and children, so the term "
    "can be placed in context."))
def get_concept(ref: str) -> dict:
    t = _resolve(ref)
    if not t:
        return {"error": f"No term found for {ref!r}. Try search_concepts."}
    crumbs, p = [], t["parent"]
    while p:
        crumbs.insert(0, {"name": BY_SLUG[p]["name"], "slug": p})
        p = BY_SLUG[p]["parent"]
    sibs = [BY_SLUG[s]["name"] for s in BY_SLUG[t["parent"]]["children"] if s != t["slug"]] if t["parent"] else []
    return {
        **_brief(t),
        "links": t["links"],
        "breadcrumb": crumbs,
        "parent": _brief(BY_SLUG[t["parent"]]) if t["parent"] else None,
        "siblings": sibs[:30],
        "children": [{"name": BY_SLUG[c]["name"], "slug": c, "type": BY_SLUG[c]["type"]} for c in t["children"]],
    }


@mcp.tool(description="List the KPIs (measurable metrics) in the map, optionally limited to one branch: Production, Consumption, or Value.")
def list_kpis(branch: str | None = None) -> dict:
    ks = [t for t in TERMS if t["type"].upper() == "KPI" and (not branch or t["branch"].lower() == branch.lower())]
    return {"count": len(ks), "kpis": [{"name": t["name"], "slug": t["slug"], "path": t["path"]} for t in ks]}


@mcp.resource(f"mindmap://{DATA_VERSION}/yaml", name="mindmap-yaml", mime_type="application/yaml",
              description="The raw pinned mind map YAML.")
def raw_yaml() -> str:
    return YAML_PATH.read_text()


@mcp.prompt(description="Explore: describe an idea in your own words and get it placed in the Tokenomics map.")
def explore(idea: str) -> str:
    return f"I have this idea and want to know what the Tokenomics map calls it and where it sits: {idea}"


# --------------------------------------------------------------------------
# Chat agent: local OpenAI-compatible model, tools via an MCP client session
# --------------------------------------------------------------------------
SYSTEM = f"""You are the Tokenomics Mind Map guide for the Tokenomics Foundation (mind map {DATA_VERSION}).
People describe an idea, sometimes without knowing the word for it. Your job:
1. Use the tools to find the matching term(s) in the map. Search more than once with different wording if the first search is weak.
2. Answer with the term name, its breadcrumb (where it sits: Production, Consumption, or Value, and the categories above it), and its definition from the map. Mention one or two neighbouring terms when they help.
3. If the description is ambiguous between different parts of the map (for example AI used inside the company versus AI built into a product, or producing versus consuming AI), say so and ask one short clarifying question.
4. Only use terms and definitions returned by the tools. If nothing fits, say the map does not cover it yet; that is useful feedback for the working group.
Format: plain short paragraphs. Write each term you cite as [[slug|Term Name]] using the slug from the tools, so the interface can link it. No em dashes. Keep answers under 180 words."""


async def _discover() -> dict[str, dict]:
    """Ask every backend in LLM_BACKENDS what it serves, at request time, so a
    model swapped on :30000/:30001 shows up without restarting this server.
    Returns {model_id: {"base": url, "label": short name, "up": bool}}."""
    found: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=4) as c:
        for base in LLM_BACKENDS:
            try:
                for m in (await c.get(f"{base}/models")).json()["data"]:
                    found.setdefault(m["id"], {"base": base, "label": _label(m["id"]), "up": True})
            except Exception:  # backend down: just omit it
                continue
    return found


def _label(model_id: str) -> str:
    short = model_id.split("/")[-1]
    return f"{short.split('-')[0].capitalize()} ({short})"


async def _pick(requested: str | None) -> tuple[str, str]:
    models = await _discover()
    if not models:
        raise RuntimeError("no local model endpoint is answering")
    if requested and requested in models:
        return requested, models[requested]["base"]
    if LLM_MODEL in models:
        return LLM_MODEL, models[LLM_MODEL]["base"]
    first = next(iter(models))
    return first, models[first]["base"]


_THINK = re.compile(r"<think>.*?</think>", re.S)


async def _tools_for_llm(client) -> list[dict]:
    res = await client.list_tools()
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "", "parameters": t.input_schema}} for t in res.tools]


def _result_text(res) -> str:  # mcp 2.x: snake_case fields
    if res.structured_content:
        return json.dumps(res.structured_content, ensure_ascii=False)
    return "\n".join(getattr(c, "text", "") for c in (res.content or []))


async def chat(request: Request) -> Response:
    body = await request.json()
    history = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant")][-12:]
    msgs = [{"role": "system", "content": SYSTEM}] + [{"role": m["role"], "content": str(m["content"])} for m in history]
    trace = []
    try:
        model, base = await _pick(body.get("model"))
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    t0 = time.monotonic()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def done(reply: str) -> Response:
        return JSONResponse({"reply": reply, "trace": trace, "model": model, "label": _label(model),
                             "elapsed_s": round(time.monotonic() - t0, 1), "usage": usage})

    async with Client(mcp) as client:  # real MCP session (in-process transport)
        tools = await _tools_for_llm(client)
        async with httpx.AsyncClient(timeout=180) as http:
            for _ in range(MAX_TOOL_ROUNDS + 1):
                r = await http.post(f"{base}/chat/completions", json={
                    "model": model, "messages": msgs, "tools": tools,
                    "temperature": 0.2, "max_tokens": 2500})  # headroom for reasoning models
                r.raise_for_status()
                data = r.json()
                for k in usage:
                    usage[k] += (data.get("usage") or {}).get(k, 0) or 0
                msg = data["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                if not calls:
                    return done(_THINK.sub("", msg.get("content") or "").strip())
                msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for call in calls:
                    fn = call["function"]["name"]
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    res = await client.call_tool(fn, args)
                    text = _result_text(res)
                    trace.append({"tool": fn, "args": args, "result": json.loads(text) if text.startswith("{") else text})
                    msgs.append({"role": "tool", "tool_call_id": call["id"], "content": text[:12000]})
    return done("I ran out of tool rounds; try a narrower question.")


async def info(request: Request) -> Response:
    models = await _discover()
    try:
        default, _ = await _pick(None)
    except RuntimeError:  # no model endpoint up: UI still loads
        default = None
    tools = await mcp.list_tools()
    return JSONResponse({"version": DATA_VERSION, "terms": len(TERMS),
                         "kpis": sum(t["type"].upper() == "KPI" for t in TERMS),
                         "models": [{"id": k, "label": v["label"], "base": v["base"]} for k, v in models.items()],
                         "default_model": default, "glossary_port": GLOSSARY_PORT,
                         "tools": [{"name": t.name, "description": t.description} for t in tools]})


@mcp.custom_route("/", methods=["GET"])
async def index(request: Request) -> Response:
    return FileResponse(ROOT / "index.html")


@mcp.custom_route("/api/chat", methods=["POST"])
async def _chat(request: Request) -> Response:
    return await chat(request)


@mcp.custom_route("/api/info", methods=["GET"])
async def _info(request: Request) -> Response:
    return await info(request)


@mcp.custom_route("/assets/{name}", methods=["GET"])
async def assets(request: Request) -> Response:
    name = request.path_params["name"]
    try:
        p = _find(f"assets/{Path(name).name}").resolve()
    except FileNotFoundError:
        return Response(status_code=404)
    if p.parent not in [(ROOT / "assets").resolve(), (ROOT.parent / "assets").resolve()] or not p.is_file():
        return Response(status_code=404)
    return FileResponse(p)


app = mcp.streamable_http_app(host="0.0.0.0", stateless_http=True, json_response=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
