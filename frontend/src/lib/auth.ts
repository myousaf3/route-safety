import { useEffect, useState } from "react";

/**
 * Client-side session helpers.
 *
 * Tokens live in localStorage because the app is a static SPA talking to a
 * separate API origin. All auth state changes are broadcast through a custom
 * event so every mounted component (header account control, auth page) stays
 * in sync without a global store.
 */

const ACCESS_KEY = "spotter_access_token";
const REFRESH_KEY = "spotter_refresh_token";
const USERNAME_KEY = "spotter_username";
const AUTH_EVENT = "spotter:auth";

export interface Session {
  username: string;
}

function emitAuthChange(): void {
  window.dispatchEvent(new Event(AUTH_EVENT));
}

/** Decode a JWT payload without verifying it; the API verifies signatures. */
function decodePayload(token: string): { exp?: number } | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded)) as { exp?: number };
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = decodePayload(token);
  if (!payload?.exp) return false;
  return payload.exp * 1000 <= Date.now();
}

export function getAccessToken(): string | null {
  const token = localStorage.getItem(ACCESS_KEY);
  if (!token || isTokenExpired(token)) return null;
  return token;
}

export function getRefreshToken(): string | null {
  const token = localStorage.getItem(REFRESH_KEY);
  if (!token || isTokenExpired(token)) return null;
  return token;
}

export function getSession(): Session | null {
  const access = getAccessToken();
  const username = localStorage.getItem(USERNAME_KEY);
  if (!access || !username) return null;
  return { username };
}

export function saveSession(tokens: { access: string; refresh: string }, username: string): void {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  localStorage.setItem(REFRESH_KEY, tokens.refresh);
  localStorage.setItem(USERNAME_KEY, username);
  emitAuthChange();
}

/** Persist refreshed tokens without changing the stored username. */
export function saveTokens(tokens: { access: string; refresh?: string }): void {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  if (tokens.refresh) localStorage.setItem(REFRESH_KEY, tokens.refresh);
  emitAuthChange();
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USERNAME_KEY);
  emitAuthChange();
}

/** React hook that re-renders when the session changes in this tab or another. */
export function useSession(): Session | null {
  const [session, setSession] = useState<Session | null>(() => getSession());

  useEffect(() => {
    const sync = () => setSession(getSession());
    window.addEventListener(AUTH_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(AUTH_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return session;
}
