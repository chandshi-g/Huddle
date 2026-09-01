"""
scheduler.py

Runs run_blocker_check() for every known team on a fixed interval
(BLOCKER_CHECK_INTERVAL_HOURS from .env, default 3). If a team's check
comes back should_escalate=True, posts escalation_message straight to
that team's Telegram chat.

Also posts a lightweight "how's it going?" reminder prompt on the same
interval, separate from the blocker escalation — this is what actually
prompts people to send check-in messages in the first place.

Import and call start_scheduler() from main.py's lifespan, after the DB
pool is ready.
"""

import os
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import connection, queries
from agents.blocker import run_blocker_check
import telegram_client as tg


async def _run_checks_for_all_teams():
    pool = await connection.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, chat_id, deadline FROM teams WHERE deadline IS NOT NULL")


    for row in rows:
        team_id, chat_id = row["id"], row["chat_id"]
        try:
            # gentle daily/periodic nudge to check in
            await tg.send_message(
                chat_id,
                "⏰ Check-in time — reply with what you got done and flag anything blocking you.",
            )

            result = await asyncio.to_thread(run_blocker_check, team_id)
            if result.get("should_escalate") and result.get("escalation_message"):
                await tg.send_message(chat_id, result["escalation_message"])
        except Exception as e:
            print(f"[scheduler] check failed for team_id={team_id}: {e}")


def start_scheduler() -> AsyncIOScheduler:
    interval_hours = float(os.environ.get("BLOCKER_CHECK_INTERVAL_HOURS", 3))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_checks_for_all_teams,
        "interval",
        hours=interval_hours,
        id="blocker_check_all_teams",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[scheduler] started, running every {interval_hours}h")
    return scheduler