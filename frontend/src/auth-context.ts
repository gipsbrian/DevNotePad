import { createContext, useContext } from "react";
import type { User } from "./types/api";

interface AuthValue {
  user: User;
  signOut: () => Promise<void>;
  markTourSeen: (name: string) => void;
}

// Only ever read inside AuthGate's provider, which renders the login
// screen instead of its children when there's nobody signed in.
export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthGate");
  return value;
}
