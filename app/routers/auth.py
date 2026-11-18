from __future__ import annotations

import secrets

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.dependencies import get_db, get_current_user, CurrentUser
from app.models import User, BotSetting
from app.security import (
    create_access_token,
    create_session,
    destroy_session,
    hash_password,
    verify_password,
    generate_session_token,
)
from app.services.telegram_bot import TelegramService, get_telegram_service

router = APIRouter(tags=["auth"])

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# In-memory pending Telegram verifications: chat_id -> {code, username, email, password, expires_at}
_pending_telegram: dict[int, dict] = {}


# ------------------------------------------------------------------ pages


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    env = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "title": "Login",
            "telegram_bot_configured": bool(env.telegram_bot_token),
        },
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page."""
    env = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "title": "Register",
            "telegram_bot_configured": bool(env.telegram_bot_token),
        },
    )


# ------------------------------------------------------------------ email/password auth


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new user account (database-only credentials)."""
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    if is_ajax:
        body = await request.json()
        username = str(body.get("username", "")).strip()
        email = str(body.get("email", "")).strip() or None
        password = str(body.get("password", ""))
        confirm_password = str(body.get("confirm_password", ""))
    else:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        email = str(form.get("email", "")).strip() or None
        password = str(form.get("password", ""))
        confirm_password = str(form.get("confirm_password", ""))

    if not username or not password:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Username and password are required"}, status_code=400)
        raise HTTPException(status_code=400, detail="Username and password are required")
    if password != confirm_password:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Passwords do not match"}, status_code=400)
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(password) < 6:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Password must be at least 6 characters"}, status_code=400)
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()

    if existing_user:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Username or email already registered"}, status_code=409)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Hash the password
    hashed_password = hash_password(password)

    # Create the user
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    db.add(user)
    db.flush()

    # Create default BotSetting for this user
    bot_setting = BotSetting(user_id=user.id)
    db.add(bot_setting)
    db.commit()
    db.refresh(user)
    db.refresh(bot_setting)

    # Auto-login after registration
    token = create_session(user.id)

    if is_ajax:
        return JSONResponse(
            {"ok": True, "message": "Account created successfully", "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            }}
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="money_machine_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate a user with username/password and create a session."""
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    if is_ajax:
        body = await request.json()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))
    else:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))

    # Find user by username
    user = db.query(User).filter(User.username == username).first()

    if not user:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Incorrect username or password"}, status_code=401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(password, user.hashed_password):
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Incorrect username or password"}, status_code=401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "User account is disabled"}, status_code=401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    # Generate session token
    token = create_session(user.id)

    # Set token in cookie
    response.set_cookie(
        key="money_machine_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    if is_ajax:
        return JSONResponse(
            {"ok": True, "message": "Signed in successfully", "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            }}
        )

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(response: Response, request: Request):
    """Logout the current user and clear the auth token cookie."""
    token = request.cookies.get("money_machine_token")
    destroy_session(token)
    response.delete_cookie(
        "money_machine_token",
        httponly=True,
        samesite="lax",
    )
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


# ------------------------------------------------------------------ Telegram auth


@router.get("/telegram/login", response_class=HTMLResponse)
async def telegram_login_page(request: Request):
    """Serve the Telegram login page."""
    env = get_settings()
    if not env.telegram_bot_token:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="telegram_login.html",
        context={"title": "Telegram Login"},
    )


@router.post("/telegram/request-code")
async def telegram_request_code(
    request: Request,
    db: Session = Depends(get_db),
):
    """Request a Telegram verification code for login/register."""
    form = await request.form()
    chat_id_raw = str(form.get("chat_id", "")).strip()
    action = str(form.get("action", "login"))  # "login" or "register"

    if not chat_id_raw:
        return JSONResponse({"ok": False, "error": "Telegram chat ID is required"}, status_code=400)

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)

    # Check if chat ID is already linked to a user
    existing_user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()

    if action == "login":
        if not existing_user:
            return JSONResponse(
                {"ok": False, "error": "This Telegram chat ID is not linked to any account. Please register first."},
                status_code=404,
            )
        if not existing_user.telegram_verified:
            return JSONResponse(
                {"ok": False, "error": "Telegram not verified for this account. Please register/link first."},
                status_code=400,
            )
    else:  # register
        if existing_user:
            return JSONResponse(
                {"ok": False, "error": "This Telegram chat ID is already linked to an account. Please login instead."},
                status_code=409,
            )

    # Generate verification code
    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = datetime.now(timezone.utc).timestamp() + 300  # 5 minutes

    _pending_telegram[chat_id] = {
        "code": code,
        "action": action,
        "expires_at": expires_at,
    }

    # Send code via Telegram bot
    telegram = get_telegram_service()
    if telegram and telegram.bot:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule the send
                asyncio.ensure_future(_send_telegram_code(telegram, chat_id, code, action))
            else:
                loop.run_until_complete(_send_telegram_code(telegram, chat_id, code, action))
        except Exception as exc:
            # Don't fail the request if bot send fails; code is still stored
            pass

    return JSONResponse(
        {"ok": True, "message": f"Verification code sent to Telegram chat {chat_id}"}
    )


async def _send_telegram_code(telegram: TelegramService, chat_id: int, code: str, action: str):
    """Send verification code via Telegram bot."""
    action_text = "log in to" if action == "login" else "register for"
    text = (
        f"🔐 <b>Money Machine Verification Code</b>\n\n"
        f"Your verification code to {action_text} the dashboard is:\n"
        f"<code>{code}</code>\n\n"
        f"This code expires in 5 minutes."
    )
    await telegram.send(text)


@router.post("/telegram/verify-code")
async def telegram_verify_code(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Verify Telegram code and login/register the user."""
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    if is_ajax:
        body = await request.json()
        chat_id_raw = str(body.get("chat_id", "")).strip()
        code = str(body.get("code", "")).strip()
    else:
        form = await request.form()
        chat_id_raw = str(form.get("chat_id", "")).strip()
        code = str(form.get("code", "")).strip()

    if not chat_id_raw or not code:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Chat ID and code are required"}, status_code=400)
        raise HTTPException(status_code=400, detail="Chat ID and code are required")

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    pending = _pending_telegram.get(chat_id)
    if not pending:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "No pending verification. Request a code first."}, status_code=400)
        raise HTTPException(status_code=400, detail="No pending verification. Request a code first.")

    if datetime.now(timezone.utc).timestamp() > pending["expires_at"]:
        _pending_telegram.pop(chat_id, None)
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Verification code expired. Request a new one."}, status_code=400)
        raise HTTPException(status_code=400, detail="Verification code expired. Request a new one.")

    if pending["code"] != code:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Invalid verification code"}, status_code=400)
        raise HTTPException(status_code=400, detail="Invalid verification code")

    action = pending["action"]

    if action == "login":
        user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
        if not user:
            _pending_telegram.pop(chat_id, None)
            if is_ajax:
                return JSONResponse({"ok": False, "error": "User not found"}, status_code=404)
            raise HTTPException(status_code=404, detail="User not found")
    else:
        # Register new user via Telegram
        username = f"tg_{chat_id}"
        # Make sure username is unique
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"tg_{chat_id}_{counter}"
            counter += 1

        user = User(
            username=username,
            email=None,
            hashed_password=hash_password(secrets.token_urlsafe(32)),  # Random password, Telegram-only login
            is_active=True,
            is_superuser=False,
            telegram_chat_id=str(chat_id),
            telegram_verified=True,
            telegram_registered_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()

        bot_setting = BotSetting(user_id=user.id)
        db.add(bot_setting)
        db.commit()
        db.refresh(user)
        db.refresh(bot_setting)

    # Link/verify Telegram
    user.telegram_chat_id = str(chat_id)
    user.telegram_verified = True
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Create session
    token = create_session(user.id)

    if is_ajax:
        _pending_telegram.pop(chat_id, None)
        return JSONResponse({"ok": True, "message": "Verified and signed in"})

    redirect_response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirect_response.set_cookie(
        key="money_machine_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    _pending_telegram.pop(chat_id, None)
    return redirect_response


@router.post("/telegram/link")
async def telegram_link(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link the current user's account to a Telegram chat ID."""
    form = await request.form()
    chat_id_raw = str(form.get("chat_id", "")).strip()
    code = str(form.get("code", "")).strip()

    if not chat_id_raw or not code:
        return JSONResponse({"ok": False, "error": "Chat ID and code are required"}, status_code=400)

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        return JSONResponse({"ok": False, "error": "Invalid chat ID"}, status_code=400)

    # Check if chat ID is already linked to another user
    existing = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
    if existing and existing.id != int(current_user.subject or 0):
        return JSONResponse({"ok": False, "error": "This Telegram chat ID is already linked to another account"}, status_code=409)

    # Verify code
    pending = _pending_telegram.get(chat_id)
    if not pending or pending["code"] != code:
        return JSONResponse({"ok": False, "error": "Invalid or expired verification code"}, status_code=400)

    user = db.query(User).filter(User.id == int(current_user.subject)).first()
    if not user:
        return JSONResponse({"ok": False, "error": "User not found"}, status_code=404)

    user.telegram_chat_id = str(chat_id)
    user.telegram_verified = True
    db.commit()

    _pending_telegram.pop(chat_id, None)
    return JSONResponse({"ok": True, "message": "Telegram account linked successfully"})


# ------------------------------------------------------------------ legacy token (Basic auth for API clients)


@router.post("/token")
async def auth_token(request: Request, db: Session = Depends(get_db)):
    """Legacy Basic auth token endpoint for API clients."""
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Basic "):
        return JSONResponse(
            {"detail": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Money Machine"'},
        )

    try:
        import base64

        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        username = password = ""

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        return JSONResponse(
            {"detail": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Money Machine"'},
        )

    token = create_session(user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/ws-token")
async def ws_token(current_user: CurrentUser | None = Depends(get_current_user)):
    """Get a WebSocket token for price stream access."""
    if current_user and current_user.authenticated:
        token = create_access_token(current_user.subject, "jwt")
        return {"token": token, "auth_required": True, "ws_url": "/ws/prices"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required for WS token",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ------------------------------------------------------------------ me


@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    """Get the current authenticated user's information."""
    db = next(get_db())
    try:
        user = db.query(User).filter(User.id == int(current_user.subject)).first() if current_user.subject else None
        if not user:
            return {"authenticated": False}

        bot_setting = (
            db.query(BotSetting).filter(BotSetting.user_id == user.id).first()
        )

        settings_data = None
        if bot_setting:
            settings_data = {
                "symbols": bot_setting.symbols,
                "risk_pct": bot_setting.risk_pct,
                "max_open_positions": bot_setting.max_open_positions,
                "leverage": bot_setting.leverage,
                "paper_mode": bool(bot_setting.paper_mode),
                "paused": bool(bot_setting.paused),
                "telegram_chat_id": bot_setting.telegram_chat_id or "",
            }

        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "telegram_chat_id": user.telegram_chat_id,
                "telegram_verified": user.telegram_verified,
            },
            "authenticated": current_user.authenticated,
            "method": current_user.method,
            "settings": settings_data,
        }
    finally:
        db.close()
