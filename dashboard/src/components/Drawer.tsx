import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { common } from "../copy";

/** Right-side modal drawer, portalled to <body>. The app behind it is made inert (no Tab escape),
 *  Escape closes, and focus returns to where it was (or the main landmark) on close. */
export default function Drawer({ title, meta, onClose, children }: { title: string; meta?: ReactNode; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const id = useId();
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const app = document.getElementById("root");
    app?.setAttribute("inert", "");
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); close.current(); } };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      app?.removeAttribute("inert");
      (prev?.isConnected && prev !== document.body ? prev : document.getElementById("main"))?.focus();
    };
  }, []);
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end">
      <div aria-hidden className="anim-fade absolute inset-0 bg-navy-ink/30" onClick={() => close.current()} />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}
        className="anim-drawer relative flex h-full w-full max-w-xl flex-col bg-white shadow-drawer outline-none">
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div className="min-w-0">
            <h2 id={id} className="text-title font-bold text-navy-ink">{title}</h2>
            {meta && <div className="mt-2 flex flex-wrap gap-2">{meta}</div>}
          </div>
          <button onClick={() => close.current()} className="rounded-panel p-2 text-ink-muted transition-colors hover:bg-page hover:text-navy" aria-label={common.close}><X size={20} aria-hidden /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

/** A titled block inside a drawer, separated by a hairline. */
export function DrawerSection({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <section className="border-t border-line py-5 first:border-t-0 first:pt-0">
      <h3 className="t-card">{title}</h3>
      {sub && <p className="mt-0.5 text-caption text-ink-muted">{sub}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}
