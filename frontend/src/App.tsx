import { Navigate, Route, Routes, useLocation, NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import Navbar from "./components/Navbar";
import Stepper from "./components/Stepper";
import AdminPage from "./pages/AdminPage";
import AuthPage from "./pages/AuthPage";
import DownloadPage from "./pages/DownloadPage";
import GeneratePage from "./pages/GeneratePage";
import HistoryPage from "./pages/HistoryPage";
import ImportPage from "./pages/ImportPage";
import LlmSetupPage from "./pages/LlmSetupPage";
import SelectIntentsPage from "./pages/SelectIntentsPage";
import { fetchAuthProfile } from "./lib/api";
import { AppStoreProvider } from "./lib/store";
import { useAppStore } from "./lib/store";

function AppInner() {
  const location = useLocation();
  const store = useAppStore();
  const [authChecked, setAuthChecked] = useState(false);
  const step =
    location.pathname.startsWith("/import") ? 1 :
    location.pathname.startsWith("/llm") ? 2 :
    location.pathname.startsWith("/select") ? 3 :
    location.pathname.startsWith("/generate") ? 4 :
    location.pathname.startsWith("/download") ? 5 : 1;

  const navItems = [
    { key: "import", label: "Import", path: "/import", icon: "upload" },
    { key: "llm", label: "Connect LLM", path: "/llm", icon: "key" },
    { key: "select", label: "Select Intents", path: "/select", icon: "list" },
    { key: "generate", label: "Generate", path: null, icon: "bolt" },
    { key: "download", label: "Download", path: null, icon: "download" },
  ];

  const extraItems = [
    { key: "history", label: "History", path: "/history", icon: "history" },
    ...(store.isAdmin ? [{ key: "admin", label: "Admin", path: "/admin", icon: "key" }] : []),
  ];

  const isActive = (key: string) => {
    if (key === "import") return location.pathname.startsWith("/import");
    if (key === "llm") return location.pathname.startsWith("/llm");
    if (key === "select") return location.pathname.startsWith("/select");
    if (key === "generate") return location.pathname.startsWith("/generate");
    if (key === "download") return location.pathname.startsWith("/download");
    if (key === "history") return location.pathname.startsWith("/history");
    return false;
  };

  const renderIcon = (name: string) => {
    switch (name) {
      case "upload":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <path d="M12 3 7 8h3v6h4V8h3z" fill="currentColor" />
            <path d="M5 14v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        );
      case "list":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <path d="M7 7h12M7 12h12M7 17h12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="4" cy="7" r="1.5" fill="currentColor" />
            <circle cx="4" cy="12" r="1.5" fill="currentColor" />
            <circle cx="4" cy="17" r="1.5" fill="currentColor" />
          </svg>
        );
      case "key":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <circle cx="8" cy="12" r="4" stroke="currentColor" strokeWidth="1.8" fill="none" />
            <path d="M12 12h9l-2 2m2-2-2-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        );
      case "bolt":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <path d="M13 2 4 14h6l-1 8 9-12h-6z" fill="currentColor" />
          </svg>
        );
      case "download":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <path d="M12 4v9m0 0 4-4m-4 4-4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 18h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        );
      case "history":
        return (
          <svg viewBox="0 0 24 24" aria-hidden>
            <path d="M4 12a8 8 0 1 0 2.4-5.7" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
            <path d="M4 6v4h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12 8v5l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        );
      default:
        return null;
    }
  };

  const showStepper = !location.pathname.startsWith("/history") && !location.pathname.startsWith("/admin") && !location.pathname.startsWith("/login");

  useEffect(() => {
    let active = true;
    const syncProfile = async () => {
      if (!store.authToken) {
        setAuthChecked(true);
        return;
      }
      try {
        if (!store.authEmail) {
          const profile = await fetchAuthProfile();
          if (active) {
            store.setAuthSession(store.authToken, profile.email, profile.role);
          }
        }
      } catch {
        if (active) {
          store.clearAuthSession();
        }
      } finally {
        if (active) {
          setAuthChecked(true);
        }
      }
    };
    syncProfile();
    return () => {
      active = false;
    };
  }, [store.authToken, store.authEmail, store.setAuthSession, store.clearAuthSession]);

  const isLoginRoute = location.pathname.startsWith("/login");
  const isAuthed = Boolean(store.authToken);
  if (!authChecked) {
    return <div className="page"><div className="card panel">Checking access...</div></div>;
  }
  if (!isAuthed && !isLoginRoute) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <Navbar />
      <div className="app-body">
        <aside className="sidebar">
          <div className="nav-section">
            {navItems.map((item) => (
              item.path ? (
                <NavLink key={item.key} className={({ isActive: active }) => `nav-item ${active || isActive(item.key) ? "active" : ""}`}
                  to={item.path}>
                  <span className="nav-icon">{renderIcon(item.icon)}</span>
                  <span>{item.label}</span>
                </NavLink>
              ) : (
                <div key={item.key} className={`nav-item ${isActive(item.key) ? "active" : "disabled"}`}>
                  <span className="nav-icon">{renderIcon(item.icon)}</span>
                  <span>{item.label}</span>
                </div>
              )
            ))}
          </div>
          <div className="nav-section">
            {extraItems.map((item) => (
              item.path ? (
                <NavLink key={item.key} className={({ isActive: active }) => `nav-item ${active || isActive(item.key) ? "active" : ""}`}
                  to={item.path}>
                  <span className="nav-icon">{renderIcon(item.icon)}</span>
                  <span>{item.label}</span>
                </NavLink>
              ) : (
                <div key={item.key} className={`nav-item ${isActive(item.key) ? "active" : "disabled"}`}>
                  <span className="nav-icon">{renderIcon(item.icon)}</span>
                  <span>{item.label}</span>
                </div>
              )
            ))}
          </div>
          <div className="sidebar-help">
            <div className="card help-card">
              <div className="help-title">Need Help?</div>
              <div className="help-text">Check documentation or reach out to the team.</div>
              <a className="btn primary" href="https://docs.kore.ai/agent-platform/abl" target="_blank" rel="noreferrer">View Docs →</a>
            </div>
          </div>
        </aside>
        <main className="app-main">
          {showStepper && <Stepper step={step} />}
          <Routes>
            <Route path="/login" element={isAuthed ? <Navigate to="/import" replace /> : <AuthPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/llm" element={<LlmSetupPage />} />
            <Route path="/select" element={<SelectIntentsPage />} />
            <Route path="/generate/:jobId" element={<GeneratePage />} />
            <Route path="/download/:jobId" element={<DownloadPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<Navigate to={isAuthed ? "/import" : "/login"} replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppStoreProvider>
      <AppInner />
    </AppStoreProvider>
  );
}