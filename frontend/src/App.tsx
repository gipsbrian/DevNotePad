import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { ThemeToggle } from "./components/ThemeToggle";
import { SettingsModal } from "./components/SettingsModal";
import { api } from "./api/client";
import type { Organization, Settings } from "./types/api";
import { OrgContext } from "./org-context";
import { OrgSwitcher } from "./components/OrgSwitcher";
import { NotificationBell } from "./components/NotificationBell";
import { IconBoard, IconHelp, IconPlus, IconShield, IconSignOut, IconUser } from "./components/Icons";
import { useAuth } from "./auth-context";
import { useStartTour } from "./tour/useTour";

export default function App() {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const onList = pathname === "/";
  const onNew = pathname === "/new";
  const startTour = useStartTour();

  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const reloadOrganizations = useCallback(async () => {
    try {
      setOrganizations(await api.listOrganizations());
    } catch {
      // Leaves the last known list; a 401 already sends the app to sign-in.
    }
  }, []);
  const switchOrganization = useCallback(
    async (id: string) => {
      await api.switchOrganization(id);
      await reloadOrganizations();
    },
    [reloadOrganizations]
  );
  useEffect(() => {
    reloadOrganizations();
  }, [reloadOrganizations]);
  const activeOrganization = organizations.find((o) => o.is_active) ?? null;

  const [settings, setSettings] = useState<Settings | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(() => {
    api.getSettings().then(setSettings).catch(() => setSettings(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Nudge on first run: without a username there are no "…me" columns,
  // and without any token nothing can load at all.
  const needsSetup = settings !== null && (!settings.github_username || !settings.has_default_token);

  return (
    <OrgContext.Provider
      value={{ organizations, active: activeOrganization, reload: reloadOrganizations, switchTo: switchOrganization }}
    >
    <div className="app-shell">
      <nav className="rail">
        <Link to="/" className="rail-logo" title="DevNotePad">
          D
        </Link>
        <OrgSwitcher />
        <div className="rail-nav">
          <Link to="/" className={`rail-btn${onList ? " active" : ""}`} title="Boards" aria-label="Boards">
            <IconBoard />
          </Link>
          <Link to="/new" className={`rail-btn${onNew ? " active" : ""}`} title="New board" aria-label="New board">
            <IconPlus />
          </Link>
          {user.is_instance_admin && (
            <Link
              to="/admin"
              className={`rail-btn${pathname === "/admin" ? " active" : ""}`}
              title="Instance admin"
              aria-label="Instance admin"
            >
              <IconShield />
            </Link>
          )}
        </div>
        <NotificationBell />
        <button
          className="rail-btn"
          data-tour="settings"
          onClick={() => setShowSettings(true)}
          title={settings?.github_username ? `Settings — ${settings.github_username}` : "Settings"}
          aria-label="Settings"
        >
          <IconUser />
          {needsSetup && <span className="rail-dot" aria-hidden />}
        </button>
        <button
          className="rail-btn"
          data-tour="help"
          // The board page has its own tour; everywhere else gets the
          // general one.
          onClick={() => startTour(pathname.startsWith("/dashboards/") ? "board" : "home")}
          title="Show me around"
          aria-label="Show me around"
        >
          <IconHelp />
        </button>
        <ThemeToggle />
        <button
          className="rail-btn"
          onClick={signOut}
          title={`Sign out — ${user.username}`}
          aria-label="Sign out"
        >
          <IconSignOut />
        </button>
      </nav>

      <Outlet context={{ settings, reloadSettings: load }} />

      {showSettings && settings && (
        <SettingsModal
          settings={settings}
          onSaved={(s) => {
            setSettings(s);
            // Boards derive their automatic columns from these, so make
            // the change visible immediately.
            window.dispatchEvent(new CustomEvent("devnotepad:settings-changed"));
          }}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
    </OrgContext.Provider>
  );
}
