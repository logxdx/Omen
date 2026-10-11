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

## Patches

See the "Omen patches" section below; each entry names its commit.

## Omen patches

_(filled in as patches land)_

## Updating from upstream

1. Clone upstream at the new tag into a scratch directory.
2. Replace `src/` and `tests/` here with the new copies in one commit ("vendor: upstream vX.Y.Z").
3. Re-apply the Omen patch commits (`git cherry-pick`), resolving conflicts.
4. Run the patched tests listed under each patch.
