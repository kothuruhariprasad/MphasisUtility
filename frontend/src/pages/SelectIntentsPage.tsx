import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startGeneration } from "../lib/api";
import { useAppStore } from "../lib/store";

export default function SelectIntentsPage() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const store = useAppStore();
  const nav = useNavigate();

  const visible = useMemo(() => store.intents.filter((i) => i.name.toLowerCase().includes(query.toLowerCase())), [store.intents, query]);

  const run = async () => {
    if (!store.llmCredentialId) {
      setError("Connect your LLM before starting generation.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const selections = [...store.selectedIds].map((intentId) => {
        const style = store.selections[intentId] === "supervisor" ? "reasoning" : store.selections[intentId];
        return {
          intentId,
          agentStyle: style,
          instructions: store.instructions[intentId] || "",
        };
      });
      const { jobId } = await startGeneration(store.sessionId, store.llmCredentialId, selections, store.addSupervisor);
      nav(`/generate/${jobId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start generation");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-grid wide single">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Select Intents</h1>
            <p className="page-subtitle">Choose which intents to include in your conversion. You can filter, select all, or deselect all.</p>
            {store.platform && (
              <div className="pill">Detected platform: {store.platform.toUpperCase()}</div>
            )}
            {!store.llmCredentialId && (
              <div className="badge warn" style={{ marginTop: 10 }}>LLM not connected. Go to Connect LLM first.</div>
            )}
          </div>

          <div className="toolbar">
            <div className="search">
              <input className="input" placeholder="Filter intents by name..." value={query} onChange={e => setQuery(e.target.value)} />
            </div>
            <div className="selected-pill">{store.selectedIds.size} of {store.intents.length} selected</div>
            <button className="btn secondary" type="button" onClick={() => store.setAllSelected(true)}>Select All</button>
            <button className="btn secondary" type="button" onClick={() => store.setAllSelected(false)}>Deselect All</button>
            <label className="inline-check">
              <input
                type="checkbox"
                checked={store.addSupervisor}
                onChange={(e) => store.setAddSupervisor(e.target.checked)}
              />
              Add supervisor
            </label>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th></th><th>Intent Name</th><th>Nodes</th><th>Type</th><th>Agent Style</th><th>Specific Instructions</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(intent => (
                  <tr key={intent.id}>
                    <td><input type="checkbox" checked={store.selectedIds.has(intent.id)} onChange={() => store.toggleSelect(intent.id)} /></td>
                    <td>{intent.name}</td>
                    <td>{intent.nodeCount}</td>
                    <td>{intent.hasAgentNode ? <span className="badge warn">Agent Node</span> : <span className="badge">Standard</span>}</td>
                    <td>
                      <select
                        className="input"
                        value={store.selections[intent.id] === "supervisor" ? "reasoning" : store.selections[intent.id]}
                        onChange={e => store.setAgentStyle(intent.id, e.target.value as "reasoning" | "flow")}
                      >
                        <option value="reasoning">Reasoning Agent</option>
                        <option value="flow">Flow Agent</option>
                      </select>
                    </td>
                    <td>
                      <textarea
                        className="input textarea"
                        placeholder="Add instructions for this agent..."
                        value={store.instructions[intent.id] || ""}
                        onChange={(e) => store.setInstruction(intent.id, e.target.value)}
                      />
                    </td>
                    <td>
                      <button className="btn tertiary" type="button">View</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {error && <p className="badge fail" style={{ marginTop: 0, marginBottom: 18, display: "inline-block" }}>{error}</p>}

          <div className="panel-actions">
            <button className="btn secondary" type="button" onClick={() => nav("/import")}>Back</button>
            <button className="btn primary" type="button" disabled={store.selectedIds.size === 0 || busy || !store.llmCredentialId} onClick={run}>{busy ? "Starting..." : "Next: Generate →"}</button>
          </div>
        </section>

      </div>

      <div className="value-strip">
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Accurate Conversion</div>
            <div className="muted">Consistent results across flows</div>
          </div>
        </div>
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Saves Time and Effort</div>
            <div className="muted">Quickly process large batches</div>
          </div>
        </div>
        <div className="value-item">
          <div className="value-icon">✓</div>
          <div>
            <div className="value-title">Built for Productivity</div>
            <div className="muted">Focused workflows for teams</div>
          </div>
        </div>
      </div>
    </div>
  );
}