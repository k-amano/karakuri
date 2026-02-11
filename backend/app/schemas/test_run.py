"""Test run schemas."""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TestRunBase(BaseModel):
    """Base test run schema."""

    test_command: str


class TestRunCreate(TestRunBase):
    """Test run creation schema."""

    pass


class TestRunResponse(TestRunBase):
    """Test run response schema."""

    id: int
    task_id: int
    exit_code: Optional[int]
    passed: bool
    output: Optional[str]
    error_output: Optional[str]
    summary: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
