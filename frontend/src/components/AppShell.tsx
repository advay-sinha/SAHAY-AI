import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { navFor, PATHS } from "../auth/routing";

/**
 * Authenticated layout: identity, role-based navigation, sign-out.
 *
 * Supervisor-only items are simply not rendered for an executive. That is
 * navigation hygiene; the route guard and, above all, the backend RBAC are
 * what actually refuse access.
 */
export function AppShell() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();

  if (!session) return null; // the guard redirects before this renders

  function signOut() {
    logout();
    navigate(PATHS.login, { replace: true });
  }

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-4 border-b border-neutral-400 px-4 py-2">
        <span className="font-semibold">SAHAY-AI</span>
        <nav aria-label="Primary" className="flex gap-3 text-sm">
          {navFor(session.role).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "font-semibold underline" : "underline-offset-2")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <span className="ml-auto text-sm" data-testid="whoami">
          {session.displayName || "Signed in"} · {session.role}
        </span>
        <button
          type="button"
          onClick={signOut}
          className="border border-neutral-500 px-3 py-1 text-sm"
          data-testid="logout"
        >
          Sign out
        </button>
      </header>
      <Outlet />
    </div>
  );
}
