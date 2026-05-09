"""Repository schemas."""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class RepositoryBase(BaseModel):
    """Base repository schema."""

    name: str
    url: str
    default_branch: str = "main"
    description: Optional[str] = None


class RepositoryCreate(RepositoryBase):
    """Repository creation schema."""

    pass


class GitHubRepoCreate(BaseModel):
    """Request to create a GitHub repository and register it."""
    name: str
    description: Optional[str] = None
    private: bool = False


class RepositoryUpdate(BaseModel):
    """Repository update schema."""

    name: Optional[str] = None
    url: Optional[str] = None
    default_branch: Optional[str] = None
    description: Optional[str] = None


class RepositoryResponse(RepositoryBase):
    """Repository response schema."""

    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
