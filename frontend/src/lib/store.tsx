import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { AgentStyle, IntentItem } from "./types";
import { setAuthToken } from "./api";

const STORE_KEY = "x011_app_store_v1";

interface PersistedState {
  sessionId: string;
  fileName: string;
  intents: IntentItem[];
  platform: "x010" | "x011" | "";
  selections: Record<string, AgentStyle>;
  selectedIds: string[];
  instructions: Record<string, string>;
  addSupervisor?: boolean;
  history?: HistoryEntry[];
  authToken?: string;
  authEmail?: string;
  authRole?: string;
}

export interface HistoryEntry {
  id: string;
  jobId: string;
  fileName: string;
  createdAt: string;
}

function loadInitialState(): PersistedState {
  if (typeof window === "undefined") {
    return { sessionId: "", fileName: "", intents: [], platform: "", selections: {}, selectedIds: [], instructions: {}, addSupervisor: false, history: [], authToken: "", authEmail: "", authRole: "" };
  }
  try {
    const raw = window.sessionStorage.getItem(STORE_KEY);
    if (!raw) {
      return { sessionId: "", fileName: "", intents: [], platform: "", selections: {}, selectedIds: [], instructions: {}, addSupervisor: false, history: [], authToken: "", authEmail: "", authRole: "" };
    }
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    return {
      sessionId: typeof parsed.sessionId === "string" ? parsed.sessionId : "",
      fileName: typeof parsed.fileName === "string" ? parsed.fileName : "",
      intents: Array.isArray(parsed.intents) ? parsed.intents : [],
      platform: parsed.platform === "x010" || parsed.platform === "x011" ? parsed.platform : "",
      selections: parsed.selections && typeof parsed.selections === "object" ? parsed.selections as Record<string, AgentStyle> : {},
      selectedIds: Array.isArray(parsed.selectedIds) ? parsed.selectedIds : [],
      instructions: parsed.instructions && typeof parsed.instructions === "object" ? parsed.instructions as Record<string, string> : {},
      addSupervisor: typeof parsed.addSupervisor === "boolean" ? parsed.addSupervisor : false,
      history: Array.isArray(parsed.history) ? parsed.history as HistoryEntry[] : [],
      authToken: typeof parsed.authToken === "string" ? parsed.authToken : "",
      authEmail: typeof parsed.authEmail === "string" ? parsed.authEmail : "",
      authRole: typeof parsed.authRole === "string" ? parsed.authRole : "",
    };
  } catch {
    return { sessionId: "", fileName: "", intents: [], platform: "", selections: {}, selectedIds: [], instructions: {}, addSupervisor: false, history: [], authToken: "", authEmail: "", authRole: "" };
  }
}

function persistState(state: PersistedState): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORE_KEY, JSON.stringify(state));
}

interface AppState {
  sessionId: string;
  fileName: string;
  intents: IntentItem[];
  platform: "x010" | "x011" | "";
  selections: Record<string, AgentStyle>;
  selectedIds: Set<string>;
  instructions: Record<string, string>;
  addSupervisor: boolean;
  history: HistoryEntry[];
  llmCredentialId: string;
  llmProvider: string;
  llmModel: string;
  authToken: string;
  authEmail: string;
  authRole: string;
  isAdmin: boolean;
  setUploadData: (sessionId: string, fileName: string, intents: IntentItem[], platform: "x010" | "x011") => void;
  toggleSelect: (intentId: string) => void;
  setAllSelected: (selected: boolean) => void;
  setAgentStyle: (intentId: string, style: AgentStyle) => void;
  setInstruction: (intentId: string, instructions: string) => void;
  setAddSupervisor: (enabled: boolean) => void;
  setLLMCredential: (credentialId: string, provider: string, model: string) => void;
  clearLLMCredential: () => void;
  setAuthSession: (token: string, email: string, role: string) => void;
  clearAuthSession: () => void;
  addHistoryEntry: (entry: HistoryEntry) => void;
  resetAll: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppStoreProvider({ children }: { children: React.ReactNode }) {
  const initial = loadInitialState();
  const [sessionId, setSessionId] = useState(initial.sessionId);
  const [fileName, setFileName] = useState(initial.fileName);
  const [intents, setIntents] = useState<IntentItem[]>(initial.intents);
  const [platform, setPlatform] = useState<"x010" | "x011" | "">(initial.platform);
  const [selections, setSelections] = useState<Record<string, AgentStyle>>(initial.selections);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(initial.selectedIds));
  const [instructions, setInstructions] = useState<Record<string, string>>(initial.instructions);
  const [addSupervisor, setAddSupervisorState] = useState<boolean>(initial.addSupervisor ?? false);
  const [history, setHistory] = useState<HistoryEntry[]>(initial.history ?? []);
  const [llmCredentialId, setLlmCredentialId] = useState("");
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [authToken, setAuthTokenState] = useState(initial.authToken ?? "");
  const [authEmail, setAuthEmail] = useState(initial.authEmail ?? "");
  const [authRole, setAuthRole] = useState(initial.authRole ?? "");

  useEffect(() => {
    setAuthToken(authToken || null);
  }, [authToken]);

  const value = useMemo<AppState>(() => ({
    sessionId,
    fileName,
    intents,
    platform,
    selections,
    selectedIds,
    instructions,
    addSupervisor,
    history,
    llmCredentialId,
    llmProvider,
    llmModel,
    authToken,
    authEmail,
    authRole,
    isAdmin: authRole === "admin",
    setUploadData(newSessionId, newFileName, newIntents, newPlatform) {
      const base: Record<string, AgentStyle> = {};
      const instructionBase: Record<string, string> = {};
      for (const item of newIntents) {
        base[item.id] = item.suggestedAgentStyle === "supervisor" ? "reasoning" : item.suggestedAgentStyle;
        instructionBase[item.id] = "";
      }
      const selected = newIntents.map((i) => i.id);
      setSessionId(newSessionId);
      setFileName(newFileName);
      setIntents(newIntents);
      setPlatform(newPlatform);
      setSelections(base);
      setSelectedIds(new Set(selected));
      setInstructions(instructionBase);
      setAddSupervisorState(false);
      persistState({ sessionId: newSessionId, fileName: newFileName, intents: newIntents, platform: newPlatform, selections: base, selectedIds: selected, instructions: instructionBase, addSupervisor: false, history });
    },
    toggleSelect(intentId) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(intentId)) next.delete(intentId);
        else next.add(intentId);
        persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...next], instructions, addSupervisor, history });
        return next;
      });
    },
    setAllSelected(selected) {
      if (selected) {
        const ids = intents.map((i) => i.id);
        setSelectedIds(new Set(ids));
        persistState({ sessionId, fileName, intents, platform, selections, selectedIds: ids, instructions, addSupervisor, history });
      } else {
        setSelectedIds(new Set());
        persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [], instructions, addSupervisor, history });
      }
    },
    setAgentStyle(intentId, style) {
      setSelections((prev) => {
        const next = { ...prev, [intentId]: style };
        persistState({ sessionId, fileName, intents, platform, selections: next, selectedIds: [...selectedIds], instructions, addSupervisor, history });
        return next;
      });
    },
    setInstruction(intentId, value) {
      setInstructions((prev) => {
        const next = { ...prev, [intentId]: value };
        persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...selectedIds], instructions: next, addSupervisor, history });
        return next;
      });
    },
    setAddSupervisor(enabled) {
      setAddSupervisorState(enabled);
      persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...selectedIds], instructions, addSupervisor: enabled, history });
    },
    setLLMCredential(credentialId, provider, model) {
      setLlmCredentialId(credentialId);
      setLlmProvider(provider);
      setLlmModel(model);
    },
    clearLLMCredential() {
      setLlmCredentialId("");
      setLlmProvider("");
      setLlmModel("");
    },
    setAuthSession(token, email, role) {
      setAuthTokenState(token);
      setAuthEmail(email);
      setAuthRole(role);
      persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...selectedIds], instructions, addSupervisor, history, authToken: token, authEmail: email, authRole: role });
    },
    clearAuthSession() {
      setAuthTokenState("");
      setAuthEmail("");
      setAuthRole("");
      persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...selectedIds], instructions, addSupervisor, history, authToken: "", authEmail: "", authRole: "" });
    },
    addHistoryEntry(entry) {
      setHistory((prev) => {
        if (prev.some((item) => item.jobId === entry.jobId)) {
          return prev;
        }
        const next = [entry, ...prev].slice(0, 50);
        persistState({ sessionId, fileName, intents, platform, selections, selectedIds: [...selectedIds], instructions, addSupervisor, history: next });
        return next;
      });
    },
    resetAll() {
      setSessionId("");
      setFileName("");
      setIntents([]);
      setPlatform("");
      setSelections({});
      setSelectedIds(new Set());
      setInstructions({});
      setAddSupervisorState(false);
      setLlmCredentialId("");
      setLlmProvider("");
      setLlmModel("");
      persistState({ sessionId: "", fileName: "", intents: [], platform: "", selections: {}, selectedIds: [], instructions: {}, addSupervisor: false, history, authToken, authEmail, authRole });
    },
  }), [sessionId, fileName, intents, platform, selections, selectedIds, instructions, addSupervisor, history, llmCredentialId, llmProvider, llmModel, authToken, authEmail, authRole]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppStore() {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useAppStore must be used within AppStoreProvider");
  }
  return ctx;
}
