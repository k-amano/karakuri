"""Test execution service."""
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re

from app.models.task import Task
from app.models.test_run import TestRun
from app.models.task_log import TaskLog, LogLevel, LogSource
from app.services.docker_service import get_docker_service


class TestService:
    """Service for executing tests in containers."""

    def __init__(self):
        """Initialize service."""
        self.docker_service = get_docker_service()

    async def execute_tests(
        self,
        db: AsyncSession,
        task_id: int,
        test_command: str,
    ) -> TestRun:
        """
        Execute tests in the task's container.

        Args:
            db: Database session
            task_id: Task ID
            test_command: Test command to execute (e.g., "npm test", "pytest")

        Returns:
            TestRun object with results
        """
        # Get task
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError("Task not found")

        if not task.container_id:
            raise ValueError("Task has no container")

        # Create test run record
        test_run = TestRun(
            task_id=task_id,
            test_command=test_command,
        )
        db.add(test_run)
        await db.commit()
        await db.refresh(test_run)

        # Log test start
        await self._log_event(
            db,
            task_id,
            f"Starting test execution: {test_command}",
            test_run_id=test_run.id,
        )

        try:
            # Update start time
            test_run.started_at = datetime.utcnow()
            await db.commit()

            # Execute test command in container
            exit_code, output, error = self.docker_service.execute_command(
                task.container_id,
                test_command,
                workdir="/workspace/repo",
            )

            # Parse test results
            passed = exit_code == 0
            summary = self._parse_test_summary(output, test_command)

            # Update test run with results
            test_run.exit_code = exit_code
            test_run.passed = passed
            test_run.output = output
            test_run.error_output = error
            test_run.summary = summary
            test_run.completed_at = datetime.utcnow()
            await db.commit()

            # Log test completion
            level = LogLevel.INFO if passed else LogLevel.ERROR
            await self._log_event(
                db,
                task_id,
                f"Test {'passed' if passed else 'failed'}: {summary}",
                level=level,
                test_run_id=test_run.id,
            )

            return test_run

        except Exception as e:
            # Update test run with error
            test_run.exit_code = -1
            test_run.passed = False
            test_run.error_output = str(e)
            test_run.completed_at = datetime.utcnow()
            await db.commit()

            # Log error
            await self._log_event(
                db,
                task_id,
                f"Test execution failed: {str(e)}",
                level=LogLevel.ERROR,
                test_run_id=test_run.id,
            )

            raise

    def _parse_test_summary(self, output: str, test_command: str) -> str:
        """
        Parse test output to extract summary.

        Args:
            output: Test output
            test_command: Test command that was run

        Returns:
            Summary string
        """
        if not output:
            return "No output"

        # Try to detect test framework and parse accordingly

        # pytest style: "10 passed, 2 failed"
        pytest_match = re.search(
            r"(\d+)\s+passed(?:,\s+(\d+)\s+failed)?",
            output,
            re.IGNORECASE
        )
        if pytest_match:
            passed = pytest_match.group(1)
            failed = pytest_match.group(2) or "0"
            return f"{passed} passed, {failed} failed"

        # Jest/npm test style: "Tests: 10 passed, 10 total"
        jest_match = re.search(
            r"Tests:\s+(\d+)\s+passed(?:,\s+(\d+)\s+failed)?",
            output,
            re.IGNORECASE
        )
        if jest_match:
            passed = jest_match.group(1)
            failed = jest_match.group(2) or "0"
            return f"{passed} passed, {failed} failed"

        # Go test style: "PASS" or "FAIL"
        if "PASS" in output.upper():
            return "Tests passed"
        if "FAIL" in output.upper():
            # Try to count failures
            fail_count = len(re.findall(r"FAIL:", output))
            return f"Tests failed ({fail_count} failures)" if fail_count > 0 else "Tests failed"

        # Generic: just return exit code status
        return "Tests completed"

    async def _log_event(
        self,
        db: AsyncSession,
        task_id: int,
        message: str,
        level: LogLevel = LogLevel.INFO,
        test_run_id: Optional[int] = None,
    ):
        """Log a test event."""
        log = TaskLog(
            task_id=task_id,
            level=level,
            source=LogSource.TEST,
            message=message,
            test_run_id=test_run_id,
        )
        db.add(log)
        await db.commit()


# Singleton instance
_test_service: Optional[TestService] = None


def get_test_service() -> TestService:
    """Get or create test service instance."""
    global _test_service
    if _test_service is None:
        _test_service = TestService()
    return _test_service
