from __future__ import annotations

from datetime import datetime

try:
    from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
except ImportError:  # pragma: no cover
    DeclarativeBase = object


if DeclarativeBase is not object:

    class Base(DeclarativeBase):
        pass


    class RepoAnalysis(Base):
        __tablename__ = "repo_analyses"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        owner: Mapped[str] = mapped_column(String(120), index=True)
        repo: Mapped[str] = mapped_column(String(120), index=True)
        branch: Mapped[str] = mapped_column(String(180), default="main")
        scanned_commit_sha: Mapped[str | None] = mapped_column(String(80), nullable=True)
        overall_score: Mapped[float] = mapped_column(Float)
        label: Mapped[str] = mapped_column(String(30))
        model_version: Mapped[str] = mapped_column(String(80))
        scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
        file_scores: Mapped[list["FileScoreRecord"]] = relationship(back_populates="analysis")


    class FileScoreRecord(Base):
        __tablename__ = "file_scores"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        analysis_id: Mapped[int] = mapped_column(ForeignKey("repo_analyses.id"), index=True)
        path: Mapped[str] = mapped_column(Text)
        language: Mapped[str] = mapped_column(String(60))
        size_bytes: Mapped[int] = mapped_column(Integer, default=0)
        score: Mapped[float] = mapped_column(Float)
        ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
        heuristic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
        analysis: Mapped[RepoAnalysis] = relationship(back_populates="file_scores")


    class ApiUsage(Base):
        __tablename__ = "api_usage"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        client_id: Mapped[str] = mapped_column(String(160), index=True)
        endpoint: Mapped[str] = mapped_column(String(160))
        called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

