# Architecture

```
 frontends   omen/tui (Textual)   omen/__main__ chat   omen/voice   web/ ── omen/server (AG-UI over SSE)
                     \                  |                  |                  /
                      └──────────── omen/core/runtime.Runtime ───────────────┘
                                         |  Omen events (omen/core/events.py)
                       omen/assistant ── persona, skills, memory, delegation, context block
                                         |
                       forked OpenAI Agents SDK (vendor/openai-agents) ── OmenModel (LiteLLM)
                                         |
                       omen/core/session.Session ── append-only JSONL tree
```

## Runtime (`omen/core/runtime.py`)

One `Runtime` per conversation drives the SDK's streamed run and turns SDK stream events into Omen
events (`omen/core/events.py`, AG-UI-shaped: text deltas, reasoning, tool call start/args/result,
UI components, questions, subagent events, custom events). For each user message:

1. `prepare` (from the assistant): keep the persona's skills loaded, route by keyword, and, if the
   user named a specialist ("ask the writer to…"), schedule a harness-made `delegate` call.
2. Compaction check (below).
3. `context`: build the `<context>` block (time, newly recalled memories, newly loaded skill
   instructions) and prepend it to the message.
4. Run the agent with the message queue attached; `send()` queues text that the SDK injects after
   the current turn's tool outputs; `answer()` resolves a pending `ask_user` question; `abort()`
   cancels.
5. After the run: per-request usage (incl. `cached_tokens`) is reported, and each assistant reply is
   passed to the component extractor; components are emitted and saved with the reply.

## Assistant (`omen/assistant.py`)

`build_assistant(persona=…)` assembles the main agent from a persona (`personas/*.md`):

- **Frozen system prompt**: persona body, guidance, a note about the context block, the specialists
  roster, the skills roster, UI hints. Nothing in it changes during a session, and the tool list is
  constant, so the model server's prompt cache stays warm (DeepSeek-Harness layout).
- **Core tools**: `load_skill`, `remember`, `ask_user`, `delegate`, plus every skill's tools.
- **Specialists**: other personas with `delegate: true` become `delegate` targets with their own
  skills and turn caps. `delegate(persona, task, share_context)` runs them on a fork of the current
  conversation (`share_context=true`) or on the task alone, records the sub-run as a detached branch
  of the session, and returns only the result. The main model decides whether to share context.
  `follow_up=true` resumes the specialist's latest branch on this path (its earlier subtasks, tool
  calls and results) and extends that branch, so its next request only appends the new subtask.
  Questions go up: every specialist has `ask_superior(question)`, which ends its run. An ask before
  any other tool call in the run is turned back once ("try your tools first"). A reply that only
  asks for missing information counts as a question too: when a reply contains "?" or request
  wording ("please provide: …"), one side-model
  call (thinking off, ~0.5 s on ling3) tells a finished draft from a request for details. A specialist that
  asks without having seen the conversation is resumed once with it shared, which is the
  superior's first answer. If it still asks, `delegate` returns "<persona> paused to ask: …"
  instead of a result. The main agent answers with another `delegate` to that specialist, which
  resumes the thread as an answer without any flag, or first asks its own superior, the user, with
  `ask_user`. A question never becomes the direct reply of a named delegation; the main model takes
  the turn.
  When the user named the specialist, the harness makes the call (continuing the thread if the
  previous message went to the same specialist) and the specialist's result is the
  reply as is (no main-model turn retyping it). Otherwise the main model can write `{{result}}`,
  shown expanded on screen and stored as written.

## Run guards (`omen/core/guard.py`)

Every tool of the main agent and the specialists is wrapped. A call identical (name and arguments)
to the previous step of the same turn is not run; the model gets a warning with concrete next moves
(and, on a second repeat, an instruction to stop and answer). Every 5th tool result in a turn ends
with "(goal: <the user's request> · step N of M)". The reminder is stored with the result: a block
re-sent on each call but never stored would cost ling3 ~2,000 re-evaluated tokens per call
(`evals/cache_tail.py`).

## Skills (`omen/core/skills.py`)

A skill is a folder with `SKILL.md` (frontmatter `name`, `description`, `keywords`; body =
instructions) and optional `tools.py` (`@tool` functions, `omen/core/tools.py`). All skill tools are
always visible (a constant tool list is what keeps the cache warm); a skill's instructions are
delivered once, as a `load_skill` result or in the next context block, when it is loaded by keyword,
by `load_skill`, or by the model simply calling one of its tools.

`@tool` returns `ToolResult(content, details)`: the model sees `content` (capped by
`OMEN_TOOL_MAX_CHARS`); `details` is a UI component that reaches the frontends and the session but
never the model. Exceptions become actionable error results.

## Model (`omen/core/models.py`)

`OmenModel` (a `LitellmModel`) repairs what small local models do: answers left in the reasoning
channel, tool calls written as text (JSON or GLM style), repetition loops, completely empty
responses (one retry), and tool calls the server can't parse (llama.cpp's "Failed to parse tool call
arguments": one retry when nothing was streamed yet). Slot pinning (`OMEN_SLOT_MAIN/SIDE`) adds
`id_slot` so side work (specialists, extractor) never evicts the main conversation.

## Session (`omen/core/session.py`)

An append-only JSONL tree implementing the SDK `Session` protocol. Each line is
`{id, parent_id, type, ts, data}`; the conversation is the path from the root to the current leaf.

- `item`: an SDK input item. Tool outputs carry UI details under `_agents_custom_data` (fork patch).
- `label`: names an entry. `ui`: a component extracted from a reply. Neither becomes the leaf.
- `compaction`: `{summary, first_kept}`: the model's view of the branch becomes the summary plus the
  items from `first_kept` on.
- Detached branches hold delegated sub-runs. Branching (`branch(entry_id)`) moves the leaf back; the
  next message starts a new branch and the old one stays in the file (TUI Ctrl+T).

`omen/ui/history.py` renders a branch for the frontends: user messages without their context block,
replies without hint tags and with their saved components, tool calls with their UI payloads, and
compaction markers. The full transcript is always shown, even where the model only sees a summary.

## Compaction (`omen/core/compaction.py`)

Before a user message, if the context (the last request's input + output tokens) is over
`OMEN_COMPACT_AT`, the conversation is cut at a user-message boundary (a tool call and its result
are never separated) and the last `OMEN_KEEP_RECENT` tokens stay verbatim. Before the cut, each user
request and final answer is kept word for word and the tool calls between them shrink to one line;
only if that is still too long are the oldest turns summarized by the side model into Goal /
Constraints and preferences / Progress / Decisions / Next steps / Files touched (exact values kept,
unconfirmed facts marked). An earlier summary is merged into the next. The summary is prepended to the first
kept user message (role alternation stays intact), and memories and skill instructions that were
summarized away are shown again. A failed or empty summary leaves the context untouched.

## Generative UI (`omen/ui/`)

- `components.py`: 18 Pydantic component types (weather, link previews, search and video results,
  files, diffs, grep, choices, delegation, memory, downloads, table, chart, card, …) and
  `UIPayload {type, version, valid, props, text}`; an invalid payload still carries its text.
- `extract.py`: components from reply text. Rules first (markdown table, closing question with
  options); the model can end a reply with `<ui:chart>` / `<ui:card>` (hidden from the stream), or
  the user can ask for a chart; then a JSON-schema-constrained call fills the component (thinking off
  for local models, one retry with the validation error, invented URLs dropped).
- `tsgen.py`: TypeScript types for the web UI (`python -m omen schema --ts`).

Clients declare what they render; other tool details are dropped (the text stays) and only those
kinds are extracted. Markdown-rendering clients extract only chart and card.

## Server and web UI (`omen/server.py`, `omen/agui.py`, `web/`)

`omen serve` speaks AG-UI 1.0 over SSE: `POST /agent` (a `RunAgentInput`; `forwardedProps.omen`
carries `persona` and `components`), `POST /threads/{id}/messages|answer|abort`, `GET /threads`,
`GET /threads/{id}` (history with components), `GET /ui/schema`, `GET /personas`, and the built web
UI at `/`. Components and questions are `ACTIVITY_SNAPSHOT` events; delegated personas are
`SUBAGENT_STARTED/FINISHED/ERROR` with every nested event tagged by `subagentRunId`.

The web UI (React 19, Vite, TypeScript) is a typed reducer from AG-UI events to transcript blocks
(`web/src/agui.ts`) plus a renderer per component type (`web/src/components/registry.tsx`).

## Voice (`omen/voice/`)

`omen voice` wires faster-whisper STT (Silero VAD, openWakeWord wake word "Jarvis") and Kokoro TTS to the same Runtime.
`VoiceSession` routes utterances: a pending question gets the answer, a running run gets a steering
message, otherwise a new run starts; speech starting pauses playback. Spoken text is cleaned of
markdown, code, tables and links; replies over ~320 characters become a short briefing from the side
model. The speech stack is only imported by this command.

## The SDK fork (`vendor/openai-agents`)

Three patches on v0.17.6 (details and tests in `vendor/openai-agents/FORK.md`): the mid-run message
queue, conversation history for tools (what `delegate` forks), and tool details persisted to the
session but stripped before the model.

## Evals (`evals/`)

`omen eval` runs `evals/tasks.yaml` against the configured model (tool choice, argument validity,
multi-step chains, delegation, skills) and reports pass rate, valid tool-call rate and steps;
`omen eval --extract` checks the UI extractor on `evals/extract_tasks.yaml`. Multi-turn tasks
(`turns:`) run every turn in one session, so follow-ups depend on what the model really said and
did earlier, and check each turn on its own; the summary also counts how many `delegate` calls
set `share_context` and `follow_up`.
