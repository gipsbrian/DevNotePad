import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useOrganizations } from "../org-context";
import type { AppNotification } from "../types/api";
import { IconBell } from "./Icons";

const POLL_MS = 60_000;

function describe(n: AppNotification): React.ReactNode {
  const org = <strong>{n.organization_name ?? "an organisation"}</strong>;
  const actor = <strong>{n.actor ?? "Someone"}</strong>;
  switch (n.kind) {
    case "join_request":
      return <>{actor} asked to join {org}</>;
    case "join_approved":
      return <>You’re in: your request to join {org} was approved</>;
    case "join_declined":
      return <>Your request to join {org} was declined</>;
    case "invitation_accepted":
      return <>{actor} joined {org} with your invitation</>;
  }
}

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Unread count in the rail, and the list behind it. Checks in on a minute's
 * interval and whenever the window regains focus. */
export function NotificationBell() {
  const navigate = useNavigate();
  const { switchTo, reload } = useOrganizations();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const feed = await api.listNotifications();
      setItems(feed.items);
      setUnread((before) => {
        // Approvals change which organisations you're in.
        if (feed.unread > before && feed.items.some((i) => !i.read && i.kind === "join_approved")) reload();
        return feed.unread;
      });
    } catch {
      // Quietly try again next time.
    }
  }, [reload]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    window.addEventListener("focus", load);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, [load]);

  useEffect(() => {
    if (!open) return;
    function onDocument(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocument);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocument);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function openItem(n: AppNotification) {
    setOpen(false);
    if (!n.read) {
      setItems((list) => list.map((i) => (i.id === n.id ? { ...i, read: true } : i)));
      setUnread((u) => Math.max(0, u - 1));
      api.markNotificationsRead([n.id]).catch(() => undefined);
    }
    if (!n.organization_id || n.kind === "join_declined") return;
    try {
      await switchTo(n.organization_id);
    } catch {
      // No longer a member there; nothing to open.
      return;
    }
    navigate(n.kind === "join_approved" ? "/" : "/organization");
  }

  async function markAll() {
    setItems((list) => list.map((i) => ({ ...i, read: true })));
    setUnread(0);
    await api.markNotificationsRead().catch(() => undefined);
  }

  return (
    <div className="bell" ref={ref}>
      <button
        className={`rail-btn${open ? " active" : ""}`}
        data-tour="notifications"
        onClick={() => setOpen((v) => !v)}
        title={unread ? `${unread} unread notification${unread === 1 ? "" : "s"}` : "Notifications"}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
      >
        <IconBell />
        {unread > 0 && <span className="bell-count">{unread > 9 ? "9+" : unread}</span>}
      </button>

      {open && (
        <div className="bell-menu" role="dialog" aria-label="Notifications">
          <div className="bell-head">
            <span>Notifications</span>
            {unread > 0 && (
              <button className="bell-mark" onClick={markAll}>
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="bell-empty">Nothing yet. Join requests and approvals show up here.</p>
          ) : (
            <ul className="bell-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button className={`bell-item${n.read ? "" : " unread"}`} onClick={() => openItem(n)}>
                    <span className="bell-text">{describe(n)}</span>
                    <time dateTime={n.created_at}>{ago(n.created_at)}</time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
