// AG-UI client for Omen: streams events from POST /agent and reduces them into transcript blocks.

import type { UIPayload } from "./generated/components";

export type AgUiEvent = { type: string; [key: string]: any };

export type Block =
  | { kind: "user"; id: string; text: string }
  | { kind: "assistant"; id: string; text: string; done: boolean }
  | { kind: "reasoning"; id: string; text: string; done: boolean }
  | { kind: "tool"; id: string; name: string; args: string; result?: string; error?: boolean; done: boolean }
  | { kind: "component"; id: string; payload: UIPayload; toolCallId?: string }
  | { kind: "question"; id: string; questionId: string; question: string; options: string[] | null; answer?: string }
  | { kind: "subagent"; id: string; name: string; toolCallId?: string; blocks: Block[]; done: boolean; error?: string }
  | { kind: "note"; id: string; text: string }
  | { kind: "error"; id: string; text: string };

export interface Usage {
  input: number;
  cached: number;
  output: number;
}

export interface ChatState {
  blocks: Block[];
  running: boolean;
  usage: Usage;
}

export const emptyChat = (): ChatState => ({ blocks: [], running: false, usage: { input: 0, cached: 0, output: 0 } });

let counter = 0;
const uid = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(counter++).toString(36)}`;

// -- reducer --------------------------------------------------------------------------- //

type BlockOf<K extends Block["kind"]> = Extract<Block, { kind: K }>;

function update<K extends Block["kind"]>(blocks: Block[], id: string, kind: K, fn: (b: BlockOf<K>) => BlockOf<K>): Block[] {
  return blocks.map((b) => (b.id === id && b.kind === kind ? fn(b as BlockOf<K>) : b));
}

function upsert(blocks: Block[], block: Block): Block[] {
  return blocks.some((b) => b.id === block.id) ? blocks.map((b) => (b.id === block.id ? block : b)) : [...blocks, block];
}

/** Apply one event to a list of blocks (the main transcript or a subagent's). */
function applyToBlocks(blocks: Block[], e: AgUiEvent): Block[] {
  switch (e.type) {
    case "TEXT_MESSAGE_START":
      return upsert(blocks, { kind: "assistant", id: e.messageId, text: "", done: false });
    case "TEXT_MESSAGE_CONTENT":
      return update(blocks, e.messageId, "assistant", (b) => ({ ...b, text: b.text + e.delta }));
    case "TEXT_MESSAGE_END":
      return update(blocks, e.messageId, "assistant", (b) => ({ ...b, done: true }));
    case "REASONING_MESSAGE_START":
      return upsert(blocks, { kind: "reasoning", id: e.messageId, text: "", done: false });
    case "REASONING_MESSAGE_CONTENT":
      return update(blocks, e.messageId, "reasoning", (b) => ({ ...b, text: b.text + e.delta }));
    case "REASONING_MESSAGE_END":
      return update(blocks, e.messageId, "reasoning", (b) => ({ ...b, done: true }));
    case "TOOL_CALL_START":
      return upsert(blocks, { kind: "tool", id: e.toolCallId, name: e.toolCallName, args: "", done: false });
    case "TOOL_CALL_ARGS":
      return update(blocks, e.toolCallId, "tool", (b) => ({ ...b, args: b.args + e.delta }));
    case "TOOL_CALL_RESULT": {
      const content = typeof e.content === "string" ? e.content : JSON.stringify(e.content);
      const error = /^(Error|An error occurred|Tool '.*' not found)/.test(content);
      return update(blocks, e.toolCallId, "tool", (b) => ({ ...b, result: content, error, done: true }));
    }
    case "ACTIVITY_SNAPSHOT": {
      if (e.activityType === "question") {
        const c = e.content ?? {};
        return upsert(blocks, {
          kind: "question", id: e.messageId, questionId: c.question_id, question: c.question, options: c.options ?? null,
        });
      }
      const { tool_call_id, source_message_id: _source, ...payload } = e.content ?? {};
      return upsert(blocks, { kind: "component", id: e.messageId, payload: payload as UIPayload, toolCallId: tool_call_id });
    }
    case "CUSTOM":
      if (e.name === "skill_loaded") return [...blocks, { kind: "note", id: uid("note"), text: `skill: ${e.value?.skill} (${e.value?.by})` }];
      if (e.name === "message_injected") return [...blocks, { kind: "user", id: uid("user"), text: String(e.value) }];
      if (e.name === "compacted") return [...blocks, { kind: "note", id: uid("note"), text: compactionNote(e.value?.tokens_before) }];
      return blocks;
    case "RUN_ERROR":
      return [...blocks, { kind: "error", id: uid("error"), text: e.message }];
    default:
      return blocks;
  }
}

function applyToSubagent(blocks: Block[], subId: string, e: AgUiEvent): Block[] {
  return blocks.map((b) => {
    if (b.kind !== "subagent") return b;
    if (b.id === subId) return { ...b, blocks: applyToBlocks(b.blocks, e) };
    return { ...b, blocks: applyToSubagent(b.blocks, subId, e) };
  });
}

export function reduce(state: ChatState, e: AgUiEvent): ChatState {
  switch (e.type) {
    case "RUN_STARTED":
      return { ...state, running: true };
    case "RUN_FINISHED": {
      const reason = e.result?.reason;
      const blocks = reason && reason !== "done" ? [...state.blocks, { kind: "note" as const, id: uid("note"), text: `[${reason}]` }] : state.blocks;
      return { ...state, running: false, blocks };
    }
    case "SUBAGENT_STARTED":
      return {
        ...state,
        blocks: upsert(state.blocks, { kind: "subagent", id: e.subagentRunId, name: e.name, toolCallId: e.parentToolCallId, blocks: [], done: false }),
      };
    case "SUBAGENT_FINISHED":
      return { ...state, blocks: update(state.blocks, e.subagentRunId, "subagent", (b) => ({ ...b, done: true })) };
    case "SUBAGENT_ERROR":
      return { ...state, blocks: update(state.blocks, e.subagentRunId, "subagent", (b) => ({ ...b, done: true, error: e.message })) };
    case "CUSTOM":
      if (e.name === "usage" && e.value) {
        const u = e.value;
        return {
          ...state,
          usage: {
            input: state.usage.input + (u.input_tokens ?? 0),
            cached: state.usage.cached + (u.cached_tokens ?? 0),
            output: state.usage.output + (u.output_tokens ?? 0),
          },
        };
      }
      break;
  }
  if (e.subagentRunId) return { ...state, blocks: applyToSubagent(state.blocks, e.subagentRunId, e) };
  return { ...state, blocks: applyToBlocks(state.blocks, e) };
}

export function addUserMessage(state: ChatState, text: string): ChatState {
  return { ...state, blocks: [...state.blocks, { kind: "user", id: uid("user"), text }] };
}

export function answerQuestion(state: ChatState, questionId: string, answer: string): ChatState {
  return {
    ...state,
    blocks: state.blocks.map((b) => (b.kind === "question" && b.questionId === questionId ? { ...b, answer } : b)),
  };
}

// -- history ------------------------------------------------------------------------------ //

export interface HistoryMessage {
  role: "user" | "assistant" | "tool_call" | "tool" | "compaction";
  content?: string;
  id?: string;
  name?: string;
  arguments?: string;
  ui?: UIPayload | null;
  components?: UIPayload[];
  tokens_before?: number;
}

export function compactionNote(tokensBefore?: number): string {
  return `earlier conversation summarized${tokensBefore ? ` (was ~${tokensBefore.toLocaleString()} tokens)` : ""}`;
}

/** A saved thread (GET /threads/{id}) as transcript blocks. */
export function fromHistory(messages: HistoryMessage[]): ChatState {
  let state = emptyChat();
  for (const m of messages) {
    if (m.role === "user") state = addUserMessage(state, m.content ?? "");
    else if (m.role === "assistant") {
      const id = uid("msg");
      if (m.content) state.blocks = [...state.blocks, { kind: "assistant", id, text: m.content, done: true }];
      (m.components ?? []).forEach((ui, i) => {
        state = reduce(state, { type: "ACTIVITY_SNAPSHOT", messageId: `${id}-ui-${i}`, activityType: ui.type, content: ui });
      });
    }
    else if (m.role === "compaction") state.blocks = [...state.blocks, { kind: "note", id: uid("note"), text: compactionNote(m.tokens_before) }];
    else if (m.role === "tool_call") state = reduce(reduce(state, { type: "TOOL_CALL_START", toolCallId: m.id, toolCallName: m.name }), { type: "TOOL_CALL_ARGS", toolCallId: m.id, delta: m.arguments ?? "" });
    else if (m.role === "tool") {
      state = reduce(state, { type: "TOOL_CALL_RESULT", toolCallId: m.id, content: m.content ?? "" });
      if (m.ui) state = reduce(state, { type: "ACTIVITY_SNAPSHOT", messageId: `ui-${m.id}`, activityType: m.ui.type, content: m.ui });
    }
  }
  return state;
}

// -- transport ------------------------------------------------------------------------------ //

export interface RunOptions {
  threadId: string;
  text: string;
  persona?: string;
  components: string[];
  signal?: AbortSignal;
}

/** POST /agent and yield AG-UI events as they arrive (SSE over a fetch stream). */
export async function* runAgent(opts: RunOptions): AsyncGenerator<AgUiEvent> {
  const response = await fetch("/agent", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    signal: opts.signal,
    body: JSON.stringify({
      threadId: opts.threadId,
      runId: uid("run"),
      state: {},
      tools: [],
      context: [],
      forwardedProps: { omen: { persona: opts.persona, components: opts.components } },
      messages: [{ id: uid("msg"), role: "user", content: opts.text }],
    }),
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "");
    yield { type: "RUN_ERROR", message: `${response.status} ${detail}` };
    return;
  }
  yield* parseSse(response.body);
}

export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<AgUiEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) yield JSON.parse(data);
    }
  }
}

export const post = (path: string, body?: unknown) =>
  fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
