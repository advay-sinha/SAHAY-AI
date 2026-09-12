import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { navFor, PATHS } from "../auth/routing";
import { BackendStatusBadge } from "./BackendStatusBadge";
import { ConsoleIcon, SahayMark } from "./ConsoleIcon";
import { Disclaimer } from "./Disclaimer";

const navIcons: Record<string, string> = { Queue: "queue", Case: "case", Audit: "audit", Supervisor: "supervisor" };
const navLabels: Record<string, string> = { Queue: "Live Queue", Case: "Case Review Workspace", Audit: "Audit Trail & Ledger", Supervisor: "Supervisor Operations" };

export function AppShell() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  if (!session) return null;

  const items = navFor(session.role);
  if (location.pathname.startsWith("/cases/")) {
    items.splice(1, 0, { to: location.pathname, label: "Case" });
  }

  function signOut() { logout(); navigate(PATHS.login, { replace: true }); }

  return <div className="min-h-screen bg-surface text-on-surface">
    <header className="fixed inset-x-0 top-0 z-50 flex h-16 items-center bg-primary-container px-3 text-white shadow-sm xl:px-4">
      <div className="w-12 xl:w-60"><span className="xl:hidden"><SahayMark compact /></span><span className="hidden xl:block"><SahayMark /></span></div>
      <div className="hidden h-8 w-px bg-slate-600 md:block" />
      <span className="ml-4 hidden rounded border border-cyan-300/20 bg-slate-700 px-3 py-1.5 text-[11px] font-semibold tracking-wide text-cyan-200 md:inline-flex">HELPLINE 14566 · NATIONAL ATROCITIES MONITORING</span>
      <BackendStatusBadge />
      <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-4">
        <div className="min-w-0 text-right" data-testid="whoami"><strong className="block truncate text-xs">{session.displayName || "Signed in"}</strong><span className="block text-[10px] uppercase tracking-wide text-slate-400">Role: {session.role}</span></div>
        <button type="button" onClick={signOut} className="flex items-center gap-2 rounded border border-slate-600 px-2 py-1.5 text-xs hover:bg-slate-800" data-testid="logout"><ConsoleIcon name="logout" className="h-4 w-4" /><span className="hidden sm:inline">Sign out</span></button>
      </div>
    </header>
    <aside className="fixed bottom-0 left-0 top-16 z-40 flex w-16 flex-col border-r border-slate-700 bg-primary-container xl:w-64">
      <div className="hidden border-b border-slate-700 px-4 py-3 text-[10px] uppercase tracking-wider text-slate-400 xl:block">Operational console</div>
      <nav aria-label="Primary" className="flex-1 space-y-1 overflow-y-auto px-2 py-3">
        {items.map((item) => <NavLink key={item.to} to={item.to} title={navLabels[item.label] ?? item.label} className={({ isActive }) => `flex items-center gap-3 rounded px-3 py-2.5 text-sm ${isActive ? "border-l-2 border-cyan-300 bg-[#213145] font-semibold text-cyan-200" : "border-l-2 border-transparent text-slate-400 hover:bg-[#1b2940] hover:text-white"}`}><ConsoleIcon name={navIcons[item.label] ?? "queue"} className="h-5 w-5 shrink-0" /><span className="hidden xl:inline">{navLabels[item.label] ?? item.label}</span></NavLink>)}
      </nav>
      <div className="border-t border-slate-700 p-3 text-[10px] text-slate-400"><div className="hidden xl:block">STATION NODE</div><div className="mt-1 flex items-center gap-2 text-cyan-300"><ConsoleIcon name="shield" className="h-4 w-4" /><span className="hidden xl:inline">End-to-End Encrypted Triage</span></div></div>
    </aside>
    <div className="min-h-screen pb-10 pl-16 pt-16 xl:pl-64"><Outlet /></div>
    <div className="fixed inset-x-0 bottom-0 z-50 bg-primary-container px-4 py-2 text-center text-[10px] text-slate-300"><Disclaimer /></div>
  </div>;
}
