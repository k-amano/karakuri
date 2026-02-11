"""WebSocket connection manager."""
from typing import Dict, List
from fastapi import WebSocket
import asyncio
import json


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: int):
        """
        Connect a WebSocket client for a specific task.

        Args:
            websocket: WebSocket connection
            task_id: Task ID
        """
        await websocket.accept()

        if task_id not in self.active_connections:
            self.active_connections[task_id] = []

        self.active_connections[task_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: int):
        """
        Disconnect a WebSocket client.

        Args:
            websocket: WebSocket connection
            task_id: Task ID
        """
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)

            # Clean up empty lists
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_to_task(self, task_id: int, message: str):
        """
        Broadcast a message to all connections for a specific task.

        Args:
            task_id: Task ID
            message: Message to broadcast
        """
        if task_id not in self.active_connections:
            return

        # Remove disconnected clients
        disconnected = []

        for connection in self.active_connections[task_id]:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection, task_id)

    async def broadcast_json_to_task(self, task_id: int, data: dict):
        """
        Broadcast JSON data to all connections for a specific task.

        Args:
            task_id: Task ID
            data: Data to broadcast as JSON
        """
        message = json.dumps(data)
        await self.broadcast_to_task(task_id, message)

    def get_connection_count(self, task_id: int) -> int:
        """
        Get the number of active connections for a task.

        Args:
            task_id: Task ID

        Returns:
            Number of active connections
        """
        if task_id not in self.active_connections:
            return 0
        return len(self.active_connections[task_id])


# Global connection manager instance
connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return connection_manager
