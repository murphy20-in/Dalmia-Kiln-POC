import { Fragment, useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { History, PanelLeftClose, PanelLeftOpen, Presentation, X } from "lucide-react";
import { brandLine, context, footer, labels, nav } from "../copy";
import { pages } from "../routes";
import { brand } from "../theme";

const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));

/** Product mark: a kiln-gauge arc. Same drawing as the favicon. */
const Mark = () => (
  <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
    <rect width="32" height="32" rx="7" fill={brand.navy} />
    <path d="M7 21a9 9 0 0 1 18 0" stroke={brand.cyan} strokeWidth="3" fill="none" strokeLinecap="round" />
    <path d="M16 21l5-6" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

export default function Shell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 768); // icon rail on phones
  const [params] = useSearchParams();
  // Accept ?present=1 in the page URL (before #) or in the hash route query.
  const [present, setPresent] = useState(params.get("present") === "1" || new URLSearchParams(window.location.search).get("present") === "1");
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // Phones and narrow windows (incl. rotation / resize) fall back to the icon rail.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const on = () => setCollapsed(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => { document.documentElement.classList.toggle("present", present); }, [present]);
  const section = pathname.split("/")[1] ?? "";
  useEffect(() => { window.scrollTo(0, 0); }, [section]);
  const current = pages.find((p) => p.path === "/" + section) ?? pages[0];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.defaultPrevented || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (document.querySelector("[role=dialog]")) return; // an open drawer owns the keyboard
      if (e.key === "P" && e.shiftKey) setPresent((v) => !v); // Shift+P: a modifier keeps it off single-key typing (WCAG 2.1.4)
      else if (e.key === "Escape") setPresent(false);
      else if (present && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const i = Math.max(0, pages.indexOf(current));
        const next = pages[i + (e.key === "ArrowRight" ? 1 : -1)];
        if (next) navigate(next.path);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [present, current, navigate]);

  return (
    <div className="flex min-h-screen">
      <a href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }} className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 btn-navy">{labels.skip}</a>
      {!present && (
        <aside className={`no-print sticky top-0 flex h-screen shrink-0 flex-col border-r border-line bg-white transition-[width] ${collapsed ? "w-16" : "w-60 max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-30 max-md:shadow-drawer"}`}>
          <div className={`flex h-14 items-center gap-2.5 border-b border-line ${collapsed ? "justify-center" : "px-4"}`}>
            <Mark />
            {!collapsed && (
              <div className="min-w-0 leading-tight">
                <div className="truncate text-label font-bold text-navy-ink">{brandLine.product}</div>
                <div className="truncate text-caption text-ink-muted">{brandLine.stage}</div>
              </div>
            )}
          </div>
          <nav aria-label={labels.pages} className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
            {pages.map(({ path, label, icon: Icon, group }, i) => (
              <Fragment key={path}>
                {group !== pages[i - 1]?.group && (collapsed
                  ? i > 0 && <hr className="mx-2 my-2 border-line" />
                  : <div className={`px-3 pb-1 text-caption font-semibold text-ink-muted ${i > 0 ? "pt-4" : "pt-1"}`}>{nav.groups[group]}</div>)}
                <NavLink to={path} end={path === "/"} title={collapsed ? label : undefined}
                  className={({ isActive }) =>
                    `relative flex h-9 items-center gap-3 rounded-panel px-3 text-label font-medium transition-colors ${collapsed ? "justify-center" : ""} ${
                      isActive ? "bg-navy-tint font-semibold text-navy-ink" : "text-ink-body hover:bg-page hover:text-navy-ink"}`}>
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-cyan" aria-hidden />}
                      <Icon size={18} aria-hidden className={`shrink-0 ${isActive ? "text-navy" : "text-ink-muted"}`} />
                      {!collapsed ? <span className="truncate">{label}</span> : <span className="sr-only">{label}</span>}
                    </>
                  )}
                </NavLink>
              </Fragment>
            ))}
          </nav>
          <div className={`flex items-center border-t border-line p-2 ${collapsed ? "justify-center" : "justify-between pl-4"}`}>
            {!collapsed && <span className="truncate text-caption text-ink-muted">{brandLine.builtBy}</span>}
            <button className="rounded-panel p-2 text-ink-muted transition-colors hover:bg-page hover:text-navy" onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? nav.expand : nav.collapse} title={collapsed ? nav.expand : nav.collapse}>
              {collapsed ? <PanelLeftOpen size={18} aria-hidden /> : <PanelLeftClose size={18} aria-hidden />}
            </button>
          </div>
        </aside>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6">
          <div className="flex min-w-0 items-center gap-2 text-label">
            <span className="hidden text-ink-muted sm:inline">{nav.groups[current.group]}</span>
            <span className="hidden text-line-strong sm:inline" aria-hidden>/</span>
            <span className="truncate font-semibold text-navy-ink">{current.label}</span>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden text-caption text-ink-muted lg:inline">{context.plant} · {context.period}</span>
            <span className="inline-flex items-center gap-1.5 rounded-panel border border-navy-line bg-navy-tint px-2 py-1 text-caption font-semibold uppercase tracking-wide text-navy-ink md:px-2.5" title={context.statusHint}>
              <History size={13} aria-hidden /> <span className="sr-only md:not-sr-only">{context.status}</span><span className="sr-only">. {context.statusHint}</span>
            </span>
            <button className="btn-outline btn-sm" onClick={() => setPresent((v) => !v)} title={nav.presentHint}>
              {present ? <X size={14} aria-hidden /> : <Presentation size={14} aria-hidden />}
              <span className="sr-only sm:not-sr-only">{present ? nav.exitPresent : nav.present}</span>
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="mx-auto min-h-[calc(100vh-3.5rem)] w-full max-w-page flex-1 px-4 py-6 outline-none sm:px-8">{children}</main>
        <footer className="no-print border-t border-line px-8 py-4 text-center text-caption text-ink-muted">{footer}</footer>
      </div>
    </div>
  );
}
