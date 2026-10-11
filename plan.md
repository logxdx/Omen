# Omen Rebuild Plan

Goal: a personal assistant that is **reliable on small local models** (Ollama, ~4–14B), with one agent core driving a **TUI**, a **web UI** and **voice**, and **generative UI** components the agent includes in its responses.

Generic harnesses (pi, Claude Code, Codex) assume a strong model. Omen should assume a weak one: few tools in context at a time, short and capped outputs, typed tool calls with validation errors fed back, and no decisions the model doesn't need to make.

---

## 0. Rebuild strategy: fresh core, same repo

**Decision: write the new core from scratch as a new `omen/` package in this repo; port leaf code; delete the old stack at the end.** Not an incremental refactor.

Why:
- The new design replaces every structural layer — the openai-agents SDK (→ own loop), 7 agents + handoffs (→ personas + skills), `cli/v1.py` (→ Textual TUI + web), the scraper (→ crawlberg), the context manager (→ compaction). Refactoring in place means keeping the SDK, handoff wiring and CLI working at every step for a design that keeps none of them.
- Measured: **~7,400 LOC is replaced outright** (runtime, agents, CLI, tool wrappers, scraper, context manager, unused modules). **~930 LOC of logic is worth porting**, plus the vendored WhisperSTT (2,672 LOC, moved as-is) and ~875 lines of prompt/persona text.

Why the same repo rather than a new one: keeps the name, git history, `.env`, `root/` sandbox data and issue trail. The old app keeps running untouched while the new one is built.

| Carry over | Into |
|---|---|
| `tools/utils/filesystem.py` (fix sandbox with `resolve()`) | `skills/files/tools.py` |
| `tools/utils/weather.py`, `download.py`, `DuckDuckGoSearch.py`, `YoutubeSearch.py` | `skills/weather`, `skills/media`, `skills/web` |
| `stt/WhisperSTT.py`, `tts/KokoroTTS.py` (fix `<think>` stripping, pass query) | `omen/voice/` |
| `my_agents/*/prompt.py`, `config/agent_personality.py` (rewrite shorter) | `personas/*.md`, `skills/*/SKILL.md` |
| `cli/art.py`, `config/ui_config.py` theme | `omen/tui/` |
| `.env` keys, `config/agent_config.py` model settings | `omen/config.py` (one model block + extractor block) |

Everything else (`my_agents/`, `agent_runtime.py`, `cli/v1.py`, `tools/*.py` wrappers, `tools/utils/scraper.py`, context manager, task/ui/computer/exec tools, Searx/Omni, Piper, Parakeet, `spider-py/`) is deleted in Phase 7 once the new TUI reaches parity.

Workflow: build on a long-lived `rebuild` branch; `uv run omen` (new) and `uv run python main.py` (old) coexist until cut-over.

---

## 1. Why the current harness struggles

Prompt size is not the problem — fixed overhead is ~1–1.5k tokens per call. The problems are structural:

- **Nested loops.** Triage calls `ask_web_search_agent` / `ask_filesystem_agent`, each a full agent loop with `max_turns=MAX_TURNS` (50) inside an outer 50-turn loop (`my_agents/base_agent.py:156-163`, `cli/v1.py:423`). Worst case ~2,500 LLM calls; the UI is silent while a subagent runs.
- **Unbounded outputs, untrimmed history.** `read_file`, `scrape_url` and search have no caps. History is `result.to_input_list()` re-sent in full every turn (`cli/v1.py:623-632`).
- **Prompt/tool mismatches.** Prompts reference tools that don't exist (`web_search`, `parse_document`, `screenshot_document`) and wrong subagent names (`web_search_agent` vs `ask_web_search_agent`).
- **Fragile run config.** A hallucinated tool name aborts the run (`tool_not_found_behavior="raise_error"` default). No temperature, `parallel_tool_calls`, `max_tokens`, or loop guard.
- **Hidden LLM calls.** `scrape_url` summarises every page with another LLM call; the web prompt demands 3–5 scrapes; the context manager adds 2 runs per turn; TTS summarises any reply > 200 chars.
- **Security.** Filesystem sandbox check is `str(SANDBOX_PATH) in str(full_path)` with no `resolve()` — `../../etc/passwd` passes (`tools/utils/filesystem.py:57`).

### Scraper verdict

`scrape_url` → `tools/utils/scraper.py` (spider_rs + bs4 + html2text + LLM summary) is not sufficient: no block detection (Cloudflare pages returned as content), text corruption (`:457` strips `\n`, `:460` unescapes after serialising), no truncation, `"pdf" in url` routing to Jina, and `spider_rs` depends on the untracked 1.8 GB `spider-py/` (`pyproject.toml:42`).

**Decision:** use the `crawlberg` Python package directly (`create_engine(CrawlConfig(...))` + `await scrape(engine, url)`, main-content `fit_content`), port the ~60-line marker logic from `scraper-api/app/engines/blocking.py`. The scraper-api service (Postgres + Redis + MinIO) is overkill for a single user; call it over HTTP only if it's already running.

---

## 2. Inspiration: pi (pi.dev)

pi (now `github.com/earendil-works/pi`) is a deliberately minimal coding agent. What to take, and what not to:

| pi idea | Omen adoption |
|---|---|
| System prompt + tools < 1k tokens; 4 core tools | **Adopt.** ≤ 8 tools visible per turn, core prompt ≤ 400 tokens. |
| Own provider layer (`pi-ai`) with per-backend `compat` flags, streaming events, partial-JSON tool args | **Adopt.** Thin LiteLLM wrapper + compat table (`enable_thinking`, developer role, `max_tokens` field, tool-call-in-reasoning quirks). |
| Validate tool args (JSON Schema/AJV); return errors as `isError` tool results so the model retries | **Adopt** with Pydantic. Never crash on a bad call. |
| Tool result = `content` (for LLM) + `details` (for UI/state) | **Adopt.** This is the backbone of generative UI (§5). |
| Agent loop events (`turn_*`, `message_*`, `tool_execution_*`); steering + follow-up queues; `abort()` | **Adopt.** User can type while the agent runs; voice barge-in = abort. |
| Skills: `SKILL.md` (agentskills.io spec), only name + description in prompt, read on demand, `/skill:name` to force | **Adopt and extend** — Omen skills also carry typed tools (§4). |
| Sub-agents as an example extension: persona markdown files (`name`, `description`, `tools`, `model`), single/parallel/chain | **Adopt** as personas (§4). |
| JSONL session tree (`id`/`parentId`), branching, structured compaction (Goal / Progress / Decisions / Next steps), never split a tool call from its result | **Adopt.** Branching is cheap recovery when a small model drifts. |
| RPC mode: JSON over stdio so any frontend drives the core | **Adopt as AG-UI over SSE** (§5) — same idea, existing web tooling. |
| Differential-rendering TUI (`pi-tui`) | Reference only — use Textual in Python. |
| "Codemode": model writes JS that calls tools in a sandbox | **Reject** for now — small models write worse code than they make typed tool calls. |
| No permission gates ("YOLO") | **Reject** — a personal assistant touches personal files; destructive ops need confirmation via a UI choice component. |

---

## 3. Target architecture

```
                ┌──────────── frontends ─────────────┐
                │  TUI (Textual)   Web (React)  Voice│
                └──────┬───────────────┬────────┬────┘
            in-process │     AG-UI/SSE │        │ text fallback
                ┌──────▼───────────────▼────────▼────┐
                │  omen.server (FastAPI) / event bus │
                ├────────────────────────────────────┤
                │  omen.core.loop   ← personas/*.md  │
                │   tool registry   ← skills/*/      │
                │   session (JSONL tree) + compaction│
                │  omen.core.llm  (LiteLLM + compat) │
                └────────────────────────────────────┘
```

Proposed layout:

```
omen/
  core/
    llm.py          # LiteLLM wrapper, compat table, streaming → events
    loop.py         # agent loop: turns, tool exec, steering/follow-up queues, abort, loop guard
    events.py       # internal event types (mirror AG-UI)
    tools.py        # @tool decorator, Pydantic validation, ToolResult(content, details)
    skills.py       # discover skills/, load_skill → expose tools
    personas.py     # discover personas/, delegate()
    session.py      # JSONL tree, branching, labels
    compaction.py   # trigger + structured summary
  ui/
    components.py   # UIPayload models (single source of truth) → JSON Schema → TS types
    extractor.py    # trigger rules + tiny JSON model (LFM2.5-350M) fills component props
  server.py         # FastAPI: POST /agent → AG-UI SSE; serves web build
  tui/              # Textual app + component renderers
  web/              # Vite + React + assistant-ui
  voice/            # STT/TTS adapters (lazy-loaded)
skills/
  web/      SKILL.md  tools.py   # search, read_url (crawlberg)
  files/    SKILL.md  tools.py   # list, read, write, edit, grep (sandboxed)
  memory/   SKILL.md  tools.py   # remember, recall
  weather/  SKILL.md  tools.py
  media/    SKILL.md  tools.py   # download_audio, download_video
  resume/   SKILL.md  references/ ...
personas/
  researcher.md  tutor.md  ideator.md  resume-writer.md
evals/
  tasks.yaml        # fixed small-model task set
```

**Decision: own the loop, drop the openai-agents SDK.** The new requirements — tools exposed dynamically per turn, `content`/`details` split, steering queue, AG-UI events, persona delegation with a shared session tree — all fight the SDK. A plain loop on LiteLLM is ~300 lines and gives full control over malformed-call repair (fuzzy-match near-miss tool names, retry once with the validation error). This reverses the earlier "stay on the SDK" call.

---

## 4. Tools, skills and personas

Three mechanisms, each doing one job:

### 4.1 Core tools — always visible (≤ 4)

| Tool | Purpose |
|---|---|
| `load_skill(name)` | Load a skill's instructions and expose its tools from the next step on |
| `delegate(persona, task)` | Hand a self-contained task to a persona; get its final answer back |
| `ask_user(question, options)` | Ask for a choice/confirmation (renders as a choice component) |
| `remember(fact)` | Long-term memory write (recall is automatic, §4.4) |

### 4.2 Skills — tools live inside skills, loaded on demand

Each skill is a folder following the agentskills.io `SKILL.md` format, plus an optional `tools.py`:

```markdown
---
name: web
description: Search the web and read pages. Use for current events, facts, prices, docs.
tools: [search, read_url]
---
1. Call `search` once with a short query.
2. Call `read_url` on the 1–2 most relevant results. Pass `query` to get only relevant paragraphs.
3. Answer in 3–5 sentences and cite URLs.
```

- The system prompt lists only skill `name: description` lines (~15 tokens each).
- `load_skill("web")` returns the body as `content` and registers `search` / `read_url` as visible tools **for the rest of the turn** (unloaded at turn end, unless pinned by a persona).
- Skills without `tools.py` are pure instructions/references (e.g. resume templates) — the pi model.
- **Why not "every tool is just docs + bash" like pi:** small models are much better at a typed 3-argument tool call than at composing CLI invocations from a README.
- **Small models under-trigger skills**, so add a cheap **pre-router**: before each turn, keyword/embedding-match the user message against skill descriptions and auto-load the top match (≤ 1). `/skill:name` forces one. Log hit rates in evals.
- Hot reload (`/reload`) rescans `skills/` and `personas/`.

### 4.3 Personas — instead of hard-coded subagents

A persona is a markdown file; the body is its system prompt:

```markdown
---
name: researcher
description: Multi-source research with citations. Delegate when a question needs > 2 pages read.
skills: [web, memory]
model: jarvis            # optional per-persona model
max_turns: 8
---
You research one question thoroughly and return a short, cited answer...
```

- **Delegate:** `delegate("researcher", task)` runs a fresh loop with the persona's prompt and **only its skills pre-loaded**, sees just the task (not the whole conversation), returns the final answer as `content`; its transcript goes in `details` (collapsible in the UI) and into the session tree as a child branch.
- **One level only.** Personas cannot `delegate`. `max_turns` defaults to 8. This replaces the 50×50 nested loops.
- **Switch:** `/persona tutor` makes a persona the main agent for the conversation (replaces `/agents`). The default persona is Jarvis.
- **Dynamic personas (later):** the agent can draft a new `personas/*.md` or `skills/*/SKILL.md`; it's written only after the user approves via `ask_user`. Same for agent-written `tools.py` — it's code execution, so always gated.
- Parallel/chain delegation (pi's subagent modes) is deferred until the single mode works reliably on the local model.

### 4.4 Memory

- `remember(fact)` appends to `memory/facts.jsonl`.
- Recall is automatic: top-k relevant facts (BM25 first, embeddings later) are injected into the system prompt each turn. Small models forget to call `recall`.

---

## 5. Generative UI

### 5.1 Principle: most UI comes free from tool results

Every tool returns `ToolResult(content, details)`:
- `content` — short text the **model** sees (capped, ~1k tokens).
- `details` — a typed `UIPayload` the **frontend** renders.

So `search` automatically renders a results list, `read_url` a link-preview card, `weather` a weather card, `edit` a diff — **with zero extra effort from the model**. This is the most reliable generative UI for small models: the model never has to decide to render anything.

### 5.2 Explicit `show_*` components for things the model composes

A small `ui` skill (auto-loaded when the frontend supports it) with flat tools:

| Tool | Args (flat, scalar/list only) | Web | TUI |
|---|---|---|---|
| `show_table` | `title, columns: list[str], rows: list[list[str]]` | shadcn table | `DataTable` |
| `show_chart` | `title, kind: line\|bar, labels: list[str], values: list[float]` | Recharts | `Sparkline` / plotext |
| `show_choices` | `question, options: list[str]` | buttons | `OptionList` |
| `show_card` | `title, body, url?` | card | `Static` panel |
| `show_steps` | `title, steps: list[str]` | checklist | `ListView` |

Rules: 3–6 arguments, no nesting, at most ~5 `show_*` tools visible. The model writes no component trees.

### 5.3 Payload contract

```python
class UIPayload(BaseModel):
    type: str            # "weather", "table", "link_preview", "diff", ...
    version: int = 1
    props: dict          # validated by a per-type Pydantic model
    text: str            # plain-text fallback (voice, markdown clients, unknown types)
```

- Pydantic models in `omen/ui/components.py` are the single source of truth → export JSON Schema → generate TS types for the web.
- **Capability negotiation:** frontends advertise supported `type`s in AG-UI `RunAgentInput.forwardedProps`. Voice or a too-weak model → the `ui` skill is not offered and the model answers in markdown; tool `details` still degrade to `text`.
- Unknown `type` → render `text` as markdown. Invalid `show_*` args → validation error back to the model once, then fall back to text.
- Later interop: the server can translate payloads to Google A2UI `updateComponents` without the model ever writing A2UI.

### 5.4 Extractor sidecar: a tiny JSON model fills components

Small main models are unreliable at authoring JSON; tiny specialised models with constrained decoding are not. So the main model mostly **talks**, and a sidecar model **structures**.

**Component pipeline (per assistant turn):**

1. **Trigger — no LLM.** Run only when (a) a tool with a known component mapping returned data (weather → weather card, search → link cards, list/CSV → table), (b) the main model ends with a one-token hint tag like `<ui:table>` / `<ui:choices>`, or (c) heuristics fire (markdown table, numbered options ending in "?", URLs).
2. **Select — cheapest first.** Tool→component rule map → main model's hint tag → optional extractor classification call with `format={"enum": [..., "none"]}`. Never pick and fill in the same call.
3. **Fill.** If the tool result is already structured (weather JSON), map it directly — no LLM. Otherwise call the extractor with the component's Pydantic schema.
4. **Validate & render.** Pydantic validation → `UIPayload` → frontends. The text answer streams first; the component attaches when ready (~0.3–2 s). Extraction never blocks the chat answer.

**Extractor setup:**

- Model: **LFM2.5-350M** (Q8, `hf.co/LiquidAI/LFM2.5-350M-GGUF`, ~0.5 GB VRAM) via Ollama; escalate to **LFM2.5-1.2B-Instruct** if field accuracy is poor in evals. Licence: LFM Open v1.0 (free under $10M revenue — fine for personal use). Apache alternatives if needed: Osmosis-Structure-0.6B, Qwen3.5-0.8B (unverified for this task).
- Always with **Ollama structured outputs**: `format=Model.model_json_schema()`, `temperature=0`, single turn, `keep_alive=-1` so it stays resident next to the main model. Grammar guarantees parseable JSON, not correct values — still validate.
- Prompt: system = "Extract a `<component>` from CONTEXT. Use only values present in it. Use null or [] if absent. Schema: {…}"; user = `CONTEXT:` tool result first, then the assistant answer, truncated to ~2–4k tokens.
- Schemas stay flat, with `enum` and `maxItems` caps (e.g. ≤ 20 rows). Strip `<think>` before parsing.
- **Fallback chain:** validation fails → retry once with the error → escalate to 1.2B (or the main model with `format`) → give up and show the plain text / markdown table.

**Evaluated and not chosen as the default:**

| Model | Why not (yet) |
|---|---|
| Cactus **Needle** (25–121M, Apache-2.0, schema-constrained, confidence + empty-list output) | No GGUF; runs only in the Cactus runtime (pip `cactus-needle` / `--serve`), not Ollama/llama.cpp. Prototype later as the component **classifier** (step 2) — its confidence score and "nothing fits" output suit that job. |
| LFM2-350M/1.2B-**Extract** | Deprecated by Liquid in favour of LFM2.5. |
| NuExtract 2.0 / 3 | Best pure extraction quality, but 2–4B vision-language models (heavy for a sidecar) and template-based rather than JSON Schema. Candidate if LFM2.5 accuracy disappoints. |
| xLAM-2 small, Arch-Function | Non-commercial / restrictive licences; function calling rather than extraction. |

This makes `show_*` tools (§5.2) **optional**: keep them for models strong enough to call them, but the default path is tool-result mapping + hint tags + the extractor.

### 5.5 Options considered

| Option | Verdict |
|---|---|
| **AG-UI** (CopilotKit protocol, MIT, Python `ag-ui-protocol`) | **Wire protocol.** Event families for text, tool calls/results, state, reasoning. No openai-agents integration yet — irrelevant since we own the loop. |
| **assistant-ui** + `@assistant-ui/react-ag-ui` | **Web frontend.** One `makeAssistantToolUI` per payload type. |
| Google A2UI (v0.9/1.0-rc) | Too heavy for the model to author (ID-linked component trees + JSON Pointer bindings). Future server-side export target. |
| vercel-labs json-render | Same authoring problem; no Python. Its Ink renderer is a useful TUI reference. |
| MCP Apps / MCP-UI | HTML iframes — can't render in a TUI. Only for embedding third-party MCP apps in the web UI later. |
| OpenAI ChatKit | Web-only widgets, OpenAI-platform domain key. Drop (the `agent_runtime.py` docstring mentions it). |
| Thesys C1 | Hosted model — conflicts with local-first. |
| CopilotKit (full), Tambo, Hashbrown | Heavier / own agent runtime / reported weak with small models. |

---

## 6. Frontends

All frontends consume the same event stream. Events mirror AG-UI: `RUN_STARTED`, `TEXT_MESSAGE_*`, `REASONING_*`, `TOOL_CALL_START/ARGS/END`, `TOOL_CALL_RESULT` (carries `UIPayload`), `STATE_*`, `RUN_FINISHED/ERROR`.

### 6.1 TUI — Textual

- Runs the core **in-process** (no server needed); `omen tui --remote URL` can attach to a running server instead.
- Layout: scrolling transcript, input box that stays active while the agent runs (→ steering queue), status bar (model, persona, context %, tokens/s).
- Streaming markdown; reasoning in a collapsed `Collapsible`; each tool call as a collapsible row (name, args, duration) with its `UIPayload` rendered below.
- Renderer registry: `RENDERERS: dict[str, Callable[[props], Widget]]`; unknown → `Markdown(text)`.
- `show_choices` / `ask_user` render as focusable `OptionList`; the selection is sent back as the tool result.
- Slash commands: `/persona`, `/skill`, `/tree` (session branches), `/compact`, `/model`, `/voice`, `/clear`, `/quit`. Command palette via Textual's built-in.
- Esc = abort the current run.

### 6.2 Web UI — React + Vite + assistant-ui

- `omen serve` → FastAPI `POST /agent` streams AG-UI over SSE and serves the built web app.
- assistant-ui thread with `@assistant-ui/react-ag-ui`; one tool UI per payload type (shadcn/ui, Recharts).
- Sidebar: sessions and branches (from the JSONL tree), persona picker, skill list.
- Choice/confirmation components post back as tool results. Push-to-talk mic button → voice pipeline on the server.
- Requires Node only to build; the built assets ship with the Python package.

### 6.3 Voice

- A frontend like the others: STT → `prompt`, consumes `TEXT_MESSAGE_*` + `UIPayload.text`, never sees components.
- Barge-in = `abort()`. TTS summarisation only for replies > ~60 words, with `<think>` stripped and the user's query passed in.
- STT/TTS lazy-loaded so text mode starts without torch.

---

## 7. Phases

### Phase 0 — Minimal fixes to the old app (only if you keep using it during the rebuild)

- [ ] Sandbox: `full_path.resolve().is_relative_to(SANDBOX_PATH)` in one helper used by every filesystem op. (Do this regardless — it's a security hole.)
- [ ] `RunConfig(tool_not_found_behavior="return_error_to_model")`; `MAX_TURNS` ≈ 10.
- [ ] Skip everything else — the old code is deleted in Phase 7.
- [ ] Create the `rebuild` branch and the empty `omen/` package with its own entry point (`[project.scripts] omen = "omen.__main__:main"`).

### Phase 1 — Core loop

- [ ] `core/llm.py`: LiteLLM streaming → internal events; compat table per backend (Ollama: `enable_thinking=false` for Qwen/Gemma tool calls, no developer role); temperature ≈ 0.3, `max_tokens` cap, `parallel_tool_calls=False`.
- [ ] `core/tools.py`: `@tool` from type hints → JSON Schema; Pydantic validation; errors returned as `is_error` results; fuzzy-match near-miss tool names; `ToolResult(content, details)` with hard `content` cap.
- [ ] `core/loop.py`: turns, tool execution, steering + follow-up queues, `abort()`, loop guard (2 identical calls → nudge, 3 → stop), `max_turns`.
- [ ] `core/session.py`: append-only JSONL tree, branch from any entry, labels.
- [ ] `evals/tasks.yaml` + runner: ~20 fixed tasks (search+answer, read file, edit file, weather, delegate, ask_user) run against the local model; report tool-call validity, task success, LLM calls per task. Run after every later phase.

### Phase 2 — Skills and core tools

- [ ] `core/skills.py`: discover `skills/*/SKILL.md`, parse frontmatter, `load_skill`, per-turn tool exposure, `/skill:name`, `/reload`.
- [ ] Pre-router (keyword first; embeddings if hit rate is poor in evals).
- [ ] Port tools into skills:
  - `web`: `search` (one backend, 5 results) + `read_url(url, query=None, max_chars=3500)` on crawlberg — `fit_content`, block detection returning one-line `BLOCKED (cloudflare)` / `NOT_FOUND` / `TIMEOUT` / `JS_REQUIRED`, JS render only when `js_render_hint`, query → BM25 paragraph ranking, no LLM call.
  - `files`: `list`, `read(path, offset, limit)` plain text, `write`, `edit` (exact match), `grep` (lines, capped); destructive ops go through `ask_user`.
  - `memory`, `weather`, `media`, `resume` (instructions + templates).
- [ ] Automatic memory recall into the system prompt.

### Phase 3 — Personas and delegation

- [ ] `core/personas.py`: discover `personas/*.md`; `delegate(persona, task)` with fresh context, pre-loaded skills, `max_turns` 8, no nested delegation; transcript → `details` + session child branch.
- [ ] `/persona name` switch; default Jarvis persona from `config/agent_personality.py`.
- [ ] Port prompts to personas (researcher, tutor, ideator, resume-writer), each ≤ 250 tokens of plain instructions with exact tool names.

### Phase 4 — Event protocol and UI components

- [ ] `core/events.py` mirroring AG-UI; `server.py` FastAPI `POST /agent` → SSE using `ag-ui-protocol` encoder.
- [ ] `ui/components.py`: `UIPayload` + per-type props models; `details` for `search`, `read_url`, `weather`, `edit`, `read`.
- [ ] `ui/extractor.py`: trigger rules, tool→component map, hint-tag parsing, LFM2.5-350M via Ollama `format` + fallback chain; eval field accuracy on a fixed set of contexts.
- [ ] Optional `ui` skill with `show_table`, `show_chart`, `show_choices`, `show_card`, `show_steps` for stronger models.
- [ ] Capability negotiation via `forwardedProps`; schema export + TS type generation.

### Phase 5 — TUI (Textual)

- [ ] App shell, streaming transcript, live input → steering, Esc → abort, status bar.
- [ ] Renderer registry for every payload type + markdown fallback; interactive choices.
- [ ] Slash commands + command palette; `/tree` branch browser.

### Phase 6 — Web UI

- [ ] Vite + React + assistant-ui + `@assistant-ui/react-ag-ui`; tool UIs per payload type.
- [ ] Sessions/branches sidebar, persona picker; build step bundled into `omen serve`.

### Phase 7 — Voice, compaction, cleanup

- [ ] Voice as a frontend (lazy STT/TTS, barge-in, text fallback).
- [ ] Compaction: trigger at window − reserve; keep recent turns verbatim, never split call/result; structured summary (Goal / Constraints / Progress / Decisions / Next steps / Files touched).
- [ ] Delete the old stack: `my_agents/`, `agent_runtime.py`, `cli/v1.py`, handoff code, task/ui/computer/exec tools, Searx/Omni search, Piper, Parakeet, old scraper paths, `spider-py/`.
- [ ] Dependencies: drop `openai-agents`, `crawl4ai`, `liteparse`, `statsmodels`, `spider_rs`, `piper-tts`; add `crawlberg`, `textual`, `fastapi`, `ag-ui-protocol`. Torch only in a `voice` extra.
- [ ] Rewrite docs to match.

---

## 8. Success criteria

- ≤ 8 tools and ≤ 1.5k tokens of prompt + schemas visible on any turn.
- A typical question (search → read 1–2 pages → answer) completes in ≤ 6 LLM calls with no hidden summariser calls.
- No single tool `content` exceeds ~1k tokens; a 10-turn session fits an 8–16k context.
- A hallucinated tool name or bad arguments produces a recoverable error, never a crashed run.
- The same session renders in the TUI and the web UI with the same components; voice gets clean text.
- `uv sync` works on a fresh clone; text mode starts without torch.
- Eval suite: ≥ 90% valid tool calls and a tracked task-success rate on the local model.

## 9. Open decisions

- **General shell tool?** Recommend no for now — typed skills only; revisit with a sandbox + `ask_user` confirmation.
- **Node toolchain for the web build** — needed at build time only. Acceptable?
- **Default local model** for evals (current Modelfile `jarvis`; which base model and context size?).
