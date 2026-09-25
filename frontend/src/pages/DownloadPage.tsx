import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { downloadReportUrl, downloadZipUrl, fetchGenerationReport } from "../lib/api";
import { useAppStore } from "../lib/store";

interface ReportIntent {
  id: string;
  name: string;
  status: "success" | "needs_review" | "failed" | "pending";
  warnings?: string[];
  unresolvedReferences?: string[];
  durationMs?: number | null;
  tokens?: {
    prompt: number;
    completion: number;
    total: number;
  };
  estimatedManualMinutes?: number;
}

interface Report {
  summary: {
    total: number;
    success: number;
    needsReview: number;
    failed: number;
    pending: number;
  };
  metrics: {
    totalDurationMs: number;
    tokens: {
      prompt: number;
      completion: number;
      total: number;
    };
    estimatedManualMinutes: number;
    timeSavedMinutes: number;
    speedupFactor: number;
  };
  intents: ReportIntent[];
}

const formatDuration = (ms: number): string => {
  if (!ms || ms <= 0) return "-";
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
};

const formatMinutes = (minutes: number): string => {
  if (!minutes || minutes <= 0) return "-";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  const remaining = Math.round(minutes % 60);
  return remaining ? `${hours}h ${remaining}m` : `${hours}h`;
};

const buildExportFileName = (uploadedName: string, platform: string): string => {
  const baseName = uploadedName.replace(/\.zip$/i, "") || "export";
  const detected = platform || "x011";
  return `${baseName}_${detected}_to_artemis.zip`;
};

export default function DownloadPage() {
  const { jobId = "" } = useParams();
  const [report, setReport] = useState<Report | null>(null);
  const [activeTab, setActiveTab] = useState<"output" | "details">("output");
  const nav = useNavigate();
  const store = useAppStore();

  useEffect(() => {
    if (!jobId) return;
    fetchGenerationReport(jobId)
      .then((json) => setReport(json))
      .catch(() => setReport(null));
  }, [jobId]);

  const zipUrl = downloadZipUrl(jobId);
  const reportUrl = downloadReportUrl(jobId);
  const exportFileName = buildExportFileName(store.fileName || "export", store.platform);

  const intents = report?.intents || [];
  const [activeIntentId, setActiveIntentId] = useState<string | null>(null);
  const selectedIntent = useMemo(() => intents.find((it) => it.id === activeIntentId) ?? intents[0] ?? null, [intents, activeIntentId]);

  useEffect(() => {
    if (!activeIntentId && intents.length > 0) {
      setActiveIntentId(intents[0].id);
    }
  }, [activeIntentId, intents]);

  const summary = report?.summary;
  const successRate = summary && summary.total > 0 ? Math.round((summary.success / summary.total) * 100) : 0;
  const metrics = report?.metrics;
  const totalTokens = metrics?.tokens?.total ?? 0;
  const totalDurationMs = metrics?.totalDurationMs ?? 0;
  const manualMinutes = metrics?.estimatedManualMinutes ?? 0;
  const timeSavedMinutes = metrics?.timeSavedMinutes ?? 0;
  const speedup = metrics?.speedupFactor ?? 0;

  useEffect(() => {
    if (!jobId || !report) return;
    const fileName = exportFileName;
    store.addHistoryEntry({
      id: jobId,
      jobId,
      fileName,
      createdAt: new Date().toISOString(),
    });
  }, [exportFileName, jobId, report, store]);

  return (
    <div className="page">
      <div className="page-grid wide">
        <section className="card panel">
          <div className="panel-header split">
            <div>
              <h1 className="page-title">Conversion Complete!</h1>
              {report ? (
                <p className="muted">{report.summary.success} of {report.summary.total} intents converted successfully. No errors found.</p>
              ) : (
                <p className="muted">Loading report...</p>
              )}
            </div>
            <div className="status-meta">
              <div className="meta-item">
                <span className="muted">Processed in</span>
                <strong>{formatDuration(totalDurationMs)}</strong>
              </div>
              <div className="meta-item">
                <span className="muted">Tokens used</span>
                <strong>{totalTokens.toLocaleString()}</strong>
              </div>
            </div>
          </div>

          <div className="tab-row">
            <button className={`tab ${activeTab === "output" ? "active" : ""}`} type="button" onClick={() => setActiveTab("output")}>Results</button>
            <button className={`tab ${activeTab === "details" ? "active" : ""}`} type="button" onClick={() => setActiveTab("details")}>Logs</button>
            <div className="tab-spacer" />
            <div className="tab-actions">
              <button className="btn tertiary" type="button">Copy</button>
              <button className="btn tertiary" type="button">Open</button>
            </div>
          </div>

          <div className="results-split">
            <div className="intent-list">
              <div className="intent-header">Intent List ({intents.length})</div>
              {intents.map((it) => (
                <button
                  key={it.id}
                  className={`intent-item ${selectedIntent?.id === it.id ? "active" : ""}`}
                  type="button"
                  onClick={() => setActiveIntentId(it.id)}
                >
                  <div>
                    <div className="intent-name">{it.name}</div>
                    <div className="muted">{it.status === "success" ? "Converted successfully" : it.status}</div>
                  </div>
                  <span className={`badge ${it.status === "success" ? "ok" : it.status === "needs_review" ? "warn" : it.status === "failed" ? "fail" : ""}`}>{it.status}</span>
                </button>
              ))}
            </div>
            <div className="intent-detail">
              <div className="detail-header">
                <div className="detail-title">
                  {selectedIntent?.name || "Intent"}
                  {selectedIntent && (
                    <span className={`badge ${selectedIntent.status === "success" ? "ok" : selectedIntent.status === "needs_review" ? "warn" : selectedIntent.status === "failed" ? "fail" : ""}`}>{selectedIntent.status}</span>
                  )}
                </div>
                <div className="detail-tabs">
                  <button className={activeTab === "output" ? "active" : ""} type="button" onClick={() => setActiveTab("output")}>ABL Output</button>
                  <button className={activeTab === "details" ? "active" : ""} type="button" onClick={() => setActiveTab("details")}>Intent Details</button>
                </div>
              </div>
              {activeTab === "output" && (
                <div className="code-box">
                  <pre>{selectedIntent ? `// ${selectedIntent.name} output is available in the downloaded ABL package.\n// Use the Download ABL File button to view the full output.` : "Select an intent to preview output."}</pre>
                </div>
              )}
              {activeTab === "details" && (
                <div className="detail-panel">
                  <div className="detail-row"><span className="muted">Status</span><strong>{selectedIntent?.status ?? "-"}</strong></div>
                  <div className="detail-row"><span className="muted">Warnings</span><strong>{selectedIntent?.warnings?.length ?? 0}</strong></div>
                </div>
              )}
            </div>
          </div>

          <div className="panel-actions">
            <div className="muted" style={{ marginRight: "auto" }}>Export file: {exportFileName}</div>
            <button className="btn secondary" type="button" onClick={() => { store.resetAll(); nav("/import"); }}>Start New Conversion</button>
            <a className="btn secondary" href={reportUrl} target="_blank" rel="noreferrer">Download Report</a>
            <a className="btn primary" href={zipUrl} download={exportFileName}>Download ABL File</a>
          </div>
        </section>

        <aside className="side-stack">
          <div className="card side-card">
            <div className="side-title">Conversion Summary</div>
            <div className="summary-list">
              <div className="summary-row"><span>Total Intents</span><strong>{summary?.total ?? 0}</strong></div>
              <div className="summary-row"><span>Successful</span><strong className="ok">{summary?.success ?? 0}</strong></div>
              <div className="summary-row"><span>Failed</span><strong className="fail">{summary?.failed ?? 0}</strong></div>
              <div className="summary-row"><span>Warnings</span><strong className="warn">{summary?.needsReview ?? 0}</strong></div>
            </div>
            <div className="summary-ring">
              <div className="progress-ring" style={{ ['--percent' as string]: `${successRate}%` }}>
                <div className="progress-ring-center">
                  <div className="progress-value">{successRate}%</div>
                  <div className="muted">Success Rate</div>
                </div>
              </div>
            </div>
          </div>
          <div className="card side-card impact-card">
            <div className="side-title">Automation Impact</div>
            <div className="impact-hero">
              {speedup > 0 ? `${speedup}x faster than manual development` : "Automation impact pending"}
            </div>
            <div className="summary-list">
              <div className="summary-row"><span>Automated</span><strong>{formatDuration(totalDurationMs)}</strong></div>
              <div className="summary-row"><span>Manual estimate</span><strong>{formatMinutes(manualMinutes)}</strong></div>
              <div className="summary-row"><span>Time saved</span><strong>{formatMinutes(timeSavedMinutes)}</strong></div>
              <div className="summary-row"><span>LLM tokens</span><strong>{totalTokens.toLocaleString()}</strong></div>
            </div>
            <div className="muted impact-note">Includes requirement review, flow complexity, and logic handling.</div>
          </div>
          <div className="card side-card success-banner">
            <div className="side-title">All intents converted successfully!</div>
            <p className="muted">Your ABL file is ready to download.</p>
            <div className="muted" style={{ marginBottom: 8 }}>Export file: {exportFileName}</div>
            <a className="btn primary" href={zipUrl} download={exportFileName}>Download ABL File</a>
            <button className="btn secondary" type="button">Preview Output</button>
          </div>
        </aside>
      </div>
    </div>
  );
}