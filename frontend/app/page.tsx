"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Database, Loader2, Play, ShieldCheck } from "lucide-react";
import { ResultChart } from "./result-chart";

type ChartSpec = {
  type: "table" | "bar" | "line" | "pie" | "number";
  x_column?: string | null;
  y_columns: string[];
};

type QueryResponse = {
  question: string;
  sql?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  chart: ChartSpec;
  explanation?: string | null;
  attempts: number;
  error?: string | null;
};

const exampleQuestions = [
  "How many new users signed up today?",
  "Show daily signups for the last 14 days.",
  "Which plans generated the most revenue this month?",
];

export default function Home() {
  const [question, setQuestion] = useState(exampleQuestions[0]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );

  async function submitQuery() {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${apiBase}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, max_attempts: 3 }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? `Request failed with ${response.status}`);
      }

      const payload = (await response.json()) as QueryResponse;
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="shell">
      <section className="topbar">
        <div className="brand">
          <span className="brandIcon">
            <Database size={22} aria-hidden="true" />
          </span>
          <div>
            <h1>SQLSense</h1>
            <p>Ask PostgreSQL questions in plain English.</p>
          </div>
        </div>
        <div className="guardrail">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>SELECT-only execution</span>
        </div>
      </section>

      <section className="workspace">
        <div className="queryPane">
          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about users, revenue, retention, or any available schema..."
          />
          <div className="examples">
            {exampleQuestions.map((example) => (
              <button
                type="button"
                key={example}
                onClick={() => setQuestion(example)}
                className={question === example ? "selected" : ""}
              >
                {example}
              </button>
            ))}
          </div>
          <button
            className="runButton"
            type="button"
            onClick={submitQuery}
            disabled={isLoading || question.trim().length < 3}
            title="Run query"
          >
            {isLoading ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            <span>{isLoading ? "Running" : "Run"}</span>
          </button>
        </div>

        <div className="resultPane">
          {!result && !error && (
            <div className="emptyState">
              <Database size={32} aria-hidden="true" />
              <p>Results, generated SQL, and charts will appear here.</p>
            </div>
          )}

          {error && (
            <div className="errorBox">
              <AlertTriangle size={20} aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="resultStack">
              <div className={result.error ? "status error" : "status success"}>
                {result.error ? <AlertTriangle size={18} /> : <ShieldCheck size={18} />}
                <span>
                  {result.error
                    ? `Stopped after ${result.attempts} attempt(s)`
                    : `Completed in ${result.attempts} attempt(s)`}
                </span>
              </div>

              {result.explanation && <p className="explanation">{result.explanation}</p>}
              {result.error && <div className="errorBox">{result.error}</div>}

              {result.sql && (
                <div className="sqlBlock">
                  <div className="blockTitle">Generated SQL</div>
                  <pre>{result.sql}</pre>
                </div>
              )}

              {!result.error && (
                <>
                  <ResultChart result={result} />
                  <div className="tableWrap">
                    <table>
                      <thead>
                        <tr>
                          {result.columns.map((column) => (
                            <th key={column}>{column}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {result.columns.map((column) => (
                              <td key={column}>{formatCell(row[column])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}
