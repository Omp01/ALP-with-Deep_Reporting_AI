"""
Pydantic schemas for Authentication, Tokens, and User Profiles.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials for authentication."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password")
    org_slug: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    """Payload to refresh an access token."""
    refresh_token: str


class TenantInfo(BaseModel):
    """Basic organization tenant metadata."""
    id: UUID
    name: str
    slug: str
    is_active: bool

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    """Full user profile with role and tenant information."""
    id: UUID
    org_id: UUID
    email: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    organization: Optional[TenantInfo] = None
    teams: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Authentication response with tokens and profile."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfileResponse
