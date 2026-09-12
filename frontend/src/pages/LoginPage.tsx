import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LOGIN_ERROR_MESSAGES, type LoginErrorKind } from "../auth/login";
import { homeFor, PATHS, shouldScrubQuery } from "../auth/routing";
import { ConsoleIcon, SahayMark } from "../components/ConsoleIcon";
import { ASSESSMENT_DISCLAIMER } from "../types/contracts";

const principles = [
  { icon: "shield", title: "Human decisions remain final", copy: "AI outputs are assistive prioritisation aids. Every operational decision remains with the reviewing officer." },
  { icon: "bolt", title: "Evidence-linked assessment", copy: "Assessment dimensions and recommendations link back to the relevant transcript turns." },
  { icon: "user", title: "Designed abstention state", copy: "When the available signal is insufficient, the console shows Needs Human Assessment instead of inventing a score." },
  { icon: "audit", title: "Accountable decision record", copy: "System recommendations, acknowledgements, overrides, and human decisions remain visibly separate in the audit trail." },
];

/** Real backend sign-in presented in the unauthenticated Stitch layout. */
export function LoginPage() {
  const { login, session } = useAuth();
  const navigate = useNavigate();
  const { search } = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<LoginErrorKind | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);
  const ids = { user: useId(), pass: useId(), error: useId(), notice: useId() };

  useEffect(() => { if (shouldScrubQuery(search)) navigate(PATHS.login, { replace: true }); }, [search, navigate]);
  useEffect(() => { usernameRef.current?.focus(); }, []);
  useEffect(() => { if (session) navigate(homeFor(session.role), { replace: true }); }, [session, navigate]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setPending(true);
    const failure = await login(username.trim(), password);
    setPending(false);
    if (failure) { setError(failure); setPassword(""); }
  }

  return <div className="flex min-h-screen flex-col bg-[#f7f9fc] text-slate-900">
    <header className="flex min-h-14 items-center justify-between gap-4 border-b border-slate-800 bg-[#0b1428] px-4 py-2 sm:px-8">
      <div className="flex min-w-0 items-center gap-4"><SahayMark /><span className="hidden h-5 w-px bg-slate-600 sm:block" /><span className="hidden truncate text-xs text-slate-400 sm:block">National Helpline Against Atrocities · 14566</span></div>
      <div className="flex shrink-0 items-center gap-2 rounded-full border border-slate-700 bg-slate-800/80 px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-slate-300 sm:px-3"><span className="h-2 w-2 rounded-full bg-secondary-fixed" /><span className="hidden sm:inline">Local console access</span><span className="sr-only sm:hidden">Local console access</span></div>
    </header>

    <main className="mx-auto grid w-full min-w-0 max-w-7xl grid-cols-1 items-center gap-8 px-4 py-8 sm:px-6 lg:grid-cols-12 lg:gap-12 lg:px-8">
      <section className="order-2 min-w-0 space-y-6 lg:order-1 lg:col-span-6" aria-labelledby="login-intro-title">
        <div className="space-y-3">
          <span className="inline-flex items-center gap-2 rounded border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800"><span className="h-1.5 w-1.5 rounded-full bg-blue-600" /> AUTHORISED HELPLINE OFFICER ACCESS</span>
          <h1 id="login-intro-title" className="max-w-2xl text-3xl font-bold leading-tight tracking-tight sm:text-4xl">Operational Decision-Support & Rapid Case Triage Console</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">AI-assisted intake, vulnerability assessment, and escalation support for helpline executives reviewing active cases.</p>
        </div>
        <div className="hidden grid-cols-2 gap-3 md:grid">
          {principles.map((item) => <article key={item.title} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-center gap-2 text-xs font-semibold"><ConsoleIcon name={item.icon} className="h-4 w-4 text-secondary" />{item.title}</div><p className="mt-2 text-xs leading-relaxed text-slate-500">{item.copy}</p></article>)}
        </div>
        <div className="flex items-start gap-2.5 rounded border border-slate-300 bg-slate-100 p-3 text-xs text-slate-600"><ConsoleIcon name="info" className="mt-0.5 h-4 w-4 shrink-0" /><div><strong className="text-slate-800">Assessment notice</strong><p className="mt-1 leading-relaxed">{ASSESSMENT_DISCLAIMER}</p></div></div>
      </section>

      <section className="order-1 flex min-w-0 justify-center lg:order-2 lg:col-span-6 lg:justify-end" aria-labelledby="sign-in-title">
        <div className="w-full min-w-0 max-w-[460px] space-y-6 overflow-hidden rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <header className="space-y-1 border-b border-slate-100 pb-4"><div className="flex items-center justify-between"><span className="font-mono text-xs font-medium uppercase tracking-wide text-slate-500">Officer Access Portal</span><span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600">LOCAL MVP</span></div><h2 id="sign-in-title" className="text-xl font-bold tracking-tight">Sign in to your console</h2><p className="text-xs text-slate-500">Use the officer credentials issued for this local console.</p></header>

          <div className="flex min-w-0 items-center gap-2 rounded border border-slate-200 bg-slate-50 p-2.5 text-xs text-slate-600"><ConsoleIcon name="shield" className="h-4 w-4 shrink-0 text-secondary" /><span className="min-w-0">Your role and permitted destination are assigned by the authenticated account.</span></div>

          <form onSubmit={onSubmit} noValidate aria-describedby={ids.notice} className="space-y-4">
            {error && <div id={ids.error} role="alert" className="flex items-start gap-2 rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700"><ConsoleIcon name="alert" className="mt-0.5 h-4 w-4 shrink-0" /><div><strong>Authentication failed</strong><p className="mt-0.5">{LOGIN_ERROR_MESSAGES[error]}</p></div></div>}
            <div className="space-y-1.5"><label htmlFor={ids.user} className="block text-xs font-semibold text-slate-700">Officer username</label><div className="relative"><ConsoleIcon name="user" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input ref={usernameRef} id={ids.user} name="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={64} value={username} onChange={(e) => setUsername(e.target.value)} aria-invalid={error === "invalid_credentials"} aria-describedby={error ? ids.error : undefined} placeholder="Enter your officer username" className="h-10 w-full rounded border border-slate-300 bg-white pl-9 pr-3 text-sm font-mono placeholder:font-sans placeholder:text-slate-400 focus:border-secondary focus:ring-secondary" data-testid="username" /></div></div>
            <div className="space-y-1.5"><label htmlFor={ids.pass} className="block text-xs font-semibold text-slate-700">Password</label><div className="relative"><ConsoleIcon name="lock" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input id={ids.pass} name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={error === "invalid_credentials"} aria-describedby={error ? ids.error : undefined} placeholder="Enter your password" className="h-10 w-full rounded border border-slate-300 bg-white pl-9 pr-10 text-sm font-mono placeholder:font-sans placeholder:text-slate-400 focus:border-secondary focus:ring-secondary" data-testid="password" /><button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} aria-controls={ids.pass} className="absolute inset-y-0 right-0 grid w-10 place-items-center text-slate-400 hover:text-slate-700"><ConsoleIcon name={showPassword ? "eyeOff" : "eye"} className="h-4 w-4" /></button></div></div>
            <button type="submit" disabled={pending || username.trim() === "" || password === ""} aria-busy={pending} className="flex h-11 w-full items-center justify-center gap-2 rounded bg-[#0f172a] px-4 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60" data-testid="submit">{pending && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />}<span>{pending ? "Signing in…" : "Sign in to Case Console"}</span>{!pending && <ConsoleIcon name="arrow" className="h-4 w-4 text-slate-400" />}</button>
          </form>

          <div id={ids.notice} className="space-y-2 border-t border-slate-100 pt-4 text-[11px] leading-relaxed text-slate-500"><div className="flex items-start gap-2"><ConsoleIcon name="lock" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><p><strong className="text-slate-700">Authorised use only.</strong> Access and decisions are recorded with the reviewing officer’s identity and time.</p></div><p>Case records concern people in distress. View only cases you are handling, do not copy case content outside this system, and sign out before leaving the workstation.</p></div>
        </div>
      </section>
    </main>

    <footer className="flex flex-col items-center justify-between gap-1 border-t border-slate-200 bg-white px-6 py-3 text-center text-[11px] text-slate-500 sm:flex-row sm:text-left"><span>National Helpline Against Atrocities · 14566</span><span className="font-mono text-slate-400">Local development build · seeded accounts only · no real case data</span></footer>
  </div>;
}
