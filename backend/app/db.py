from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

from .config import settings
from .crypto import GENERATE_HINT, PREFIX, encrypt

db_path = Path(settings.database_path)
db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False},
)

# Columns added to existing tables after the first release. SQLModel's
# create_all() only creates missing *tables*, so an existing database
# would keep the old shape and every query naming these would fail.
# Full migration tooling is overkill here; additive ALTERs are enough.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "column": {"creator": "VARCHAR", "issue_type": "VARCHAR"},
    "dashboard": {
        "accent_color": "VARCHAR",
        "background_url": "VARCHAR",
        "uuid": "VARCHAR",
        "owner_id": "INTEGER",
        "organization_id": "INTEGER",
        "kind": "VARCHAR NOT NULL DEFAULT 'personal'",
        "shared_with_organization": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "organization": {"token": "VARCHAR"},
    "localnote": {"user_id": "INTEGER"},
    "ssologinattempt": {
        "organization_id": "INTEGER",
        "sso_provider_id": "INTEGER",
        "land_organization_id": "INTEGER",
        "notice": "VARCHAR",
    },
    "stickynote": {"user_id": "INTEGER"},
    "appsettings": {"user_id": "INTEGER"},
    # Accounts that exist when this column arrives already know the app, so
    # they start with every tour marked seen; new ones start with none.
    "user": {
        "tours_seen": "VARCHAR NOT NULL DEFAULT 'home,board'",
        "default_organization_id": "INTEGER",
        "last_organization_id": "INTEGER",
    },
}

# Indexes create_all only puts on a freshly created table.
_ADDED_INDEXES = [
    'CREATE INDEX IF NOT EXISTS ix_dashboard_owner_id ON "dashboard" (owner_id)',
    'CREATE INDEX IF NOT EXISTS ix_dashboard_organization_id ON "dashboard" (organization_id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_appsettings_user_id ON "appsettings" (user_id)',
]


def _backfill_dashboard_uuids(connection) -> None:
    """Boards created before the uuid existed have none, and ALTER TABLE
    can't default them to distinct values — each needs its own."""
    rows = connection.execute(
        text('SELECT id FROM "dashboard" WHERE uuid IS NULL OR uuid = \'\'')
    ).all()
    for (row_id,) in rows:
        connection.execute(
            text('UPDATE "dashboard" SET uuid = :value WHERE id = :id'),
            {"value": str(uuid4()), "id": row_id},
        )
    # create_all only puts the unique index on a freshly created table, so
    # a database that predates the column would otherwise go without it.
    connection.execute(
        text('CREATE UNIQUE INDEX IF NOT EXISTS ix_dashboard_uuid ON "dashboard" (uuid)')
    )


def _apply_additive_migrations(connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {
            row[1] for row in connection.execute(text(f"PRAGMA table_info('{table}')"))
        }
        if not existing:
            continue  # table not created yet; create_all handles it
        for name, sql_type in columns.items():
            if name not in existing:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {sql_type}'))
    for statement in _ADDED_INDEXES:
        connection.execute(text(statement))


# Tables and columns holding a GitHub token. Rows written before tokens
# were encrypted are still plaintext; the column type reads those back
# unchanged, and this rewrites them once so nothing is left in the clear.
_TOKEN_COLUMNS: dict[str, str] = {
    "dashboard": "token",
    "appsettings": "default_token",
    "organization": "token",
    "ssoprovider": "client_secret",
}


def _encrypt_stored_tokens(connection) -> None:
    for table, column in _TOKEN_COLUMNS.items():
        rows = connection.execute(
            text(
                f'SELECT id, "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL AND "{column}" NOT LIKE :prefix'
            ),
            {"prefix": f"{PREFIX}%"},
        ).all()
        for row_id, plaintext in rows:
            connection.execute(
                text(f'UPDATE "{table}" SET "{column}" = :value WHERE id = :id'),
                {"value": encrypt(plaintext), "id": row_id},
            )


def init_db() -> None:
    if not settings.secret_key:
        raise RuntimeError(
            "SECRET_KEY must be set — it encrypts the GitHub tokens this app "
            f"stores. {GENERATE_HINT}"
        )
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        _apply_additive_migrations(connection)
        _backfill_dashboard_uuids(connection)
        _encrypt_stored_tokens(connection)


def get_session():
    with Session(engine) as session:
        yield session
