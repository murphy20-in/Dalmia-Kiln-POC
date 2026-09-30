import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, Presentation, X } from "lucide-react";
import { brandLine, footer, labels, nav, topChip } from "../copy";
import { pages } from "../routes";

const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));

export default function Shell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 768); // icon rail on phones
  const [params] = useSearchParams();
  // Accept ?present=1 in the page URL (before #) or in the hash route query.
  const [present, setPresent] = useState(params.get("present") === "1" || new URLSearchParams(window.location.search).get("present") === "1");
  const { pathname } = useLocation();
  const navigate = useNavigate();

  useEffect(() => { document.documentElement.classList.toggle("present", present); }, [present]);
  const section = pathname.split("/")[1] ?? "";
  useEffect(() => { window.scrollTo(0, 0); }, [section]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.defaultPrevented || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (document.querySelector("[role=dialog]")) return; // an open drawer owns the keyboard
      if (e.key === "p" || e.key === "P") setPresent((v) => !v);
      else if (e.key === "Escape") setPresent(false);
      else if (present && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const base = "/" + (pathname.split("/")[1] ?? "");
        const i = Math.max(0, pages.findIndex((p) => p.path === base));
        const next = pages[i + (e.key === "ArrowRight" ? 1 : -1)];
        if (next) navigate(next.path);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [present, pathname, navigate]);

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 btn-navy">{labels.skip}</a>
      {!present && (
        <div className={`no-print sticky top-0 h-screen shrink-0 border-r border-line bg-white transition-[width] ${collapsed ? "w-16" : "w-60"}`}>
          <div className="flex h-16 items-center justify-between border-b border-line px-4">
            {!collapsed && <span className="text-sm font-bold text-navy">{brandLine.product}</span>}
            <button className="rounded p-1.5 text-ink-muted hover:bg-navy-tint" onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? nav.expand : nav.collapse} title={collapsed ? nav.expand : nav.collapse}>
              {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>
          <nav aria-label={labels.pages} className="flex flex-col gap-1 p-2">
            {pages.map(({ path, label, icon: Icon, muted }) => (
              <NavLink key={path} to={path} end={path === "/"} title={label}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${muted ? "mt-4" : ""} ${
                    isActive ? "bg-navy text-white" : muted ? "text-ink-muted hover:bg-navy-tint" : "text-ink hover:bg-navy-tint"}`}>
                <Icon size={18} aria-hidden className="shrink-0" />
                {!collapsed && <span className="truncate">{label}</span>}
              </NavLink>
            ))}
          </nav>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-20 flex h-16 items-center justify-between gap-2 border-b border-line bg-white/95 px-3 backdrop-blur sm:gap-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-1.5 text-xs font-bold tracking-wide whitespace-nowrap sm:gap-2 sm:text-sm">
            <span className="text-navy">{brandLine.dalmia}</span>
            <span className="text-cyan" aria-hidden>×</span>
            <span className="sr-only">{labels.with}</span>
            <span className="text-ink">{brandLine.vendor}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="chip hidden md:inline-flex"><span className="h-2 w-2 rounded-full bg-cyan" aria-hidden />{topChip}</span>
            <button className="btn-outline py-1.5" onClick={() => setPresent((v) => !v)} title={nav.presentHint}>
              {present ? <X size={16} aria-hidden /> : <Presentation size={16} aria-hidden />}
              <span className="hidden sm:inline">{present ? nav.exitPresent : nav.present}</span>
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="outline-none min-h-[calc(100vh-4rem)] mx-auto w-full max-w-page flex-1 px-4 py-8 sm:px-8">{children}</main>
        <footer className="no-print border-t border-line px-8 py-4 text-center text-xs text-ink-muted">{footer}</footer>
      </div>
    </div>
  );
}
