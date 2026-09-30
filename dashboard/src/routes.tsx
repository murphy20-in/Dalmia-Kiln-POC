import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { CalendarRange, Database, Flame, Gauge, LayoutDashboard, Map, ShieldCheck, TrendingUp, type LucideIcon } from "lucide-react";
import { nav } from "./copy";

export interface PageRoute {
  path: string;
  label: string;
  icon: LucideIcon;
  Component: LazyExoticComponent<ComponentType>;
  muted?: boolean;
}

// Pitch order = nav order = presentation ← → order.
export const pages: PageRoute[] = [
  { path: "/", label: nav.summary, icon: LayoutDashboard, Component: lazy(() => import("./pages/ExecSummary")) },
  { path: "/console", label: nav.console, icon: Gauge, Component: lazy(() => import("./pages/Console")) },
  { path: "/efficiency", label: nav.efficiency, icon: TrendingUp, Component: lazy(() => import("./pages/Efficiency")) },
  { path: "/periods", label: nav.periods, icon: CalendarRange, Component: lazy(() => import("./pages/Periods")) },
  { path: "/alternative-fuel", label: nav.fuel, icon: Flame, Component: lazy(() => import("./pages/AltFuel")) },
  { path: "/data", label: nav.data, icon: Database, Component: lazy(() => import("./pages/DataReadiness")) },
  { path: "/roadmap", label: nav.roadmap, icon: Map, Component: lazy(() => import("./pages/Roadmap")) },
  { path: "/validation", label: nav.validation, icon: ShieldCheck, Component: lazy(() => import("./pages/Validation")), muted: true },
];
