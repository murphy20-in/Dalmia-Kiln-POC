import { useId, useState, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { common } from "../copy";
import { Legend, Source } from "./ui";

export interface TableData { columns: string[]; rows: (string | number)[][] }

/** Takeaway title → subtitle → chart (or its data table) → legend → source line. */
export default function ChartCard({ title, sub, table, children, actions, legend, source, className = "" }: {
  title: string; sub?: string; table?: TableData; children: ReactNode; actions?: ReactNode;
  legend?: { name: string; color: string; dashed?: boolean }[]; source?: string; className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <section className={`card flex flex-col ${className}`} aria-labelledby={id}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-[22rem]">
          <h2 id={id} className="t-section">{title}</h2>
          {sub && <p className="mt-1 max-w-prose text-label text-ink-muted">{sub}</p>}
        </div>
        <div className="no-print flex flex-wrap items-center justify-end gap-2">
          {actions}
          {table && (
            <button className="btn-outline btn-sm" onClick={() => setShowTable((v) => !v)}>
              {showTable ? <BarChart3 size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
              {showTable ? common.viewChart : common.viewData}
            </button>
          )}
        </div>
      </div>
      {showTable && table ? (
        <div className="anim-fade max-h-80 overflow-auto rounded-panel border border-line" tabIndex={0} role="region" aria-label={title}>
          <table className="data-table [&_td:first-child]:pl-3 [&_th:first-child]:pl-3">
            <caption className="sr-only">{title}</caption>
            <thead><tr>{table.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "text-right" : undefined}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        <>
          {children}
          {legend && <Legend items={legend} className="mt-3" />}
        </>
      )}
      {source && <Source>{source}</Source>}
    </section>
  );
}
