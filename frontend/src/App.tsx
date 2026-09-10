import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { RouteGuard } from "./auth/RouteGuard";
import { homeFor, PATHS } from "./auth/routing";
import { AppShell } from "./components/AppShell";
import { AuditPage } from "./pages/AuditPage";
import { CasePage } from "./pages/CasePage";
import { LoginPage } from "./pages/LoginPage";
import { QueuePage } from "./pages/QueuePage";
import { SupervisorPage } from "./pages/SupervisorPage";

function RootRedirect() {
  const { current } = useAuth();
  const session = current();
  return <Navigate to={session ? homeFor(session.role) : PATHS.login} replace />;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            path={PATHS.login}
            element={
              <RouteGuard>
                <LoginPage />
              </RouteGuard>
            }
          />
          <Route
            element={
              <RouteGuard>
                <AppShell />
              </RouteGuard>
            }
          >
            <Route path={PATHS.queue} element={<QueuePage />} />
            <Route path="/cases/:caseId" element={<CasePage />} />
            <Route path={PATHS.audit} element={<AuditPage />} />
            <Route path="/audit/:caseId" element={<AuditPage />} />
            <Route path={PATHS.supervisor} element={<SupervisorPage />} />
          </Route>
          <Route path="/" element={<RootRedirect />} />
          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
