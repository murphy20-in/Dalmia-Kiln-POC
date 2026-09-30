import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { common } from "../copy";

/** Right-side modal drawer, portalled to <body>. The app behind it is made inert (no Tab escape),
 *  Escape closes, and focus returns to where it was (or the main landmark) on close. */
export default function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
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
      (prev && prev !== document.body ? prev : document.getElementById("main"))?.focus();
    };
  }, []);
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end">
      <div aria-hidden className="absolute inset-0 bg-navy-ink/30" onClick={() => close.current()} />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}
        className="relative h-full w-full max-w-lg overflow-y-auto bg-white p-8 shadow-2xl outline-none">
        <div className="mb-6 flex items-start justify-between gap-4">
          <h2 id={id} className="text-2xl font-bold">{title}</h2>
          <button onClick={() => close.current()} className="rounded p-1.5 text-ink-muted hover:bg-navy-tint" aria-label={common.close}><X size={20} aria-hidden /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
