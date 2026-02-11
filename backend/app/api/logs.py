"""Task log endpoints."""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
import asyncio

from app.database import get_db
from app.models.task import Task
from app.models.task_log import TaskLog
from app.websocket.manager import get_connection_manager
from app.api.auth import verify_token

router = APIRouter(tags=["logs"])


# WebSocket endpoint for real-time logs
@router.websocket("/api/v1/ws/tasks/{task_id}/logs")
async def websocket_task_logs(websocket: WebSocket, task_id: int):
    """
    WebSocket endpoint for real-time task logs.

    Clients connect to this endpoint to receive live log updates for a task.
    """
    manager = get_connection_manager()

    await manager.connect(websocket, task_id)

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Connected to task {task_id} logs",
        })

        # Keep connection alive and handle incoming messages
        while True:
            # Receive messages (ping/pong for keepalive)
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                # Echo ping messages
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, task_id)


# WebSocket endpoint for task status updates
@router.websocket("/api/v1/ws/tasks/{task_id}/status")
async def websocket_task_status(websocket: WebSocket, task_id: int):
    """
    WebSocket endpoint for real-time task status updates.

    Clients connect to this endpoint to receive task status changes.
    """
    manager = get_connection_manager()

    # For now, use the same connection pool as logs
    # In production, you might want separate pools
    await manager.connect(websocket, task_id)

    try:
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, task_id)


# HTTP endpoint to get historical logs
@router.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Get task logs (historical)."""
    # Verify task exists
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get logs
    result = await db.execute(
        select(TaskLog)
        .where(TaskLog.task_id == task_id)
        .order_by(TaskLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()

    # Reverse to get chronological order
    logs = list(reversed(logs))

    return [
        {
            "id": log.id,
            "level": log.level,
            "source": log.source,
            "message": log.message,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
