import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadArchive } from "../lib/api";
import { useAppStore } from "../lib/store";

export default function ImportPage() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const store = useAppStore();

  const pick = () => inputRef.current?.click();

  const stage = (f: File | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".zip")) {
      setError("Only .zip archives are supported.");
      return;
    }
    if (f.size > 200 * 1024 * 1024) {
      setError("File exceeds 200MB limit.");
      return;
    }
    setError("");
    setFile(f);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const data = await uploadArchive(file);
      store.setUploadData(data.sessionId, file.name, data.intents, data.platform);
      nav("/llm");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-grid import-grid">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Import Flow Definition</h1>
            <p className="page-subtitle">Upload your exported <b>.zip</b> package from Enterprise Flow Builder.</p>
          </div>

          <div
            className="dropzone"
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault();
              stage(e.dataTransfer.files?.[0] ?? null);
            }}
          >
            <div className="dropzone-content">
              <div className="dropzone-icon">
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path d="M12 4 7 9h3v6h4V9h3z" fill="currentColor" />
                  <path d="M5 15v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </div>
              <div className="dropzone-text">Drag & drop your .zip file here</div>
              <div className="dropzone-sub">or</div>
              <button className="btn primary" type="button" onClick={pick}>Browse Local System</button>
              <input
                ref={inputRef}
                type="file"
                accept=".zip"
                style={{ display: "none" }}
                onChange={e => stage(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>

          {file && (
            <div className="file-card">
              <div>
                <div className="file-name">{file.name}</div>
                <div className="muted">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
              </div>
              <button className="icon-btn" onClick={() => setFile(null)} aria-label="Remove file">×</button>
            </div>
          )}

          {error && <p className="badge fail" style={{ marginTop: 0, marginBottom: 18, display: "inline-block" }}>{error}</p>}

          <div className="panel-actions import-actions">
            <button className="btn secondary" type="button" onClick={() => setFile(null)} disabled={!file || busy}>Clear</button>
            <button className="btn primary" type="button" disabled={!file || busy} onClick={submit}>{busy ? "Uploading..." : "Upload & Continue →"}</button>
          </div>
        </section>

        <aside className="side-stack">
          <div className="card side-card">
            <div className="side-title">File Requirements</div>
            <ul className="side-list">
              <li>ZIP file exported from Enterprise Flow Builder</li>
              <li>Valid AppDef structure</li>
              <li>Maximum size: 200 MB</li>
            </ul>
          </div>
          <div className="card side-card soft">
            <div className="side-title">Need Help?</div>
            <p className="muted">Make sure your export includes all required flow definitions and resources.</p>
            <a className="btn secondary" href="https://docs.kore.ai/agent-platform/abl" target="_blank" rel="noreferrer">View Docs →</a>
          </div>
        </aside>
      </div>

      <div className="value-strip">
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Fast & Accurate</div>
            <div className="muted">Get reliable conversions in seconds</div>
          </div>
        </div>
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Error Detection</div>
            <div className="muted">Built-in validation and safeguards</div>
          </div>
        </div>
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Developer Friendly</div>
            <div className="muted">Clean, readable output</div>
          </div>
        </div>
      </div>
    </div>
  );
}