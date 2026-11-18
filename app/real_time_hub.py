"""Real-time data hub for WebSocket connections and SSE streams.

This module provides a unified infrastructure for real-time data distribution:
- WebSocket connections for browser clients
- SSE stream management for dashboard updates
- Event-driven data distribution
- Connection pooling and health monitoring
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from app.services.tickers import ticker_snapshot
from app.config import get_settings

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    WEBSOCKET = "websocket"
    SSE = "sse"
    BOTH = "both"


class ConnectionStatus(Enum):
    CONNECTING = "connecting"
    ACTIVE = "active"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    CLOSING = "closing"


class RealTimeHub:
    """Central hub for managing real-time data distribution to all connected clients.
    
    This hub provides:
    - WebSocket connection management with automatic reconnection
    - SSE stream distribution with caching
    - Event-driven data distribution
    - Connection health monitoring and recovery
    - Performance metrics and statistics
    """

    def __init__(self):
        # Connection management
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.connection_queues: Dict[str, asyncio.Queue] = {}
        self.connection_tasks: Dict[str, asyncio.Task] = {}

        # Event system
        self.event_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self.event_queue = asyncio.Queue()
        self.event_processor_task: Optional[asyncio.Task] = None

        # Data caching and distribution
        self.data_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = 60  # seconds

        # Performance monitoring
        self.metrics: Dict[str, Dict[str, Any]] = {
            'connections': {'total': 0, 'active': 0, 'disconnected': 0},
            'messages': {'sent': 0, 'failed': 0, 'rate': 0},
            'events': {'processed': 0, 'failed': 0},
            'performance': {'last_check': time.monotonic(), 'health_score': 100.0}
        }

        # Health monitoring
        self.health_checker_task: Optional[asyncio.Task] = None
        self.last_heartbeat = time.monotonic()
        self.heartbeat_interval = 30  # seconds

        # Shutdown control
        self.shutdown_event = asyncio.Event()
        self._start_event = asyncio.Event()

    async def start(self):
        """Start the real-time hub services."""
        logger.info("Starting RealTimeHub...")

        # Start event processor
        self.event_processor_task = asyncio.create_task(self._process_events())

        # Start health checker
        self.health_checker_task = asyncio.create_task(self._health_check_loop())

        self._start_event.set()
        logger.info("RealTimeHub started successfully")

    async def stop(self):
        """Stop the real-time hub gracefully."""
        logger.info("Stopping RealTimeHub...")
        self.shutdown_event.set()

        # Cancel all connection tasks
        for task in self.connection_tasks.values():
            task.cancel()

        # Cancel event processor
        if self.event_processor_task:
            self.event_processor_task.cancel()

        # Cancel health checker
        if self.health_checker_task:
            self.health_checker_task.cancel()

        # Close all connections
        await self._close_all_connections()

        logger.info("RealTimeHub stopped")

    async def register_websocket(self, websocket: WebSocket, client_id: str) -> bool:
        """Register a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            client_id: Unique identifier for the client
            
        Returns:
            True if connection was registered successfully, False otherwise
        """
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.connection_queues[client_id] = asyncio.Queue(maxsize=100)
            self.connection_metadata[client_id] = {
                'type': ConnectionType.WEBSOCKET,
                'registered_at': time.monotonic(),
                'last_heartbeat': time.monotonic(),
                'status': ConnectionStatus.ACTIVE,
                'message_count': 0,
                'error_count': 0,
                'client_info': self._extract_client_info(websocket)
            }

            # Start connection task
            self.connection_tasks[client_id] = asyncio.create_task(
                self._handle_websocket_client(websocket, client_id)
            )

            self.metrics['connections']['total'] += 1
            self.metrics['connections']['active'] += 1

            logger.info("WebSocket registered: %s", client_id)
            return True

        except Exception as exc:
            logger.error("Failed to register WebSocket %s: %s", client_id, exc)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
            return False

    async def unregister_websocket(self, client_id: str):
        """Unregister a WebSocket connection.
        
        Args:
            client_id: Unique identifier for the client
        """
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                await websocket.close(code=1000)
            except Exception:
                pass

        # Clean up connection data
        self.active_connections.pop(client_id, None)
        self.connection_queues.pop(client_id, None)
        self.connection_metadata.pop(client_id, None)

        # Cancel connection task
        if client_id in self.connection_tasks:
            self.connection_tasks[client_id].cancel()
            del self.connection_tasks[client_id]

        self.metrics['connections']['active'] = max(0, self.metrics['connections']['active'] - 1)
        logger.debug("WebSocket unregistered: %s", client_id)

    async def subscribe_to_events(self, client_id: str, event_types: List[str]):
        """Subscribe a client to specific event types.
        
        Args:
            client_id: Unique identifier for the client
            event_types: List of event types to subscribe to
        """
        for event_type in event_types:
            self.event_subscribers[event_type].add(client_id)

        logger.debug("Client %s subscribed to events: %s", client_id, event_types)

    async def publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish an event to all subscribers.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_id': f"{event_type}_{time.time()}"
        }

        try:
            self.event_queue.put_nowait(event)
            logger.debug("Event published: %s", event_type)
        except asyncio.QueueFull:
            logger.warning("Event queue full, dropping event: %s", event_type)

    async def _process_events(self):
        """Process events from the event queue and distribute to subscribers."""
        while not self.shutdown_event.is_set():
            try:
                # Wait for event with timeout
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                # Distribute event to subscribers
                subscribers = self.event_subscribers.get(event['type'], set())
                if subscribers:
                    await self._distribute_event_to_subscribers(event, subscribers)

                self.event_queue.task_done()
                self.metrics['events']['processed'] += 1

            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error("Event processing error: %s", exc)
                self.metrics['events']['failed'] += 1

    async def _distribute_event_to_subscribers(self, event: Dict[str, Any], subscribers: Set[str]):
        """Distribute an event to connected subscribers.
        
        Args:
            event: The event to distribute
            subscribers: Set of client IDs to receive the event
        """
        for client_id in subscribers:
            try:
                if client_id in self.connection_queues:
                    queue = self.connection_queues[client_id]
                    if queue.qsize() < queue.maxsize:
                        await queue.put(event)
                    else:
                        logger.warning("Connection queue full for client: %s", client_id)

            except Exception as exc:
                logger.error("Failed to distribute event to client %s: %s", client_id, exc)
                self.metrics['messages']['failed'] += 1

    async def _handle_websocket_client(self, websocket: WebSocket, client_id: str):
        """Handle a WebSocket client connection.
        
        Args:
            websocket: The WebSocket connection
            client_id: Unique identifier for the client
        """
        metadata = self.connection_metadata.get(client_id, {})

        try:
            interval = max(1, min(30, get_settings().ws_interval_seconds))

            while not self.shutdown_event.is_set():
                try:
                    # Get data from ticker snapshot service
                    snapshot = await asyncio.to_thread(ticker_snapshot)
                    snapshot["type"] = "ticker"
                    snapshot["interval_seconds"] = interval
                    snapshot["client_id"] = client_id
                    snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()

                    # Send to WebSocket client
                    await websocket.send_json(snapshot)

                    # Update metadata
                    metadata['last_heartbeat'] = time.monotonic()
                    metadata['message_count'] = metadata.get('message_count', 0) + 1

                    # Update metrics
                    self.metrics['messages']['sent'] += 1

                    await asyncio.sleep(interval)

                except WebSocketDisconnect:
                    logger.debug("WebSocket disconnected: %s", client_id)
                    break
                except Exception as exc:
                    logger.error("WebSocket error for client %s: %s", client_id, exc)
                    metadata['error_count'] = metadata.get('error_count', 0) + 1
                    await asyncio.sleep(min(5, interval * 2))  # Exponential backoff

        except Exception as exc:
            logger.error("WebSocket handler error for client %s: %s", client_id, exc)
        finally:
            await self.unregister_websocket(client_id)

    async def _health_check_loop(self):
        """Periodically check the health of all connections and services."""
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._perform_health_check()
            except Exception as exc:
                logger.error("Health check error: %s", exc)

    async def _perform_health_check(self):
        """Perform comprehensive health check of all services."""
        now = time.monotonic()
        self.last_heartbeat = now
        health_score = 100.0

        # Check connection health
        dead_connections = []
        for client_id, metadata in self.connection_metadata.items():
            if metadata['status'] == ConnectionStatus.ACTIVE:
                # Check if connection is alive
                if now - metadata['last_heartbeat'] > self.heartbeat_interval * 2:
                    metadata['status'] = ConnectionStatus.DEGRADED
                    health_score -= 5.0

                # Check error rate
                error_count = metadata.get('error_count', 0)
                message_count = metadata.get('message_count', 0)
                if message_count > 0 and (error_count / message_count) > 0.1:
                    metadata['status'] = ConnectionStatus.DEGRADED
                    health_score -= 10.0

                # Mark dead connections for cleanup
                if metadata['status'] == ConnectionStatus.DEGRADED and now - metadata['last_heartbeat'] > 300:
                    dead_connections.append(client_id)

        # Clean up dead connections
        for client_id in dead_connections:
            await self.unregister_websocket(client_id)
            health_score -= 5.0

        # Check data cache health
        cache_age = now - self.cache_timestamps.get('dashboard', now)
        if cache_age > self.cache_ttl * 2:
            health_score -= 10.0

        # Update performance metrics
        self.metrics['performance']['last_check'] = now
        self.metrics['performance']['health_score'] = max(0.0, health_score)

        logger.debug("Health check completed: score=%.2f, active=%d", health_score, self.metrics['connections']['active'])

    async def _close_all_connections(self):
        """Close all WebSocket connections gracefully."""
        for client_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.close(code=1001)
                logger.debug("Closed connection: %s", client_id)
            except Exception as exc:
                logger.error("Error closing connection %s: %s", client_id, exc)

    def _extract_client_info(self, websocket: WebSocket) -> Dict[str, Any]:
        """Extract client information from WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            
        Returns:
            Dictionary with client information
        """
        client_info = {
            'user_agent': websocket.headers.get('user-agent', 'unknown'),
            'host': websocket.headers.get('host', 'unknown'),
            'origin': websocket.headers.get('origin', 'unknown'),
            'connected_at': datetime.now(timezone.utc).isoformat()
        }

        try:
            token = websocket.query_params.get("token", "").strip()
            if not token:
                authorization = websocket.headers.get("authorization", "")
                if authorization.lower().startswith("bearer "):
                    token = authorization[7:].strip()

            # Decode token for client identification
            if token:
                from app.security import authenticate_bearer
                identity = authenticate_bearer(token, get_settings())
                if identity:
                    client_info['authenticated'] = True
                    client_info['auth_method'] = identity[0]
                    client_info['subject'] = identity[1]

        except Exception:
            pass

        return client_info

    async def get_hub_statistics(self) -> Dict[str, Any]:
        """Get current statistics from the real-time hub."""
        active_connections = len(self.active_connections)
        total_messages = self.metrics['messages']['sent']
        failed_messages = self.metrics['messages']['failed']

        return {
            'connections': {
                'total': self.metrics['connections']['total'],
                'active': active_connections,
                'rate': self.metrics['connections']['total'] - active_connections
            },
            'messages': {
                'sent': total_messages,
                'failed': failed_messages,
                'success_rate': ((total_messages - failed_messages) / total_messages * 100) if total_messages > 0 else 0
            },
            'events': {
                'processed': self.metrics['events']['processed'],
                'failed': self.metrics['events']['failed']
            },
            'performance': {
                'health_score': self.metrics['performance']['health_score'],
                'last_check': self.metrics['performance']['last_check']
            },
            'cache_stats': self._get_cache_statistics()
        }

    def _get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {}
        for key, timestamp in self.cache_timestamps.items():
            age = time.monotonic() - timestamp
            stats[key] = {
                'age_seconds': age,
                'ttl': self.cache_ttl,
                'stale': age > self.cache_ttl
            }
        return stats

    async def cache_data(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None):
        """Cache data for distribution.
        
        Args:
            key: Cache key
            data: Data to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        self.data_cache[key] = data
        self.cache_timestamps[key] = time.monotonic()
        if ttl is not None:
            self.cache_ttl = ttl

        logger.debug("Cached data: %s", key)

    async def get_cached_data(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data if available and not expired, None otherwise
        """
        if key not in self.data_cache:
            return None

        timestamp = self.cache_timestamps[key]
        if time.monotonic() - timestamp > self.cache_ttl:
            logger.debug("Cache expired: %s", key)
            return None

        return self.data_cache[key]


# Global real-time hub instance
_real_time_hub: Optional[RealTimeHub] = None
_hub_lock = asyncio.Lock()


async def get_real_time_hub() -> RealTimeHub:
    """Get or create the global real-time hub instance."""
    global _real_time_hub
    async with _hub_lock:
        if _real_time_hub is None:
            _real_time_hub = RealTimeHub()
            await _real_time_hub.start()
        return _real_time_hub


async def publish_market_data(event_type: str, data: Dict[str, Any]):
    """Publish market data event to all subscribers."""
    hub = await get_real_time_hub()
    await hub.publish_event(event_type, data)


async def get_hub_statistics() -> Dict[str, Any]:
    """Get current real-time hub statistics."""
    hub = await get_real_time_hub()
    return await hub.get_hub_statistics()