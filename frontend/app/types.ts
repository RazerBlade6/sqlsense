export type Route = "sql" | "docs" | "both" | "clarify" | "refuse";

export type ChartSpec = {
  type: "table" | "bar" | "line" | "pie" | "number";
  x_column?: string | null;
  y_columns: string[];
};

export type QueryResult = {
  question: string;
  sql?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  chart: ChartSpec;
  explanation?: string | null;
  attempts: number;
  engine?: string | null;
  bytes_scanned?: number | null;
  execution_ms?: number | null;
  truncated: boolean;
  error?: string | null;
};

export type Citation = {
  id: number;
  chunk_id: string;
  doc_id: string;
  doc_type: string;
  title: string;
  heading: string;
  path: string;
  content: string;
  score: number;
};

export type TraceStep = {
  step: "memory" | "planner" | "retrieval" | "sql" | "synthesizer";
  label: string;
  status: "ok" | "rejected" | "failed";
  duration_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  bytes_scanned?: number | null;
  detail: Record<string, unknown>;
};

export type ChatResponse = {
  session_id: string;
  question: string;
  standalone_question: string;
  route: Route;
  answer: string;
  citations: Citation[];
  result?: QueryResult | null;
  trace: TraceStep[];
  total_ms: number;
  error?: string | null;
};

export type Turn =
  | { id: string; question: string; status: "pending" }
  | { id: string; question: string; status: "done"; response: ChatResponse }
  | { id: string; question: string; status: "error"; error: string };
