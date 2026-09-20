from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] == repo root (DevNotePad/)
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    git_token: Optional[str] = None
    git_org_url: Optional[str] = None
    # Fernet key that encrypts stored GitHub tokens. Required: without it
    # the app would silently keep them in plaintext.
    secret_key: Optional[str] = None
    # The initial account, created on first startup into an empty user
    # table. Changing these later doesn't touch an existing account.
    admin_username: Optional[str] = None
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    # Lets anyone who can reach the sign-in page create an account, which
    # joins only the main organisation. Set false to close sign-up.
    allow_registration: bool = True

    # ---- Single sign-on. Configure providers per organisation in the app
    # (or with `python -m app.cli sso`). The values below are only a fallback
    # for the main organisation while it has none saved. ----
    # Where people reach the app, e.g. https://devnotepad.example.com. SSO
    # returns people here after signing in, and builds its callback URLs
    # from it -- never from the incoming request, which behind a proxy or
    # load balancer can carry the wrong scheme or port.
    public_url: Optional[str] = None
    # Only when the API is on a different origin from the app (the plain
    # local Docker setup); defaults to public_url.
    public_api_url: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None
    # "common" (any work, school or personal account), "organizations",
    # "consumers", or one tenant's id to admit only that organisation.
    microsoft_tenant: str = "common"
    # Sign in with Apple: the Services ID, your Team ID, and the Key ID and
    # contents of the .p8 key made for it.
    apple_client_id: Optional[str] = None
    apple_team_id: Optional[str] = None
    apple_key_id: Optional[str] = None
    apple_private_key: Optional[str] = None
    # Marks the session cookie Secure. Turn on wherever the app is served
    # over HTTPS; off by default so plain http://localhost works.
    session_https_only: bool = False
    database_path: str = str(DATA_DIR / "devnotepad.db")
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
