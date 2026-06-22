"""create observability portal schema

Revision ID: 20260615_0001
Revises:
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260615_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all PostgreSQL tables and indexes required by the portal backend."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            password_hash VARCHAR(255) NOT NULL,
            grafana_user_id VARCHAR(100),
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            deleted BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE', 'LOCKED', 'DISABLED'))
        );

        CREATE INDEX ix_users_username ON users (username);
        CREATE INDEX ix_users_email ON users (email);
        CREATE UNIQUE INDEX uq_users_username_active ON users (username) WHERE deleted = false;
        CREATE UNIQUE INDEX uq_users_email_active ON users (email) WHERE deleted = false;

        CREATE TABLE vm_instances (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vm_name VARCHAR(255) NOT NULL,
            cloud_provider VARCHAR(50) NOT NULL,
            public_ip VARCHAR(50),
            private_ip VARCHAR(50),
            os_type VARCHAR(50) NOT NULL,
            os_version VARCHAR(100),
            environment VARCHAR(50),
            description TEXT,
            monitoring_status VARCHAR(50) NOT NULL DEFAULT 'NOT_INSTALLED',
            is_monitoring BOOLEAN NOT NULL DEFAULT false,
            last_seen_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            deleted BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_vm_monitoring_status CHECK (
                monitoring_status IN ('NOT_INSTALLED', 'PACKAGE_GENERATED', 'DOWNLOADED', 'INSTALLING', 'RUNNING', 'STOPPED', 'ERROR', 'NO_DATA')
            )
        );

        CREATE INDEX ix_vm_instances_user_id ON vm_instances (user_id);
        CREATE UNIQUE INDEX uq_vm_user_name_provider_active ON vm_instances (user_id, vm_name, cloud_provider) WHERE deleted = false;

        CREATE TABLE agent_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID NOT NULL REFERENCES vm_instances(id) ON DELETE CASCADE,
            token_hash VARCHAR(255) UNIQUE NOT NULL,
            token_prefix VARCHAR(30),
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            expired_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_agent_tokens_status CHECK (status IN ('ACTIVE', 'REVOKED', 'EXPIRED'))
        );

        CREATE INDEX ix_agent_tokens_vm_id ON agent_tokens (vm_id);
        CREATE UNIQUE INDEX uq_agent_tokens_one_active_per_vm ON agent_tokens (vm_id) WHERE status = 'ACTIVE';

        CREATE TABLE agent_packages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID NOT NULL REFERENCES vm_instances(id) ON DELETE CASCADE,
            generated_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            package_name VARCHAR(255) NOT NULL,
            package_path VARCHAR(500) NOT NULL,
            config_version INT NOT NULL DEFAULT 1,
            checksum VARCHAR(255),
            file_size_bytes BIGINT,
            os_type VARCHAR(50) NOT NULL,
            agent_version VARCHAR(50),
            status VARCHAR(30) NOT NULL DEFAULT 'GENERATED',
            downloaded_at TIMESTAMPTZ,
            expired_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_agent_packages_status CHECK (status IN ('GENERATED', 'DOWNLOADED', 'EXPIRED', 'REVOKED'))
        );

        CREATE INDEX ix_agent_packages_vm_id ON agent_packages (vm_id);
        CREATE INDEX ix_agent_packages_generated_by ON agent_packages (generated_by);

        CREATE TABLE agent_install_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID NOT NULL REFERENCES vm_instances(id) ON DELETE CASCADE,
            package_id UUID REFERENCES agent_packages(id) ON DELETE SET NULL,
            event_type VARCHAR(50) NOT NULL,
            event_status VARCHAR(30) NOT NULL,
            message TEXT,
            error_detail TEXT,
            agent_version VARCHAR(50),
            source_ip VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_agent_install_events_type CHECK (
                event_type IN ('PACKAGE_GENERATED', 'PACKAGE_DOWNLOADED', 'INSTALL_STARTED', 'INSTALLED', 'STARTED', 'STOPPED', 'UNINSTALLED', 'ERROR')
            ),
            CONSTRAINT ck_agent_install_events_status CHECK (event_status IN ('SUCCESS', 'FAILED', 'PENDING'))
        );

        CREATE INDEX ix_agent_install_events_vm_id ON agent_install_events (vm_id);

        CREATE TABLE vm_agent_status (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID UNIQUE NOT NULL REFERENCES vm_instances(id) ON DELETE CASCADE,
            agent_status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
            agent_version VARCHAR(50),
            service_status VARCHAR(50),
            last_seen_at TIMESTAMPTZ,
            last_heartbeat_at TIMESTAMPTZ,
            last_error_message TEXT,
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_vm_agent_status_agent_status CHECK (agent_status IN ('UNKNOWN', 'RUNNING', 'STOPPED', 'ERROR', 'NO_DATA', 'UNINSTALLED')),
            CONSTRAINT ck_vm_agent_status_service_status CHECK (service_status IS NULL OR service_status IN ('active', 'inactive', 'failed', 'unknown'))
        );

        CREATE INDEX ix_vm_agent_status_vm_id ON vm_agent_status (vm_id);

        CREATE TABLE grafana_mappings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            vm_id UUID REFERENCES vm_instances(id) ON DELETE CASCADE,
            grafana_org_id VARCHAR(100),
            grafana_user_id VARCHAR(100),
            grafana_folder_uid VARCHAR(100),
            dashboard_uid VARCHAR(100),
            dashboard_url VARCHAR(500),
            mapping_type VARCHAR(50) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_grafana_mappings_type CHECK (mapping_type IN ('USER', 'VM', 'DASHBOARD', 'FOLDER')),
            CONSTRAINT ck_grafana_mappings_status CHECK (status IN ('ACTIVE', 'ERROR', 'DISABLED'))
        );

        CREATE INDEX ix_grafana_mappings_user_id ON grafana_mappings (user_id);
        CREATE INDEX ix_grafana_mappings_vm_id ON grafana_mappings (vm_id);

        CREATE TABLE grafana_dashboard_panels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vm_id UUID REFERENCES vm_instances(id) ON DELETE CASCADE,
            dashboard_uid VARCHAR(100) NOT NULL,
            panel_id INT NOT NULL,
            panel_name VARCHAR(255) NOT NULL,
            panel_type VARCHAR(50) NOT NULL,
            iframe_url VARCHAR(1000) NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            CONSTRAINT ck_grafana_dashboard_panels_type CHECK (panel_type IN ('CPU', 'MEMORY', 'DISK', 'NETWORK', 'AGENT_STATUS', 'VM_STATUS')),
            CONSTRAINT ck_grafana_dashboard_panels_status CHECK (status IN ('ACTIVE', 'ERROR', 'DISABLED'))
        );

        CREATE INDEX ix_grafana_dashboard_panels_vm_id ON grafana_dashboard_panels (vm_id);

        CREATE TABLE alert_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vm_id UUID REFERENCES vm_instances(id) ON DELETE CASCADE,
            rule_name VARCHAR(255) NOT NULL,
            rule_code VARCHAR(100) NOT NULL,
            metric_name VARCHAR(255),
            promql_expr TEXT NOT NULL,
            condition_text VARCHAR(500),
            duration VARCHAR(50) NOT NULL,
            severity VARCHAR(30) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            deleted BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_alert_rules_severity CHECK (severity IN ('info', 'warning', 'critical'))
        );

        CREATE INDEX ix_alert_rules_user_id ON alert_rules (user_id);
        CREATE INDEX ix_alert_rules_vm_id ON alert_rules (vm_id);
        CREATE UNIQUE INDEX uq_alert_rules_user_code_active ON alert_rules (user_id, rule_code) WHERE deleted = false;

        CREATE TABLE notification_channels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel_name VARCHAR(255) NOT NULL,
            channel_type VARCHAR(50) NOT NULL,
            receiver VARCHAR(500) NOT NULL,
            config_json JSONB,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ,
            deleted BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_notification_channels_type CHECK (channel_type IN ('EMAIL', 'WEBHOOK', 'TELEGRAM', 'SLACK'))
        );

        CREATE INDEX ix_notification_channels_user_id ON notification_channels (user_id);

        CREATE TABLE alert_rule_channels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_rule_id UUID NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_alert_rule_channel UNIQUE (alert_rule_id, channel_id)
        );

        CREATE INDEX ix_alert_rule_channels_alert_rule_id ON alert_rule_channels (alert_rule_id);
        CREATE INDEX ix_alert_rule_channels_channel_id ON alert_rule_channels (channel_id);

        CREATE TABLE audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            target_type VARCHAR(100),
            target_id UUID,
            request_ip VARCHAR(50),
            user_agent VARCHAR(500),
            detail_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);
        CREATE INDEX ix_audit_logs_action ON audit_logs (action);
        """
    )


def downgrade() -> None:
    """Drop all portal tables in reverse dependency order."""
    op.execute(
        """
        DROP TABLE IF EXISTS audit_logs;
        DROP TABLE IF EXISTS alert_rule_channels;
        DROP TABLE IF EXISTS notification_channels;
        DROP TABLE IF EXISTS alert_rules;
        DROP TABLE IF EXISTS grafana_dashboard_panels;
        DROP TABLE IF EXISTS grafana_mappings;
        DROP TABLE IF EXISTS vm_agent_status;
        DROP TABLE IF EXISTS agent_install_events;
        DROP TABLE IF EXISTS agent_packages;
        DROP TABLE IF EXISTS agent_tokens;
        DROP TABLE IF EXISTS vm_instances;
        DROP TABLE IF EXISTS users;
        """
    )
