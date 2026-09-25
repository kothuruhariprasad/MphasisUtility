import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { configureLLM, testLLMConnection } from "../lib/api";
import type { LLMCredentialInput, LLMProvider } from "../lib/types";
import { useAppStore } from "../lib/store";

const PROVIDER_LABELS: Record<LLMProvider, string> = {
  openai: "OpenAI",
  azure_openai: "Azure OpenAI",
  claude: "Claude (Anthropic)",
};

export default function LlmSetupPage() {
  const nav = useNavigate();
  const store = useAppStore();
  const [provider, setProvider] = useState<LLMProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [azureDomain, setAzureDomain] = useState("");
  const [azureApiVersion, setAzureApiVersion] = useState("");
  const [cookie, setCookie] = useState("");
  const [label, setLabel] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const needsAzure = provider === "azure_openai";

  const payload: LLMCredentialInput = useMemo(() => ({
    provider,
    apiKey,
    model,
    azureDomain: needsAzure ? azureDomain : undefined,
    azureApiVersion: needsAzure ? azureApiVersion : undefined,
    cookie: needsAzure && cookie ? cookie : undefined,
    label: label.trim() || undefined,
  }), [provider, apiKey, model, azureDomain, azureApiVersion, cookie, label, needsAzure]);

  const canTest = Boolean(apiKey && model && (!needsAzure || (azureDomain && azureApiVersion)));
  const canSave = Boolean(testResult?.success && !saving);

  useEffect(() => {
    setTestResult(null);
  }, [provider, apiKey, model, azureDomain, azureApiVersion, cookie, label]);

  const onTest = async () => {
    if (!canTest) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testLLMConnection(payload);
      setTestResult(res);
    } catch (e) {
      setTestResult({ success: false, message: e instanceof Error ? e.message : "Test failed" });
    } finally {
      setTesting(false);
    }
  };

  const onSave = async () => {
    if (!testResult?.success) return;
    setSaving(true);
    try {
      const res = await configureLLM(payload);
      store.setLLMCredential(res.credentialId, res.provider, model);
      nav("/select");
    } catch (e) {
      setTestResult({ success: false, message: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <div className="page-grid llm-grid">
        <section className="card panel">
          <div className="panel-header">
            <h1 className="page-title">Connect Your LLM</h1>
            <p className="page-subtitle">Bring your own key. We encrypt credentials in-memory and never expose them to the browser after setup.</p>
          </div>

          <div className="form-grid">
            <label className="form-row">
              <span className="form-label">Provider</span>
              <select className="input" value={provider} onChange={(e) => setProvider(e.target.value as LLMProvider)}>
                <option value="openai">OpenAI</option>
                <option value="azure_openai">Azure OpenAI</option>
                <option value="claude">Claude (Anthropic)</option>
              </select>
            </label>

            <label className="form-row">
              <span className="form-label">API key</span>
              <input
                className="input"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste your API key"
              />
            </label>

            <label className="form-row">
              <span className="form-label">Model / Deployment</span>
              <input
                className="input"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={provider === "azure_openai" ? "Deployment name" : "Model name"}
              />
            </label>

            {needsAzure && (
              <>
                <label className="form-row">
                  <span className="form-label">Azure domain</span>
                  <input
                    className="input"
                    value={azureDomain}
                    onChange={(e) => setAzureDomain(e.target.value)}
                    placeholder="example-resource"
                  />
                </label>
                <label className="form-row">
                  <span className="form-label">API version</span>
                  <input
                    className="input"
                    value={azureApiVersion}
                    onChange={(e) => setAzureApiVersion(e.target.value)}
                    placeholder="2024-02-15-preview"
                  />
                </label>
                <label className="form-row">
                  <span className="form-label">Cookie (optional)</span>
                  <input
                    className="input"
                    value={cookie}
                    onChange={(e) => setCookie(e.target.value)}
                    placeholder="Optional Azure Cookie"
                  />
                </label>
              </>
            )}

            <label className="form-row">
              <span className="form-label">Label (optional)</span>
              <input
                className="input"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={`e.g., ${PROVIDER_LABELS[provider]} key`}
              />
            </label>
          </div>

          {testResult && (
            <div className={`alert ${testResult.success ? "ok" : "fail"}`}>
              <strong>{testResult.success ? "Connection OK" : "Connection failed"}</strong>
              <span>{testResult.message}</span>
            </div>
          )}

          <div className="panel-actions">
            <button className="btn secondary" type="button" onClick={() => nav("/import")}>Back</button>
            <button className="btn secondary" type="button" onClick={onTest} disabled={!canTest || testing}>{testing ? "Testing..." : "Test Connection"}</button>
            <button className="btn primary" type="button" onClick={onSave} disabled={!canSave}>{saving ? "Saving..." : "Save & Continue ->"}</button>
          </div>
        </section>

        <aside className="side-stack">
          <div className="card side-card">
            <div className="side-title">Security Promise</div>
            <ul className="side-list">
              <li>Keys are encrypted immediately using server-side encryption.</li>
              <li>No credentials are stored in the browser or local storage.</li>
              <li>In-memory credentials auto-expire after the configured TTL.</li>
            </ul>
          </div>
          <div className="card side-card soft">
            <div className="side-title">Provider Tips</div>
            <p className="muted">
              {provider === "azure_openai"
                ? "Use the Azure resource name as the domain, and the deployment name as the model."
                : "Use the exact model name you want to run for generation."}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
