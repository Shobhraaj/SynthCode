from __future__ import annotations

from backend.app.config import get_settings

settings = get_settings()

try:
    from celery import Celery

    celery_app = Celery(
        "synthcode",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=["backend.app.workers.tasks"],
    )
    celery_app.conf.task_track_started = True
except ImportError:  # pragma: no cover
    celery_app = None

