"""Task log model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class LogLevel(str, enum.Enum):
    """Log level enum."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogSource(str, enum.Enum):
    """Log source enum."""

    SYSTEM = "system"  # Karakuri system logs
    DOCKER = "docker"  # Docker container logs
    CLAUDE = "claude"  # Claude Code execution logs
    GIT = "git"  # Git operation logs
    TEST = "test"  # Test execution logs


class TaskLog(Base):
    """Task log model."""

    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)

    level = Column(Enum(LogLevel), default=LogLevel.INFO, nullable=False, index=True)
    source = Column(Enum(LogSource), default=LogSource.SYSTEM, nullable=False, index=True)
    message = Column(Text, nullable=False)

    # Optional metadata
    instruction_id = Column(Integer, ForeignKey("instructions.id"), nullable=True)
    test_run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=True)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    task = relationship("Task", back_populates="logs")
