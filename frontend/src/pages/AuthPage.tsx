import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { loginSharedPassword } from "../lib/api";
import { useAppStore } from "../lib/store";

export default function AuthPage() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const store = useAppStore();
  const nav = useNavigate();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!password.trim()) {
      setError("Password is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const profile = await loginSharedPassword(password);
      store.setAuthSession(profile.token, profile.email, profile.role);
      nav("/import");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-grid">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Team Access</h1>
            <p className="page-subtitle">Enter the shared password provided by your team.</p>
          </div>

          <form className="form-grid" onSubmit={submit}>
            <label className="form-row">
              <span className="form-label">Shared Password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter shared password"
              />
            </label>

            {error && <p className="badge fail" style={{ marginTop: 0, marginBottom: 0, display: "inline-block" }}>{error}</p>}

            <div className="panel-actions">
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "Signing in..." : "Access Workspace"}
              </button>
            </div>
          </form>
        </section>

        <aside className="side-stack">
          <div className="card side-card">
            <div className="side-title">Security Notes</div>
            <ul className="side-list">
              <li>The password is never stored in your browser.</li>
              <li>Access is limited to verified sessions.</li>
              <li>Contact the owner to rotate access if needed.</li>
            </ul>
          </div>
          <div className="card side-card soft">
            <div className="side-title">Need Access?</div>
            <p className="muted">Ask your team lead for the current shared password.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
