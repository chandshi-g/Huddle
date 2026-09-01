"""
agents/planner.py — RoadmapPlanner agent (P3)

Exposes:
    run_planner(team_id: int) -> dict

Reads teams.mvp_features + skills from Postgres (via db/queries.py), runs a
CrewAI agent that splits tasks by skill and proposes time-based milestones,
writes tasks rows + roadmap back to the DB, and returns the same dict to the
caller (P2's webhook).

Contract (frozen in Huddle kickoff doc, section 4) — do not change without
telling the group:
    {
        "tasks": [{"title": str, "assigned_to": str, "reasoning": str, "target_hour": int}],
        "roadmap": [{"milestone": str, "target_hour": int}]
    }

Depends on ScopeAndGapCritic having already written mvp_features into the
teams table for this team_id (i.e. run_critic should run before run_planner
in P2's webhook / P5's integration flow).
"""

import asyncio
import json
import os

from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM

from db import queries


from db.connection import get_main_loop


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


def _get_llm() -> LLM:
    # CrewAI's LLM class routes through LiteLLM, which supports Gemini
    # natively via the "gemini/<model>" prefix + GEMINI_API_KEY env var.
    return LLM(
        model=os.environ.get("GEMINI_MODEL", "gemini/gemini-2.0-flash"),
        api_key=os.environ["GEMINI_API_KEY"],
        temperature=0.3,
    )


def _fetch_team_context(team_id: int) -> dict:
    team = _run_async(queries.get_team_by_id(team_id))
    existing_tasks = _run_async(queries.get_tasks(team_id))
    return {"team": team or {}, "existing_tasks": existing_tasks or []}


def _build_agent() -> Agent:
    return Agent(
        role="Roadmap Planner",
        goal=(
            "Turn an agreed MVP scope into a concrete, time-boxed task list "
            "split across the team's actual skills, with realistic milestones."
        ),
        backstory=(
            "You've run the planning phase of dozens of time-boxed team "
            "sprints. You know that vague tasks ('build backend') get people "
            "stuck, and that milestones need to be checkable, not aspirational. "
            "You assign work to real people based on their real skills, and you "
            "always leave buffer time before the deadline for integration and "
            "demo prep."
        ),
        llm=_get_llm(),
        verbose=False,
        allow_delegation=False,
    )


def _build_task(agent: Agent, context: dict) -> Task:
    team = context["team"]
    existing_tasks = context["existing_tasks"]

    mvp_features = team.get("mvp_features") or []
    skills = team.get("skills") or []
    deadline = team.get("deadline", "unknown")
    headcount = team.get("headcount", "unknown")

    prompt = f"""
Team headcount: {headcount}
Deadline: {deadline}
Skills on team: {json.dumps(skills)}
Agreed MVP features (from the scope critic): {json.dumps(mvp_features)}
Tasks already logged (avoid exact duplicates): {json.dumps(existing_tasks[:20], default=str)}

Break the MVP features into concrete tasks, assigned by skill, and propose a
milestone-based roadmap. Respond with ONLY a JSON object — no markdown
fences, no preamble, no commentary — matching exactly this shape:

{{
  "tasks": [{{"title": "string", "assigned_to": "string", "reasoning": "string", "target_hour": 0}}],
  "roadmap": [{{"milestone": "string", "target_hour": 0}}]
}}

Rules:
- target_hour is an integer hour offset from project start (e.g. 2, 5, 8, 10, 13).
- assigned_to should reference a skill or role present in "Skills on team",
  not a specific person's name.
- Every task needs a one-line reasoning tying it back to an MVP feature.
- roadmap should have 4-6 milestones, ending with a demo-ready milestone
  scheduled with buffer before the deadline.
- Output must be valid JSON and nothing else.
"""

    return Task(
        description=prompt,
        expected_output="A single JSON object matching the schema above, nothing else.",
        agent=agent,
    )


def _parse_llm_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def run_planner(team_id: int) -> dict:
    context = _fetch_team_context(team_id)
    agent = _build_agent()
    task = _build_task(agent, context)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    raw_result = crew.kickoff()

    try:
        result = _parse_llm_json(str(raw_result))
    except (json.JSONDecodeError, ValueError):
        result = {
            "tasks": [],
            "roadmap": [
                {"milestone": "Planner returned unparseable output; check logs.", "target_hour": 0}
            ],
        }

    result.setdefault("tasks", [])
    result.setdefault("roadmap", [])

    # Write tasks into the tasks table via P1's queries module.
    for t in result["tasks"]:
        _run_async(
            queries.create_task(
                team_id,
                title=t.get("title", ""),
                assigned_to=t.get("assigned_to", ""),
                reasoning=t.get("reasoning", ""),
                target_hour=t.get("target_hour", 0),
            )
        )

    # Write roadmap into teams table.
    _run_async(queries.update_team(team_id, roadmap=result["roadmap"]))

    return result



if __name__ == "__main__":
    # Quick manual smoke test: python -m agents.planner <team_id>
    import sys

    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(run_planner(tid), indent=2))