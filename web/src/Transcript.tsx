import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";

import type { Block } from "./agui";
import { Component } from "./components/registry";

function compactArgs(raw: string): string {
  try {
    const data = JSON.parse(raw || "{}");
    return Object.entries(data)
      .map(([k, v]) => `${k}=${typeof v === "string" ? (v.length > 60 ? JSON.stringify(v.slice(0, 57) + "…") : JSON.stringify(v)) : JSON.stringify(v)}`)
      .join(", ");
  } catch {
    return raw.slice(0, 200);
  }
}

function Collapsible({ title, className, open: initial = false, children }: { title: React.ReactNode; className?: string; open?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className={`collapsible ${className ?? ""} ${open ? "open" : ""}`}>
      <button className="collapsible-title" onClick={() => setOpen(!open)}>
        <span className="chevron">{open ? "▾" : "▸"}</span> {title}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}

function Question({ block, onAnswer }: { block: Extract<Block, { kind: "question" }>; onAnswer: (questionId: string, answer: string) => void }) {
  const [text, setText] = useState("");
  if (block.answer) {
    return <div className="line"><span className="icon">?</span>{block.question} <b>→ {block.answer}</b></div>;
  }
  return (
    <div className="question">
      <div className="question-text">? {block.question}</div>
      <div className="options">
        {(block.options ?? []).map((o) => (
          <button key={o} onClick={() => onAnswer(block.questionId, o)}>{o}</button>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) onAnswer(block.questionId, text.trim()); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="or type an answer…" />
        </form>
      </div>
    </div>
  );
}

export function Transcript({ blocks, onAnswer }: { blocks: Block[]; onAnswer: (questionId: string, answer: string) => void }) {
  return (
    <>
      {blocks.map((block) => {
        switch (block.kind) {
          case "user":
            return <div key={block.id} className="user"><div className="bubble">{block.text}</div></div>;
          case "assistant":
            return (
              <div key={block.id} className={`assistant ${block.done ? "" : "streaming"}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{block.text}</ReactMarkdown>
              </div>
            );
          case "reasoning":
            return block.text.trim() ? (
              <Collapsible key={block.id} className="reasoning" title={block.done ? "thought" : "thinking…"}>
                <div className="reasoning-text">{block.text}</div>
              </Collapsible>
            ) : null;
          case "tool":
            return (
              <Collapsible
                key={block.id}
                className={`tool ${block.error ? "error" : ""}`}
                title={<><span className="status">{block.done ? (block.error ? "✗" : "✓") : "…"}</span> {block.name} <span className="muted">{compactArgs(block.args)}</span></>}
              >
                {block.result && <pre className="tool-result">{block.result}</pre>}
              </Collapsible>
            );
          case "component":
            return <Component key={block.id} payload={block.payload} />;
          case "question":
            return <Question key={block.id} block={block} onAnswer={onAnswer} />;
          case "subagent":
            return (
              <Collapsible key={block.id} className="subagent" open={!block.done} title={<>↳ <b>{block.name}</b>{block.done ? "" : " working…"}</>}>
                <Transcript blocks={block.blocks} onAnswer={onAnswer} />
                {block.error && <div className="error">{block.error}</div>}
              </Collapsible>
            );
          case "note":
            return <div key={block.id} className="note">{block.text}</div>;
          case "error":
            return <div key={block.id} className="error">✗ {block.text}</div>;
        }
      })}
    </>
  );
}
