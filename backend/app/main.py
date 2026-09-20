from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import claim_unowned_rows, require_user, seed_first_user, session_secret
from .orgs import migrate_to_organizations
from .config import settings
from .db import engine, init_db
from .routers import (
    admin,
    auth,
    sso,
    sso_admin,
    dashboards,
    insights,
    invitations,
    join_requests,
    notes,
    notifications,
    orgs,
    settings as settings_router,
    sticky,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        seed_first_user(session)
        claim_unowned_rows(session)
        migrate_to_organizations(session)
    yield


app = FastAPI(title="DevNotePad", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="devnotepad_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    # Set SESSION_HTTPS_ONLY=true wherever the app is actually served over
    # HTTPS; left off by default so http://localhost still keeps a session.
    https_only=settings.session_https_only,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    # The session rides in a cookie, so the browser has to be allowed to
    # send it on cross-origin calls.
    allow_credentials=True,
)

app.include_router(auth.router)
app.include_router(sso.router)

# Everything below holds board data or drives GitHub with a stored token,
# so all of it sits behind a session.
_authenticated = [Depends(require_user)]
app.include_router(dashboards.router, dependencies=_authenticated)
app.include_router(notes.router, dependencies=_authenticated)
app.include_router(settings_router.router, dependencies=_authenticated)
app.include_router(insights.router, dependencies=_authenticated)
app.include_router(sticky.router, dependencies=_authenticated)
app.include_router(orgs.router, dependencies=_authenticated)
app.include_router(invitations.manage, dependencies=_authenticated)
app.include_router(join_requests.router, dependencies=_authenticated)
app.include_router(notifications.router, dependencies=_authenticated)
app.include_router(sso_admin.router, dependencies=_authenticated)
app.include_router(admin.router, dependencies=_authenticated)
# Previewing an invitation comes before signing in; accepting one checks the
# session itself.
app.include_router(invitations.public)


@app.get("/api/health")
def health():
    return {"status": "ok"}
