"""Repair saved searches and add week 7 operational state.

Revision ID: 7a01_week7
Revises: 62cbe6c55481
"""
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa

revision = "7a01_week7"
down_revision = "62cbe6c55481"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("saved_searches")}
    if "keywords" not in columns:
        op.alter_column("saved_searches", "keyword", new_column_name="keywords")
    elif "keyword" in columns:
        op.execute("UPDATE saved_searches SET keywords = COALESCE(keywords, keyword)")
    for name, kind in [("location", sa.String()), ("filters", sa.JSON()),
                       ("signature", sa.String(64))]:
        if name not in columns:
            op.add_column("saved_searches", sa.Column(name, kind))
    if "is_active" not in columns:
        op.add_column("saved_searches", sa.Column("is_active", sa.Boolean(), server_default=sa.true()))
    op.execute("UPDATE saved_searches SET is_active = false, email = '' WHERE email IS NULL")
    op.execute("UPDATE saved_searches SET is_active = false WHERE keywords IS NULL OR trim(keywords) = ''")
    op.execute("UPDATE saved_searches SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE saved_searches SET created_at = now() WHERE created_at IS NULL")
    op.alter_column("saved_searches", "email", nullable=False)
    op.alter_column("saved_searches", "is_active", nullable=False, server_default=sa.true())
    # Legacy endpoints accepted unverified recipient addresses. Require an authenticated re-save.
    op.execute("UPDATE saved_searches SET is_active = false")
    op.create_unique_constraint("uq_saved_search_signature", "saved_searches", ["user_id", "signature"])

    op.add_column("jobs", sa.Column("location", sa.String()))
    op.add_column("jobs", sa.Column("is_remote", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Preserve old rows; don't pretend source metadata that wasn't retained is known.
    op.execute("UPDATE jobs SET is_remote = true WHERE source_id LIKE 'remoteok_%' OR source_id LIKE 'jobicy_%'")
    op.add_column("jobs", sa.Column("fingerprint", sa.String(64)))
    seen = set()
    for row in bind.execute(sa.text("SELECT id, url FROM jobs ORDER BY id")).mappings():
        parts = urlsplit(row["url"].strip())
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "fbclid", "gclid"}]
        url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/",
                         urlencode(sorted(query)), ""))
        value = hashlib.sha256(url.encode()).hexdigest()
        if value not in seen:
            bind.execute(sa.text("UPDATE jobs SET fingerprint=:value WHERE id=:id"), {"value": value, "id": row["id"]})
            seen.add(value)
    op.create_unique_constraint("uq_jobs_fingerprint", "jobs", ["fingerprint"])

    op.create_table("job_sources",
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_job_sources_job_id", "job_sources", ["job_id"])
    op.create_table("alert_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_id", sa.Integer(), sa.ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider_id", sa.String()),
        sa.UniqueConstraint("search_id", "job_id", name="uq_alert_search_job"))
    op.create_index("ix_alert_deliveries_search_id", "alert_deliveries", ["search_id"])
    op.create_index("ix_alert_pending", "alert_deliveries", ["status", "next_attempt_at"])
    op.create_table("scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("duration_ms", sa.Float()),
        sa.Column("fetched", sa.Integer(), nullable=False), sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(100)))
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])
    op.create_index("ix_scrape_runs_source_id", "scrape_runs", ["source", "id"])
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops)")
    op.execute("CREATE INDEX ix_jobs_company_trgm ON jobs USING gin (company gin_trgm_ops)")


def downgrade():
    # Explicitly refuse a lossy downgrade: delivery history prevents duplicate mail.
    raise RuntimeError("Week 7 rollback requires restoring a verified pre-migration database backup.")
