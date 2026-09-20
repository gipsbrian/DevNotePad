import type { TokenInfo } from "../types/api";

export function TokenBadge({ info }: { info: TokenInfo }) {
  let cls = "";
  let label = info.type_label;
  let title = info.warning;

  if (info.error) {
    cls = "error";
    label = "Token problem";
    title = `${info.type_label} — ${info.error}`;
  } else if (info.inferred_can_write) {
    cls = "write";
    label = "Read + write";
    title = `${info.type_label} · write access inferred from repo permissions (not verified by GitHub). ${info.warning}`;
  } else if (info.inferred_can_read) {
    cls = "read";
    label = "Read-only";
    title = `${info.type_label} · read-only inferred from repo permissions (not verified by GitHub). ${info.warning}`;
  } else if (info.classic_scopes) {
    label = info.classic_scopes.join(", ") || "no scopes";
    title = `${info.type_label} · scopes reported by GitHub`;
  }

  return (
    <span className={`token-badge ${cls}`} title={title}>
      <span className="dot" />
      {label}
    </span>
  );
}
