import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useOrganizations } from "../org-context";
import type { Dashboard, OrganizationMember } from "../types/api";
import { IconRepo } from "../components/Icons";

/** A member of the current organisation, and the boards they've shared with
 * you. View only: nothing else of theirs is visible here. */
export function MemberPage() {
  const { userId = "" } = useParams();
  const { active } = useOrganizations();
  const [member, setMember] = useState<OrganizationMember | null>(null);
  const [boards, setBoards] = useState<Dashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    const id = Number(userId);
    Promise.all([api.listOrganizationMembers(active.id), api.listMemberBoards(active.id, id)])
      .then(([members, list]) => {
        setMember(members.find((m) => m.user_id === id) ?? null);
        setBoards(list);
      })
      .catch((e) => setError((e as Error).message));
  }, [active, userId]);

  useEffect(() => {
    document.title = `${member?.username ?? "Member"} · DevNotePad`;
  }, [member]);

  if (error) return <main className="app-main"><p className="state-msg">{error}</p></main>;
  if (!boards) return <main className="app-main"><p className="state-msg">Loading…</p></main>;

  return (
    <main className="app-main">
      <header className="page-head">
        <div className="org-page-title">
          <span className="org-page-badge">{(member?.username ?? "?").slice(0, 2).toUpperCase()}</span>
          <div>
            <h1 className="page-title">{member?.username ?? "Member"}</h1>
            <p className="page-sub">
              {member ? `${member.role === "admin" ? "Admin" : "Member"} of ${active?.name}. ` : ""}
              Boards they’ve shared with you, view only.
            </p>
          </div>
        </div>
      </header>

      {boards.length === 0 ? (
        <p className="empty-hint">Nothing shared with you yet.</p>
      ) : (
        <div className="dashboard-grid">
          {boards.map((d) => (
            <Link
              key={d.id}
              to={`/dashboards/${d.id}`}
              className="dashboard-tile"
              style={{ ["--tile-accent" as string]: d.accent_color ?? undefined }}
            >
              <div className="tile-cover">
                {d.background_url && <div className="tile-cover-img" style={{ backgroundImage: `url(${d.background_url})` }} />}
                <span className="tile-badge">View only</span>
              </div>
              <div className="tile-body">
                <h3>{d.name}</h3>
                <div className="tile-repo">
                  <IconRepo />
                  {d.repo_owner}/{d.repo_name}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
