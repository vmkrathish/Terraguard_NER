export function DashboardError({ error }: { error: string }) {
  return (
    <div className="form-alert error fade-in-up" role="alert">
      Could not reach the backend API at the configured URL: {error}
    </div>
  );
}

export function DashboardLoading() {
  return (
    <div className="full-page-loader" style={{ minHeight: "40vh" }}>
      <div className="loader-ring" />
      <span>Loading dashboard…</span>
    </div>
  );
}
