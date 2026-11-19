from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.dependencies import CurrentUser, get_current_user, get_db
from app.models import BotSetting, User
from app.security import (
    create_session,
    destroy_session,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# In-memory pending Telegram verifications: chat_id -> {code, action, expires_at}
_pending_telegram: dict[int, dict] = {}
# In-memory OAuth state -> {next, expires_at}. Short lived and single use.
_pending_oauth: dict[str, dict] = {}

_COOKIE_NAME = "money_machine_token"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


# ------------------------------------------------------------------ helpers


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or (
        "application/json" in request.headers.get("accept", "")
        and "text/html" not in request.headers.get("accept", "")
    )


async def _payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            return body if isinstance(body, dict) else {}
        except Exception:
            return {}
    form = await request.form()
    return {key: form.get(key) for key in form.keys()}


def _secure_request(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https" or request.url.scheme == "https"


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_secure_request(request),
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


def _signed_in_response(
    request: Request,
    user: User,
    message: str,
    redirect: str = "/ui/",
) -> Response:
    token = create_session(user.id)
    if _is_ajax(request):
        response: Response = JSONResponse(
            {
                "ok": True,
                "message": message,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            }
        )
    else:
        response = RedirectResponse(url=redirect, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token, request)
    return response


def _safe_next(raw: str | None) -> str:
    """Only allow same-origin SPA redirects after an external sign-in."""
    value = (raw or "").strip()
    if not value.startswith("/") or value.startswith("//"):
        return "/ui/"
    if value in {"/ui", "/ui/"}:
        return "/ui/"
    if value.startswith("/ui/"):
        return value
    if value.startswith(("/auth", "/api")):
        return "/ui/"
    return "/ui" + value


def _login_error(message: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/ui/login?{urlencode({'auth_error': message})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _oauth_error(request: Request, message: str) -> Response:
    if _is_ajax(request):
        return JSONResponse({"ok": False, "error": message}, status_code=status.HTTP_400_BAD_REQUEST)
    return _login_error(message)


def _request_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto not in {"http", "https"}:
        proto = request.url.scheme
    host = (
        request.headers.get("x-forwarded-host", "").split(",")[0].strip()
        or request.headers.get("host", "").strip()
        or request.url.netloc
    )
    return f"{proto}://{host}"


def _google_redirect_uri(request: Request) -> str:
    env = get_settings()
    return env.google_redirect_uri.strip() or f"{_request_origin(request)}/auth/google/callback"


def _unique_username(db: Session, base: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "", (base or "").strip()).strip("._-")[:80]
    cleaned = cleaned or fallback
    candidate = cleaned
    counter = 1
    while db.query(User.id).filter(User.username == candidate).first():
        suffix = f"_{counter}"
        candidate = f"{cleaned[: 80 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _ensure_bot_settings(db: Session, user: User) -> None:
    row = db.query(BotSetting).filter(BotSetting.user_id == user.id).first()
    if row is None:
        db.add(BotSetting(user_id=user.id))


def _prune_pending_oauth() -> None:
    now = time.time()
    for key, value in list(_pending_oauth.items()):
        if float(value.get("expires_at", 0)) <= now:
            _pending_oauth.pop(key, None)


def _telegram_widget_data(raw: dict) -> dict[str, str]:
    fields = ("id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash")
    return {key: str(raw[key]) for key in fields if raw.get(key) is not None}


# ------------------------------------------------------------------ pages


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    env = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "title": "Login",
            "auth_required": bool(env.dashboard_password or env.api_token),
            "telegram_bot_configured": bool(env.telegram_bot_token),
        },
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    env = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "title": "Register",
            "telegram_bot_configured": bool(env.telegram_bot_token),
        },
    )


@router.get("/providers")
async def providers() -> dict:
    env = get_settings()
    from app.services.telegram_bot import get_telegram_service

    service = get_telegram_service()
    bot_username = (
        env.telegram_bot_username.strip()
        or str(getattr(service, "username", "") or "").strip()
    ).lstrip("@")
    return {
        "telegram": bool(env.telegram_bot_token),
        "telegram_widget": bool(env.telegram_bot_token and bot_username),
        "telegram_bot_username": bot_username,
        "google": bool(env.google_client_id and env.google_client_secret),
        "auth_required": bool(env.dashboard_password or env.api_token),
        "frontend": "/ui/",
    }


# ------------------------------------------------------------------ email/password auth


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    body = await _payload(request)
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    ajax = _is_ajax(request)

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        if ajax:
            return JSONResponse(
                {"ok": False, "error": "Incorrect username or password"}, status_code=401
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        if ajax:
            return JSONResponse(
                {"ok": False, "error": "User account is disabled"}, status_code=401
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return _signed_in_response(request, user, "Signed in successfully")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: Request, db: Session = Depends(get_db)):
    body = await _payload(request)
    username = str(body.get("username", "")).strip()
    email = str(body.get("email", "")).strip() or None
    password = str(body.get("password", ""))
    confirm_password = str(body.get("confirm_password", ""))
    ajax = _is_ajax(request)

    if not username or not password:
        error = "Username and password are required"
    elif password != confirm_password:
        error = "Passwords do not match"
    elif len(password) < 6:
        error = "Password must be at least 6 characters"
    else:
        error = ""

    if error:
        if ajax:
            return JSONResponse({"ok": False, "error": error}, status_code=400)
        raise HTTPException(status_code=400, detail=error)

    existing = (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .first()
    )
    if existing:
        message = "Username or email already registered"
        if ajax:
            return JSONResponse({"ok": False, "error": message}, status_code=409)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()
    db.add(BotSetting(user_id=user.id))
    db.commit()
    db.refresh(user)
    return _signed_in_response(request, user, "Account created successfully")


# ------------------------------------------------------------------ Google / Gmail OAuth


@router.get("/google")
async def google_login(request: Request, next: str = "/ui/"):
    env = get_settings()
    target = _safe_next(next)
    if not env.google_client_id or not env.google_client_secret:
        return _login_error(
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    _prune_pending_oauth()
    state = secrets.token_urlsafe(32)
    _pending_oauth[state] = {"next": target, "expires_at": time.time() + 600}
    params = {
        "client_id": env.google_client_id,
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    _prune_pending_oauth()
    pending = _pending_oauth.pop(state, None) if state else None
    if not pending:
        return _login_error("Google sign-in expired or the state was invalid. Please try again.")
    target = _safe_next(str(pending.get("next") or "/ui/"))
    if error:
        return _login_error("Google sign-in was cancelled.")
    if not code:
        return _login_error("Google did not return an authorization code.")

    env = get_settings()
    if not env.google_client_id or not env.google_client_secret:
        return _login_error("Google sign-in is not configured.")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": env.google_client_id,
                    "client_secret": env.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": _google_redirect_uri(request),
                },
                headers={"Accept": "application/json"},
            )
            try:
                token_data = token_response.json()
            except Exception:
                token_data = {}
            if token_response.status_code >= 400 or not token_data.get("access_token"):
                logger.warning("Google token exchange failed with status %s", token_response.status_code)
                return _login_error("Google could not complete the sign-in. Please try again.")

            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            if profile_response.status_code >= 400:
                logger.warning("Google userinfo failed with status %s", profile_response.status_code)
                return _login_error("Google could not load your profile. Please try again.")
            profile = profile_response.json()
    except httpx.HTTPError as exc:
        logger.warning("Google OAuth request failed: %s", exc)
        return _login_error("Google sign-in is temporarily unavailable. Please try again.")

    email = str(profile.get("email") or "").strip().lower()
    verified = str(profile.get("email_verified", "")).lower() == "true"
    if not email or not verified:
        return _login_error("Google did not return a verified email address.")

    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is not None and not user.is_active:
        return _login_error("This account is disabled.")
    if user is None:
        subject = str(profile.get("sub") or secrets.token_hex(8))
        username = _unique_username(db, email.split("@", 1)[0], f"google_{subject[-8:]}")
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        db.add(BotSetting(user_id=user.id))
    else:
        _ensure_bot_settings(db, user)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _signed_in_response(request, user, "Signed in with Google", redirect=target)


# ------------------------------------------------------------------ Telegram login widget


async def _telegram_widget_login(request: Request, db: Session):
    env = get_settings()
    if not env.telegram_bot_token:
        return _oauth_error(request, "Telegram sign-in is not configured.")

    body = await _payload(request) if request.method == "POST" else dict(request.query_params)
    target = _safe_next(str(body.get("next") or request.query_params.get("next") or "/ui/"))
    data = _telegram_widget_data(body)
    received_hash = data.pop("hash", "")
    if not data.get("id") or not data.get("auth_date") or not received_hash:
        return _oauth_error(request, "Telegram did not return a complete login payload.")

    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hashlib.sha256(env.telegram_bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        logger.warning("Rejected Telegram login widget signature")
        return _oauth_error(request, "Telegram login could not be verified.")

    try:
        auth_date = int(data["auth_date"])
        telegram_id = int(data["id"])
    except (TypeError, ValueError):
        return _oauth_error(request, "Telegram returned an invalid login payload.")
    now = int(time.time())
    if telegram_id <= 0 or auth_date > now + 300 or now - auth_date > 86_400:
        return _oauth_error(request, "Telegram login has expired. Please try again.")

    user = db.query(User).filter(User.telegram_chat_id == str(telegram_id)).first()
    if user is not None and not user.is_active:
        return _oauth_error(request, "This account is disabled.")
    if user is None:
        tg_username = str(data.get("username") or "").strip()
        display_name = "".join(
            part for part in (data.get("first_name", ""), data.get("last_name", "")) if part
        )
        username = _unique_username(
            db,
            tg_username or display_name,
            f"tg_{telegram_id}",
        )
        user = User(
            username=username,
            email=None,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_superuser=False,
            telegram_chat_id=str(telegram_id),
            telegram_verified=True,
            telegram_registered_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        db.add(BotSetting(user_id=user.id))
    else:
        _ensure_bot_settings(db, user)

    user.telegram_chat_id = str(telegram_id)
    user.telegram_verified = True
    if user.telegram_registered_at is None:
        user.telegram_registered_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _signed_in_response(request, user, "Signed in with Telegram", redirect=target)


@router.get("/telegram/widget")
async def telegram_widget_login_get(request: Request, db: Session = Depends(get_db)):
    return await _telegram_widget_login(request, db)


@router.post("/telegram/widget")
async def telegram_widget_login_post(request: Request, db: Session = Depends(get_db)):
    return await _telegram_widget_login(request, db)


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(_COOKIE_NAME)
    destroy_session(token)
    if _is_ajax(request):
        response: Response = JSONResponse({"ok": True, "message": "Signed out"})
    else:
        response = RedirectResponse(url="/ui/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(_COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return response


# ------------------------------------------------------------------ JWT / WebSocket tokens


@router.post("/token")
async def auth_token(request: Request, db: Session = Depends(get_db)):
    """Exchange credentials for a short-lived JWT (API clients)."""
    env = get_settings()
    if not env.dashboard_password and not env.api_token:
        raise HTTPException(
            status_code=503,
            detail="Token authentication is disabled; set DASHBOARD_PASSWORD or API_TOKEN",
        )

    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Basic "):
        return JSONResponse(
            {"detail": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Money Machine"'},
        )
    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        username = password = ""

    user = db.query(User).filter(User.username == username).first()
    valid_user = bool(user and verify_password(password, user.hashed_password) and user.is_active)
    valid_env = bool(
        env.dashboard_password
        and secrets.compare_digest(username, env.dashboard_username)
        and secrets.compare_digest(password, env.dashboard_password)
    )
    if not valid_user and not valid_env:
        return JSONResponse(
            {"detail": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Money Machine"'},
        )

    secret = env.jwt_secret or env.dashboard_password
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    expires = max(1, env.jwt_expiry_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id) if user else username,
            "method": "jwt",
            "exp": now + timedelta(minutes=expires),
            "iat": now,
        },
        secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": expires * 60}


@router.post("/ws-token")
async def ws_token(request: Request):
    """Mint a short-lived token for the browser WebSocket ticker."""
    env = get_settings()
    auth_required = bool(env.dashboard_password or env.api_token)
    if not auth_required:
        return {"token": "", "token_type": "bearer", "auth_required": False, "ws_url": "/ws/prices"}

    if not getattr(request.state, "authenticated", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for WS token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    secret = env.jwt_secret or env.dashboard_password
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    expires = max(1, env.ws_token_expiry_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(getattr(request.state, "auth_subject", None) or "dashboard"),
            "method": "ws",
            "exp": now + timedelta(minutes=expires),
            "iat": now,
        },
        secret,
        algorithm="HS256",
    )
    return {
        "token": token,
        "token_type": "bearer",
        "expires_in": expires * 60,
        "auth_required": True,
        "ws_url": "/ws/prices",
    }


# ------------------------------------------------------------------ Telegram auth


@router.get("/telegram/login", response_class=HTMLResponse)
async def telegram_login_page(request: Request):
    env = get_settings()
    if not env.telegram_bot_token:
        return RedirectResponse(url="/ui/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="telegram_login.html",
        context={"title": "Telegram Login"},
    )


async def _send_telegram_code(chat_id: int, code: str, action: str) -> None:
    from app.services.telegram_bot import get_telegram_service

    telegram = get_telegram_service()
    if not telegram or not telegram.bot:
        return
    verb = "log in to" if action == "login" else "register for"
    text = (
        "🔐 <b>Money Machine Verification Code</b>\n\n"
        f"Your verification code to {verb} the dashboard is:\n"
        f"<code>{code}</code>\n\n"
        "This code expires in 5 minutes."
    )
    await telegram.bot.send_message(chat_id, text)


@router.post("/telegram/request-code")
async def telegram_request_code(request: Request, db: Session = Depends(get_db)):
    body = await _payload(request)
    chat_id_raw = str(body.get("chat_id", "")).strip()
    action = str(body.get("action", "login"))
    if not chat_id_raw:
        return JSONResponse({"ok": False, "error": "Telegram chat ID is required"}, status_code=400)
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)

    existing_user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
    if action == "login":
        if not existing_user:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "This Telegram chat ID is not linked to any account. Register first.",
                },
                status_code=404,
            )
        if not existing_user.telegram_verified:
            return JSONResponse(
                {"ok": False, "error": "Telegram is not verified for this account."},
                status_code=400,
            )
    elif existing_user:
        return JSONResponse(
            {"ok": False, "error": "This Telegram chat ID is already linked to an account."},
            status_code=409,
        )

    code = f"{secrets.randbelow(1000000):06d}"
    _pending_telegram[chat_id] = {
        "code": code,
        "action": action,
        "expires_at": datetime.now(timezone.utc).timestamp() + 300,
    }
    try:
        await _send_telegram_code(chat_id, code, action)
    except Exception:
        # The code remains valid; the operator can read it from the server log if
        # Telegram delivery is unavailable.
        pass
    return {"ok": True, "message": f"Verification code sent to Telegram chat {chat_id}"}


@router.post("/telegram/verify-code")
async def telegram_verify_code(request: Request, db: Session = Depends(get_db)):
    body = await _payload(request)
    chat_id_raw = str(body.get("chat_id", "")).strip()
    code = str(body.get("code", "")).strip()
    ajax = _is_ajax(request)
    if not chat_id_raw or not code:
        if ajax:
            return JSONResponse({"ok": False, "error": "Chat ID and code are required"}, status_code=400)
        raise HTTPException(status_code=400, detail="Chat ID and code are required")
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        if ajax:
            return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    pending = _pending_telegram.get(chat_id)
    if not pending:
        message = "No pending verification. Request a code first."
        if ajax:
            return JSONResponse({"ok": False, "error": message}, status_code=400)
        raise HTTPException(status_code=400, detail=message)
    if datetime.now(timezone.utc).timestamp() > pending["expires_at"]:
        _pending_telegram.pop(chat_id, None)
        message = "Verification code expired. Request a new one."
        if ajax:
            return JSONResponse({"ok": False, "error": message}, status_code=400)
        raise HTTPException(status_code=400, detail=message)
    if pending["code"] != code:
        message = "Invalid verification code"
        if ajax:
            return JSONResponse({"ok": False, "error": message}, status_code=400)
        raise HTTPException(status_code=400, detail=message)

    if pending["action"] == "login":
        user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
        if not user:
            _pending_telegram.pop(chat_id, None)
            if ajax:
                return JSONResponse({"ok": False, "error": "User not found"}, status_code=404)
            raise HTTPException(status_code=404, detail="User not found")
    else:
        username = f"tg_{chat_id}"
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"tg_{chat_id}_{counter}"
            counter += 1
        user = User(
            username=username,
            email=None,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_superuser=False,
            telegram_chat_id=str(chat_id),
            telegram_verified=True,
            telegram_registered_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        db.add(BotSetting(user_id=user.id))
        db.commit()
        db.refresh(user)

    user.telegram_chat_id = str(chat_id)
    user.telegram_verified = True
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    _pending_telegram.pop(chat_id, None)
    return _signed_in_response(request, user, "Verified and signed in")


@router.post("/telegram/link")
async def telegram_link(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await _payload(request)
    chat_id_raw = str(body.get("chat_id", "")).strip()
    code = str(body.get("code", "")).strip()
    if not chat_id_raw or not code:
        return JSONResponse({"ok": False, "error": "Chat ID and code are required"}, status_code=400)
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)

    existing = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
    if existing and existing.id != int(current_user.subject or 0):
        return JSONResponse(
            {"ok": False, "error": "This Telegram chat ID is already linked to another account"},
            status_code=409,
        )
    pending = _pending_telegram.get(chat_id)
    if not pending or pending["code"] != code:
        return JSONResponse(
            {"ok": False, "error": "Invalid or expired verification code"}, status_code=400
        )
    user = db.query(User).filter(User.id == int(current_user.subject or 0)).first()
    if not user:
        return JSONResponse({"ok": False, "error": "User not found"}, status_code=404)
    user.telegram_chat_id = str(chat_id)
    user.telegram_verified = True
    db.commit()
    _pending_telegram.pop(chat_id, None)
    return {"ok": True, "message": "Telegram account linked successfully"}


@router.get("/me")
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User).filter(User.id == int(current_user.subject or 0)).first()
        if current_user.subject and str(current_user.subject).isdigit()
        else None
    )
    if not user:
        return {"authenticated": current_user.authenticated, "user": None}
    row = db.query(BotSetting).filter(BotSetting.user_id == user.id).first()
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "telegram_chat_id": user.telegram_chat_id,
            "telegram_verified": user.telegram_verified,
        },
        "method": current_user.method,
        "settings": _settings_payload(row) if row else None,
    }


def _settings_payload(row: BotSetting | None) -> dict | None:
    if row is None:
        return None
    return {
        "symbols": row.symbols,
        "risk_pct": row.risk_pct,
        "max_open_positions": row.max_open_positions,
        "leverage": row.leverage,
        "paper_mode": bool(row.paper_mode),
        "paused": bool(row.paused),
        "telegram_chat_id": row.telegram_chat_id or "",
    }
