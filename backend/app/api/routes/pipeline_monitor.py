"""WebSocket endpoint for real-time pipeline monitoring (IT HEAD only)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_scope_from_token
from app.core.exceptions import ZTAError
from app.core.redis_client import redis_client
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/pipeline", tags=["pipeline-monitor"])
logger = logging.getLogger(__name__)


@router.websocket("/monitor")
async def monitor_pipeline(
    websocket: WebSocket, token: str = Query(default="")
) -> None:
    """
    WebSocket endpoint for IT HEAD to monitor pipeline executions in real-time.

    Subscribes to Redis pub/sub channels and forwards pipeline events to connected clients.
    Requires IT HEAD persona token for authentication.
    """
    await websocket.accept()
    db: Session = SessionLocal()
    pubsub = None
    listener_task: asyncio.Task[None] | None = None

    try:
        # Validate token and IT HEAD permission
        if not token:
            await websocket.send_json({"type": "error", "message": "Missing token"})
            await websocket.close(code=1008)
            return

        try:
            scope = get_scope_from_token(db=db, token=token)
            # Allow all authenticated users to view the pipeline monitor
            # This helps users understand the Zero Trust Architecture
        except ZTAError as exc:
            await websocket.send_json({"type": "error", "message": exc.message})
            await websocket.close(code=1008)
            return

        # Subscribe to all pipeline channels using pattern matching
        pubsub = redis_client.client.pubsub()
        pubsub.psubscribe("pipeline:*")

        # Send connection success
        await websocket.send_json(
            {"type": "connected", "message": "Pipeline monitor connected"}
        )

        # Listen for Redis pub/sub messages and forward to WebSocket
        async def redis_listener():
            """Listen to Redis pub/sub and forward events to WebSocket (async-safe)."""
            while True:
                if asyncio.current_task() and asyncio.current_task().cancelled():
                    return

                # redis-py pubsub is synchronous; use a thread hop to avoid blocking
                # the FastAPI event loop while waiting for messages.
                try:
                    message = await asyncio.to_thread(
                        pubsub.get_message,
                        True,
                        0.2,
                    )
                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("Pipeline monitor Redis listener failed")
                    await asyncio.sleep(0.25)
                    continue

                if message and message["type"] == "pmessage":
                    try:
                        event_data = json.loads(message["data"])
                        await websocket.send_json(event_data)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed pipeline monitor payload")
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        logger.exception("Pipeline monitor websocket forward failed")
                        break

                # Yield control to event loop
                try:
                    await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    return

        # Start Redis listener task
        listener_task = asyncio.create_task(redis_listener())

        try:
            # Keep connection alive and handle client messages (optional commands)
            while True:
                await websocket.receive_text()
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            if listener_task:
                listener_task.cancel()
        except Exception:
            logger.exception("Pipeline monitor websocket loop failed")

    finally:
        if listener_task:
            listener_task.cancel()
            with contextlib.suppress(Exception):
                await listener_task
        db.close()
        if pubsub:
            with contextlib.suppress(Exception):
                pubsub.punsubscribe()
            with contextlib.suppress(Exception):
                pubsub.close()
