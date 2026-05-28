"""Compatibility entrypoint for the Phase 2 backend package.

Keep supporting the existing local command:
    uvicorn main:app --reload
"""

from backend.app.main import app

