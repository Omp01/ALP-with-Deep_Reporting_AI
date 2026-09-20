"""
Quiz, QuizQuestion, QuizOption, QuizAttempt, and QuestionResponse models.
Real LMS assessment and grading framework.
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Quiz(Base):
    """
    Structured quiz/assessment tied to a course and/or module.
    Supports both traditional and adaptive modes.
    """
    __tablename__ = "quizzes"
    __table_args__ = (
        Index("uq_quizzes_content_item", "content_item_id", unique=True, postgresql_where=text("content_item_id IS NOT NULL")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=True, index=True)
    # The lesson item that presents this quiz in the course outline (unique when set).
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    time_limit_mins = Column(Integer, default=30, nullable=False)
    passing_score = Column(Float, default=70.0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    is_adaptive = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    course = relationship("Course", back_populates="quizzes")
    module = relationship("Module", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order_index")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    """
    Individual question within a quiz, linked to an optional competency.
    """
    __tablename__ = "quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id", ondelete="SET NULL"), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default="multiple_choice", nullable=False)  # multiple_choice, multi_select, true_false
    points = Column(Integer, default=1, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    explanation = Column(Text, nullable=True)
    # 0 (easy) .. 1 (hard). NULL = not known; never defaulted, so an unrated question is not mistaken for a medium one.
    difficulty = Column(Float, nullable=True)
    # For short_answer / open_ended questions (Phase 5). Never sent to learners.
    expected_answer = Column(Text, nullable=True)
    # [{"criterion": "...", "description": "...", "weight": 0.5}, ...] shown to learners and given to the grader
    rubric = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
    competency = relationship("Competency")
    options = relationship("QuizOption", back_populates="question", cascade="all, delete-orphan", order_by="QuizOption.order_index")
    responses = relationship("QuestionResponse", back_populates="question", cascade="all, delete-orphan")


class QuizOption(Base):
    """
    Multiple choice / multi-select option choice for a question.
    """
    __tablename__ = "quiz_options"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    explanation = Column(Text, nullable=True)

    # Relationships
    question = relationship("QuizQuestion", back_populates="options")


class QuizAttempt(Base):
    """
    User submission and grading record for a quiz.
    """
    __tablename__ = "quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Float, default=0.0, nullable=False)
    passed = Column(Boolean, default=False, nullable=False)
    # graded | needs_review: some written answers await a person; the score and pass/fail are provisional until then
    grading_status = Column(String(20), default="graded", nullable=False, server_default="graded")
    attempt_number = Column(Integer, default=1, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    quiz = relationship("Quiz", back_populates="attempts")
    user = relationship("User")
    responses = relationship("QuestionResponse", back_populates="attempt", cascade="all, delete-orphan")


class QuestionResponse(Base):
    """
    User response to a single question in an attempt.
    """
    __tablename__ = "question_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_option_id = Column(UUID(as_uuid=True), ForeignKey("quiz_options.id", ondelete="SET NULL"), nullable=True)
    text_response = Column(Text, nullable=True)
    is_correct = Column(Boolean, default=False, nullable=False)
    points_awarded = Column(Float, default=0.0, nullable=False)
    # Milliseconds the learner spent on this question, as reported by the player and clamped to the attempt's
    # real elapsed time (`response_time_source` says so). NULL = not measured.
    response_time_ms = Column(Integer, nullable=True)
    response_time_source = Column(String(20), nullable=True)
    # graded | needs_review (a written answer waiting for a person: the AI was unavailable or not sure enough)
    grading_status = Column(String(20), default="graded", nullable=False, server_default="graded")
    # 0..1 share of the question's points awarded; NULL until graded
    score_fraction = Column(Float, nullable=True)
    grading_result_id = Column(UUID(as_uuid=True), nullable=True)
    # Deterministic classification for objective questions (see app/events/evidence.py); NULL when correct.
    error_type = Column(String(40), nullable=True)

    # Relationships
    attempt = relationship("QuizAttempt", back_populates="responses")
    question = relationship("QuizQuestion", back_populates="responses")
    selected_option = relationship("QuizOption")
