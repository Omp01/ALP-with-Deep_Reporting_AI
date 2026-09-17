"""
Authentication endpoints: Login, Refresh, Me, Logout.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.models import User, Organization, UserTeam
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserProfileResponse,
    TenantInfo,
)
from app.api.deps import get_current_user, log_audit_action

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _build_user_profile(user: User) -> UserProfileResponse:
    """Helper to convert a User ORM instance into UserProfileResponse."""
    org_info = None
    if user.organization:
        org_info = TenantInfo(
            id=user.organization.id,
            name=user.organization.name,
            slug=user.organization.slug,
            is_active=user.organization.is_active,
        )

    team_names = []
    if user.team_memberships:
        for tm in user.team_memberships:
            if tm.team:
                team_names.append(tm.team.name)

    return UserProfileResponse(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at,
        organization=org_info,
        teams=team_names,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user with email and password.
    Optionally scopes to an organization slug if provided.
    """
    query = (
        select(User)
        .where(User.email == payload.email)
        .options(
            selectinload(User.organization),
            selectinload(User.team_memberships).selectinload(UserTeam.team),
        )
    )

    if payload.org_slug:
        query = query.join(Organization, User.org_id == Organization.id).where(
            Organization.slug == payload.org_slug
        )

    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if user.organization and not user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization tenant is deactivated",
        )

    # Issue JWT access token
    token_claims = {
        "org_id": str(user.org_id),
        "role": user.role,
        "email": user.email,
    }
    access_token = create_access_token(
        subject=str(user.id),
        claims=token_claims,
        expires_delta=timedelta(minutes=settings.jwt_expiration_minutes),
    )

    # Log login audit event
    client_ip = request.client.host if request.client else None
    await log_audit_action(
        db=db,
        org_id=user.org_id,
        user_id=user.id,
        action="AUTH_LOGIN_SUCCESS",
        resource_type="USER",
        resource_id=str(user.id),
        ip_address=client_ip,
    )

    user_profile = _build_user_profile(user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60,
        user=user_profile,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh an expired access token using a valid token or refresh token.
    """
    token_data = decode_access_token(payload.refresh_token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id_str = token_data.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject missing",
        )

    query = (
        select(User)
        .where(User.id == user_id_str)
        .options(
            selectinload(User.organization),
            selectinload(User.team_memberships).selectinload(UserTeam.team),
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer active",
        )

    new_access_token = create_access_token(
        subject=str(user.id),
        claims={"org_id": str(user.org_id), "role": user.role, "email": user.email},
        expires_delta=timedelta(minutes=settings.jwt_expiration_minutes),
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60,
        user=_build_user_profile(user),
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve profile and tenant details of the currently authenticated user.
    """
    return _build_user_profile(current_user)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Log user logout event in the audit trail.
    """
    client_ip = request.client.host if request.client else None
    await log_audit_action(
        db=db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="AUTH_LOGOUT",
        resource_type="USER",
        resource_id=str(current_user.id),
        ip_address=client_ip,
    )
    return {"status": "success", "message": "Successfully logged out"}
