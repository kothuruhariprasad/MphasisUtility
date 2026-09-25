import type {
  ConfigureResponse,
  GenerateRequest,
  GenerateResponse,
  LLMCredentialInput,
  SelectionItem,
  TestConnectionResponse,
  UploadResponse,
} from "./types";

const apiBaseEnv = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE = apiBaseEnv && apiBaseEnv.trim() ? apiBaseEnv.trim() : "http://127.0.0.1:8000/api";
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token && token.trim() ? token.trim() : null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: { ...(init?.headers ?? {}), ...headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

function toBackendCredentialPayload(payload: LLMCredentialInput): Record<string, unknown> {
  return {
    provider: payload.provider,
    api_key: payload.apiKey,
    model: payload.model,
    azure_domain: payload.azureDomain,
    azure_api_version: payload.azureApiVersion,
    cookie: payload.cookie,
    label: payload.label,
  };
}

export async function uploadArchive(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return requestJson<UploadResponse>(`${API_BASE}/upload`, { method: "POST", body: form });
}

export async function startGeneration(sessionId: string, credentialId: string, selections: SelectionItem[], addSupervisor?: boolean): Promise<GenerateResponse> {
  const payload: GenerateRequest = { sessionId, credentialId, selections, addSupervisor };
  return requestJson<GenerateResponse>(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function testLLMConnection(payload: LLMCredentialInput): Promise<TestConnectionResponse> {
  return requestJson<TestConnectionResponse>(`${API_BASE}/llm/test-connection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toBackendCredentialPayload(payload)),
  });
}

export async function configureLLM(payload: LLMCredentialInput): Promise<ConfigureResponse> {
  return requestJson<ConfigureResponse>(`${API_BASE}/llm/configure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toBackendCredentialPayload(payload)),
  });
}

export function openGenerationStream(jobId: string): EventSource {
  const token = authToken ? `?token=${encodeURIComponent(authToken)}` : "";
  return new EventSource(`${API_BASE}/generate/stream/${jobId}${token}`, { withCredentials: true });
}

export async function abortGeneration(jobId: string): Promise<void> {
  await requestJson(`${API_BASE}/generate/abort/${jobId}`, { method: "POST" });
}

export async function fetchGenerationReport(jobId: string): Promise<{ summary: { total: number; success: number; needsReview: number; failed: number; pending: number }; metrics: { totalDurationMs: number; tokens: { prompt: number; completion: number; total: number }; estimatedManualMinutes: number; timeSavedMinutes: number; speedupFactor: number }; intents: Array<{ id: string; name: string; status: "pending" | "processing" | "success" | "needs_review" | "failed"; warnings: string[]; unresolvedReferences: string[]; durationMs?: number | null; tokens?: { prompt: number; completion: number; total: number }; estimatedManualMinutes?: number }> }> {
  return requestJson(`${API_BASE}/generate/report/${jobId}`);
}

export function downloadZipUrl(jobId: string, token?: string): string {
  const tokenValue = token ?? authToken;
  const query = tokenValue ? `?token=${encodeURIComponent(tokenValue)}` : "";
  return `${API_BASE}/generate/download/${jobId}${query}`;
}

export function downloadReportUrl(jobId: string, token?: string): string {
  const tokenValue = token ?? authToken;
  const query = tokenValue ? `?token=${encodeURIComponent(tokenValue)}` : "";
  return `${API_BASE}/generate/report/${jobId}${query}`;
}

export async function fetchAuthProfile(): Promise<{ email: string; role: string }> {
  return requestJson(`${API_BASE}/auth/me`);
}

export async function loginSharedPassword(password: string): Promise<{ token: string; email: string; role: string }> {
  return requestJson(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export async function logoutSharedPassword(): Promise<void> {
  await requestJson(`${API_BASE}/auth/logout`, { method: "POST" });
}

export async function listAllowlist(): Promise<Array<{ email: string; role: string; enabled: boolean; created_at?: string }>> {
  return requestJson(`${API_BASE}/admin/allowlist`);
}

export async function upsertAllowlist(payload: { email: string; role: string; enabled: boolean }): Promise<{ email: string; role: string; enabled: boolean }>{
  return requestJson(`${API_BASE}/admin/allowlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateAllowlist(email: string, payload: { role?: string; enabled?: boolean }): Promise<{ email: string; role: string; enabled: boolean }>{
  return requestJson(`${API_BASE}/admin/allowlist/${encodeURIComponent(email)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteAllowlist(email: string): Promise<{ deleted: boolean }> {
  return requestJson(`${API_BASE}/admin/allowlist/${encodeURIComponent(email)}`, { method: "DELETE" });
}
