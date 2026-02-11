"""Test run model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class TestRun(Base):
    """Test run model."""

    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)

    # Test execution info
    test_command = Column(String(512), nullable=False)
    exit_code = Column(Integer, nullable=True)
    passed = Column(Boolean, default=False, nullable=False)

    # Results
    output = Column(Text, nullable=True)
    error_output = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)  # e.g., "10 passed, 2 failed"

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    task = relationship("Task", back_populates="test_runs")
