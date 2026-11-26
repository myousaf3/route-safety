import { useQueryClient } from "@tanstack/react-query";
import { clearSession, useSession } from "../lib/auth";

/**
 * Compact account control for the app header.
 *
 * The full sign-in / registration experience lives on its own page
 * (`#/login` and `#/register`); this only reflects the current session.
 */
export default function AccountControl() {
  const session = useSession();
  const queryClient = useQueryClient();

  const signOut = () => {
    clearSession();
    void queryClient.invalidateQueries({ queryKey: ["analyses"] });
  };

  if (!session) {
    return (
      <a className="btn btn-secondary btn-small account-signin" href="#/login">
        Sign in
      </a>
    );
  }

  return (
    <div className="account-control">
      <a
        className="account-identity"
        href="#/login"
        title="View account"
        aria-label={`Signed in as ${session.username}`}
      >
        <span className="auth-avatar" aria-hidden="true">
          {session.username.slice(0, 1).toUpperCase()}
        </span>
        <span className="account-name">{session.username}</span>
      </a>
      <button
        type="button"
        className="btn btn-ghost btn-small"
        onClick={signOut}
      >
        Sign out
      </button>
    </div>
  );
}
