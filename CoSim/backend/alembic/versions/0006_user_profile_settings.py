"""Add user profile fields and preferences JSON

Revision ID: 0006_user_profile_settings
Revises: 0005_add_user_external_id_stub
Create Date: 2025-10-05 00:00:00.000000

"""
from __future__ import annotations

import json

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0006_user_profile_settings'
down_revision: Union[str, None] = '0005_add_user_external_id_stub'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_PREFERENCES = {
    "notifications": {
        "email_enabled": True,
        "project_updates": True,
        "session_alerts": True,
        "billing_alerts": True,
    },
    "appearance": {
        "theme": "auto",
        "editor_font_size": 14,
    },
    "privacy": {
        "profile_visibility": "private",
        "show_activity": False,
    },
    "resources": {
        "auto_hibernate": True,
        "hibernate_minutes": 5,
    },
}

DEFAULT_PREFERENCES_SQL = f"'{json.dumps(DEFAULT_PREFERENCES)}'::jsonb"


def upgrade() -> None:
    op.add_column('users', sa.Column('display_name', sa.String(length=120), nullable=True))
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column(
        'users',
        sa.Column(
            'preferences',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(DEFAULT_PREFERENCES_SQL),
            nullable=False,
        ),
    )

    # Ensure existing rows receive default preferences
    op.execute(f"UPDATE users SET preferences = {DEFAULT_PREFERENCES_SQL}")

    # Remove server default to avoid future implicit defaults managed by the application layer
    op.alter_column('users', 'preferences', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'preferences')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'display_name')
