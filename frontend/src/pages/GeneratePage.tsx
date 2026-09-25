import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { abortGeneration, fetchGenerationReport, openGenerationStream } from "../lib/api";
import type { DoneEvent, LogEvent, QueueEvent, QueueStatus } from "../lib/types";
import { SUPERVISOR_INTENT_ID } from "../lib/types";
import { useAppStore } from "../lib/store";

interface QueueRow {
  id: string;
  name: string;
  status: QueueStatus;
  message: string;
  durationMs?: number;
}

export default function GeneratePage() {
  const { jobId = "" } = useParams();
  const nav = useNavigate();
  const store = useAppStore();
  const [rows, setRows] = useState<Record<string, QueueRow>>({});
  const [logs, setLogs] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const connectedJobRef = useRef<string>("");
  const doneRef = useRef(false);
  const abortedRef = useRef(false);
  const intentionalCloseRef = useRef(false);
  const streamSeqRef = useRef(0);
  const completedJobsRef = useRef<Set<string>>(new Set());
  const errorCountRef = useRef(0);
  const disconnectLoggedRef = useRef(false);

  useEffect(() => {
    const initial: Record<string, QueueRow> = {};
    for (const intent of store.intents) {
      if (store.selectedIds.has(intent.id)) {
        initial[intent.id] = { id: intent.id, name: intent.name, status: "pending", message: "Waiting in queue..." };
      }
    }
    if (store.addSupervisor) {
      initial[SUPERVISOR_INTENT_ID] = { id: SUPERVISOR_INTENT_ID, name: "Supervisor Agent", status: "pending", message: "Waiting in queue..." };
    }
    setRows(initial);
  }, [store.intents, store.selectedIds, store.addSupervisor]);

  useEffect(() => {
    doneRef.current = done;
  }, [done]);

  useEffect(() => {
    if (!jobId) return;
    if (completedJobsRef.current.has(jobId)) {
      setDone(true);
      doneRef.current = true;
      return;
    }

    if (eventSourceRef.current && connectedJobRef.current === jobId) {
      return;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const es = openGenerationStream(jobId);
    const streamSeq = streamSeqRef.current + 1;
    streamSeqRef.current = streamSeq;

    const isCurrentStream = (): boolean => {
      return streamSeqRef.current === streamSeq && eventSourceRef.current === es && connectedJobRef.current === jobId;
    };

    eventSourceRef.current = es;
    connectedJobRef.current = jobId;
    intentionalCloseRef.current = false;
    errorCountRef.current = 0;
    disconnectLoggedRef.current = false;
    setLogs((prev) => [...prev.slice(-300), `[INIT] Opened stream for job ${jobId}`]);

    es.onopen = () => {
      if (!isCurrentStream()) return;
      errorCountRef.current = 0;
      disconnectLoggedRef.current = false;
      setLogs((prev) => [...prev.slice(-300), `[INFO] Stream connected for job ${jobId}`]);
    };

    es.onmessage = (evt) => {
      if (!isCurrentStream()) return;
      try {
        const payload = JSON.parse(evt.data) as QueueEvent | LogEvent | DoneEvent;
        if ((payload as LogEvent).type === "log") {
          const log = payload as LogEvent;
          setLogs((prev) => [...prev.slice(-300), `[${log.level}] ${log.text}`]);
          return;
        }
        if ((payload as DoneEvent).type === "done") {
          const donePayload = payload as DoneEvent;
          setRows((prev) => {
            const next: Record<string, QueueRow> = { ...prev };
            if (Array.isArray(donePayload.results) && donePayload.results.length > 0) {
              for (const item of donePayload.results) {
                next[item.intentId] = {
                  id: item.intentId,
                  name: item.name,
                  status: item.status,
                  message: item.message || "",
                  durationMs: item.durationMs,
                };
              }
            } else {
              for (const row of Object.values(next)) {
                if (row.status === "pending" || row.status === "processing") {
                  next[row.id] = { ...row, status: "failed", message: "No terminal status received from stream" };
                }
              }
            }
            return next;
          });

          setLogs((prev) => [
            ...prev.slice(-300),
            `[INFO] done total=${donePayload.summary.total} success=${donePayload.summary.success} needsReview=${donePayload.summary.needsReview} failed=${donePayload.summary.failed} pending=${donePayload.summary.pending}`,
          ]);
          completedJobsRef.current.add(jobId);
          setDone(true);
          doneRef.current = true;
          intentionalCloseRef.current = true;
          es.close();
          eventSourceRef.current = null;
          connectedJobRef.current = "";
          setLogs((prev) => [...prev.slice(-300), `[INFO] Stream closed for job ${jobId} (completed)`]);
          return;
        }
        const q = payload as QueueEvent;
        setRows((prev) => ({
          ...prev,
          [q.intentId]: {
            id: q.intentId,
            name: q.name,
            status: q.status,
            message: q.message || "",
            durationMs: q.durationMs,
          },
        }));
      } catch {
      }
    };

    es.onerror = () => {
      if (!isCurrentStream()) return;
      if (doneRef.current || abortedRef.current || intentionalCloseRef.current) {
        return;
      }

      errorCountRef.current += 1;
      if (!disconnectLoggedRef.current) {
        disconnectLoggedRef.current = true;
        setLogs((prev) => [...prev.slice(-300), "[WARN] Stream disconnected. Browser will retry automatically."]);
      } else if (errorCountRef.current <= 3) {
        setLogs((prev) => [...prev.slice(-300), `[INFO] Stream reconnect attempt ${errorCountRef.current}...`]);
      }

      if (errorCountRef.current >= 3) {
        void (async () => {
          try {
            const report = await fetchGenerationReport(jobId);
            const summary = report.summary;
            if (summary.pending === 0) {
              setRows((prev) => {
                const next: Record<string, QueueRow> = { ...prev };
                for (const item of report.intents) {
                  next[item.id] = {
                    id: item.id,
                    name: item.name,
                    status: item.status,
                    message:
                      item.status === "success"
                        ? "Converted successfully"
                        : item.status === "needs_review"
                          ? "Converted with review notes"
                          : item.status === "failed"
                            ? "Generation failed"
                            : next[item.id]?.message || "",
                    durationMs: next[item.id]?.durationMs,
                  };
                }
                return next;
              });
              setLogs((prev) => [...prev.slice(-300), "[INFO] Recovered final status via report endpoint."]);
              completedJobsRef.current.add(jobId);
              setDone(true);
              doneRef.current = true;
              intentionalCloseRef.current = true;
              es.close();
              eventSourceRef.current = null;
              connectedJobRef.current = "";
            }
          } catch {
          }
        })();
      }
    };

    return () => {
      if (eventSourceRef.current === es) {
        intentionalCloseRef.current = true;
        setLogs((prev) => [...prev.slice(-300), `[INFO] Closing stream for job ${jobId}`]);
        es.close();
        eventSourceRef.current = null;
        streamSeqRef.current += 1;
      }
      if (connectedJobRef.current === jobId) {
        connectedJobRef.current = "";
      }
    };
  }, [jobId]);

  const summary = useMemo(() => {
    const all = Object.values(rows);
    const total = all.length;
    const success = all.filter((x) => x.status === "success").length;
    const processing = all.filter((x) => x.status === "processing").length;
    const warnings = all.filter((x) => x.status === "needs_review").length;
    const pending = all.filter((x) => x.status === "pending").length;
    const failed = all.filter((x) => x.status === "failed").length;
    const completed = success + warnings + failed;
    const percent = total === 0 ? 0 : Math.round((completed / total) * 100);
    return { total, success, processing, warnings, pending, failed, completed, percent };
  }, [rows]);

  return (
    <div className="page generate-page">
      <div className="page-grid wide">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Generating Files</h1>
            <p className="page-subtitle">Your selected intents are being converted. Please wait for the process to complete.</p>
          </div>

          <div className="progress-track" style={{ marginBottom: 14 }}>
            <div className="progress-fill" style={{ width: `${summary.percent}%` }} />
          </div>
          <div className="status-row">
            <span className="pill">Total: {summary.total}</span>
            <span className="pill ok">Completed: {summary.completed}</span>
            <span className="pill info">In Progress: {summary.processing}</span>
            <span className="pill warn">Warnings: {summary.warnings}</span>
            <span className="pill">Pending: {summary.pending}</span>
          </div>

          <div className="card soft" style={{ marginBottom: 18 }}>
            <div className="card-title">Conversion Queue</div>
            {Object.values(rows).map((row, idx) => (
              <div className="queue-row" key={row.id}>
                <div>
                  <div className="queue-title">{idx + 1}. {row.name}</div>
                  <div className="muted">{row.message}</div>
                </div>
                <div className="row" style={{ gap: 12 }}>
                  <span className="muted">{row.durationMs ? `${row.durationMs}ms` : "-"}</span>
                  <span className={`badge ${row.status === "success" ? "ok" : row.status === "processing" ? "info" : row.status === "needs_review" ? "warn" : row.status === "failed" ? "fail" : ""}`}>{row.status}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="log" style={{ marginBottom: 18 }}>
            {logs.map((line, i) => <div key={i}>{line}</div>)}
          </div>

          <div className="panel-actions">
            <button className="btn secondary" type="button" onClick={async () => {
              if (!jobId) return;
              abortedRef.current = true;
              setLogs((prev) => [...prev.slice(-300), `[WARN] Abort requested for job ${jobId}`]);

              if (eventSourceRef.current) {
                intentionalCloseRef.current = true;
                eventSourceRef.current.close();
                eventSourceRef.current = null;
                connectedJobRef.current = "";
                setLogs((prev) => [...prev.slice(-300), `[INFO] Stream closed for job ${jobId} (abort requested)`]);
              }

              try {
                await abortGeneration(jobId);
                setLogs((prev) => [...prev.slice(-300), `[INFO] Abort acknowledged by server for job ${jobId}`]);
                setDone(true);
                doneRef.current = true;
              } catch (e) {
                abortedRef.current = false;
                setLogs((prev) => [...prev.slice(-300), `[ERR] Abort failed: ${String(e)}`]);
              }
            }}>Abort</button>
            <button className="btn primary" type="button" disabled={!done} onClick={() => nav(`/download/${jobId}`)}>Next: Download →</button>
          </div>
        </section>

        <aside className="side-stack">
          <div className="card side-card progress-card">
            <div className="progress-ring" style={{ ['--percent' as string]: `${summary.percent}%` }}>
              <div className="progress-ring-center">
                <div className="progress-value">{summary.percent}%</div>
                <div className="muted">Overall Progress</div>
              </div>
            </div>
          </div>
          <div className="card side-card">
            <div className="side-title">Converting Intents into ABL</div>
            <ul className="side-checklist">
              <li className={summary.processing > 0 || summary.completed > 0 ? "done" : ""}>Parsing flow definitions</li>
              <li className={summary.completed > 0 ? "done" : ""}>Generating ABL files</li>
              <li className={summary.warnings > 0 ? "warn" : summary.completed > 0 ? "done" : ""}>Validation output</li>
              <li className={summary.pending === 0 && summary.total > 0 ? "done" : ""}>Preparing for download</li>
            </ul>
          </div>
          <div className="card side-card soft">
            <div className="side-title">Tip</div>
            <p className="muted">You can safely navigate away. We will notify you once the conversion is complete.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}