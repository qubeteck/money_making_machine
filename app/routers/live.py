from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.config import BASE_DIR, get_settings
from app.security import authenticate_bearer, create_access_token
from app.services.tickers import ticker_snapshot
from app.real_time_hub import get_real_time_hub

router = APIRouter(tags=["live"])
logger = logging.getLogger(__name__)


@router.get("/live", response_class=HTMLResponse)
async def live_prices_page(request: Request) -> str:
    """Serve the WebSocket ticker demo.

    The page is behind the normal auth middleware, so it can embed a
    short-lived JWT for the browser's WebSocket connection.
    """
    html = (BASE_DIR / "app" / "static" / "live" / "index.html").read_text(encoding="utf-8")
    env = get_settings()
    token = ""
    if env.dashboard_password or env.api_token:
        secret = env.jwt_secret or env.dashboard_password
        if secret:
            subject = (
                getattr(request.state, "auth_subject", None)
                or env.dashboard_username
                or "dashboard"
            )
            token = create_access_token(subject, secret, max(1, env.ws_token_expiry_minutes))
    return html.replace("__EMBEDDED_WS_TOKEN__", token)


@router.websocket("/ws/prices")
async def price_stream(websocket: WebSocket) -> None:
    """Stream the latest scan prices as JSON messages over a WebSocket.

    This enhanced version uses the RealTimeHub infrastructure for better
    connection management, automatic reconnection, and event distribution.

    Browsers cannot set an Authorization header on WebSocket handshakes, so the
    token is accepted from ``?token=`` (short-lived JWT or API_TOKEN). When no
    dashboard password or API token is configured the feed is open, matching
    the rest of the local-development behaviour.
    """
    env = get_settings()
    client_id = f"ws_{id(websocket)}_{int(time.time())}"

    # Mirror the HTTP CSRF origin check for browser WebSocket clients.
    origin = websocket.headers.get("origin")
    if origin:
        origin_host = (urlsplit(origin).hostname or "").lower()
        request_host = (
            urlsplit(f"//{websocket.headers.get('host', '')}").hostname or ""
        ).lower()
        if not origin_host or origin_host != request_host:
            logger.warning("WebSocket origin check failed for client: %s", client_id)
            await websocket.close(code=1008)
            return

    # Authentication check
    if env.dashboard_password or env.api_token:
        token = websocket.query_params.get("token", "").strip()
        if not token:
            authorization = websocket.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                token = authorization[7:].strip()
        if authenticate_bearer(token, env) is None:
            logger.warning("WebSocket authentication failed for client: %s", client_id)
            await websocket.close(code=1008)
            return

    try:
        # Get the real-time hub
        hub = await get_real_time_hub()

        # Subscribe to market data events
        await hub.subscribe_to_events(client_id, ["ticker", "market_update"])

        # Register WebSocket connection with hub
        if await hub.register_websocket(websocket, client_id):
            logger.info("WebSocket connection established: %s", client_id)

            # Send initial connection acknowledgment
            await websocket.send_json({
                "type": "connection_established",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "client_id": client_id,
                "hub_version": "2.0.0"
            })

            # Wait for connection to close
            await websocket.receive()
        else:
            logger.warning("Failed to register WebSocket connection: %s", client_id)

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected: %s", client_id)
    except Exception as exc:
        logger.error("WebSocket connection error for client %s: %s", client_id, exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        # Unregister connection from hub
        await hub.unregister_websocket(client_id)
        logger.info("WebSocket cleaned up: %s", client_id)
