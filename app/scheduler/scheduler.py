from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler.jobs import release_expired_reservations


scheduler = AsyncIOScheduler()


def configure_scheduler() -> None:
    if scheduler.get_job("release-expired-reservations"):
        return

    scheduler.add_job(
        release_expired_reservations,
        trigger=IntervalTrigger(minutes=1),
        id="release-expired-reservations",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
