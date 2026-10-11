import { useCallback, useEffect, useRef, useState } from "react";

import { addUserMessage, answerQuestion, emptyChat, fromHistory, post, reduce, runAgent, type ChatState } from "./agui";
import { SUPPORTED } from "./components/registry";
import { Transcript } from "./Transcript";

interface Thread {
  id: string;
  updated: number;
}
interface Persona {
  name: string;
  description: string;
  main: boolean;
}

const newThreadId = () => `web-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}-${Math.random().toString(36).slice(2, 6)}`;

export default function App() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<string>("omen");
  const [threadId, setThreadId] = useState<string>(newThreadId);
  const [chat, setChat] = useState<ChatState>(emptyChat);
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  const refreshThreads = useCallback(() => {
    fetch("/threads").then((r) => r.json()).then(setThreads).catch(() => setThreads([]));
  }, []);

  useEffect(() => {
    refreshThreads();
    fetch("/personas").then((r) => r.json()).then((list: Persona[]) => setPersonas(list.filter((p) => p.main))).catch(() => {});
  }, [refreshThreads]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [chat.blocks]);

  const openThread = async (id: string) => {
    if (chat.running) return;
    const response = await fetch(`/threads/${id}`);
    if (!response.ok) return;
    const data = await response.json();
    setThreadId(id);
    setChat(fromHistory(data.messages));
  };

  const newChat = () => {
    if (chat.running) return;
    setThreadId(newThreadId());
    setChat(emptyChat());
  };

  const send = async (text: string) => {
    if (chat.running) {
      // Steering: delivered to the running agent after its current step.
      const response = await post(`/threads/${threadId}/messages`, { text });
      if (response.ok) setChat((c) => addUserMessage(c, `${text}  (queued)`));
      return;
    }
    setChat((c) => ({ ...addUserMessage(c, text), running: true }));
    for await (const event of runAgent({ threadId, text, persona, components: SUPPORTED })) {
      setChat((c) => reduce(c, event));
    }
    setChat((c) => ({ ...c, running: false }));
    refreshThreads();
  };

  const submit = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    void send(text);
  };

  const onAnswer = async (questionId: string, answer: string) => {
    const response = await post(`/threads/${threadId}/answer`, { text: answer });
    if (response.ok) setChat((c) => answerQuestion(c, questionId, answer));
  };

  const cacheRate = chat.usage.input ? Math.round((100 * chat.usage.cached) / chat.usage.input) : null;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">omen</div>
        <button className="new-chat" onClick={newChat} disabled={chat.running}>+ New chat</button>
        <label className="persona">
          persona
          <select value={persona} onChange={(e) => setPersona(e.target.value)} disabled={chat.running}>
            {(personas.length ? personas : [{ name: "omen", description: "", main: true }]).map((p) => (
              <option key={p.name} value={p.name} title={p.description}>{p.name}</option>
            ))}
          </select>
        </label>
        <div className="threads">
          {threads.map((t) => (
            <button key={t.id} className={`thread ${t.id === threadId ? "active" : ""}`} onClick={() => openThread(t.id)}>
              {t.id}
              <span className="muted">{new Date(t.updated * 1000).toLocaleString()}</span>
            </button>
          ))}
        </div>
        <div className="stats muted">
          {chat.usage.input + chat.usage.output} tokens{cacheRate !== null ? ` · cache ${cacheRate}%` : ""}
        </div>
      </aside>
      <main className="chat">
        <div className="transcript">
          {chat.blocks.length === 0 && <div className="empty">Ask Omen anything. Try “What’s the weather in Pune?”</div>}
          <Transcript blocks={chat.blocks} onAnswer={onAnswer} />
          <div ref={bottom} />
        </div>
        <div className="composer">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={chat.running ? "Omen is working… type to steer (delivered after the current step)" : "Message Omen…"}
            rows={2}
          />
          {chat.running ? (
            <button className="stop" onClick={() => post(`/threads/${threadId}/abort`)}>Stop</button>
          ) : (
            <button onClick={submit} disabled={!input.trim()}>Send</button>
          )}
        </div>
      </main>
    </div>
  );
}
