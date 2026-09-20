"""Command-line administration, for scripting and for setting things up
before anyone can sign in.

    docker exec devnotepad-backend python -m app.cli org list
    docker exec devnotepad-backend python -m app.cli org create --name "Acme" --admin alice
    docker exec devnotepad-backend python -m app.cli admin promote alice
    docker exec devnotepad-backend python -m app.cli sso list --org main
    docker exec devnotepad-backend python -m app.cli sso set --org main --type google \\
        --client-id ID --client-secret-file /run/secret --enable
    docker exec -i devnotepad-backend python -m app.cli sso import --org main < providers.json
    docker exec devnotepad-backend python -m app.cli sso remove --org main --type apple

Secrets are read from files or stdin, never from arguments, so they don't
land in shell history or process listings.
"""

import argparse
import json
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import Session, select

from .auth import seed_first_user
from .db import engine, init_db
from .models import Membership, Organization, SsoProvider, User
from .orgs import add_member, available_slug, ensure_main_has_admin, get_main, membership, migrate_to_organizations
from .routers.sso_admin import SsoProviderUpdate, save_provider
from .sso import PROVIDER_TYPES


def _org(session: Session, slug: str) -> Organization:
    organization = get_main(session) if slug == "main" else session.exec(select(Organization).where(Organization.slug == slug)).first()
    if organization is None:
        sys.exit(f"No organization with slug {slug!r}.")
    return organization


def _user(session: Session, username: str) -> User:
    user = session.exec(select(User).where(User.username == username.strip().lower())).first()
    if user is None:
        sys.exit(f"No account named {username!r}.")
    return user


def org_list(session: Session, args) -> None:
    for o in session.exec(select(Organization).order_by(Organization.is_main.desc(), Organization.name)).all():
        members = session.exec(select(Membership).where(Membership.organization_id == o.id, Membership.removed_at == None)).all()  # noqa: E711
        print(f"{o.slug:24} {o.name:30} members={len(members)}{'  (main)' if o.is_main else ''}")


def org_create(session: Session, args) -> None:
    admin = _user(session, args.admin)
    organization = Organization(name=args.name.strip(), slug=available_slug(session, args.name), created_by=admin.id)
    session.add(organization)
    session.commit()
    session.refresh(organization)
    add_member(session, organization, admin, role="admin")
    print(f"Created {organization.name!r} (slug {organization.slug}) with {admin.username} as admin.")


def admin_role(session: Session, args, role: str) -> None:
    """Instance admins are the main organisation's admins."""
    user = _user(session, args.username)
    main = get_main(session)
    row = membership(session, main.id, user.id)
    if row is None:
        row = add_member(session, main, user, role=role)
    if role == "member" and row.role == "admin":
        admins = session.exec(
            select(Membership).where(Membership.organization_id == main.id, Membership.role == "admin", Membership.removed_at == None)  # noqa: E711
        ).all()
        if len(admins) <= 1:
            sys.exit("That's the last instance admin; promote someone else first.")
    row.role = role
    session.add(row)
    session.commit()
    print(f"{user.username} is now {'an instance admin' if role == 'admin' else 'a regular member of main'}.")


def sso_list(session: Session, args) -> None:
    organization = _org(session, args.org)
    rows = session.exec(select(SsoProvider).where(SsoProvider.organization_id == organization.id)).all()
    if not rows:
        print(f"{organization.name}: no providers saved" + (" (the .env fallback applies)" if organization.is_main else ""))
    for r in rows:
        extra = f" tenant={r.tenant}" if r.tenant else ""
        extra += f" team={r.team_id} key={r.key_id}" if r.type == "apple" else ""
        print(f"{r.type:10} enabled={r.enabled} client_id={r.client_id} secret={'set' if r.client_secret else 'missing'}{extra}"
              f" auto_join={r.auto_join_domains or '-'}")


def _read_secret(path: str) -> str:
    return (sys.stdin.read() if path == "-" else Path(path).read_text()).strip()


def sso_set(session: Session, args) -> None:
    organization = _org(session, args.org)
    existing = session.exec(
        select(SsoProvider).where(SsoProvider.organization_id == organization.id, SsoProvider.type == args.type)
    ).first()
    payload = SsoProviderUpdate(
        enabled=args.enable if args.enable is not None else bool(existing and existing.enabled),
        client_id=args.client_id if args.client_id is not None else (existing.client_id if existing else ""),
        client_secret=_read_secret(args.client_secret_file) if args.client_secret_file else None,
        tenant=args.tenant if args.tenant is not None else (existing.tenant if existing else None),
        team_id=args.team_id if args.team_id is not None else (existing.team_id if existing else None),
        key_id=args.key_id if args.key_id is not None else (existing.key_id if existing else None),
        auto_join_domains=(args.auto_join_domains.split(",") if args.auto_join_domains is not None
                           else ((existing.auto_join_domains or "").split(",") if existing else [])),
    )
    _save(session, organization, args.type, payload)


def sso_import(session: Session, args) -> None:
    """A JSON list on stdin: [{"type", "client_id", "client_secret", "tenant",
    "team_id", "key_id", "enabled", "auto_join_domains"}]. Prints no secrets."""
    organization = _org(session, args.org)
    for item in json.load(sys.stdin):
        payload = SsoProviderUpdate(
            enabled=item.get("enabled", True),
            client_id=item.get("client_id", ""),
            client_secret=item.get("client_secret"),
            tenant=item.get("tenant"),
            team_id=item.get("team_id"),
            key_id=item.get("key_id"),
            auto_join_domains=item.get("auto_join_domains", []),
        )
        _save(session, organization, item["type"], payload)


def _save(session: Session, organization: Organization, provider_type: str, payload: SsoProviderUpdate) -> None:
    try:
        row = save_provider(session, organization, provider_type, payload)
    except HTTPException as exc:
        sys.exit(f"{provider_type}: {exc.detail}")
    print(f"{organization.name}: {row.type} saved (enabled={row.enabled}, client_id={row.client_id}, secret={'set' if row.client_secret else 'missing'}).")


def sso_remove(session: Session, args) -> None:
    organization = _org(session, args.org)
    row = session.exec(
        select(SsoProvider).where(SsoProvider.organization_id == organization.id, SsoProvider.type == args.type)
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
    print(f"{organization.name}: {args.type} removed.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="DevNotePad administration")
    groups = parser.add_subparsers(dest="group", required=True)

    org = groups.add_parser("org").add_subparsers(dest="action", required=True)
    org.add_parser("list").set_defaults(run=org_list)
    create = org.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--admin", required=True, help="username of its first admin")
    create.set_defaults(run=org_create)

    admin = groups.add_parser("admin", help="instance admins (the main organisation's admins)").add_subparsers(dest="action", required=True)
    promote = admin.add_parser("promote")
    promote.add_argument("username")
    promote.set_defaults(run=lambda s, a: admin_role(s, a, "admin"))
    demote = admin.add_parser("demote")
    demote.add_argument("username")
    demote.set_defaults(run=lambda s, a: admin_role(s, a, "member"))

    sso = groups.add_parser("sso").add_subparsers(dest="action", required=True)
    listing = sso.add_parser("list")
    listing.add_argument("--org", default="main")
    listing.set_defaults(run=sso_list)
    setter = sso.add_parser("set")
    setter.add_argument("--org", default="main")
    setter.add_argument("--type", required=True, choices=PROVIDER_TYPES)
    setter.add_argument("--client-id")
    setter.add_argument("--client-secret-file", help="file holding the secret (for Apple, the .p8 key); '-' for stdin")
    setter.add_argument("--tenant", help="Microsoft: common, organizations, consumers, or a tenant id")
    setter.add_argument("--team-id", help="Apple")
    setter.add_argument("--key-id", help="Apple")
    setter.add_argument("--auto-join-domains", help="comma-separated")
    toggle = setter.add_mutually_exclusive_group()
    toggle.add_argument("--enable", dest="enable", action="store_true", default=None)
    toggle.add_argument("--disable", dest="enable", action="store_false")
    setter.set_defaults(run=sso_set)
    importer = sso.add_parser("import", help="JSON list of providers on stdin")
    importer.add_argument("--org", default="main")
    importer.set_defaults(run=sso_import)
    remove = sso.add_parser("remove")
    remove.add_argument("--org", default="main")
    remove.add_argument("--type", required=True, choices=PROVIDER_TYPES)
    remove.set_defaults(run=sso_remove)

    args = parser.parse_args(argv)
    init_db()
    with Session(engine) as session:
        seed_first_user(session)
        migrate_to_organizations(session)
        ensure_main_has_admin(session)
        args.run(session, args)


if __name__ == "__main__":
    main()
