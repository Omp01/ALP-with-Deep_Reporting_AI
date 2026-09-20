"""Add LMS entities: quizzes, questions, options, attempts, responses, content progress, content competencies, adaptive decisions, course metadata

Revision ID: 002_lms_entities
Revises: 001_initial_schema
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_lms_entities'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Revision 001 runs create_all() from the *current* models, so on a brand-new
    # database everything below already exists. Only an existing pre-002 database
    # needs this upgrade.
    if sa.inspect(op.get_bind()).has_table('quizzes'):
        return

    # 1. Add presentation fields to courses
    op.add_column('courses', sa.Column('thumbnail_url', sa.String(length=1024), nullable=True))
    op.add_column('courses', sa.Column('instructor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
    op.add_column('courses', sa.Column('category', sa.String(length=100), server_default='Computer Science', nullable=False))
    op.add_column('courses', sa.Column('difficulty', sa.String(length=50), server_default='intermediate', nullable=False))
    op.add_column('courses', sa.Column('rating', sa.Float(), server_default='4.8', nullable=False))
    op.add_column('courses', sa.Column('duration_minutes', sa.Integer(), server_default='120', nullable=False))
    op.create_index(op.f('ix_courses_category'), 'courses', ['category'], unique=False)
    op.create_index(op.f('ix_courses_difficulty'), 'courses', ['difficulty'], unique=False)

    # 2. Add content_id to learning_events
    op.add_column('learning_events', sa.Column('content_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='SET NULL'), nullable=True))
    op.create_index(op.f('ix_learning_events_content_id'), 'learning_events', ['content_id'], unique=False)

    # 3. Create quizzes
    op.create_table(
        'quizzes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('modules.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('time_limit_mins', sa.Integer(), server_default='30', nullable=False),
        sa.Column('passing_score', sa.Float(), server_default='70.0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('is_adaptive', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_quizzes_org_id'), 'quizzes', ['org_id'], unique=False)
    op.create_index(op.f('ix_quizzes_course_id'), 'quizzes', ['course_id'], unique=False)
    op.create_index(op.f('ix_quizzes_module_id'), 'quizzes', ['module_id'], unique=False)

    # 4. Create quiz_questions
    op.create_table(
        'quiz_questions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('quiz_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('competency_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('competencies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('question_type', sa.String(length=50), server_default='multiple_choice', nullable=False),
        sa.Column('points', sa.Integer(), server_default='1', nullable=False),
        sa.Column('order_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_quiz_questions_quiz_id'), 'quiz_questions', ['quiz_id'], unique=False)
    op.create_index(op.f('ix_quiz_questions_competency_id'), 'quiz_questions', ['competency_id'], unique=False)

    # 5. Create quiz_options
    op.create_table(
        'quiz_options',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('option_text', sa.Text(), nullable=False),
        sa.Column('is_correct', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('order_index', sa.Integer(), server_default='0', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
    )
    op.create_index(op.f('ix_quiz_options_question_id'), 'quiz_options', ['question_id'], unique=False)

    # 6. Create quiz_attempts
    op.create_table(
        'quiz_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('quiz_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quizzes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('passed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_quiz_attempts_quiz_id'), 'quiz_attempts', ['quiz_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_user_id'), 'quiz_attempts', ['user_id'], unique=False)

    # 7. Create question_responses
    op.create_table(
        'question_responses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('attempt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_attempts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_questions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('selected_option_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quiz_options.id', ondelete='SET NULL'), nullable=True),
        sa.Column('text_response', sa.Text(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('points_awarded', sa.Float(), server_default='0.0', nullable=False),
    )
    op.create_index(op.f('ix_question_responses_attempt_id'), 'question_responses', ['attempt_id'], unique=False)
    op.create_index(op.f('ix_question_responses_question_id'), 'question_responses', ['question_id'], unique=False)

    # 8. Create content_progress
    op.create_table(
        'content_progress',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='not_started', nullable=False),
        sa.Column('progress_percent', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('time_spent_seconds', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_accessed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_content_progress_user_id'), 'content_progress', ['user_id'], unique=False)
    op.create_index(op.f('ix_content_progress_content_item_id'), 'content_progress', ['content_item_id'], unique=False)
    op.create_index(op.f('ix_content_progress_status'), 'content_progress', ['status'], unique=False)

    # 9. Create content_competencies
    op.create_table(
        'content_competencies',
        sa.Column('content_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('competency_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('competencies.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('weight', sa.Float(), server_default='1.0', nullable=False),
    )

    # 10. Create adaptive_decisions
    op.create_table(
        'adaptive_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('adaptive_sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('competency_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('competencies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('decision_type', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('rule_applied', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index(op.f('ix_adaptive_decisions_org_id'), 'adaptive_decisions', ['org_id'], unique=False)
    op.create_index(op.f('ix_adaptive_decisions_session_id'), 'adaptive_decisions', ['session_id'], unique=False)
    op.create_index(op.f('ix_adaptive_decisions_user_id'), 'adaptive_decisions', ['user_id'], unique=False)
    op.create_index(op.f('ix_adaptive_decisions_competency_id'), 'adaptive_decisions', ['competency_id'], unique=False)
    op.create_index(op.f('ix_adaptive_decisions_decision_type'), 'adaptive_decisions', ['decision_type'], unique=False)
    op.create_index(op.f('ix_adaptive_decisions_created_at'), 'adaptive_decisions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('adaptive_decisions')
    op.drop_table('content_competencies')
    op.drop_table('content_progress')
    op.drop_table('question_responses')
    op.drop_table('quiz_attempts')
    op.drop_table('quiz_options')
    op.drop_table('quiz_questions')
    op.drop_table('quizzes')
    op.drop_column('learning_events', 'content_id')
    op.drop_column('courses', 'duration_minutes')
    op.drop_column('courses', 'rating')
    op.drop_column('courses', 'difficulty')
    op.drop_column('courses', 'category')
    op.drop_column('courses', 'instructor_id')
    op.drop_column('courses', 'thumbnail_url')
