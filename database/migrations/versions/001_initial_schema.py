"""Initial schema with all 25 models

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.models import Base
from app.core.database import sync_engine

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create all tables declared in Base.metadata
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Drop all tables declared in Base.metadata
    Base.metadata.drop_all(bind=op.get_bind())
