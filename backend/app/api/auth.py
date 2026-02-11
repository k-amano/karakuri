"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from app.config import get_settings
from app.schemas.auth import DevLoginResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


async def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify authentication token (MVP: simple token check)."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]
    if token != settings.dev_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


@router.get("/dev-login", response_model=DevLoginResponse)
async def dev_login():
    """Development login endpoint (MVP only)."""
    return DevLoginResponse(
        token=settings.dev_auth_token,
        message="Development token (MVP only - not secure)",
    )
