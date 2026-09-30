import { useId, useState, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { common } from "../copy";

export interface TableData { columns: string[]; rows: (string | number)[][] }

/** Card with a takeaway title and a "View data" toggle that swaps the chart for its table. */
export default function ChartCard({ title, sub, table, children, actions, className = "" }: {
  title: string; sub?: string; table?: TableData; children: ReactNode; actions?: ReactNode; className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <section className={`card ${className}`} aria-labelledby={id}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={id} className="text-lg font-semibold leading-snug">{title}</h2>
          {sub && <p className="mt-0.5 text-sm text-ink-muted">{sub}</p>}
        </div>
        <div className="no-print flex items-center gap-2">
          {actions}
          {table && (
            <button className="btn-outline px-3 py-1.5 text-xs" onClick={() => setShowTable((v) => !v)}>
              {showTable ? <BarChart3 size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
              {showTable ? common.viewChart : common.viewData}
            </button>
          )}
        </div>
      </div>
      {showTable && table ? (
        <div className="max-h-80 overflow-auto" tabIndex={0} role="region" aria-label={title}>
          <table className="data-table">
            <caption className="sr-only">{title}</caption>
            <thead><tr>{table.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : children}
    </section>
  );
}
