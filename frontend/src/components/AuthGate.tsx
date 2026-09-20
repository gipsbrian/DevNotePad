import { useCallback, useEffect, useState } from "react";
import { UNAUTHORIZED_EVENT, api } from "../api/client";
import type { User } from "../types/api";
import { LoginPage } from "../pages/LoginPage";
import { AuthContext } from "../auth-context";

export function AuthGate({ children }: { children: React.ReactNode }) {
  // undefined while we're still asking; null once we know nobody is signed in.
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  // A session can lapse mid-visit, so any call that comes back 401 drops
  // the whole app back to the login screen rather than leaving a page
  // that silently fails to load.
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const markTourSeen = useCallback((name: string) => {
    // Locally first: a failed save shouldn't make the tour start over
    // again on the next page of this visit.
    setUser((u) => (u && !u.tours_seen.includes(name) ? { ...u, tours_seen: [...u.tours_seen, name] } : u));
    api.markTourSeen(name).catch(() => {
      // Worst case it shows once more on the next visit.
    });
  }, []);

  if (user === undefined) return <div className="auth-loading" aria-busy="true" />;
  if (user === null) return <LoginPage onSignedIn={setUser} />;

  return <AuthContext.Provider value={{ user, signOut, markTourSeen }}>{children}</AuthContext.Provider>;
}
