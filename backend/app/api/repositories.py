"""Repository management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryResponse, RepositoryUpdate
from app.api.auth import verify_token

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


async def get_or_create_default_user(db: AsyncSession) -> User:
    """Get or create the default user (MVP: single user)."""
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            username="default",
            email="default@karakuri.local",
            full_name="Default User",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


@router.get("", response_model=List[RepositoryResponse])
async def list_repositories(
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """List all repositories."""
    result = await db.execute(select(Repository))
    repositories = result.scalars().all()
    return repositories


@router.post("", response_model=RepositoryResponse, status_code=201)
async def create_repository(
    repository_data: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Create a new repository."""
    # Get or create default user
    user = await get_or_create_default_user(db)

    # Create repository
    repository = Repository(
        **repository_data.model_dump(),
        owner_id=user.id,
    )
    db.add(repository)
    await db.commit()
    await db.refresh(repository)

    return repository


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Get a repository by ID."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    return repository


@router.patch("/{repository_id}", response_model=RepositoryResponse)
async def update_repository(
    repository_id: int,
    repository_data: RepositoryUpdate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Update a repository."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Update fields
    update_data = repository_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(repository, field, value)

    await db.commit()
    await db.refresh(repository)

    return repository


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_token),
):
    """Delete a repository."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repository = result.scalar_one_or_none()

    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    await db.delete(repository)
    await db.commit()

    return None
