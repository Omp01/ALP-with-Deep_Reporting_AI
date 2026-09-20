"""Runs due scheduled reports in the background when REPORT_SCHEDULER_ENABLED is true (otherwise use POST /reports/schedules/run-due)."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import ScheduledReport

logger = logging.getLogger("api.reporting")


async def run_scheduler() -> None:
    from app.api.v1.reports import _run_schedule       # imported late: the API module imports the reporting package

    while True:
        try:
            async with AsyncSessionLocal() as db:
                due = (await db.execute(select(ScheduledReport).where(ScheduledReport.is_active.is_(True), ScheduledReport.next_run_at <= datetime.utcnow()))).scalars().all()
                for schedule in due:
                    result = await _run_schedule(db, schedule, datetime.utcnow())
                    logger.info("scheduled_report_run", extra=result)
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled report pass failed")
        await asyncio.sleep(settings.report_scheduler_interval_seconds)
