"""
LearningEvent model for event tracking and streaming audit.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class LearningEvent(Base):
    """
    Immutable granular learning event emitted by learners and LMS interactions.
    """
    __tablename__ = "learning_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("adaptive_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSONB, default=dict, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    user = relationship("User")
    session = relationship("AdaptiveSession")
    course = relationship("Course")
    module = relationship("Module")
