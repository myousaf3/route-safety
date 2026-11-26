import { useState } from "react";
import { fetchMe, login, register } from "../lib/api";

export default function AuthPanel() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [message, setMessage] = useState<string | null>(null);
  const [user, setUser] = useState<string | null>(
    localStorage.getItem("spotter_username"),
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(null);
    try {
      const tokens =
        mode === "login"
          ? await login(username, password)
          : await register(username, password, email);
      localStorage.setItem("spotter_access_token", tokens.access);
      localStorage.setItem("spotter_refresh_token", tokens.refresh);
      localStorage.setItem("spotter_username", username);
      setUser(username);
      setMessage(`Signed in as ${username}.`);
      const me = await fetchMe();
      if (me.username) localStorage.setItem("spotter_username", me.username);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed.");
    }
  };

  const logout = () => {
    localStorage.removeItem("spotter_access_token");
    localStorage.removeItem("spotter_refresh_token");
    localStorage.removeItem("spotter_username");
    setUser(null);
    setMessage("Signed out.");
  };

  if (user) {
    return (
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Account</span>
            <h2 id="auth-title">Signed in</h2>
          </div>
        </div>
        <p className="subtle">JWT access token is attached to API requests.</p>
        <strong>{user}</strong>
        <button type="button" className="btn btn-ghost btn-small" onClick={logout}>
          Sign out
        </button>
        {message && <p className="field-help">{message}</p>}
      </section>
    );
  }

  return (
    <section className="panel auth-panel" aria-labelledby="auth-title">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Account</span>
          <h2 id="auth-title">{mode === "login" ? "Sign in" : "Create account"}</h2>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Register" : "Sign in"}
        </button>
      </div>
      <form onSubmit={submit} className="auth-form">
        <div className="field">
          <label htmlFor="auth-username">Username</label>
          <input
            id="auth-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </div>
        {mode === "register" && (
          <div className="field">
            <label htmlFor="auth-email">Email (optional)</label>
            <input
              id="auth-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />
          </div>
        )}
        <div className="field">
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </div>
        <button type="submit" className="btn btn-primary btn-small">
          {mode === "login" ? "Sign in" : "Create account"}
        </button>
        {message && <p className="field-error">{message}</p>}
      </form>
      <p className="field-help">
        Analyses can still be run anonymously; signing in scopes history to your account.
      </p>
    </section>
  );
}
