"""Shared FastAPI dependencies.

The middleware already authenticates every HTTP request before it reaches a
route. These helpers expose that identity and a managed SQLAlchemy session to
route handlers through ``Depends`` instead of ad-hoc globals.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from app.db import SessionLocal


@dataclass(frozen=True)
class CurrentUser:
    authenticated: bool
    method: str
    subject: str | None = None
    claims: dict[str, str | None, ...] | None = None


def get_db():
    """Yield a session, committing on success and rolling back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(request: Request) -> CurrentUser:
    """Return the identity resolved by the global auth middleware."""
    return CurrentUser(
        authenticated=bool(getattr(request.state, "authenticated", False)),
        method=getattr(request.state, "auth_method", "none"),
        subject=getattr(request.state, "auth_subject", None),
        claims=getattr(request.state, "auth_claims", None),
    )


def get_user_settings(db: Session, user_id: int | None):
    """Return the BotSetting row for *user_id*, or the global (single) row when
    ``user_id`` is ``None``.  This lets a SaaS deployment have one settings row
    per authenticated user while keeping the existing single‑row behaviour for
    local/development use."""
    from app.models import BotSetting

    if user_id is not None:
        row = db.query(BotSetting).filter(BotSetting.user_id == user_id).one_or_none()
        if row is not None:
            return row
        # create a new row tied to this user
        new_row = BotSetting(user_id=user_id)
        db.add(new_row)
        db.flush()
        return new_row
    # global (single) row
    row = db.query(BotSetting).filter(BotSetting.user_id == None).one_or_none()
    if row is not None:
        return row
    new_row = BotSetting(user_id=None)
    db.add(new_row)
    db.flush()
    return new_row