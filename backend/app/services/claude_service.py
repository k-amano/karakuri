"""Claude Code execution service."""
from typing import AsyncGenerator
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task import Task, TaskStatus
from app.models.instruction import Instruction, InstructionStatus
from app.models.task_log import TaskLog, LogLevel, LogSource
from app.services.docker_service import get_docker_service


class ClaudeCodeService:
    """Service for executing Claude Code in containers."""

    def __init__(self):
        """Initialize service."""
        self.docker_service = get_docker_service()

    async def execute_instruction(
        self,
        db: AsyncSession,
        task_id: int,
        instruction_content: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute Claude Code instruction and stream output.

        Args:
            db: Database session
            task_id: Task ID
            instruction_content: Instruction content

        Yields:
            Log lines from execution
        """
        # Get task
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError("Task not found")

        if not task.container_id:
            raise ValueError("Task has no container")

        if task.status not in [TaskStatus.IDLE, TaskStatus.RUNNING]:
            raise ValueError(f"Task is not ready (status: {task.status})")

        # Create instruction record
        instruction = Instruction(
            task_id=task_id,
            content=instruction_content,
            status=InstructionStatus.PENDING,
        )
        db.add(instruction)
        await db.commit()
        await db.refresh(instruction)

        try:
            # Update statuses
            task.status = TaskStatus.RUNNING
            instruction.status = InstructionStatus.RUNNING
            instruction.started_at = datetime.utcnow()
            await db.commit()

            # Log start
            yield f"[SYSTEM] Starting instruction execution...\n"
            yield f"[INSTRUCTION] {instruction_content}\n"
            yield f"[SYSTEM] Container: {task.container_name}\n"
            yield "\n"

            # For MVP, simulate Claude Code execution with a simple script
            # In production, replace with actual Claude Code CLI execution
            command = '''python3 -c "
import sys
import time

print('[Claude Code Simulation]')
print('Received instruction: ''' + instruction_content.replace('"', '\\"').replace("'", "\\'") + '''')
print()
print('Processing...')
time.sleep(1)
print('Analyzing codebase...')
time.sleep(1)
print('Generating changes...')
time.sleep(1)
print()
print('[Result]')
print('Changes generated successfully.')
print('Files modified: README')
print()
print('[Next Steps]')
print('Run tests to verify changes.')
"'''

            # Execute command with streaming
            output_buffer = []
            async for chunk in self.docker_service.execute_command_stream(
                task.container_id,
                command,
                workdir="/workspace/repo",
            ):
                # Yield chunk to client
                yield chunk

                # Store in buffer for database
                output_buffer.append(chunk)

                # Log to database periodically (every 100 chunks)
                if len(output_buffer) >= 100:
                    log_message = "".join(output_buffer)
                    log = TaskLog(
                        task_id=task_id,
                        level=LogLevel.INFO,
                        source=LogSource.CLAUDE,
                        message=log_message,
                        instruction_id=instruction.id,
                    )
                    db.add(log)
                    await db.commit()
                    output_buffer = []

            # Save remaining buffer
            if output_buffer:
                log_message = "".join(output_buffer)
                log = TaskLog(
                    task_id=task_id,
                    level=LogLevel.INFO,
                    source=LogSource.CLAUDE,
                    message=log_message,
                    instruction_id=instruction.id,
                )
                db.add(log)
                await db.commit()

            # Update instruction status
            instruction.status = InstructionStatus.COMPLETED
            instruction.completed_at = datetime.utcnow()
            instruction.output = "".join(output_buffer) if output_buffer else "Completed"
            instruction.exit_code = 0

            # Update task status back to idle
            task.status = TaskStatus.IDLE
            await db.commit()

            yield "\n[SYSTEM] Instruction completed successfully.\n"

        except Exception as e:
            # Handle errors
            error_msg = str(e)

            # Update instruction status
            instruction.status = InstructionStatus.FAILED
            instruction.completed_at = datetime.utcnow()
            instruction.error_message = error_msg
            instruction.exit_code = 1

            # Update task status
            task.status = TaskStatus.IDLE  # Allow retry
            await db.commit()

            # Log error
            log = TaskLog(
                task_id=task_id,
                level=LogLevel.ERROR,
                source=LogSource.CLAUDE,
                message=f"Instruction failed: {error_msg}",
                instruction_id=instruction.id,
            )
            db.add(log)
            await db.commit()

            yield f"\n[ERROR] {error_msg}\n"


# Singleton instance
from typing import Optional as Opt
_claude_service: Opt[ClaudeCodeService] = None


def get_claude_service() -> ClaudeCodeService:
    """Get or create Claude Code service instance."""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeCodeService()
    return _claude_service
