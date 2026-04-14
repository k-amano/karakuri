"""Test run schemas."""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.test_run import TestType


class TestRunBase(BaseModel):
    """Base test run schema."""

    test_command: Optional[str] = None


class TestRunCreate(TestRunBase):
    """Test run creation schema."""

    pass


class TestRunResponse(TestRunBase):
    """Test run response schema."""

    id: int
    task_id: int
    test_type: TestType
    test_cases: Optional[str]
    exit_code: Optional[int]
    passed: bool
    retry_count: int
    output: Optional[str]
    error_output: Optional[str]
    summary: Optional[str]
    report_path: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
