"""Test execution endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models.task import Task
from app.models.test_run import TestRun
from app.schemas.test_run import TestRunCreate, TestRunResponse
from app.api.auth import verify_token
from app.services.test_service import get_test_service

router = APIRouter(prefix="/api/v1/tasks/{task_id}/test-runs", tags=["test-runs"])


@router.post("", response_model=TestRunResponse, status_code=201)
async def create_test_run(
    task_id: int,
    test_data: TestRunCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """
    Execute tests for a task.

    This endpoint runs the specified test command in the task's container
    and returns the results.
    """
    # Verify task exists
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get test service
    test_service = get_test_service()

    try:
        # Execute tests
        test_run = await test_service.execute_tests(
            db, task_id, test_data.test_command
        )
        return test_run

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Test execution failed: {str(e)}"
        )


@router.get("", response_model=List[TestRunResponse])
async def list_test_runs(
    task_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """List all test runs for a task."""
    # Verify task exists
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get test runs
    result = await db.execute(
        select(TestRun)
        .where(TestRun.task_id == task_id)
        .order_by(TestRun.created_at.desc())
        .limit(limit)
    )
    test_runs = result.scalars().all()

    return test_runs


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    task_id: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Get a specific test run by ID."""
    result = await db.execute(
        select(TestRun)
        .where(
            TestRun.id == run_id,
            TestRun.task_id == task_id,
        )
    )
    test_run = result.scalar_one_or_none()

    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    return test_run
