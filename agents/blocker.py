"""
agents/blocker.py

Owns the BlockerWatcher agent. Exposes exactly one function other modules
should call: run_blocker_check(team_id: int) -> dict

Contract (do not change without telling the group):
{
  "blocked_tasks": [{"task_id": int, "reason": str}],
  "should_escalate": bool,
  "escalation_message": str   # empty string if should_escalate is False
}

Escalation rule: 2+ missed check-ins in a row for a task, OR check-in text
that reads as stuck/blocked, triggers should_escalate = True.

This function only DECIDES — it does not send anything to Telegram.
scheduler.py / main.py is responsible for actually posting
escalation_message to the group chat.
"""

import json
import asyncio
from crewai import Agent, Task, Crew, Process
from db import queries

import os
from crewai.llm import LLM
from db.connection import get_main_loop

def _get_llm() -> LLM:
    return LLM(
        model=os.environ.get("GEMINI_MODEL", "gemini/gemini-2.0-flash"),
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=0.3,
    )

def _run_async(coro):
    main_loop = get_main_loop()
    if main_loop and main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, main_loop)
        return future.result()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import nest_asyncio

        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    return asyncio.run(coro)

EXPECTED_JSON_SHAPE = """{
  "blocked_tasks": [{"task_id": 0, "reason": "string"}],
  "should_escalate": false,
  "escalation_message": "string"
}"""


def _build_agent() -> Agent:
    return Agent(
        role="Hackathon Blocker Watcher",
        goal=(
            "Detect blocked or slipping tasks early from check-in patterns "
            "and missed check-ins, and decide when to escalate to the group."
        ),
        backstory=(
            "You watch a hackathon team's task list and check-in history the "
            "way a good team lead would — catching a stuck teammate before "
            "it costs the team hours, not after. Your escalation rule is "
            "fixed: a task with 2 or more missed check-ins in a row, or a "
            "check-in whose text genuinely reads as the person being stuck "
            "(not just a normal in-progress update), should be flagged. You "
            "escalate sparingly and precisely — flagging every task as "
            "blocked makes the alert meaningless, so you only flag what the "
            "evidence actually supports."
        ),
        llm=_get_llm(),
        verbose=False,
        allow_delegation=False,
    )


def _build_task(agent: Agent, blocker_context: dict) -> Task:
    return Task(
        description=(
            "Here is a hackathon team's current tasks and their most recent "
            "check-ins, newest first:\n\n"
            f"{json.dumps(blocker_context, default=str)}\n\n"
            "For each task, judge whether it is blocked or slipping — either "
            "because it has 2 or more consecutive check-ins missing/absent "
            "relative to other active tasks, or because a check-in's text "
            "reads as the person being stuck (e.g. describing being unable "
            "to proceed, repeating the same unresolved problem, or asking "
            "for help). List every task you judge as blocked with a specific "
            "one-sentence reason. Decide should_escalate=true only if at "
            "least one task meets the rule above; otherwise false. If "
            "should_escalate is true, write a short, direct message suitable "
            "for posting straight into the team's group chat, tagging the "
            "relevant person by their name from assigned_to.\n\n"
            "Output ONLY valid JSON matching this exact schema, no markdown "
            "fences, no commentary before or after:\n\n"
            f"{EXPECTED_JSON_SHAPE}"
        ),
        expected_output="A single JSON object matching the exact schema given, nothing else.",
        agent=agent,
    )


def _parse_json_response(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[blocker] JSON parse failed: {e}\nRaw response was:\n{raw_text}")
        return {"blocked_tasks": [], "should_escalate": False, "escalation_message": ""}


def run_blocker_check(team_id: int) -> dict:
    """
    Synchronous entry point — this is the only function main.py,
    scheduler.py, or the manual /trigger-reminder/{team_id} endpoint should
    call.
    """
    team = _run_async(queries.get_team_by_id(team_id))
    if team is None:
        raise ValueError(f"run_blocker_check called with unknown team_id={team_id}")

    tasks = _run_async(queries.get_tasks(team_id))
    recent_checkins = _run_async(queries.get_recent_checkins(team_id, limit=20))

    blocker_context = {
        "tasks": [
            {
                "task_id": t["id"],
                "title": t["title"],
                "assigned_to": t["assigned_to"],
                "status": t["status"],
                "target_hour": t.get("target_hour"),
            }
            for t in tasks
        ],
        "recent_checkins": [
            {
                "task_id": c["task_id"],
                "author": c["author"],
                "message": c["message"],
                "is_blocked": c["is_blocked"],
                "created_at": c["created_at"],
            }
            for c in recent_checkins
        ],
    }

    agent = _build_agent()
    task = _build_task(agent, blocker_context)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    result = crew.kickoff()
    parsed = _parse_json_response(str(result))

    # Best-effort: mark any newly-identified blocked tasks in the DB so
    # get_tasks() reflects it on the next call. Non-fatal if a task_id in
    # the LLM's response doesn't actually exist — just skip it.
    for bt in parsed.get("blocked_tasks", []):
        task_id = bt.get("task_id")
        if isinstance(task_id, int):
            try:
                _run_async(queries.update_task_status(task_id, "blocked"))
            except Exception as e:
                print(f"[blocker] could not mark task_id={task_id} as blocked: {e}")

    return parsed


    return parsed


if __name__ == "__main__":
    import sys
    test_team_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    output = run_blocker_check(test_team_id)
    print(json.dumps(output, indent=2, default=str))