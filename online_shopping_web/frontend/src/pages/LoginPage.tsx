import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api";
import { sendAgiEvent, startNewAgiSession } from "../tracking/agiClient";
import { usePageTracking } from "../tracking/usePageTracking";

export function LoginPage() {
  usePageTracking("login");
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response =
        mode === "register" ? await register(username, password, name || username) : await login(username, password);
      localStorage.setItem("demoUserId", response.user.id);
      localStorage.setItem("demoUserName", response.user.name);
      startNewAgiSession();
      window.dispatchEvent(new Event("demo-auth-changed"));
      if (mode === "register") {
        sendAgiEvent({
          type: "register_success",
          pageType: "login",
          metadata: { username: response.user.username },
        });
      }
      sendAgiEvent({
        type: "session_start",
        pageType: "login",
        metadata: { username: response.user.username },
      });
      navigate("/products");
    } catch (err) {
      if (mode === "register") {
        sendAgiEvent({ type: "register_failed", pageType: "login", metadata: { username } });
      }
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-page">
      <form className="auth-panel" onSubmit={submit}>
        <p className="eyebrow">MockMart account</p>
        <h1>{mode === "register" ? "Create your account" : "Sign in to MockMart"}</h1>
        <div className="segmented-control">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Login
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Register
          </button>
        </div>
        {mode === "register" ? (
          <label>
            Display name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
        ) : null}
        <label>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button disabled={loading}>
          {loading ? "Working..." : mode === "register" ? "Create account" : "Sign in"}
        </button>
      </form>
    </section>
  );
}
