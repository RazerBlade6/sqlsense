"use client";

import { useEffect, useRef, useState } from "react";
import { Database, Loader2, MessageSquarePlus, Send, ShieldCheck } from "lucide-react";
import { AnswerCard } from "./components/answer-card";
import { TracePanel } from "./components/trace-panel";
import type { ChatResponse, Turn } from "./types";

const examples = [
  "Which 5 departments had the highest sales?",
  "How many active households are there?",
  "What was the household retention rate from Q3 to Q4?",
  "How are Type A campaigns targeted?",
  "What was the coupon redemption rate for campaign 13?",
];

const SESSION_KEY = "sqlsense-session";

export default function Home() {
  const [apiBase, setApiBase] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(loadSession());
    // Deployed: CloudFront serves config.json with the API URL. Locally: env or localhost.
    fetch("/config.json")
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((config) =>
        setApiBase(
          (config?.apiUrl ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
        ),
      );
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  const busy = turns.some((t) => t.status === "pending");
  const selectedTurn = turns.find((t) => t.id === selected);
  const selectedResponse =
    selectedTurn?.status === "done" ? selectedTurn.response : latestResponse(turns);

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 3 || !apiBase || busy) return;
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, question: q, status: "pending" }]);
    setQuestion("");
    try {
      const res = await fetch(`${apiBase}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, session_id: sessionId }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail ?? `Request failed with ${res.status}`);
      const response = payload as ChatResponse;
      setTurns((prev) => prev.map((t) => (t.id === id ? { id, question: q, status: "done", response } : t)));
      setSelected(id);
    } catch (caught) {
      const error = caught instanceof Error ? caught.message : "Something went wrong";
      setTurns((prev) => prev.map((t) => (t.id === id ? { id, question: q, status: "error", error } : t)));
    }
  }

  function newConversation() {
    setSessionId(loadSession(true));
    setTurns([]);
    setSelected(null);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brandIcon">
            <Database size={22} aria-hidden="true" />
          </span>
          <div>
            <h1>SQLSense</h1>
            <p>Ask about a year of grocery retail data. Agents query the warehouse and search the business documents.</p>
          </div>
        </div>
        <div className="topActions">
          <span className="guardrail">
            <ShieldCheck size={18} aria-hidden="true" /> Read-only
          </span>
          <button type="button" className="ghostButton" onClick={newConversation}>
            <MessageSquarePlus size={18} aria-hidden="true" /> New conversation
          </button>
        </div>
      </header>

      <section className="workspace">
        <div className="chatPane">
          <div className="thread">
            {turns.length === 0 && (
              <div className="emptyState">
                <p>Try one of these, then ask a follow-up:</p>
                <div className="examples">
                  {examples.map((example) => (
                    <button type="button" key={example} onClick={() => ask(example)} disabled={!apiBase}>
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((turn) => (
              <div key={turn.id} className="turn">
                <div className="userBubble">{turn.question}</div>
                {turn.status === "pending" && (
                  <div className="pending">
                    <Loader2 className="spin" size={18} /> Planning, retrieving and querying…
                  </div>
                )}
                {turn.status === "error" && <div className="errorBox">{turn.error}</div>}
                {turn.status === "done" && (
                  <AnswerCard
                    response={turn.response}
                    selected={selectedResponse === turn.response}
                    onSelect={() => setSelected(turn.id)}
                  />
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              ask(question);
            }}
          >
            <textarea
              aria-label="Question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(question);
                }
              }}
              placeholder="Ask about sales, households, promotions or campaigns…"
              rows={2}
            />
            <button className="runButton" type="submit" disabled={busy || !apiBase || question.trim().length < 3} title="Ask">
              {busy ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            </button>
          </form>
        </div>

        <aside className="tracePane">
          <div className="blockTitle">Agent trace</div>
          <TracePanel response={selectedResponse ?? null} />
        </aside>
      </section>

      <footer className="footer">
        Data: The Complete Journey (84.51°, CC0), 2017. Business documents are synthetic.{" "}
        <a href="https://github.com/RazerBlade6/sqlsense">Source on GitHub</a>
      </footer>
    </main>
  );
}

function latestResponse(turns: Turn[]): ChatResponse | undefined {
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.status === "done") return t.response;
  }
  return undefined;
}

function loadSession(fresh = false): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing && !fresh) return existing;
    const id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}
