"use client";

import { useState } from "react";
import { AlertTriangle, BookOpen, Code2, Table2 } from "lucide-react";
import { ResultChart } from "../result-chart";
import type { ChatResponse } from "../types";
import { Markdown } from "./markdown";

const routeLabels: Record<ChatResponse["route"], string> = {
  sql: "Warehouse",
  docs: "Documents",
  both: "Warehouse + documents",
  clarify: "Needs clarification",
  refuse: "Declined",
};

export function AnswerCard({
  response,
  selected,
  onSelect,
}: {
  response: ChatResponse;
  selected: boolean;
  onSelect: () => void;
}) {
  const [openCitation, setOpenCitation] = useState<number | null>(null);
  const result = response.result;
  const hasRows = !!result && !result.error && result.rows.length > 0;

  return (
    <article className={`answerCard${selected ? " selected" : ""}`} onClick={onSelect}>
      <div className="answerMeta">
        <span className={`routeBadge route-${response.route}`}>{routeLabels[response.route]}</span>
        <span>{(response.total_ms / 1000).toFixed(1)}s</span>
        {response.standalone_question !== response.question && (
          <span className="rewritten" title="The planner rewrote the follow-up">
            Understood as: {response.standalone_question}
          </span>
        )}
      </div>

      <Markdown text={response.answer} onCite={(id) => setOpenCitation(id)} />

      {result?.error && (
        <div className="errorBox">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>{result.error}</span>
        </div>
      )}

      {result && hasRows && <ResultChart result={result} />}

      {result?.sql && (
        <details className="collapsible">
          <summary>
            <Code2 size={16} aria-hidden="true" /> SQL
            {result.bytes_scanned != null && (
              <span className="muted"> · {formatBytes(result.bytes_scanned)} scanned on {result.engine}</span>
            )}
          </summary>
          <pre>{result.sql}</pre>
        </details>
      )}

      {result && hasRows && (
        <details className="collapsible">
          <summary>
            <Table2 size={16} aria-hidden="true" /> {result.rows.length} row{result.rows.length === 1 ? "" : "s"}
            {result.truncated && <span className="muted"> (truncated)</span>}
          </summary>
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
                {result.rows.map((row, i) => (
                  <tr key={i}>
                    {result.columns.map((column) => (
                      <td key={column}>{formatCell(row[column])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {response.citations.length > 0 && (
        <div className="citations">
          <div className="blockTitle">
            <BookOpen size={14} aria-hidden="true" /> Sources
          </div>
          {response.citations.map((c) => (
            <details
              key={c.id}
              className="citation"
              open={openCitation === c.id}
              onToggle={(e) => (e.currentTarget.open ? setOpenCitation(c.id) : null)}
            >
              <summary>
                <span className="citeMarker static">{c.id}</span>
                <span>{c.title}</span>
                <span className="muted">{c.path}</span>
              </summary>
              <pre className="citationText">{c.content}</pre>
            </details>
          ))}
        </div>
      )}
    </article>
  );
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return new Intl.NumberFormat().format(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
