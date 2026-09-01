"""
agents/critic.py — ScopeAndGapCritic agent (P3)

Exposes:
    run_critic(team_id: int) -> dict

Reads team context from Postgres (via db/queries.py — never imports another
teammate's module directly), runs a CrewAI agent that critiques scope and
flags missing pieces, writes the result back into the `teams` table, and
returns the same dict to the caller (P2's webhook).

Contract (frozen in Huddle kickoff doc, section 4) — do not change without
telling the group:
    {
        "mvp_features": [{"feature": str, "why_mvp": str}],
        "cut_features": [{"feature": str, "why_cut": str}],
        "missing_pieces": [{"gap": str, "why_it_matters": str}],
        "risk_note": str
    }
"""

import asyncio
import json
import os

from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM

from db import queries


from db.connection import get_main_loop


# --------------------------------------------------------------------------
# Async bridge — db/queries.py is asyncpg-based (async), but the contract in
# section 4 requires run_critic() to be a plain sync function so P2 can call
# it without awaiting. This bridges the two.
# --------------------------------------------------------------------------
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
    tasks = _run_async(queries.get_tasks(team_id))
    checkins = _run_async(queries.get_checkins(team_id))
    return {"team": team or {}, "tasks": tasks or [], "checkins": checkins or []}


def _build_agent() -> Agent:
    return Agent(
        role="Scope and Gap Critic",
        goal=(
            "Critique a hackathon team's planned scope honestly and surface "
            "missing pieces they haven't thought of yet."
        ),
        backstory=(
            "You've mentored and judged dozens of hackathon teams. You've seen "
            "demos fail because of an integration nobody built, an auth flow "
            "nobody planned, or a feature that sounded easy but wasn't. You're "
            "blunt but constructive — your job is to save the team from a bad "
            "demo, not to be nice."
        ),
        llm=_get_llm(),
        verbose=False,
        allow_delegation=False,
    )


def _build_task(agent: Agent, context: dict) -> Task:
    team = context["team"]
    tasks = context["tasks"]
    checkins = context["checkins"]

    prompt = f"""
Team: {team.get("team_name", "Unnamed team")}
Deadline: {team.get("deadline", "unknown")}
Headcount: {team.get("headcount", "unknown")}
Skills on team: {json.dumps(team.get("skills") or [])}
Features mentioned so far: {json.dumps(team.get("mvp_features") or [])}
Tasks logged: {json.dumps(tasks[:20], default=str)}
Recent check-ins: {json.dumps(checkins[-20:], default=str)}

Critique this team's scope for a time-boxed hackathon. Respond with ONLY a
JSON object — no markdown fences, no preamble, no commentary — matching
exactly this shape:

{{
  "mvp_features": [{{"feature": "string", "why_mvp": "string"}}],
  "cut_features": [{{"feature": "string", "why_cut": "string"}}],
  "missing_pieces": [{{"gap": "string", "why_it_matters": "string"}}],
  "risk_note": "string"
}}

Rules:
- mvp_features: only what's realistically demoable given headcount and deadline.
- cut_features: anything currently in scope that should be cut, with a reason.
- missing_pieces: things the team hasn't mentioned but will need (auth, error
  states, seed data, deployment, etc.) — specific to this project, not generic.
- risk_note: one or two sentences on the single biggest risk to a working demo.
- Output must be valid JSON and nothing else.
"""

    return Task(
        description=prompt,
        expected_output="A single JSON object matching the schema above, nothing else.",
        agent=agent,
    )


def _parse_llm_json(raw: str) -> dict:
    """LLM output sometimes wraps JSON in code fences — strip defensively."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def run_critic(team_id: int) -> dict:
    context = _fetch_team_context(team_id)
    agent = _build_agent()
    task = _build_task(agent, context)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    raw_result = crew.kickoff()

    try:
        result = _parse_llm_json(str(raw_result))
    except (json.JSONDecodeError, ValueError):
        # Never let a malformed LLM response take down the webhook.
        result = {
            "mvp_features": [],
            "cut_features": [],
            "missing_pieces": [],
            "risk_note": "Critic agent returned unparseable output; check logs.",
        }

    for key in ("mvp_features", "cut_features", "missing_pieces"):
        result.setdefault(key, [])
    result.setdefault("risk_note", "")

    _run_async(
        queries.update_team(
            team_id,
            mvp_features=result["mvp_features"],
            cut_features=result["cut_features"],
            missing_pieces=result["missing_pieces"],
        )
    )

    return result



if __name__ == "__main__":
    # Quick manual smoke test: python -m agents.critic <team_id>
    import sys

    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(run_critic(tid), indent=2))