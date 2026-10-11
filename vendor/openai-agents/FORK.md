# Omen fork of the OpenAI Agents SDK

- Upstream: https://github.com/openai/openai-agents-python
- Base: tag `v0.17.6`, commit `510b7de2ceea05df5ffbbfd461db2f60522dac09`
- Vendored: `src/`, `tests/`, `LICENSE`, `README.md`, `pyproject.toml` (docs, examples and `uv.lock` omitted)

The first commit that adds this directory is the pristine upstream copy. Every
Omen change is a separate commit on top, so `git log -p -- vendor/openai-agents`
shows the full fork diff.

## Why a fork

Omen targets small local models that call tools well but plan poorly over long
contexts. It needs control over context that the SDK doesn't expose:

1. **Mid-run message queue** — user messages sent while a run is in progress are
   injected after the current tool call/turn instead of waiting for the run to end.
2. **Forked-context delegation** — a sub-agent starts from a fork of the main
   agent's current history plus a subtask, runs as its own branch, and returns
   only its result to the main agent.
3. **Tool output split** — the model sees short `content`; the UI receives
   structured `details` (generative UI).

## Omen patches

| Patch | What | Files | Tests |
|---|---|---|---|
| Mid-run message queue | `RunConfig(message_queue=MessageQueue())`; queued text is injected as `UserMessageItem` after the current turn's tool outputs (stream event `user_message_injected`, persisted to the session); a pending message turns a final output into another turn; `as_tool` sub-runs don't inherit the queue | `message_queue.py` (new), `items.py`, `stream_events.py`, `run_internal/streaming.py`, `run_config.py`, `run_internal/run_loop.py`, `run_state.py`, `agent.py`, `__init__.py` | `tests/test_omen_message_queue.py` |
| Conversation history for tools | `RunContextWrapper.conversation_history` / `ToolContext.conversation_history`: model-visible history when tools run, minus tool calls without outputs (the in-flight call and parallel siblings) | `run_context.py`, `tool_context.py`, `run_internal/turn_resolution.py` | `tests/test_omen_conversation_history.py` |
| Tool details persisted | `ToolCallOutputItem.custom_data` (e.g. UI details from `custom_data_extractor`) is written to the session under `_agents_custom_data` and stripped before items reach the model | `run_internal/items.py`, `run_internal/session_persistence.py` | `tests/test_omen_tool_details.py` |

Already possible without a patch: a tool returning an object whose `str()` is the model-visible
text keeps the object itself on `ToolCallOutputItem.output` for the UI.

## Running the tests

```
cd vendor/openai-agents
uv run --with pytest --with pytest-asyncio --with pytest-mock --with inline-snapshot \
    pytest tests --ignore=tests/extensions --ignore=tests/realtime --ignore=tests/voice \
    --ignore=tests/sandbox --ignore=tests/mcp --ignore=tests/fastapi
```

Tests that import the upstream `examples/` package (not vendored) or `graphviz` fail to collect;
skip them with `--ignore`. At the time of patching: 2351 passed, 4 skipped, 2 failed (both need
`examples/`).

## Updating from upstream

1. Clone upstream at the new tag into a scratch directory.
2. Replace `src/` and `tests/` here with the new copies in one commit ("vendor: upstream vX.Y.Z").
3. Re-apply the Omen patch commits (`git cherry-pick`), resolving conflicts.
4. Run the patched tests listed under each patch.
