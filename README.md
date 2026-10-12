# Omen

A personal assistant built to work well on **small local models** (tested daily on Ling 3.0 Tiny,
a 7.9B MoE served by llama.cpp on a 6 GB laptop GPU). One runtime, four frontends: a terminal UI,
a line chat, a web UI with generative components, and voice.

What makes it work on a small model:

- **Few tools, short outputs.** Core tools plus skills; every tool result the model sees is capped
  (~1k tokens) while the UI gets the full structured details.
- **Prompt-cache friendly.** The system prompt and tool list never change during a session;
  everything that varies (time, recalled memories, skill instructions) goes in a `<context>` block
  at the start of each user message. Turns after the first hit the llama.cpp prompt cache at 97–99%.
- **Delegation as branches.** The main persona can hand a subtask to a specialist persona, which
  runs on a fork of the conversation (or just the task) and returns only its result. Follow-ups
  ("ask the writer to make it shorter") continue the specialist's earlier thread. A specialist that
  is missing something asks Omen (`ask_superior`); Omen answers it or asks you.
- **Steer mid-run.** Messages you send while Omen is working are delivered after the current step.
- **Compaction.** Long conversations are summarized into fixed sections before they slow the model
  down; the latest turns stay verbatim.
- **Generative UI without JSON from the main model.** Tools return typed components; the model ends a
  reply with `<ui:chart>` or `<ui:card>` and a small JSON-schema-constrained extractor fills it.

## Install

```sh
uv sync                  # text mode: TUI, chat, web server (~240 MB, no torch)
uv sync --extra voice    # + speech: faster-whisper, openwakeword, pyaudio, torch
```

Omen talks to any OpenAI-compatible server through LiteLLM. By default it expects a local server at
`http://localhost:11434/v1` serving a model named `ling3` (Ling 3.0 Tiny, the default and the eval
model; see [Local model](#local-model)).

## Run

```sh
uv run python -m omen               # terminal UI (Textual)
uv run python -m omen chat          # plain line chat
uv run python -m omen voice         # speech in/out (voice extra + a Kokoro TTS server)
uv run python -m omen serve         # web UI + AG-UI API at http://127.0.0.1:8765
uv run python -m omen eval          # small-model eval suite (--extract for the UI extractor)
```

Common flags: `--persona <name>`, `--session <file>` (resume), `--no-router` (don't auto-load
skills by keyword).

**TUI:** Enter sends; while Omen works, Enter steers; Esc stops; Ctrl+P command palette; Ctrl+T
branch tree (continue from any earlier point, including a specialist's side branch). Commands:
`/personas /persona <name> /skills /skill <name> /reload /compact /new /tree /quit`.

**Web UI:** built into `web/dist` and served by `omen serve`. To work on it:
`cd web && npm install && npm run dev` (proxies to the server on :8765); `npm run build` to rebuild;
`npm run types` regenerates `src/generated/components.ts` from the Python component models.

**Voice:** say the wake word ("Jarvis", openWakeWord) and then your request; talking pauses speech; speaking while Omen works steers it; questions are spoken and the
next utterance answers them. Replies are printed in full and spoken as clean text (long ones as a
short briefing). Without the voice extra or a microphone it falls back to the text chat.

## Configuration

Environment variables (a `.env` file in the repo root is read):

| Variable | Default | Meaning |
|---|---|---|
| `OMEN_LOCAL` | `1` | `1`: local server (`OLLAMA_BASE_URL`); `0`: hosted (`CEREBRAS_BASE_URL`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | local OpenAI-compatible endpoint |
| `OMEN_MODEL` | `openai/ling3` | LiteLLM model name |
| `OMEN_API_KEY` / `TRIAGE_API_KEY` | | API key |
| `OMEN_EXTRA_BODY` | `{}` | JSON merged into every request (backend-specific fields) |
| `OMEN_PERSONA` | `omen` | main persona |
| `OMEN_MAX_TURNS` | `50` | model steps per user message |
| `OMEN_COMPACT_AT` / `OMEN_KEEP_RECENT` | `24000` / `6000` | compaction trigger / tokens kept verbatim (`0` disables) |
| `OMEN_TOOL_MAX_CHARS` | `4000` | cap on tool output the model sees |
| `OMEN_EXTRACTOR_MODEL` / `_BASE_URL` / `_API_KEY` | main model | model for UI extraction, summaries and spoken briefings |
| `OMEN_EXTRACTOR_THINKING` | `0` | keep reasoning on for those calls (local thinking models otherwise run out of tokens) |
| `OMEN_SLOT_MAIN` / `OMEN_SLOT_SIDE` | | pin llama.cpp slots (`-np 2`) so side work never evicts the main conversation |
| `OMEN_HOME` | `~/.omen` | sessions, memory, your own skills and personas |
| `OMEN_SANDBOX` | `<repo>/root` | the only directory the file and download tools may touch |
| `OMEN_TTS_URL` | `http://localhost:8880/v1` | Kokoro (OpenAI-compatible) speech server |

## Personas and skills

**Personas** (`personas/*.md`, or `~/.omen/personas/`) are who Omen is for a conversation and who it
can delegate to: `omen` (default, focused generalist), `researcher` (web facts with sources),
`writer` (drafts and edits).

```markdown
---
name: researcher
description: Finds and checks facts on the web and reports them with sources.
skills: [web]        # loaded for this persona
max_turns: 8         # cap for a delegated run
main: true           # can be the main persona
delegate: true       # others can hand it subtasks
model: openai/other  # optional
---
You are a careful researcher. ...
```

**Skills** (`skills/<name>/`, or `~/.omen/skills/`) are a `SKILL.md` with instructions and keywords,
plus an optional `tools.py` of `@tool` functions (`files`, `web`, `media`, `weather`, `resume`).
Their tools are always visible; the instructions arrive when the skill is loaded (by keyword, by the
model calling `load_skill`, or by using one of its tools).

```markdown
---
name: weather
description: Current weather and the next days' forecast for a city.
keywords: [weather, forecast, rain, temperature]
---
Call `get_weather` with the city name. Answer in one or two sentences.
```

## Local model

Any OpenAI-compatible server works. Notes for llama.cpp (`llama-server`):

- Start it with `--jinja` (native tool calls) and `--alias ling3`, or set `OMEN_MODEL`. The default and
  eval model is Ling 3.0 Tiny (`Ling-3.0-tiny-Q5_K_M.gguf`, 7.9B MoE, 1.3B active).
- Hybrid/MoE models on a small GPU: `--cpu-moe --moe-cache-mib <free VRAM>` keeps hot experts on the
  GPU; a larger `-ub` (2048) prefills ~40% faster than 512 at the same decode speed.
- Cap the host prompt cache (`--cache-ram 2048`): the default 8 GB can push a 15 GB machine into swap.
- Decode speed depends on how full the context is (Ling 3 Tiny: ~115 tok/s at 2k, ~65 at 64k), which
  is one reason compaction triggers early.

## Layout

```
omen/            runtime, assistant, server, TUI, voice, UI components (see docs/architecture.md)
skills/          built-in skills          personas/   built-in personas
web/             React web UI (dist/ is committed)
evals/           eval suites              tests/      unit tests
vendor/openai-agents/   the forked OpenAI Agents SDK (vendor/openai-agents/FORK.md)
plan.md          the rebuild plan and what each phase delivered
```

Tests: `uv run python -m unittest discover -s tests -t .` · web: `cd web && npm test`.
