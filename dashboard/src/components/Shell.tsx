import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { History, PanelLeftClose, PanelLeftOpen, Presentation, X } from "lucide-react";
import { brandLine, context, labels, nav } from "../copy";
import { pages } from "../routes";
import { BrandFooter, BrandLockup, ProductLine } from "./Brand";

const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));

export default function Shell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1024); // icon rail below 1024 px
  const [params] = useSearchParams();
  // Accept ?present=1 in the page URL (before #) or in the hash route query.
  const [present, setPresent] = useState(params.get("present") === "1" || new URLSearchParams(window.location.search).get("present") === "1");
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // Narrow windows (incl. rotation / resize) fall back to the icon rail.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const on = () => setCollapsed(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => { document.documentElement.classList.toggle("present", present); }, [present]);
  const section = pathname.split("/")[1] ?? "";
  useEffect(() => { window.scrollTo(0, 0); }, [section]);
  useEffect(() => { if (window.innerWidth < 768) setCollapsed(true); }, [pathname]); // the overlay menu closes after a choice
  const current = pages.find((p) => p.path === "/" + section) ?? pages[0];
  // A route change is announced: the tab title names the page and focus moves to <main> (not on first load).
  const firstRoute = useRef(true);
  useEffect(() => {
    document.title = `${current.label} · ${brandLine.product} · ${brandLine.short}`;
    if (firstRoute.current) { firstRoute.current = false; return; }
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [current]);

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
    <div className="flex min-h-screen flex-col">
      <a href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }} className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 btn-navy">{labels.skip}</a>

      {/* One brand moment, top-left: the co-brand lockup. The sidebar and footer carry text only. */}
      <header className="no-print on-dark sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-haze/15 bg-night px-4 sm:px-6">
        <BrandLockup />
        <ProductLine />
        <div className="ml-auto flex shrink-0 items-center gap-4">
          <div className="flex items-center gap-2.5">
            <History size={16} className="text-sky" aria-hidden />
            <div className="hidden text-right leading-none md:block">
              <div className="font-mono text-eyebrow font-medium uppercase text-white">{context.plantShort}</div>
              <div className="mt-1.5 font-mono text-eyebrow uppercase text-haze">{context.statusShort}</div>
            </div>
            <span className="sr-only">{context.status}, {context.period}. {context.statusHint}</span>
          </div>
          <button className="btn-ghost btn-sm" onClick={() => setPresent((v) => !v)} title={nav.presentHint}>
            {present ? <X size={14} aria-hidden /> : <Presentation size={14} aria-hidden />}
            <span className="sr-only sm:not-sr-only">{present ? nav.exitPresent : nav.present}</span>
          </button>
        </div>
      </header>

      <div className="flex flex-1">
        {!present && (
          <div className={`no-print on-dark sticky top-16 flex h-[calc(100vh-4rem)] shrink-0 flex-col self-start border-r border-haze/15 bg-sidebar transition-[width] ${collapsed ? "w-16" : "w-60 max-md:fixed max-md:left-0 max-md:z-30 max-md:shadow-drawer"}`}>
            <nav aria-label={labels.pages} className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2.5 pt-3">
              {pages.map(({ path, label, icon: Icon, group }, i) => (
                <Fragment key={path}>
                  {group !== pages[i - 1]?.group && (collapsed
                    ? i > 0 && <hr className="mx-2 my-2.5 border-haze/20" />
                    : <div className={`px-3 pb-1.5 font-mono text-eyebrow font-medium uppercase text-haze ${i > 0 ? "pt-5" : "pt-1"}`}>{nav.groups[group]}</div>)}
                  <NavLink to={path} end={path === "/"} title={collapsed ? label : undefined}
                    className={({ isActive }) =>
                      `group relative flex h-10 items-center gap-3 rounded-panel px-3 text-label font-medium transition-colors duration-fast ${collapsed ? "justify-center" : ""} ${
                        isActive ? "bg-white/[0.07] font-semibold text-white" : "text-mist hover:bg-white/[0.05] hover:text-white"}`}>
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-sky shadow-glow" aria-hidden />}
                        <Icon size={18} aria-hidden className={`shrink-0 transition-colors duration-fast ${isActive ? "text-sky" : "text-haze group-hover:text-mist"}`} />
                        {!collapsed ? <span className="truncate">{label}</span> : <span className="sr-only">{label}</span>}
                      </>
                    )}
                  </NavLink>
                </Fragment>
              ))}
            </nav>
            <div className={`flex items-center border-t border-haze/15 p-2.5 ${collapsed ? "justify-center" : "justify-between pl-4"}`}>
              {!collapsed && (
                <div className="min-w-0 leading-none">
                  <div className="truncate font-mono text-eyebrow font-medium uppercase text-mist">{brandLine.short}</div>
                  <div className="mt-1.5 truncate text-caption text-haze">{brandLine.stage}</div>
                </div>
              )}
              <button className="rounded-panel p-2 text-haze transition-colors duration-fast hover:bg-white/10 hover:text-white" onClick={() => setCollapsed((c) => !c)}
                aria-label={collapsed ? nav.expand : nav.collapse} title={collapsed ? nav.expand : nav.collapse}>
                {collapsed ? <PanelLeftOpen size={18} aria-hidden /> : <PanelLeftClose size={18} aria-hidden />}
              </button>
            </div>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <main id="main" key={section} tabIndex={-1} className="anim-page min-h-[calc(100vh-4rem)] flex-1 outline-none">{children}</main>
          <BrandFooter />
        </div>
      </div>
    </div>
  );
}
