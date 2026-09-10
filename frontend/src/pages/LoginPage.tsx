import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LOGIN_ERROR_MESSAGES, type LoginErrorKind } from "../auth/login";
import { homeFor, PATHS, shouldScrubQuery } from "../auth/routing";

/**
 * Executive console sign-in.
 *
 * - Credentials go to POST /auth/login and nowhere else. Nothing is prefilled,
 *   and no credential is compiled into the bundle.
 * - The page URL never authenticates anyone. If it was opened with a query
 *   string (for example `?token=...`), the string is removed from the address
 *   bar with a history replace and its contents are never read.
 * - Error text is fixed wording; server responses are never shown.
 */
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

  // Scrub any query string. Its value is never read, only its presence.
  useEffect(() => {
    if (shouldScrubQuery(search)) navigate(PATHS.login, { replace: true });
  }, [search, navigate]);

  useEffect(() => {
    usernameRef.current?.focus();
  }, []);

  useEffect(() => {
    if (session) navigate(homeFor(session.role), { replace: true });
  }, [session, navigate]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setPending(true);
    const failure = await login(username.trim(), password);
    setPending(false);
    if (failure) {
      setError(failure);
      setPassword("");
      return;
    }
    // Navigation happens in the session effect above, with `replace`, so the
    // login page does not remain behind the destination in history.
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-6">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-wide text-neutral-600">
          National Helpline Against Atrocities · 14566
        </p>
        <h1 className="mt-1 text-2xl font-semibold">SAHAY-AI</h1>
        <p className="text-sm text-neutral-700">Helpline Executive Console</p>
      </header>

      <form
        onSubmit={onSubmit}
        noValidate
        aria-describedby={ids.notice}
        className="space-y-4 border border-neutral-400 p-5"
      >
        <div>
          <label htmlFor={ids.user} className="block text-sm font-medium">
            Username
          </label>
          <input
            ref={usernameRef}
            id={ids.user}
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={64}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            aria-invalid={error === "invalid_credentials"}
            aria-describedby={error ? ids.error : undefined}
            className="mt-1 w-full border border-neutral-500 px-2 py-2"
            data-testid="username"
          />
        </div>

        <div>
          <label htmlFor={ids.pass} className="block text-sm font-medium">
            Password
          </label>
          <div className="mt-1 flex">
            <input
              id={ids.pass}
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              maxLength={256}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error === "invalid_credentials"}
              aria-describedby={error ? ids.error : undefined}
              className="w-full border border-neutral-500 px-2 py-2"
              data-testid="password"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-pressed={showPassword}
              aria-controls={ids.pass}
              className="ml-2 border border-neutral-500 px-3 text-sm"
            >
              {showPassword ? "Hide" : "Show"}
              <span className="sr-only"> password</span>
            </button>
          </div>
        </div>

        {error && (
          <p id={ids.error} role="alert" className="border border-red-700 p-2 text-sm text-red-800">
            {LOGIN_ERROR_MESSAGES[error]}
          </p>
        )}

        <button
          type="submit"
          disabled={pending || username.trim() === "" || password === ""}
          aria-busy={pending}
          className="w-full border border-neutral-800 bg-neutral-900 px-3 py-2 font-medium text-white disabled:opacity-60"
          data-testid="submit"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <section id={ids.notice} className="mt-6 space-y-2 text-xs text-neutral-700">
        <p>
          <strong>Authorised use only.</strong> This console is for assigned helpline officers.
          Access and every decision taken here are recorded with your identity and time.
        </p>
        <p>
          Case records concern people in distress. View only the cases you are handling, do not
          copy case content outside this system, and sign out when you leave the workstation.
        </p>
        <p>
          Local development build. Accounts are created by the project seed script for testing
          only and must never be used with real case data.
        </p>
      </section>
    </main>
  );
}
