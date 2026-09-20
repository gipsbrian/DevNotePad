import { createContext, useContext } from "react";
import type { Organization } from "./types/api";

interface OrgValue {
  organizations: Organization[];
  /** Null only until the first load finishes. */
  active: Organization | null;
  reload: () => Promise<void>;
  switchTo: (id: string) => Promise<void>;
}

export const OrgContext = createContext<OrgValue | null>(null);

export function useOrganizations(): OrgValue {
  const value = useContext(OrgContext);
  if (!value) throw new Error("useOrganizations must be used inside App");
  return value;
}
