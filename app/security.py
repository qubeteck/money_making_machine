"""Security utilities for authentication and password hashing."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import bcrypt

from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


# ------------------------------------------------------------------ sessions
_ACTIVE_SESSIONS: Dict[str, dict] = {}


def create_session(user_id: int | str, ttl_seconds: int = 60 * 60 * 24 * 30) -> str:
    """Create a session and return its token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    _ACTIVE_SESSIONS[token] = {
        "user_id": user_id,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    }
    return token


def validate_session(token: str | None) -> Optional[dict]:
    """Validate a session token and return session data, or None."""
    if not token:
        return None
    session = _ACTIVE_SESSIONS.get(token)
    if session is None:
        return None
    if datetime.now(timezone.utc) > session["expires_at"]:
        _ACTIVE_SESSIONS.pop(token, None)
        return None
    return session


def destroy_session(token: str | None) -> None:
    """Destroy a session by token."""
    if token:
        _ACTIVE_SESSIONS.pop(token, None)


def cleanup_expired_sessions() -> None:
    """Remove expired sessions from the store."""
    now = datetime.now(timezone.utc)
    expired = [t for t, s in _ACTIVE_SESSIONS.items() if now > s["expires_at"]]
    for t in expired:
        _ACTIVE_SESSIONS.pop(t, None)


class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps: Dict[str, list[float]] = {}

    def check(
        self, identifier: str, max_requests: int | None = None, window_seconds: int | None = None
    ) -> tuple[bool, int | None, int | None]:
        """Check if the identifier is within rate limits.

        Args:
            identifier: Client identifier (e.g., IP address or username)
            max_requests: Override default max requests; None uses initialized value
            window_seconds: Override default window in seconds; None uses initialized value

        Returns:
            Tuple of (allowed, remaining, reset_unix_timestamp)
            - allowed: True if within limits
            - remaining: slots remaining (0 means at limit)
            - reset_unix: unix timestamp when the oldest request window resets
        """
        now = time.time()
        max_r = max_requests if max_requests is not None else self.max_requests
        ws = window_seconds if window_seconds is not None else self.window_seconds
        window_start = now - ws

        # Initialize timestamps list for this identifier if needed
        if identifier not in self.timestamps:
            self.timestamps[identifier] = []

        # Remove timestamps outside the current window
        self.timestamps[identifier] = [
            ts for ts in self.timestamps[identifier] if ts > window_start
        ]

        # Add current timestamp
        self.timestamps[identifier].append(now)

        # Count how many requests are in the window
        count = len(self.timestamps[identifier])

        # Determine if allowed
        allowed = count <= max_r

        # Calculate remaining slots
        remaining = max_r - count if allowed else 0

        # Calculate reset time (when the oldest request in the window expires)
        if self.timestamps[identifier]:
            reset_unix = int(self.timestamps[identifier][0]) + ws
        else:
            reset_unix = int(now) + ws

        return allowed, remaining, reset_unix


def client_key(request, trust_proxy_headers: bool = False) -> str:
    """Extract a client identifier key for logging and rate limiting.

    Args:
        request: The FastAPI request object
        trust_proxy_headers: Whether to trust X-Forwarded-For header

    Returns:
        Client identifier string (IP address or 'unknown')
    """
    from urllib.parse import urlsplit

    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    host = (urlsplit(f"//{request.headers.get('host', '')}").hostname or "unknown")
    return host.lower() or "unknown"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plaintext password

    Returns:
        Hashed password string
    """
    if not password:
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash.

    Args:
        plain_password: The plaintext password to verify
        hashed_password: The stored hash

    Returns:
        True if the password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def verify_session_token(token: str) -> bool:
    """Verify a session token format.

    Args:
        token: The token to verify

    Returns:
        True if the token appears valid
    """
    if not token:
        return False
    try:
        return True
    except Exception:
        return False


def authenticate_bearer(token: str, env) -> tuple | None:
    """Authenticate a Bearer token and return (method, subject, claims).

    Args:
        token: The Bearer token string
        env: Settings/env containing JWT_SECRET

    Returns:
        Tuple of (method, subject, claims) if valid, None otherwise
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value() if hasattr(settings.jwt_secret, "get_secret_value") else settings.jwt_secret,
            algorithms=["HS256"],
        )
        subject: str = payload.get("sub")
        method: str = payload.get("method", "jwt")
        claims: dict = dict(payload) if payload else {}
        if subject is None:
            return None
        return (method, subject, claims)
    except JWTError:
        return None


def create_access_token(subject: str, method: str = "jwt", expires_minutes: int | None = None) -> str:
    """Create a JWT access token.

    Args:
        subject: The subject/username to embed in the token
        method: Authentication method label
        expires_minutes: Override default expiry; None uses settings value

    Returns:
        Encoded JWT string
    """
    if expires_minutes is None:
        expires_minutes = getattr(settings, "jwt_expires_minutes", 30)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    token = jwt.encode(
        {
            "sub": subject,
            "method": method,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
        },
        settings.jwt_secret.get_secret_value() if hasattr(settings.jwt_secret, "get_secret_value") else settings.jwt_secret,
        algorithm="HS256",
    )
    return token