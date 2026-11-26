import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Brand from "./Brand";
import { ApiError, login, register } from "../lib/api";
import { clearSession, saveSession, useSession } from "../lib/auth";

export type AuthMode = "login" | "register";

interface Props {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onDone: () => void;
}

type FieldErrors = Record<string, string>;

function firstMessage(value: string[] | string | undefined): string | null {
  if (!value) return null;
  return Array.isArray(value) ? (value[0] ?? null) : value;
}

function mapApiFieldErrors(error: ApiError): FieldErrors {
  const mapped: FieldErrors = {};
  for (const [field, value] of Object.entries(error.fieldErrors ?? {})) {
    const message = firstMessage(value);
    if (message) mapped[field] = message;
  }
  return mapped;
}

export default function AuthPage({ mode, onModeChange, onDone }: Props) {
  const session = useSession();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isRegister = mode === "register";

  // Clear transient feedback when switching between sign in and registration.
  useEffect(() => {
    setErrors({});
    setFormError(null);
    setPassword("");
    setConfirmPassword("");
    setShowPassword(false);
  }, [mode]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;

    const trimmedUsername = username.trim();
    const trimmedEmail = email.trim();
    const nextErrors: FieldErrors = {};

    if (!trimmedUsername) nextErrors.username = "Enter your username.";
    if (!password) nextErrors.password = "Enter your password.";
    if (isRegister) {
      if (password && password.length < 8) {
        nextErrors.password = "Use at least 8 characters.";
      }
      if (password !== confirmPassword) {
        nextErrors.confirmPassword = "Passwords do not match.";
      }
      if (trimmedEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
        nextErrors.email = "Enter a valid email address.";
      }
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setFormError(null);
      return;
    }

    setSubmitting(true);
    setErrors({});
    setFormError(null);
    try {
      const tokens = isRegister
        ? await register(trimmedUsername, password, trimmedEmail || undefined)
        : await login(trimmedUsername, password);
      saveSession(tokens, trimmedUsername);
      void queryClient.invalidateQueries({ queryKey: ["analyses"] });
      onDone();
    } catch (error) {
      if (error instanceof ApiError) {
        const mapped = mapApiFieldErrors(error);
        setErrors(mapped);
        setFormError(
          Object.keys(mapped).length > 0
            ? "Check the highlighted fields and try again."
            : error.detail,
        );
      } else {
        setFormError("Authentication failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-shell">
      <header className="auth-topbar">
        <a className="brand-link" href="#/" aria-label="Spotter Route Safety home">
          <Brand />
        </a>
        <a className="btn btn-ghost btn-small" href="#/">
          Back to app
        </a>
      </header>

      <main className="auth-layout">
        <section className="auth-intro" aria-labelledby="auth-intro-title">
          <span className="eyebrow">Driver account</span>
          <h1 id="auth-intro-title">
            Keep the routes that keep your load safe.
          </h1>
          <p className="auth-lede">
            Sign in to save analyses to your own history, revisit the exact forecast
            snapshot behind a decision, and share a stable deep link with your team.
          </p>

          <ul className="auth-benefits">
            <li>
              <span className="auth-benefit-icon" aria-hidden="true">
                01
              </span>
              <div>
                <strong>Your history, scoped to you</strong>
                <p>Only your analyses appear in the Saved panel when you are signed in.</p>
              </div>
            </li>
            <li>
              <span className="auth-benefit-icon" aria-hidden="true">
                02
              </span>
              <div>
                <strong>Stable, reproducible results</strong>
                <p>Saved analyses keep the routes, checkpoint risk, and forecast times used.</p>
              </div>
            </li>
            <li>
              <span className="auth-benefit-icon" aria-hidden="true">
                03
              </span>
              <div>
                <strong>Secure token sessions</strong>
                <p>Short-lived JWT access tokens are refreshed automatically in the background.</p>
              </div>
            </li>
          </ul>

          <p className="auth-guest-note">
            Just exploring? <a href="#/">Run an analysis anonymously</a> — no account required.
          </p>
        </section>

        <section className="auth-card" aria-labelledby="auth-form-title">
          {session ? (
            <div className="auth-signed-in">
              <span className="auth-avatar auth-avatar-large" aria-hidden="true">
                {session.username.slice(0, 1).toUpperCase()}
              </span>
              <span className="eyebrow">Signed in</span>
              <h2 id="auth-form-title">Welcome back, {session.username}</h2>
              <p className="subtle">
                Your API requests now use a bearer token and saved analyses are scoped to
                your account.
              </p>
              <button type="button" className="btn btn-primary auth-submit" onClick={onDone}>
                Continue to the app
              </button>
              <button
                type="button"
                className="btn btn-ghost auth-submit"
                onClick={() => {
                  clearSession();
                  void queryClient.invalidateQueries({ queryKey: ["analyses"] });
                }}
              >
                Sign out
              </button>
            </div>
          ) : (
            <>
              <div className="auth-card-heading">
                <span className="eyebrow">Account</span>
                <h2 id="auth-form-title">
                  {isRegister ? "Create your account" : "Sign in to Spotter"}
                </h2>
                <p className="subtle">
                  {isRegister
                    ? "One account keeps every route decision in one place."
                    : "Use your Spotter username and password."}
                </p>
              </div>

              <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
                <button
                  type="button"
                  role="tab"
                  aria-selected={!isRegister}
                  className={!isRegister ? "auth-tab active" : "auth-tab"}
                  onClick={() => onModeChange("login")}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={isRegister}
                  className={isRegister ? "auth-tab active" : "auth-tab"}
                  onClick={() => onModeChange("register")}
                >
                  Create account
                </button>
              </div>

              <form className="auth-form" onSubmit={submit} noValidate>
                {formError && (
                  <p className="auth-alert" role="alert">
                    {formError}
                  </p>
                )}

                <div className="field">
                  <label htmlFor="auth-username">Username</label>
                  <input
                    id="auth-username"
                    name="username"
                    type="text"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    autoFocus
                    aria-invalid={Boolean(errors.username)}
                    aria-describedby={errors.username ? "auth-username-error" : undefined}
                  />
                  {errors.username && (
                    <p className="field-error" id="auth-username-error">
                      {errors.username}
                    </p>
                  )}
                </div>

                {isRegister && (
                  <div className="field">
                    <label htmlFor="auth-email">Email (optional)</label>
                    <input
                      id="auth-email"
                      name="email"
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="email"
                      aria-invalid={Boolean(errors.email)}
                      aria-describedby={errors.email ? "auth-email-error" : undefined}
                    />
                    {errors.email && (
                      <p className="field-error" id="auth-email-error">
                        {errors.email}
                      </p>
                    )}
                  </div>
                )}

                <div className="field">
                  <label htmlFor="auth-password">Password</label>
                  <div className="auth-password">
                    <input
                      id="auth-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete={isRegister ? "new-password" : "current-password"}
                      aria-invalid={Boolean(errors.password)}
                      aria-describedby={
                        errors.password
                          ? "auth-password-error"
                          : isRegister
                            ? "auth-password-help"
                            : undefined
                      }
                    />
                    <button
                      type="button"
                      className="auth-password-toggle"
                      onClick={() => setShowPassword((current) => !current)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}
                    >
                      {showPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  {errors.password && (
                    <p className="field-error" id="auth-password-error">
                      {errors.password}
                    </p>
                  )}
                  {isRegister && !errors.password && (
                    <p className="field-help" id="auth-password-help">
                      At least 8 characters. Avoid common or all-numeric passwords.
                    </p>
                  )}
                </div>

                {isRegister && (
                  <div className="field">
                    <label htmlFor="auth-confirm-password">Confirm password</label>
                    <input
                      id="auth-confirm-password"
                      name="confirmPassword"
                      type={showPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      autoComplete="new-password"
                      aria-invalid={Boolean(errors.confirmPassword)}
                      aria-describedby={
                        errors.confirmPassword ? "auth-confirm-error" : undefined
                      }
                    />
                    {errors.confirmPassword && (
                      <p className="field-error" id="auth-confirm-error">
                        {errors.confirmPassword}
                      </p>
                    )}
                  </div>
                )}

                <button
                  type="submit"
                  className="btn btn-primary auth-submit"
                  disabled={submitting}
                >
                  {submitting
                    ? isRegister
                      ? "Creating account…"
                      : "Signing in…"
                    : isRegister
                      ? "Create account"
                      : "Sign in"}
                </button>

                <p className="auth-switch">
                  {isRegister ? "Already have an account?" : "New to Spotter?"}{" "}
                  <button
                    type="button"
                    className="auth-link-button"
                    onClick={() => onModeChange(isRegister ? "login" : "register")}
                  >
                    {isRegister ? "Sign in" : "Create one"}
                  </button>
                </p>
              </form>
            </>
          )}
        </section>
      </main>

      <footer className="auth-footer">
        <span>JWT access tokens · Automatic refresh · Owner-scoped history</span>
        <a href="#/">Continue without signing in</a>
      </footer>
    </div>
  );
}
