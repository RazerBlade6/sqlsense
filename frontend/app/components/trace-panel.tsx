import { BookOpen, Brain, Database, MessageSquareText, Route } from "lucide-react";
import type { ReactNode } from "react";
import type { ChatResponse, TraceStep } from "../types";
import { formatBytes } from "./answer-card";

const icons: Record<TraceStep["step"], ReactNode> = {
  memory: <MessageSquareText size={16} />,
  planner: <Route size={16} />,
  retrieval: <BookOpen size={16} />,
  sql: <Database size={16} />,
  synthesizer: <Brain size={16} />,
};

/** Timeline of one answer: planner → retrieval → SQL attempts → synthesis. */
export function TracePanel({ response }: { response: ChatResponse | null }) {
  if (!response) {
    return (
      <div className="tracePanel empty">
        <p>Ask a question to see how the agents answered it: the route the planner chose, the
          documents retrieved, every SQL attempt and its errors, and the time and tokens each
          step used.</p>
      </div>
    );
  }

  const total = Math.max(response.total_ms, 1);
  const tokens = response.trace.reduce(
    (sum, s) => sum + (s.input_tokens ?? 0) + (s.output_tokens ?? 0),
    0,
  );

  return (
    <div className="tracePanel">
      <div className="traceSummary">
        <div><strong>{(response.total_ms / 1000).toFixed(1)}s</strong><span>total</span></div>
        <div><strong>{tokens.toLocaleString()}</strong><span>tokens</span></div>
        <div><strong>{response.trace.length}</strong><span>steps</span></div>
      </div>
      <ol className="timeline">
        {response.trace.map((step, i) => (
          <li key={i} className={`traceStep status-${step.status}`}>
            <div className="traceHead">
              <span className="traceIcon">{icons[step.step]}</span>
              <span className="traceLabel">{step.label}</span>
              <span className="muted">{step.duration_ms} ms</span>
            </div>
            <div className="traceBar">
              <span style={{ width: `${Math.max(2, (100 * step.duration_ms) / total)}%` }} />
            </div>
            <div className="traceStats muted">
              {step.input_tokens != null && (
                <span>{step.input_tokens.toLocaleString()} in / {(step.output_tokens ?? 0).toLocaleString()} out tokens</span>
              )}
              {step.bytes_scanned != null && <span>{formatBytes(step.bytes_scanned)} scanned</span>}
            </div>
            <StepDetail step={step} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function StepDetail({ step }: { step: TraceStep }) {
  const d = step.detail as Record<string, any>;
  if (step.step === "planner") {
    return (
      <div className="traceDetail">
        <div>Standalone question: {d.standalone_question}</div>
        {d.needs_definitions?.length > 0 && <div>Needs definitions: {d.needs_definitions.join(", ")}</div>}
        {d.upgraded_by_glossary && <div>Route upgraded to &ldquo;both&rdquo;: the question uses a documented term.</div>}
      </div>
    );
  }
  if (step.step === "retrieval") {
    return (
      <div className="traceDetail">
        <div>Queries: {(d.queries ?? []).join(" · ")}</div>
        <table className="hits">
          <thead>
            <tr><th>Document</th><th>Vector</th><th>Keyword</th></tr>
          </thead>
          <tbody>
            {(d.hits ?? []).map((h: any) => (
              <tr key={h.doc_id}>
                <td>{h.title}</td>
                <td>{h.vector_rank ?? "–"}</td>
                <td>{h.keyword_rank ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (step.step === "sql") {
    return (
      <details className="traceDetail">
        <summary>SQL{d.error ? " and error" : ""}</summary>
        <pre>{d.sql}</pre>
        {d.error && <div className="traceError">{d.error}</div>}
      </details>
    );
  }
  return null;
}
