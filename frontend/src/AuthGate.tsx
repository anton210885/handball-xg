import { createContext, FormEvent, ReactNode, useCallback, useContext, useEffect, useState } from "react";

/** Login vor der App – nur wenn der Server ein Passwort verlangt (Betrieb im Internet). */
type Auth = { required: boolean; logout: () => void };
const AuthContext = createContext<Auth>({ required: false, logout: () => {} });
export const useAuth = () => useContext(AuthContext);

/** Wird ausgelöst, wenn eine Anfrage 401 bekommt (Login abgelaufen). */
export const LOGOUT_EVENT = "hxg-unauthorized";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"checking" | "login" | "ok">("checking");
  const [required, setRequired] = useState(false);

  const check = useCallback(() => {
    fetch("/api/auth")
      .then((r) => r.json())
      .then((a: { required: boolean; logged_in: boolean }) => {
        setRequired(a.required);
        setState(a.logged_in ? "ok" : "login");
      })
      .catch(() => setState("ok")); // Server nicht erreichbar → App zeigt ihre eigene Fehlermeldung
  }, []);

  useEffect(() => {
    check();
    const onUnauthorized = () => setState("login");
    window.addEventListener(LOGOUT_EVENT, onUnauthorized);
    return () => window.removeEventListener(LOGOUT_EVENT, onUnauthorized);
  }, [check]);

  const logout = () => fetch("/api/logout", { method: "POST" }).finally(() => setState("login"));

  if (state === "checking") return null;
  if (state === "login") return <LoginPage onDone={() => setState("ok")} />;
  return <AuthContext.Provider value={{ required, logout }}>{children}</AuthContext.Provider>;
}

function LoginPage({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
      });
      if (r.ok) return onDone();
      const body = await r.json().catch(() => ({}));
      setError(body.detail ?? `Fehler ${r.status}`);
    } catch {
      setError("Server nicht erreichbar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="panel login-box" onSubmit={submit}>
        <div className="brand" style={{ margin: "0 0 14px" }}>Handball xG <small>Bitte anmelden</small></div>
        <label className="small muted" htmlFor="pw">Passwort</label>
        <input id="pw" type="password" autoFocus autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} style={{ width: "100%", margin: "4px 0 12px" }} />
        {error && <div className="error" style={{ marginBottom: 10 }}>{error}</div>}
        <button type="submit" disabled={busy || !password} style={{ width: "100%" }}>{busy ? "Prüfe …" : "Anmelden"}</button>
      </form>
    </div>
  );
}
