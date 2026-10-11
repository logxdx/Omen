import { describe, expect, it } from "vitest";

import { answerQuestion, emptyChat, fromHistory, parseSse, reduce, type AgUiEvent, type Block, type ChatState } from "./agui";

const run = (events: AgUiEvent[], start: ChatState = emptyChat()) => events.reduce(reduce, start);
const kinds = (blocks: Block[]) => blocks.map((b) => b.kind);

describe("reduce", () => {
  it("streams assistant text and finishes the run", () => {
    const state = run([
      { type: "RUN_STARTED", threadId: "t", runId: "r" },
      { type: "TEXT_MESSAGE_START", messageId: "m1", role: "assistant" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "Hel" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "m1", delta: "lo" },
      { type: "TEXT_MESSAGE_END", messageId: "m1" },
      { type: "RUN_FINISHED", threadId: "t", runId: "r", result: { reason: "done" } },
    ]);
    expect(state.running).toBe(false);
    expect(state.blocks).toEqual([{ kind: "assistant", id: "m1", text: "Hello", done: true }]);
  });

  it("tool calls, results and their components", () => {
    const payload = { type: "weather", version: 1, valid: true, props: { place: "Pune", temp_c: 26, condition: "Cloudy" }, text: "Pune 26C" };
    const state = run([
      { type: "TOOL_CALL_START", toolCallId: "w1", toolCallName: "get_weather" },
      { type: "TOOL_CALL_ARGS", toolCallId: "w1", delta: '{"city": "Pune"}' },
      { type: "TOOL_CALL_END", toolCallId: "w1" },
      { type: "TOOL_CALL_RESULT", toolCallId: "w1", messageId: "result-w1", content: "Pune: 26°C" },
      { type: "ACTIVITY_SNAPSHOT", messageId: "ui-w1", activityType: "weather", content: { ...payload, tool_call_id: "w1" } },
      { type: "TOOL_CALL_RESULT", toolCallId: "missing", content: "ignored" },
    ]);
    expect(kinds(state.blocks)).toEqual(["tool", "component"]);
    expect(state.blocks[0]).toMatchObject({ name: "get_weather", args: '{"city": "Pune"}', result: "Pune: 26°C", error: false, done: true });
    expect(state.blocks[1]).toMatchObject({ payload, toolCallId: "w1" });
  });

  it("marks tool errors", () => {
    const state = run([
      { type: "TOOL_CALL_START", toolCallId: "x", toolCallName: "read_file" },
      { type: "TOOL_CALL_RESULT", toolCallId: "x", content: "Error in read_file: missing" },
    ]);
    expect(state.blocks[0]).toMatchObject({ error: true });
  });

  it("nests a delegated persona's events under its subagent block", () => {
    const state = run([
      { type: "TOOL_CALL_START", toolCallId: "d1", toolCallName: "delegate" },
      { type: "SUBAGENT_STARTED", subagentRunId: "sub-d1", name: "writer", parentToolCallId: "d1" },
      { type: "TEXT_MESSAGE_START", messageId: "s1", subagentRunId: "sub-d1" },
      { type: "TEXT_MESSAGE_CONTENT", messageId: "s1", delta: "Hi Priya", subagentRunId: "sub-d1" },
      { type: "SUBAGENT_FINISHED", subagentRunId: "sub-d1", result: "Hi Priya" },
      { type: "TOOL_CALL_RESULT", toolCallId: "d1", content: "Hi Priya" },
    ]);
    expect(kinds(state.blocks)).toEqual(["tool", "subagent"]);
    const sub = state.blocks[1] as Extract<Block, { kind: "subagent" }>;
    expect(sub).toMatchObject({ name: "writer", done: true });
    expect(sub.blocks).toEqual([{ kind: "assistant", id: "s1", text: "Hi Priya", done: false }]);
  });

  it("questions and answers", () => {
    let state = run([
      { type: "ACTIVITY_SNAPSHOT", messageId: "question-q1", activityType: "question", content: { question_id: "q1", question: "Tea?", options: ["tea", "coffee"] } },
    ]);
    expect(state.blocks[0]).toMatchObject({ kind: "question", questionId: "q1", options: ["tea", "coffee"] });
    state = answerQuestion(state, "q1", "tea");
    expect(state.blocks[0]).toMatchObject({ answer: "tea" });
  });

  it("accumulates usage for the cache-hit display and notes non-done endings", () => {
    const state = run([
      { type: "CUSTOM", name: "usage", value: { input_tokens: 1000, cached_tokens: 900, output_tokens: 50 } },
      { type: "CUSTOM", name: "usage", value: { input_tokens: 500, cached_tokens: 480, output_tokens: 20 } },
      { type: "CUSTOM", name: "skill_loaded", value: { skill: "web", by: "router" } },
      { type: "RUN_FINISHED", result: { reason: "aborted" } },
    ]);
    expect(state.usage).toEqual({ input: 1500, cached: 1380, output: 70 });
    expect(state.blocks.map((b) => (b.kind === "note" ? b.text : b.kind))).toEqual(["skill: web (router)", "[aborted]"]);
  });
});

describe("fromHistory", () => {
  it("rebuilds blocks with components from a saved thread", () => {
    const state = fromHistory([
      { role: "user", content: "weather?" },
      { role: "tool_call", id: "w1", name: "get_weather", arguments: "{}" },
      { role: "tool", id: "w1", name: "get_weather", content: "26C", ui: { type: "weather", valid: true, props: {}, text: "26C" } },
      { role: "assistant", content: "It's 26°C." },
    ]);
    expect(kinds(state.blocks)).toEqual(["user", "tool", "component", "assistant"]);
  });

  it("puts a reply's saved components after it", () => {
    const chart = { type: "chart", valid: true, props: { labels: ["a"], values: [1] }, text: "a: 1" };
    const state = fromHistory([
      { role: "user", content: "chart it" },
      { role: "assistant", content: "a: 1", components: [chart] },
    ]);
    expect(kinds(state.blocks)).toEqual(["user", "assistant", "component"]);
  });
});

describe("parseSse", () => {
  it("handles frames split across chunks", async () => {
    const encoder = new TextEncoder();
    const chunks = ['data: {"type":"RUN_STA', 'RTED"}\n\ndata: {"type":"TEXT_MESSAGE_CONTENT","delta":"a\\nb"}\n', "\n"];
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
        controller.close();
      },
    });
    const events: AgUiEvent[] = [];
    for await (const e of parseSse(body)) events.push(e);
    expect(events).toEqual([{ type: "RUN_STARTED" }, { type: "TEXT_MESSAGE_CONTENT", delta: "a\nb" }]);
  });
});
