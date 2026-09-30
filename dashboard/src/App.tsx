import { Component, Suspense, type ReactNode } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Shell from "./components/Shell";
import { pages } from "./routes";
import { common } from "./copy";

class Boundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) return <div className="card text-warning-ink" role="alert">{common.error} ({this.state.error.message})</div>;
    return this.props.children;
  }
}

/** Resets the boundary on navigation so one failed page does not blank every other page. */
function RouteBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Boundary key={pathname.split("/")[1]}>{children}</Boundary>;
}

const Periods = pages.find((p) => p.path === "/periods")!.Component;

export default function App() {
  return (
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Shell>
        <RouteBoundary>
          <Suspense fallback={<div className="p-8 text-ink-muted">{common.loading}</div>}>
            <Routes>
              {pages.map(({ path, Component }) => <Route key={path} path={path} element={<Component />} />)}
              <Route path="/periods/:id" element={<Periods />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </RouteBoundary>
      </Shell>
    </HashRouter>
  );
}
