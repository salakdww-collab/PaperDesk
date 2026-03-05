from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from tzlocal import get_localzone

from app.database import session_scope
from app.services.backup_service import run_backup

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=get_localzone())
_started = False



def _run_job(kind: str) -> None:
    try:
        with session_scope() as db:
            run_backup(db, kind=kind)
    except Exception as exc:
        logger.exception("backup job failed: %s", exc)



def start_scheduler() -> None:
    global _started
    if _started:
        return

    scheduler.add_job(_run_job, "cron", hour=2, minute=0, id="daily_backup", args=["daily"], replace_existing=True)
    scheduler.add_job(
        _run_job,
        "cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="weekly_backup",
        args=["weekly"],
        replace_existing=True,
    )
    scheduler.start()
    _started = True



def stop_scheduler() -> None:
    global _started
    if _started and scheduler.running:
        scheduler.shutdown(wait=False)
    _started = False
