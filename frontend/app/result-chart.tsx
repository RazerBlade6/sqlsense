"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type QueryResponse = {
  columns: string[];
  rows: Record<string, unknown>[];
  chart: {
    type: "table" | "bar" | "line" | "pie" | "number";
    x_column?: string | null;
    y_columns: string[];
  };
};

const colors = ["#2563eb", "#0f9f6e", "#f59e0b", "#dc2626", "#7c3aed"];

export function ResultChart({ result }: { result: QueryResponse }) {
  const chart = normalizeChart(result);

  if (result.rows.length === 0) {
    return <div className="emptyChart">No rows returned.</div>;
  }

  if (chart.type === "number") {
    const metricColumn = chart.yColumns[0] ?? result.columns[0];
    if (!metricColumn) {
      return null;
    }

    const value = result.rows[0]?.[metricColumn];
    return (
      <div className="metric">
        <span>{metricColumn}</span>
        <strong>{formatValue(value)}</strong>
      </div>
    );
  }

  if (!chart.xColumn || chart.yColumns.length === 0 || chart.type === "table") {
    return null;
  }

  if (chart.type === "pie") {
    const dataKey = chart.yColumns[0];
    return (
      <div className="chartBox">
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Tooltip />
            <Pie
              data={result.rows}
              dataKey={dataKey}
              nameKey={chart.xColumn}
              outerRadius={105}
              label
            >
              {result.rows.map((_, index) => (
                <Cell key={index} fill={colors[index % colors.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (chart.type === "line") {
    return (
      <div className="chartBox">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={result.rows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={chart.xColumn} />
            <YAxis />
            <Tooltip />
            {chart.yColumns.map((column, index) => (
              <Line
                key={column}
                type="monotone"
                dataKey={column}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div className="chartBox">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={result.rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={chart.xColumn} />
          <YAxis />
          <Tooltip />
          {chart.yColumns.map((column, index) => (
            <Bar key={column} dataKey={column} fill={colors[index % colors.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function normalizeChart(result: QueryResponse) {
  const numericColumns = result.columns.filter((column) =>
    result.rows.some((row) => typeof row[column] === "number"),
  );
  const firstLabelColumn = result.columns.find((column) => !numericColumns.includes(column));

  return {
    type: result.chart.type,
    xColumn: result.chart.x_column ?? firstLabelColumn ?? result.columns[0],
    yColumns: result.chart.y_columns.length > 0 ? result.chart.y_columns : numericColumns,
  };
}

function formatValue(value: unknown) {
  if (typeof value === "number") {
    return new Intl.NumberFormat().format(value);
  }
  return value === null || value === undefined ? "" : String(value);
}
