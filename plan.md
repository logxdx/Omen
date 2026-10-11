# Omen Simplification Plan

Goal: make Omen reliable on small local models (Ollama). Generic harnesses (pi, Claude Code, Codex) assume a strong model; Omen should assume a weak one.

## Why small models struggle with the current harness

Prompt size is not the problem — fixed overhead is ~1–1.5k tokens per call (system prompt + tool schemas). The problems are structural:

- **Nested loops.** Triage calls `ask_web_search_agent` / `ask_filesystem_agent`, each a full agent loop with `max_turns=MAX_TURNS` (50) inside an outer 50-turn loop (`my_agents/base_agent.py:156-163`, `cli/v1.py:423`). Worst case ~2,500 LLM calls; the UI is silent while a subagent runs.
- **Unbounded outputs, untrimmed history.** `read_file`, `scrape_url` and search have no size caps. History is `result.to_input_list()` re-sent in full every turn (`cli/v1.py:623-632`), so every file read and scraped page accumulates.
- **Prompt/tool mismatches.** Prompts reference tools that don't exist (`web_search`, `parse_document`, `screenshot_document`, `weather`, `open_url`) and the wrong subagent names (`web_search_agent` vs actual `ask_web_search_agent`).
- **Fragile run config.** A hallucinated tool name aborts the whole run (`tool_not_found_behavior="raise_error"` default). No temperature, `parallel_tool_calls`, `max_tokens`, or loop guard.
- **Hidden extra LLM calls.** `scrape_url` summarises every page with another LLM call; the web prompt demands 3–5 scrapes per question; the context manager adds 2 runs per turn; TTS summarises any reply > 200 chars.

## Scraper verdict

Current `scrape_url` → `tools/utils/scraper.py` (spider_rs + bs4 + html2text + LLM bullet-point summary). Not sufficient:

- No block detection — Cloudflare challenge pages, 403s and JS-only shells are returned as content. Headless retry only when HTML is empty.
- Cleaning corrupts text: `scraper.py:457` strips all control chars including `\n` (code blocks collapse); `:460` unescapes entities after serialising (`&lt;div&gt;` becomes a real tag); removing `<header>` drops article titles.
- No truncation. If summarisation fails, the full raw page is returned. The summariser sends the whole page unchunked with a prompt that ignores the user's question.
- `"pdf" in url` routes any URL containing "pdf" to Jina's cloud reader.
- `spider_rs` depends on the untracked 1.8 GB `spider-py/` dir (`pyproject.toml:42`) — `uv sync` breaks on a fresh clone.

`scraper-api` (crawlberg) is far stronger (engine escalation, block detection, WAF challenge solving, TLS impersonation, main-content `fit_content`), but the service needs Postgres + Redis + MinIO — overkill for a single-user assistant.

**Decision:** use the `crawlberg` Python package directly (`create_engine(CrawlConfig(...))` + `await scrape(engine, url)`), port the ~60-line marker logic from `scraper-api/app/engines/blocking.py`. Call scraper-api over HTTP only if it's already running for other reasons.

---

## Phase 0 — Quick fixes (< 1 hour)

- [ ] **Security: sandbox path traversal.** `tools/utils/filesystem.py` checks `str(SANDBOX_PATH) in str(full_path)` without resolving, so `../../etc/passwd` passes for every op except `list_files`. Replace with `full_path.resolve().is_relative_to(SANDBOX_PATH)` in a single helper used by all ops.
- [ ] Pass `RunConfig(tool_not_found_behavior="return_error_to_model")` in `cli/v1.py`.
- [ ] Set `MAX_TURNS` to ~10 in `config/agent_config.py`.
- [ ] Fix prompt/tool name mismatches:
  - `web_search` → `duckduckgo_web_search` (`web_search_agent/prompt.py:7,15`, `triage_agent/prompt.py:32`)
  - subagent names → `ask_web_search_agent` / `ask_filesystem_agent`
  - remove `parse_document`, `screenshot_document` (`filesystem_agent/prompt.py`)
  - remove the "ALWAYS scrape 3–5 sources" rule
  - remove "never delete without explicit user confirmation" for the fs subagent (it can't reach the user)
- [ ] Fix `tools/__init__.py` `__all__` (lists unimported task tools and nonexistent `change_heirarchy_mode`).

## Phase 1 — One agent loop

- [ ] Remove the triage layer and subagents-as-tools.
- [ ] Single agent, ~8 tools:
  - `search` — web search
  - `read_url` — fetch a page (Phase 2)
  - `list_files`, `read_file`, `write_file`, `edit_file`, `grep`
  - `remember` / `recall` — context memory
- [ ] Keep `/agents`, but modes (default, tutor, idea, resume) become **prompt swaps over the same loop** (optionally a tool subset per mode), not separate agents.
- [ ] Rewrite each mode prompt to ~150–250 tokens of plain instructions: who you are, what tools exist (exact names), 3–5 rules. Drop XML tags and rigid multi-section output formats.
- [ ] Inject current date/time per turn instead of baking it in at import (and drop `get_current_datetime` as a tool).

## Phase 2 — Bound every tool output

- [ ] **`read_url(url: str, query: str | None = None, max_chars: int = 3500) -> str`** on crawlberg:
  - use `fit_content` (main content only); keep headings and `<pre>`; drop images and link URLs (keep anchor text); collapse whitespace
  - first line: `Title | URL | shown/total chars | truncated?`
  - with `query`: split into paragraphs, rank by BM25/keyword overlap, return the top ones up to `max_chars` — no LLM call
  - failures return one line: `BLOCKED (cloudflare)`, `NOT_FOUND`, `TIMEOUT`, `JS_REQUIRED`; retry with JS rendering only when crawlberg's `js_render_hint` is set
  - PDFs via crawlberg's `is_pdf` handling, not URL substring
- [ ] **`read_file(path, offset=0, limit=200)`** — plain text (no box drawing, no line wrapping) so models can copy exact text into `edit_file`; append `[truncated — use offset=N]` when cut.
- [ ] **`search`** — one tool, 5 results, short snippets.
- [ ] **`grep`** — return matching lines with line numbers (currently returns `re.findall` tuples), capped.
- [ ] One-line tool descriptions; make defaulted params truly optional (strict schemas currently force them to be required).

## Phase 3 — History management

- [ ] Delete the context-manager flow (`cli/v1.py:729-777`): 2 extra LLM runs per turn, and it can clobber `CONVERSATION_HISTORY` with the context agent's own transcript.
- [ ] Replace with deterministic trimming: keep the last N turns verbatim; replace older tool outputs with a one-line stub (`[read_url: <title>, 3.2k chars — elided]`).
- [ ] Keep `remember` / `recall` as explicit tools for long-term memory instead of an automatic summariser.

## Phase 4 — Run config hardening

- [ ] `ModelSettings(temperature≈0.3, parallel_tool_calls=False, max_tokens=<cap>)`.
- [ ] Loop guard: stop (or inject a nudge) after 2 identical consecutive tool calls.
- [ ] TTS: skip summarisation when the reply is already short; strip `<think>` before speaking; pass the actual user query to the summariser.
- [ ] Re-evaluate: if malformed tool calls (bad JSON, near-miss tool names) are still common, replace the openai-agents SDK with a ~150-line custom LiteLLM loop that can repair JSON and fuzzy-match tool names. Otherwise stay on the SDK.

## Phase 5 — Delete

- [ ] Dead code (~1.9k LOC + Parakeet 2.4k):
  - handoff code in `base_agent.py` (`add_handoffs`, `_handoff_message_filter`, comment block, `RECOMMENDED_PROMPT_PREFIX`) and handoff display in `cli/v1.py`
  - `tools/task_tools.py`, `tools/ui_tools.py`, `tools/computer.py`, `execute_code` + `tools/utils/code_execution.py`
  - `tools/utils/SearxSearch.py`, `tools/utils/OmniSearch.py`, unused `web_search` / `search_the_web`
  - `tts/PiperTTS.py`, `stt/ParakeetSTT.py`
  - `CONTEXT_MANAGER_AGENT_SYSTEM_PROMPT_v1` (`context_memory_agent/prompt.py:32-227`)
  - old scraper paths: spider_rs fetch, Jina fallback, ReaderLM `html2md`, `crawl_links` / `crawl_page`
  - `analysis_agent` entries in `config/agent_config.py`
- [ ] Dependencies: remove `crawl4ai`, `liteparse`, `statsmodels`, `spider_rs`, `piper-tts`; delete `spider-py/`.
- [ ] Lazy-load STT/TTS so text mode starts without torch / faster-whisper.
- [ ] Rewrite docs (`docs/architecture.md`, `docs/cli.md`, `docs/tools.md`, `docs/task_management.md`, `docs/configuration.md`) — they describe hierarchy modes, `/hierarchy`, `analysis_agent` and task tools that don't exist.

---

## Success criteria

- A typical question (search → read 1–2 pages → answer) completes in ≤ 6 LLM calls with no hidden summariser calls.
- No single tool result exceeds ~1k tokens; a 10-turn session stays inside an 8–16k context.
- A hallucinated tool name or bad arguments produces an error the model can recover from, never a crashed run.
- `uv sync` works on a fresh clone; text mode starts without loading torch.
