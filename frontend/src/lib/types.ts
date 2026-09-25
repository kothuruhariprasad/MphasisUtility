export type AgentStyle = "reasoning" | "flow" | "supervisor";

export type LLMProvider = "openai" | "azure_openai" | "claude";

export const SUPERVISOR_INTENT_ID = "__supervisor__";

export interface IntentItem {
  id: string;
  name: string;
  fileSafeName: string;
  nodeCount: number;
  hasAgentNode: boolean;
  suggestedAgentStyle: AgentStyle;
}

export interface UploadResponse {
  sessionId: string;
  intents: IntentItem[];
  platform: "x010" | "x011";
}

export interface SelectionItem {
  intentId: string;
  agentStyle: AgentStyle;
  instructions?: string;
}

export interface GenerateResponse {
  jobId: string;
}

export interface GenerateRequest {
  sessionId: string;
  credentialId: string;
  selections: SelectionItem[];
  addSupervisor?: boolean;
}

export interface LLMCredentialInput {
  provider: LLMProvider;
  apiKey: string;
  model: string;
  azureDomain?: string;
  azureApiVersion?: string;
  cookie?: string;
  label?: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export interface ConfigureResponse {
  credentialId: string;
  provider: LLMProvider;
}

export interface AuthProfile {
  email: string;
  role: string;
}

export type QueueStatus = "pending" | "processing" | "success" | "needs_review" | "failed";

export interface QueueEvent {
  intentId: string;
  name: string;
  outputClass?: string;
  status: QueueStatus;
  message?: string;
  durationMs?: number;
}

export interface LogEvent {
  type: "log";
  level: "INIT" | "INFO" | "WARN" | "ERR" | "RUN";
  text: string;
}

export interface DoneEvent {
  type: "done";
  summary: {
    total: number;
    success: number;
    needsReview: number;
    failed: number;
    pending: number;
  };
  results?: QueueEvent[];
}
