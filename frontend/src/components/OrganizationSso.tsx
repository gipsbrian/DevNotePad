import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Organization, OrganizationSso, SsoProviderSettings } from "../types/api";
import { copyText } from "../utils/clipboard";
import { IconCopy } from "./Icons";

/** An organisation's identity providers, for its admins. Secrets are
 * write-only: the page says whether one is saved, never what it is. */
export function OrganizationSsoSettings({ organization }: { organization: Organization }) {
  const [sso, setSso] = useState<OrganizationSso | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.getOrganizationSso(organization.id).then(setSso).catch((e) => setError((e as Error).message));
  }, [organization.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(null), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy(text: string, what: string) {
    setCopied((await copyText(text)) ? what : "Couldn’t copy");
  }

  return (
    <section className="org-section">
      <h2>Single sign-on</h2>
      <p className="empty-hint">
        {organization.is_main
          ? "Providers offered on the main sign-in page."
          : "Providers offered on this organisation’s sign-in link. Members land here; anyone else signing in is sent to Main and a join request comes to you."}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {sso && !sso.public_url_set && (
        <p className="form-error" role="alert">
          Set PUBLIC_URL in the instance’s .env before single sign-on can work: callback addresses are built from it.
        </p>
      )}
      {sso?.login_url && (
        <div className="org-share">
          <span>Sign-in link</span>
          <code>{sso.login_url}</code>
          <button className="btn small" onClick={() => copy(sso.login_url!, "Sign-in link copied")}>
            <IconCopy /> Copy
          </button>
        </div>
      )}
      {copied && <p className="org-saved">{copied}</p>}

      <ul className="sso-providers">
        {sso?.providers.map((p) => (
          <li key={p.type}>
            <button className="sso-provider-head" onClick={() => setOpen(open === p.type ? null : p.type)} aria-expanded={open === p.type}>
              <strong>{p.label}</strong>
              <span className={`sso-state ${p.ready ? "on" : p.configured ? "off" : "none"}`}>
                {p.ready ? "On" : p.configured ? (p.enabled ? "Incomplete" : "Off") : "Not set up"}
              </span>
            </button>
            {open === p.type && (
              <ProviderForm
                organization={organization}
                provider={p}
                onCopy={copy}
                onSaved={(next) => {
                  setSso(next);
                  setOpen(null);
                }}
                onRemoved={() => {
                  setOpen(null);
                  load();
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProviderForm({
  organization,
  provider: p,
  onCopy,
  onSaved,
  onRemoved,
}: {
  organization: Organization;
  provider: SsoProviderSettings;
  onCopy: (text: string, what: string) => void;
  onSaved: (sso: OrganizationSso) => void;
  onRemoved: () => void;
}) {
  const [enabled, setEnabled] = useState(p.configured ? p.enabled : true);
  const [clientId, setClientId] = useState(p.client_id);
  const [secret, setSecret] = useState("");
  const [tenant, setTenant] = useState(p.tenant ?? "common");
  const [teamId, setTeamId] = useState(p.team_id ?? "");
  const [keyId, setKeyId] = useState(p.key_id ?? "");
  const [domains, setDomains] = useState(p.auto_join_domains.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isApple = p.type === "apple";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await api.saveOrganizationSso(organization.id, p.type, {
          enabled,
          client_id: clientId,
          client_secret: secret ? secret : undefined,
          tenant: p.type === "microsoft" ? tenant : null,
          team_id: isApple ? teamId : null,
          key_id: isApple ? keyId : null,
          auto_join_domains: domains.split(",").map((d) => d.trim()).filter(Boolean),
        })
      );
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form className="sso-provider-form" onSubmit={save}>
      {p.callback_url && (
        <div className="org-share">
          <span>{isApple ? "Return URL" : "Redirect URI"} to register with {p.label}</span>
          <code>{p.callback_url}</code>
          <button type="button" className="btn small" onClick={() => onCopy(p.callback_url!, "Callback URL copied")}>
            <IconCopy /> Copy
          </button>
        </div>
      )}

      <label className="org-default">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span>Offer {p.label} sign-in</span>
      </label>

      <div className="sso-grid">
        <div className="form-row">
          <label htmlFor={`${p.type}-client`}>{isApple ? "Services ID" : "Client ID"}</label>
          <input id={`${p.type}-client`} value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" />
        </div>
        {p.type === "microsoft" && (
          <div className="form-row">
            <label htmlFor="ms-tenant">Tenant</label>
            <input id="ms-tenant" value={tenant} onChange={(e) => setTenant(e.target.value)} placeholder="common, organizations, consumers, or a tenant ID" />
          </div>
        )}
        {isApple && (
          <>
            <div className="form-row">
              <label htmlFor="apple-team">Team ID</label>
              <input id="apple-team" value={teamId} onChange={(e) => setTeamId(e.target.value)} autoComplete="off" />
            </div>
            <div className="form-row">
              <label htmlFor="apple-key">Key ID</label>
              <input id="apple-key" value={keyId} onChange={(e) => setKeyId(e.target.value)} autoComplete="off" />
            </div>
          </>
        )}
      </div>

      <div className="form-row">
        <label htmlFor={`${p.type}-secret`}>{isApple ? "Private key (.p8 contents)" : "Client secret"}</label>
        {isApple ? (
          <textarea
            id={`${p.type}-secret`}
            rows={4}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={p.has_secret ? "A key is saved. Paste a new one to replace it." : "-----BEGIN PRIVATE KEY-----"}
            spellCheck={false}
          />
        ) : (
          <input
            id={`${p.type}-secret`}
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={p.has_secret ? "A secret is saved. Type a new one to replace it." : ""}
          />
        )}
      </div>

      <div className="form-row">
        <label htmlFor={`${p.type}-domains`}>Auto-join domains (optional)</label>
        <input
          id={`${p.type}-domains`}
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
          placeholder="example.com, another.example"
        />
        <p className="empty-hint" style={{ marginTop: 6 }}>
          {organization.is_main
            ? "Everyone is in Main already, so this has no effect here."
            : `People whose ${p.label}-verified email is on one of these join ${organization.name} without asking.${p.type === "microsoft" ? " Microsoft doesn’t verify emails, so for Microsoft this never applies." : ""}`}
        </p>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="sso-actions">
        {p.configured && (
          <button
            type="button"
            className="btn ghost danger"
            disabled={busy}
            onClick={async () => {
              if (!confirm(`Remove ${p.label} sign-in settings for ${organization.name}?`)) return;
              setBusy(true);
              try {
                await api.removeOrganizationSso(organization.id, p.type);
                onRemoved();
              } catch (err) {
                setError((err as Error).message);
                setBusy(false);
              }
            }}
          >
            Remove
          </button>
        )}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : `Save ${p.label}`}
        </button>
      </div>
    </form>
  );
}
