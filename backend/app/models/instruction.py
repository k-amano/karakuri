"""Instruction model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class InstructionStatus(str, enum.Enum):
    """Instruction status enum."""

    PENDING = "pending"  # Created, waiting to execute
    RUNNING = "running"  # Executing
    COMPLETED = "completed"  # Completed
    FAILED = "failed"  # Failed


class Instruction(Base):
    """Instruction model - commands sent to Claude Code."""

    __tablename__ = "instructions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)

    content = Column(Text, nullable=False)
    status = Column(Enum(InstructionStatus), default=InstructionStatus.PENDING, nullable=False)

    # Execution results
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    task = relationship("Task", back_populates="instructions")
