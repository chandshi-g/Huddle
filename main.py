"""
main.py

FastAPI app: sets up the DB pool + schema on startup, receives Telegram
webhook updates, and routes each message to the right stage:
  1. onboarding (no deadline yet)      -> extract deadline/headcount/skills
  2. scope review (mvp_features empty) -> run_critic
  3. planning (no tasks yet)           -> run_planner
  4. otherwise                         -> treat as a check-in

Also exposes manual /trigger-* endpoints as a demo-day safety net in case
the Telegram webhook or scheduler timing doesn't cooperate live.
"""

import os
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from dotenv import load_dotenv

from db import connection, queries
from agents.critic import run_critic
from agents.planner import run_planner
from agents.pitch import run_pitch
from agents.blocker import run_blocker_check
from scheduler import start_scheduler
import telegram_client as tg

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.environ.get("DATABASE_URL")
    pool = await connection.get_pool(database_url)
    queries.init_pool(pool)

    with open("db/schema.sql") as f:
        schema_sql = f.read()
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)

    print("[main] DB pool ready, schema applied.")
    scheduler = start_scheduler()

    yield

    scheduler.shutdown()
    await pool.close()


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# onboarding — lightweight, no full CrewAI agent needed for this stage
# ---------------------------------------------------------------------------

async def _extract_onboarding_info(team_id: int, text: str) -> None:
    """
    Very simple stage: a single direct Gemini call (via CrewAI's LiteLLM
    Gemini provider through the anthropic/gemini SDK is overkill here) to
    pull deadline/headcount/skills out of a free-text message. Kept separate
    from the four contract agents since this stage isn't part of the frozen
    contract — it just needs to populate `teams` well enough that
    run_critic has something to work with.
    """
    import litellm

    prompt = (
        "Extract hackathon team setup info from this message. Return ONLY "
        "JSON, no markdown fences, matching exactly:\n"
        '{"team_name": string|null, "deadline_hours_from_now": number|null, '
        '"headcount": number|null, "skills": {"name": ["skill1","skill2"]}}\n\n'
        "If a field isn't mentioned, use null (or {} for skills).\n\n"
        f"Message:\n{text}"
    )
    try:
        response = litellm.completion(
            model=os.environ.get("GEMINI_MODEL", "gemini/gemini-2.0-flash"),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[onboarding] extraction failed, using safe defaults: {e}")
        parsed = {}

    update_fields = {}
    if parsed.get("team_name"):
        update_fields["team_name"] = parsed["team_name"]
    if parsed.get("headcount"):
        update_fields["headcount"] = parsed["headcount"]
    if parsed.get("skills"):
        update_fields["skills"] = parsed["skills"]

    hours = parsed.get("deadline_hours_from_now")
    # Always set SOME deadline so the team doesn't get stuck re-triggering
    # onboarding forever if extraction fails — default to 24h out.
    update_fields["deadline"] = datetime.now() + timedelta(hours=hours or 24)

    await queries.update_team(team_id, **update_fields)



# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        message = update.get("message")
        if not message or "text" not in message:
            return {"ok": True}  # ignore non-text updates, never 500 to Telegram

        chat_id = message["chat"]["id"]
        text = message["text"]
        author = message["from"].get("username") or message["from"].get("first_name", "unknown")

        team = await queries.get_or_create_team(chat_id)
        team_id = team["id"]

        await queries.log_raw_message(team_id, author, text)

        if team.get("deadline") is None:
            await _extract_onboarding_info(team_id, text)
            await tg.send_message(
                chat_id,
                "Got it — noted your deadline, headcount, and skills. "
                "Send your project concept next and I'll review the scope.",
            )
            return {"ok": True}

        if not team.get("mvp_features"):
            result = await asyncio.to_thread(run_critic, team_id)
            await tg.send_message(chat_id, tg.format_critic_result(result))
            return {"ok": True}

        existing_tasks = await queries.get_tasks(team_id)
        if not existing_tasks:
            result = await asyncio.to_thread(run_planner, team_id)
            await tg.send_message(chat_id, tg.format_planner_result(result))
            return {"ok": True}

        # otherwise: treat this message as a check-in
        matching_task = await queries.get_task_by_assignee(team_id, author)
        task_id = matching_task["id"] if matching_task else None
        await queries.create_checkin(task_id, team_id, author, text)
        await tg.send_message(chat_id, "Logged your check-in ✅")
        return {"ok": True}

    except Exception as e:
        print(f"[webhook] error: {e}")
        return {"ok": True}


# ---------------------------------------------------------------------------
# manual trigger endpoints — demo-day safety net
# ---------------------------------------------------------------------------

@app.post("/trigger-pitch/{team_id}")
async def trigger_pitch(team_id: int):
    team = await queries.get_team_by_id(team_id)
    if team is None:
        return {"ok": False, "error": "unknown team_id"}
    result = await asyncio.to_thread(run_pitch, team_id)
    await tg.send_message(team["chat_id"], tg.format_pitch_result(result))
    return {"ok": True, "result": result}


@app.post("/trigger-reminder/{team_id}")
async def trigger_reminder(team_id: int):
    team = await queries.get_team_by_id(team_id)
    if team is None:
        return {"ok": False, "error": "unknown team_id"}
    result = await asyncio.to_thread(run_blocker_check, team_id)
    if result.get("should_escalate") and result.get("escalation_message"):
        await tg.send_message(team["chat_id"], result["escalation_message"])
    else:
        await tg.send_message(team["chat_id"], "No blockers detected right now 👍")
    return {"ok": True, "result": result}


@app.get("/health")
async def health():
    return {"ok": True}