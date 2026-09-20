"""
Role and UserRole models.

`roles` is a platform-wide catalogue (not tenant-owned, so it has no org_id).
`user_roles` is tenant-owned: every assignment carries the organisation of the
user it belongs to, which keeps the "every tenant record has org_id" rule
uniform and lets us index and query assignments per tenant.
"""

from datetime import datetime
import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class RoleDefinition(Base):
    """A role in the platform catalogue (learner, manager, ld_admin, org_admin, super_admin)."""
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    rank = Column(Integer, nullable=False, default=0)
    is_system = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assignments = relationship("UserRole", back_populates="role")


class UserRole(Base):
    """Assignment of a role to a user."""
    __tablename__ = "user_roles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="role_links")
    role = relationship("RoleDefinition", back_populates="assignments", lazy="joined")
