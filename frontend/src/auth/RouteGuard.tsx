import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { decide } from "./routing";

/**
 * Applies `decide()` to the current pathname. Navigation only — the backend
 * re-checks the token and role on every request.
 *
 * The session is re-read from storage on every render, so a token that expired
 * while the page sat open is dropped at the next navigation. React state is
 * brought in line afterwards, in an effect, never during render.
 *
 * Redirects use `replace` and a bare path, so nothing from the original URL,
 * query string included, is carried forward into history.
 */
export function RouteGuard({ children }: { children: ReactNode }) {
  const { session, current, logout } = useAuth();
  const { pathname } = useLocation();
  const live = current();

  useEffect(() => {
    if (session && !live) logout();
  }, [session, live, logout]);

  const decision = decide(pathname, live);
  if (decision.kind === "redirect") return <Navigate to={decision.to} replace />;
  return <>{children}</>;
}
