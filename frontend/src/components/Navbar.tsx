import { useNavigate } from "react-router-dom";
import { useAppStore } from "../lib/store";
import { logoutSharedPassword } from "../lib/api";

export default function Navbar() {
  const store = useAppStore();
  const nav = useNavigate();

  const onSignOut = async () => {
    await logoutSharedPassword();
    store.clearAuthSession();
    nav("/login");
  };

  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
            <path d="M5 12a7 7 0 1 0 7-7" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
            <path d="M12 5a7 7 0 0 1 7 7" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
            <path d="M12 5v7l4 3" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <div className="brand-title">Mphasis X011 Transformer</div>
          <div className="brand-subtitle">Convert AppDef configurations to ABL with accuracy and ease</div>
        </div>
      </div>
      {store.authEmail && (
        <div className="top-actions">
          <div className="profile-chip">
            <span>{store.authEmail}</span>
          </div>
          <button className="btn secondary" type="button" onClick={onSignOut}>Sign out</button>
        </div>
      )}
    </header>
  );
}