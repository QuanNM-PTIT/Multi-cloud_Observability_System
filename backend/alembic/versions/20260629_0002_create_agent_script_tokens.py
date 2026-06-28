"""create agent script tokens

Revision ID: 20260629_0002
Revises: 20260615_0001
Create Date: 2026-06-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260629_0002"
down_revision: str | None = "20260615_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one-time script tokens for VM install and uninstall flows."""
    op.execute(
        """
        CREATE TABLE agent_script_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID NOT NULL REFERENCES vm_instances(id) ON DELETE CASCADE,
            package_id UUID REFERENCES agent_packages(id) ON DELETE SET NULL,
            token_hash VARCHAR(255) UNIQUE NOT NULL,
            token_prefix VARCHAR(30),
            action VARCHAR(30) NOT NULL,
            os_type VARCHAR(50) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            expired_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_agent_script_tokens_action CHECK (action IN ('INSTALL', 'UNINSTALL')),
            CONSTRAINT ck_agent_script_tokens_status CHECK (status IN ('ACTIVE', 'USED', 'EXPIRED', 'REVOKED'))
        );

        CREATE INDEX ix_agent_script_tokens_vm_id ON agent_script_tokens (vm_id);
        CREATE INDEX ix_agent_script_tokens_package_id ON agent_script_tokens (package_id);
        CREATE UNIQUE INDEX uq_agent_script_tokens_one_active_action_per_vm
            ON agent_script_tokens (vm_id, action)
            WHERE status = 'ACTIVE';
        """
    )


def downgrade() -> None:
    """Drop script token storage."""
    op.execute("DROP TABLE IF EXISTS agent_script_tokens;")
