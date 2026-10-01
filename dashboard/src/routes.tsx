import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { CalendarRange, Database, Flame, Gauge, LayoutDashboard, Map, ShieldCheck, TrendingUp, type LucideIcon } from "lucide-react";
import { nav } from "./copy";

export type NavGroup = keyof typeof nav.groups;

export interface PageRoute {
  path: string;
  label: string;
  icon: LucideIcon;
  group: NavGroup;
  Component: LazyExoticComponent<ComponentType>;
}

// Nav order = presentation ← → order: findings first, then the evidence behind them, then the ask.
export const pages: PageRoute[] = [
  { path: "/", label: nav.summary, icon: LayoutDashboard, group: "intelligence", Component: lazy(() => import("./pages/ExecSummary")) },
  { path: "/console", label: nav.console, icon: Gauge, group: "intelligence", Component: lazy(() => import("./pages/Console")) },
  { path: "/efficiency", label: nav.efficiency, icon: TrendingUp, group: "intelligence", Component: lazy(() => import("./pages/Efficiency")) },
  { path: "/periods", label: nav.periods, icon: CalendarRange, group: "intelligence", Component: lazy(() => import("./pages/Periods")) },
  { path: "/alternative-fuel", label: nav.fuel, icon: Flame, group: "intelligence", Component: lazy(() => import("./pages/AltFuel")) },
  { path: "/data", label: nav.data, icon: Database, group: "evidence", Component: lazy(() => import("./pages/DataReadiness")) },
  { path: "/validation", label: nav.validation, icon: ShieldCheck, group: "evidence", Component: lazy(() => import("./pages/Validation")) },
  { path: "/roadmap", label: nav.roadmap, icon: Map, group: "roadmap", Component: lazy(() => import("./pages/Roadmap")) },
];
