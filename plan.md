# Omen Rebuild Plan

Goal: a personal assistant that is **reliable on small local models** (Ollama, ~4–14B), with one agent core driving a **TUI**, a **web UI** and **voice**, and **generative UI** components the agent includes in its responses.

Generic harnesses (pi, Claude Code, Codex) assume a strong model. Omen should assume a weak one: few tools in context at a time, short and capped outputs, typed tool calls with validation errors fed back, and no decisions the model doesn't need to make.

---

## 0. Rebuild strategy: fresh core, same repo

**Decision: write the new core from scratch as a new `omen/` package in this repo; port leaf code; delete the old stack at the end.** Not an incremental refactor.

Why:
- The new design replaces every structural layer — the agent wiring (→ a forked SDK with a thin Omen runtime), 7 agents + handoffs (→ personas + skills), `cli/v1.py` (→ Textual TUI + web), the scraper (→ crawlberg), the context manager (→ compaction). Refactoring in place means keeping the SDK, handoff wiring and CLI working at every step for a design that keeps none of them.
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
| Own provider layer (`pi-ai`) with per-backend `compat` flags, streaming events, partial-JSON tool args | **Via the SDK.** `LitellmModel` + `ModelSettings` (`extra_body` for backend quirks such as `enable_thinking`). |
| Validate tool args (JSON Schema/AJV); return errors as `isError` tool results so the model retries | **Adopt** with Pydantic. Never crash on a bad call. |
| Tool result = `content` (for LLM) + `details` (for UI/state) | **Adopt.** This is the backbone of generative UI (§5). |
| Agent loop events (`turn_*`, `message_*`, `tool_execution_*`); steering + follow-up queues; `abort()` | **Adopt** via the fork: a mid-run message queue (delivered after the current turn) and `cancel()`. Voice barge-in = abort. |
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
                │  omen.core.runtime ← personas/*.md │
                │   tools / delegate ← skills/*/     │
                │   session (JSONL tree) + compaction│
                │  forked Agents SDK + LitellmModel  │
                └────────────────────────────────────┘
```

Proposed layout:

```
omen/
  core/
    runtime.py      # drives the forked SDK: message queue, abort, SDK stream → Omen events
    models.py       # LitellmModel + ModelSettings from config
    events.py       # internal event types (mirror AG-UI)
    tools.py        # @tool over function_tool: ToolResult(content, details), error labels
    delegate.py     # delegate(persona, task, share_context) — optional forked context
    skills.py       # discover skills/, load_skill → expose tools
    personas.py     # discover personas/*.md → SDK Agents
    session.py      # JSONL tree implementing the SDK Session protocol; detached delegation branches
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
  omen.md  researcher.md  writer.md
evals/
  tasks.yaml        # fixed small-model task set
vendor/
  openai-agents/    # forked OpenAI Agents SDK v0.17.6 (FORK.md lists the patches)
```

**Decision: fork the OpenAI Agents SDK** (`vendor/openai-agents`, base v0.17.6) instead of writing our own loop. The SDK keeps the loop, tool calling, validation, LiteLLM, sessions and cancellation; Omen's models call tools well but plan poorly over long contexts, so what we need is control over *context*, added as small patches:

| Patch | Why |
|---|---|
| Mid-run message queue (`RunConfig.message_queue`) | Messages typed while the agent works are delivered after the current tool call/turn; a pending message turns a final answer into another turn. |
| `ToolContext.conversation_history` | Lets `delegate` fork the current conversation into a persona run. |
| Tool `custom_data` persisted with session items | UI details (generative UI) survive reload; stripped before the model sees them. |

Already possible without a patch: a tool returning an object whose `str()` is the model text keeps the object for the UI (`ToolResult(content, details)`). Each patch is a separate commit with its own tests; the upstream suite still passes (see `FORK.md`). An earlier hand-written loop (Phase 1, first pass) was replaced by this.

---

## 4. Tools, skills and personas

Three mechanisms, each doing one job:

### 4.1 Core tools — always visible (≤ 4)

| Tool | Purpose |
|---|---|
| `load_skill(name)` | Load a skill's instructions and expose its tools from the next step on |
| `delegate(persona, task, share_context)` | Hand a subtask to a persona; get its result back. The main model decides whether the persona also sees the conversation so far |
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

- **Delegate:** `delegate("researcher", task, share_context=false)` runs the persona as its own short SDK run with its own prompt and **only its skills**, and returns only its final answer as `content`. **The main model decides what the persona sees:** by default just the task (short, clean context — write the task self-contained); with `share_context: true` a *fork* of the main conversation (via the fork's `conversation_history`, minus the in-flight call) plus the task.
- The persona's run streams to the UI as `SUBAGENT_EVENT`s nested under the delegate call, and is stored in the session as a **detached branch** — off the main conversation, never part of the main agent's context.
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
| **AG-UI** (CopilotKit protocol, MIT, Python `ag-ui-protocol`) | **Wire protocol.** Event families for text, tool calls/results, state, reasoning. No openai-agents integration yet — Omen maps SDK stream events to AG-UI-shaped events itself (`core/runtime.py`). |
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

- [x] Sandbox: `full_path.resolve().is_relative_to(SANDBOX_PATH)` in one helper used by every filesystem op. (Do this regardless — it's a security hole.)
- [x] `RunConfig(tool_not_found_behavior="return_error_to_model")`; `MAX_TURNS` set to 50 (old app and new core default; override with `OMEN_MAX_TURNS`).
- [x] Skip everything else — the old code is deleted in Phase 7.
- [x] Create the `rebuild` branch and the `omen/` package. Entry point is `python -m omen` for now; `[project.scripts]` lands at the Phase 7 cut-over together with the dependency rework.
- [x] Copy carry-over files unchanged into `skills/*/`, `omen/voice/`, `omen/tui/` (see §0).

### Phase 1 — Core on a forked Agents SDK

- [x] Vendor the OpenAI Agents SDK v0.17.6 into `vendor/openai-agents` (pristine commit, then one commit per patch); `pyproject` points `openai-agents` at it (editable path source).
- [x] Fork patches with tests: mid-run message queue, `conversation_history` for tools, tool `custom_data` persisted with session items. Upstream suite: 2351 passed (2 failures need the non-vendored `examples/`).
- [x] `core/runtime.py`: `Runtime.run()` streams Omen events from the SDK stream; `send()` queues a message mid-run (delivered after the current turn, or as a follow-up run if it arrives after the last turn); `abort()`; usage events; error/max-turns handling.
- [x] `core/tools.py`: `@tool` over `function_tool` (non-strict schemas, `ToolResult(content, details)`, capped content, exceptions → error results, error labels `invalid_args` / `exception` / `unknown_tool`).
- [x] `core/delegate.py`: `delegate(persona, task, share_context)` — the main model decides whether the persona gets a fork of the conversation; persona events stream as `SUBAGENT_EVENT`; its run is stored as a detached session branch.
- [x] `core/session.py`: JSONL tree implementing the SDK `Session` protocol; branching, labels, detached forks, `ui_details()`.
- [x] Tests: 33 unit tests on the SDK's `FakeModel` (`python -m unittest discover -s tests -t .`).
- [x] Evals: 12 tasks (incl. 2 delegation tasks). **Local `ling3` (7.9B Q5_K_M, llama.cpp): 36/36 passed over 3 repeats, 38/38 valid tool calls, ~2.1 steps and ~1.2 s per task.**
- [ ] Multi-turn eval tasks (needed to measure when the model chooses `share_context`).

### Phase 2 — Skills and core tools

- [x] `core/skills.py`: discover `skills/*/SKILL.md` (frontmatter: name, description, keywords) + optional `tools.py` (relative imports work); skill tools registered up front but gated by SDK `is_enabled` until loaded; `load_skill`; loaded skills' instructions go into the system prompt; up to 3 stay loaded across turns (LRU); `/skills`, `/skill name`, `/reload`. User skills in `~/.omen/skills` override repo skills.
- [x] Keyword pre-router (`Assistant.prepare`) auto-loads the best-matching skill before each run; `--no-router` / eval `router: false` to test explicit `load_skill`.
- [x] Core tools (always visible): `load_skill`, `remember`, `ask_user` (frontends answer via `Runtime.answer()`; evals via `ask_handler`).
- [x] Skills (copied helpers adapted minimally: `OMEN_SANDBOX` override, `fetch_weather_json` split, yt-dlp quality fix):
  - `web`: `search` (DuckDuckGo) + `read_url` on crawlberg — metadata/link-noise cleaning, BM25 paragraph ranking with `query`, one-line `BLOCKED (vendor)` / `NOT_FOUND` / `TIMEOUT` / `JS_REQUIRED` / `EMPTY` using the scraper-api's `blocking.py` (copied unchanged), ~3.5k char cap, no LLM call.
  - `files`: `list_files`, `read_file(path, offset, limit)` plain text, `write_file` (confirms overwrite), `append_to_file`, `edit_file` (unique exact match), `grep` (lines, case/punctuation-insensitive fallback), `delete_file` (confirms); sandboxed with the resolved-path check.
  - `weather` (wttr.in, weather card details), `media` (`search_youtube`, `download_audio`, `download_video`).
- [x] Memory: `remember` → `~/.omen/memory/facts.jsonl`; relevant facts recalled into the system prompt every turn.
- [x] `OmenModel` (LitellmModel subclass) repairs small-model output: answer only in the reasoning channel → visible answer; `<tool_call>` text (JSON or GLM `<arg_key>` style) → real function calls; repetition loops → short "got stuck" reply instead of garbage.
- [x] Tests: 72 unit tests. Evals: 20 tasks (8 full-assistant with real skills, 2 live-network opt-in via `OMEN_EVAL_NETWORK=1`). **Local `ling3`: 38/40 over 2 repeats, 100% valid tool calls; all files/memory/weather/skill-loading tasks pass.** Remaining misses: one live-web run where the model looped in its reasoning (now shown as "got stuck"), one flaky two-tool chain.
- [x] `resume` skill (rules + inline template), loadable by the main agent.
- [ ] `read_url` ranking favours short image captions on some pages; down-weight very short paragraphs.

### Phase 3 — Personas and delegation

- [x] `core/personas.py`: `personas/*.md` (frontmatter: name, description, skills, max_turns, main, delegate, model) → SDK agents; user personas in `~/.omen/personas` override; broken files are skipped with a warning.
- [x] Main persona: `omen` (default, `OMEN_PERSONA` / `--persona` to change). Its text + shared guidance form the system prompt; its skills stay loaded.
- [x] Specialists (`delegate: true`): `researcher` (web), `writer` (files; drafts emails/messages/docs). A `resume-writer` persona was tried and removed by the owner; the `resume` skill stays. Each runs with its skills' tools always on, its own `max_turns`, optional own model; no nested delegation.
- [x] `delegate` lists specialists in its schema and the system prompt; `load_skill` with a persona's name points the model to `delegate`; guidance: delegate when the user names a specialist, relay the result itself.
- [x] `/persona name` (keeps session and loaded skills) and `/personas` in the REPL.
- [x] Old voices (Vanessa, Marvin, Rex, ...), tutor and ideator dropped by the owner; `config/agent_personality.py` is deleted with the old stack in Phase 7.
- [x] Evals: multi-turn task (`history`) for context passing — the model writes the needed context into the task (`expect_context_passed`); writer and live researcher delegation tasks. **Local `ling3`: 45/46 over 2 repeats, 98% valid tool calls.** Eval answers are compared without markdown emphasis; the stand-in user only says "yes" to yes/no questions.
- [x] Tests: 80 unit tests.

### Phase 4 — Event protocol and UI components

- [x] `ui/components.py`: 18 typed components (weather, link_preview, search_results, video_results, file, file_list, file_write, file_delete, diff, grep, choice, delegation, memory_saved, skill_loaded, download, table, chart, card). Tool `details` → `UIPayload {type, version, valid, props, text}`; invalid/unknown props still delivered with `valid: false` and a text fallback. `json_schema()` / `GET /ui/schema` / `python -m omen schema` for TypeScript generation (Phase 6).
- [x] `ui/extract.py`: components from assistant text — rules first (markdown table → `table`, closing question + options → `choice`), hint tags `<ui:chart>` / `<ui:card>` (hidden from the stream) → JSON-schema-constrained extractor model (`OMEN_EXTRACTOR_MODEL`, default the main model), Pydantic validation, one retry with the error, invented URLs dropped, otherwise text only. Emitted as `UI_COMPONENT` before `RUN_FINISHED`.
- [x] `omen/agui.py`: Omen events → AG-UI 1.0 (`ag-ui-protocol`): paired step/reasoning events; tool-result payloads, extracted components and `ask_user` questions → `ACTIVITY_SNAPSHOT`; delegated personas → `SUBAGENT_STARTED/FINISHED/ERROR` with every nested event tagged `subagent_run_id`.
- [x] `omen/server.py` (`python -m omen serve`): `POST /agent` (AG-UI SSE), `POST /threads/{id}/messages|answer|abort`, `GET /threads`, `GET /threads/{id}` (history with UI payloads), `GET /ui/schema`. Capability negotiation via `forwardedProps.omen.components`; persona via `forwardedProps.omen.persona`.
- [x] `OmenModel` retries once when a response is completely empty (seen live after a delegation); memory guidance narrowed to lasting personal facts; delegation guidance discourages over-delegating simple questions.
- [x] Extractor eval (`python -m omen eval --extract`, `evals/extract_tasks.yaml`, 6 contexts). Live spot-checks on `ling3`: chart (5 values, 4.8 s) and card (2 s) valid; invented URL caught. **Full extractor eval not yet run** (the local model server went down during the phase).
- [x] Live server check on `ling3`: weather question → paired AG-UI stream with a `weather` ACTIVITY_SNAPSHOT; numbers question → `table` component extracted from the markdown reply.
- [x] Tests: 105 unit tests (server/AG-UI tests skip if `fastapi`/`ag-ui-protocol` aren't installed).
- [ ] Optional `ui` skill with `show_*` tools for stronger models — not needed so far: tables come from markdown and charts/cards from hint tags.
- [x] Re-ran on `ling3` after the changes: extractor eval 12/12, main suite 44/46 (same level as before). Extractor now returns no component on model/API errors (seen: 503 "Loading model").

### Phase 5 — TUI (Textual)

- [x] `omen/tui/app.py` (`python -m omen`, or `omen tui --persona/--session/--no-router`; `omen chat` keeps the line REPL): header (persona, model, loaded skills), scrolling transcript, live input, status bar (state, tokens, session file).
- [x] Transcript: streamed markdown answers (`Markdown.get_stream`), collapsed "thinking", collapsible tool rows (✓/✗, args, result) with the component rendered below, delegated personas as nested blocks (same renderer, collapsed when done), routed-skill notes, injected-message notes, errors.
- [x] Input: Enter sends; while working Enter steers (queued); with a pending question Enter or picking an option answers; Esc stops. Messages typed after the run's last delivery point start a follow-up run.
- [x] `omen/tui/render.py`: a renderer for all 18 component types (weather panel, link/search/video lists, file views, red/green diff, grep, choices, delegation, memory, skill, download, DataTable, bar chart, card); invalid/unknown → markdown text. Reply extraction in the TUI is limited to chart/card (markdown already shows tables and option lists).
- [x] Slash commands (`/help /personas /persona /skills /skill /reload /new /tree /quit`), Ctrl+P command palette (personas, skills, new session, branches), Ctrl+T branch tree: pick any entry (incl. delegation side branches) to continue from; transcript re-renders from the session (`omen/ui/history.py`, shared with the server).
- [x] Live on `ling3` (headless pilot screenshots): weather card + answer; delegation to the writer as a nested block; table in the reply. Fixed from those: duplicate table, `remember` used for request data (rule moved into the tool description), unbounded nested-block height.
- [x] Tests: 115 unit tests (Textual pilot tests skip if textual isn't installed).

### Prompt cache (DeepSeek Harness layout)

llama.cpp reuses its KV cache only for an unchanged token prefix; the tool list is rendered into the first system block, so any change to the system prompt or tools reprocesses the whole conversation. Following DeepSeek Harness (`dsh`, ~95–99% reported hit rates):

- [x] System prompt frozen per session: persona, guidance, a note about the context block, specialists roster, skills roster, UI hints. No clock, no recalled memory, no per-turn skill text.
- [x] Each new user message starts with a `<context>` block (time; memories not yet shown this session; instructions of skills loaded since the last message), stored once and never rewritten; TUI/server history hide it (`strip_context`).
- [x] Constant tool list: every skill tool is always visible; calling one marks its skill loaded; `load_skill` returns the skill's instructions as its result; each skill's instructions enter the conversation exactly once.
- [x] Named specialists ("ask the writer to …", "@researcher …") are delegated by the harness before the model runs (llama.cpp ignores a named `tool_choice`, and with all tools visible the model otherwise did the work itself); the call and result are appended to the session like a model-made call.
- [x] Instrumentation: usage events carry `cached_tokens`; the TUI status bar shows the session's cache hit rate.
- [x] Opt-in llama.cpp slot pinning: `OMEN_SLOT_MAIN` / `OMEN_SLOT_SIDE` (`id_slot`) so personas and the UI extractor don't evict the main conversation; needs `llama-server -np 2+`.
- [x] Results on `ling3` (5-turn scripted conversation): cache hit **69% → 86%** overall; turns after the first **97–99%** (skill-loading turns were ~50% and every new clock minute reset to 0%). First request is larger (~2.4k vs ~1.1k tokens) because all tools are listed; it's cached across turns and sessions. Eval suite: **45/46, 100% valid tool calls**; named delegation 8/8.
- [ ] Compaction (Phase 7) must keep the prefix: summarizer = same system prompt + tools + history + a final instruction; new session starts with the same system prompt and tools.

### Phase 6 — Web UI

- [x] `web/`: Vite 8 + React 19 + TypeScript, no chat framework: `src/agui.ts` is a typed reducer from AG-UI events to transcript blocks (user, assistant, reasoning, tool, component, question, subagent, note, error), an SSE parser over `fetch`, and `fromHistory()` for saved threads. Chosen over assistant-ui to keep `ACTIVITY_SNAPSHOT` components, questions and nested subagent runs fully under our control with one small dependency-free module.
- [x] `src/components/registry.tsx`: a React renderer for all 18 component types (SVG bar/line chart, sortable table, weather, files, diff, choices, …); invalid/unknown payloads fall back to their text. The client advertises what it renders via `forwardedProps.omen.components`. Types come from the Pydantic models: `python -m omen schema --ts > web/src/generated/components.ts` (`omen/ui/tsgen.py`).
- [x] Sidebar (threads, persona picker, tokens + prompt-cache rate), composer (Enter sends; while running it steers via the message queue; Stop aborts), questions answered inline, delegated personas as nested blocks. `npm run build` → `web/dist`, committed and served by `omen serve` at `/` (API routes win).
- [x] Reply components persist: extracted charts/cards are stored as `ui` side entries on the session (never the leaf, never sent to the model) and come back in `GET /threads/{id}` → reloading a thread (web or TUI) re-renders them. History strips `<ui:…>` hint tags like the live stream does.
- [x] Charts on request: asking for a chart/graph/plot with numbers adds a one-line note to that message's `<context>` block (not the frozen system prompt) and makes the extractor build a chart even if the model forgets `<ui:chart>`; the server extracts only what markdown can't show (chart, card).
- [x] Found live and fixed: ling3 drew ASCII charts into files and once looped `█` until llama.cpp rejected the tool call (500 "Failed to parse tool call arguments") → `OmenModel` retries that once; the extractor reasoned past `max_tokens` (empty JSON, `finish_reason=length`) → local extractor calls send `chat_template_kwargs.enable_thinking=false` (`OMEN_EXTRACTOR_THINKING=1` to keep it) and now forward `extra_body` (side slot); chart labels/values must have equal length (one retry with the error).
- [x] Live on `ling3` (headless Chromium): weather card, file components, two chart requests rendered, thread reload keeps the chart, no console errors, cache 95–97 %. Extractor eval 12/12 (≈0.3–0.6 s per call, was 2–5 s). Tests: 122 Python + 9 vitest.

### Phase 7 — Voice, compaction, cleanup

- [ ] Voice as a frontend (lazy STT/TTS, barge-in, text fallback).
- [x] Compaction (`omen/core/compaction.py`): before a user message, if the context (last request's input + output tokens, from the SDK's per-request usage) is over `OMEN_COMPACT_AT` (24000; 0 disables), cut at a user-message boundary (a call and its result are never split), keep the last `OMEN_KEEP_RECENT` (6000) tokens verbatim, and summarize the rest with one side-model call (thinking off) into Goal / Constraints and preferences / Progress / Decisions / Next steps / Files touched. Stored as a `compaction` entry in the session tree (`first_kept` + summary): the model sees the summary prepended to the first kept user message (alternation intact); the TUI and web still show the whole transcript with a "summarized" note. A previous summary is merged into the next one. Memories and skill instructions summarized away are shown again in the next context block. `/compact` in the TUI forces it. Never fails a run: summary errors or a summary that is only the template's headings (seen live on ling3 with a bare-headings prompt; fixed by a template with example bullets) leave the context as is.
- [x] Live on ling3 (trigger lowered to 3000/300): facts from summarized turns (dates, budget, companion, diet) answered correctly afterwards; the frozen system prefix stayed cached across the compaction (2407 of 3534 tokens), the rest re-prefilled once. Tests: 130 Python + 10 vitest; main eval suite 20/20, 100% valid tool calls.
- [x] Deleted the old stack: `my_agents/`, `tools/` (task/ui/computer/exec tools, Searx/Omni search, old scraper), `tts/` (Piper), `stt/` (Parakeet), `cli/`, `config/`, `docs/` (rewritten below), `main.py`, `agent_runtime.py` (68 files). Nothing in `omen/`, `skills/`, `evals/` or `tests/` imported them; `omen/voice/KokoroTTS.py` now reads the side model from `omen.config`.
- [x] Dependencies: dropped `beautifulsoup4`, `crawl4ai`, `html2text`, `liteparse`, `piper-tts`, `spider_rs` (+ its `spider-py` source), `statsmodels`; speech packages (`faster-whisper`, `pyaudio`, `openwakeword`, `numpy`, `scipy`, `halo`, `markdown`, `torch>=2.14.0`) moved to the `voice` extra (`uv sync --extra voice`). A fresh `uv sync` is 238 MB instead of 6.4 GB, has no torch, and passes all 130 tests; `omen` CLI, server and TUI import cleanly.
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
