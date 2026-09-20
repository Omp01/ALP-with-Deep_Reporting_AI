"""
Course, Module, ContentItem, and ContentChunk models.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Course(Base):
    """
    Top-level curriculum container.
    """
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False, index=True)  # draft, published, archived
    thumbnail_url = Column(String(1024), nullable=True)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(100), default="Computer Science", nullable=False, index=True)
    difficulty = Column(String(50), default="intermediate", nullable=False, index=True)  # beginner, intermediate, advanced
    # Both are NULL unless real data exists. `rating` has no source yet (there is no
    # ratings table), so it stays NULL and the UI hides it. `duration_minutes` is an
    # optional author override; when NULL the API computes it from content durations.
    rating = Column(Float, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    course_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="courses")
    creator = relationship("User", foreign_keys=[created_by_id])
    instructor = relationship("User", foreign_keys=[instructor_id])
    modules = relationship("Module", back_populates="course", order_by="Module.sequence_order", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="course", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    competency_mappings = relationship("CourseCompetency", back_populates="course", cascade="all, delete-orphan")
    adaptive_sessions = relationship("AdaptiveSession", back_populates="course", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")


class Module(Base):
    """
    Instructional unit belonging to a course.
    """
    __tablename__ = "modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sequence_order = Column(Integer, default=0, nullable=False)
    estimated_duration_mins = Column(Integer, default=30, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    course = relationship("Course", back_populates="modules")
    content_items = relationship("ContentItem", back_populates="module", cascade="all, delete-orphan", order_by="ContentItem.order_index")
    assessment_items = relationship("AssessmentItem", back_populates="module", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="module", cascade="all, delete-orphan")
    competency_mappings = relationship("ModuleCompetency", back_populates="module", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="module", cascade="all, delete-orphan")


class ContentItem(Base):
    """
    Pedagogical resource (video, article, quiz, assignment, document).
    """
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False, index=True)  # VIDEO, ARTICLE, QUIZ, ASSIGNMENT, DOCUMENT, TEXT
    content_url = Column(String(1024), nullable=True)
    text_content = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="published", nullable=False)  # draft, processing, review, published, failed
    # Where the content came from: authored (typed in the LMS), upload (file), youtube, url.
    source_type = Column(String(30), default="authored", nullable=False, server_default="authored")
    source_url = Column(String(2048), nullable=True)
    # Output of content analysis (learning objectives, detected concepts). Populated by ingestion.
    analysis = Column(JSONB, nullable=True)
    # SHA-256 of the file (or transcript) the analysis was computed from; unchanged content is not re-analysed.
    content_hash = Column(String(64), nullable=True, index=True)
    item_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    module = relationship("Module", back_populates="content_items")
    chunks = relationship("ContentChunk", back_populates="content_item", cascade="all, delete-orphan")
    progress_records = relationship("ContentProgress", back_populates="content_item", cascade="all, delete-orphan")
    competency_mappings = relationship("ContentCompetency", back_populates="content_item", cascade="all, delete-orphan")


class ContentChunk(Base):
    """
    Vectorizable, granular text chunk for semantic search and retrieval grounding.
    """
    __tablename__ = "content_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0, nullable=False)
    text_content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0, nullable=False)
    embedding = Column(JSONB, nullable=True)  # Stored as float array in JSONB for universal portability
    embedding_model = Column(String(120), nullable=True)  # which model produced the vector
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    content_item = relationship("ContentItem", back_populates="chunks")
