"""Initial SynthCode schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "repo_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("repo", sa.String(length=120), nullable=False),
        sa.Column("branch", sa.String(length=180), nullable=False),
        sa.Column("scanned_commit_sha", sa.String(length=80), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("label", sa.String(length=30), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "file_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("repo_analyses.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=60), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("ml_score", sa.Float(), nullable=True),
        sa.Column("heuristic_score", sa.Float(), nullable=True),
    )
    op.create_table(
        "api_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(length=160), nullable=False),
        sa.Column("endpoint", sa.String(length=160), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_analyses_owner_repo", "repo_analyses", ["owner", "repo"])
    op.create_index("idx_analyses_expires", "repo_analyses", ["expires_at"])
    op.create_index("idx_file_scores_analysis", "file_scores", ["analysis_id"])
    op.create_index("idx_api_usage_client", "api_usage", ["client_id", "called_at"])


def downgrade():
    op.drop_index("idx_api_usage_client", table_name="api_usage")
    op.drop_index("idx_file_scores_analysis", table_name="file_scores")
    op.drop_index("idx_analyses_expires", table_name="repo_analyses")
    op.drop_index("idx_analyses_owner_repo", table_name="repo_analyses")
    op.drop_table("api_usage")
    op.drop_table("file_scores")
    op.drop_table("repo_analyses")

