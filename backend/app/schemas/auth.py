"""Authentication schemas."""
from pydantic import BaseModel


class DevLoginResponse(BaseModel):
    """Development login response."""

    token: str
    message: str
