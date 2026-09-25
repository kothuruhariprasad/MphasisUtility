export default function AdminPage() {
  return (
    <div className="page">
      <div className="page-grid">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Admin Controls</h1>
            <p className="page-subtitle">Shared-password access is enabled for this workspace.</p>
          </div>

          <div className="card" style={{ boxShadow: "none" }}>
            <div className="side-title">Next steps</div>
            <ul className="side-list">
              <li>Rotate the shared password when team access changes.</li>
              <li>Use the deployment platform password gate for production.</li>
              <li>Review server logs for rate limit warnings.</li>
            </ul>
          </div>
        </section>

        <aside className="side-stack">
          <div className="card side-card">
            <div className="side-title">Security Tips</div>
            <ul className="side-list">
              <li>Store secrets only in server environment variables.</li>
              <li>Do not reuse shared passwords across tools.</li>
              <li>Prefer unique admin passwords when possible.</li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
