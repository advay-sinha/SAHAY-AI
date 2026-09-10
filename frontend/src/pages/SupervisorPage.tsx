/**
 * Supervisor view. Reachable only with a supervisor session (route guard), and
 * its data endpoints will check the role server-side (BE-021, P3). Contents —
 * reassignment, override review, cross-case audit, metrics — are EC-13, P1/P3.
 */
export function SupervisorPage() {
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="text-xl font-medium">Supervisor</h1>
      <p className="mt-2 text-sm text-neutral-700">
        Reassignment, override review, cross-case audit and operational metrics arrive with the
        supervisor endpoints.
      </p>
    </main>
  );
}
