"""add alert receiver verification fields

Revision ID: 20260701_0003
Revises: 20260629_0002
Create Date: 2026-07-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260701_0003"
down_revision: str | None = "20260629_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add OTP verification state to webhook notification channels."""
    op.execute(
        """
        ALTER TABLE notification_channels
            ADD COLUMN verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
            ADD COLUMN verification_code_hash VARCHAR(128),
            ADD COLUMN verification_expires_at TIMESTAMPTZ,
            ADD COLUMN verified_at TIMESTAMPTZ,
            ADD COLUMN last_verification_sent_at TIMESTAMPTZ,
            ADD COLUMN last_verification_error TEXT,
            ADD CONSTRAINT ck_notification_channels_verification_status
                CHECK (verification_status IN ('PENDING', 'VERIFIED', 'FAILED'));

        CREATE INDEX ix_notification_channels_verification_status
            ON notification_channels (verification_status);
        """
    )


def downgrade() -> None:
    """Remove OTP verification state from notification channels."""
    op.execute(
        """
        DROP INDEX IF EXISTS ix_notification_channels_verification_status;
        ALTER TABLE notification_channels
            DROP CONSTRAINT IF EXISTS ck_notification_channels_verification_status,
            DROP COLUMN IF EXISTS last_verification_error,
            DROP COLUMN IF EXISTS last_verification_sent_at,
            DROP COLUMN IF EXISTS verified_at,
            DROP COLUMN IF EXISTS verification_expires_at,
            DROP COLUMN IF EXISTS verification_code_hash,
            DROP COLUMN IF EXISTS verification_status;
        """
    )
