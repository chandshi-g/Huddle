"""
agents/pitch.py

Owns the PitchCoach agent. Exposes exactly one function other modules
should call: run_pitch(team_id: int) -> dict

Contract (do not change without telling the group):
{
  "problem": str,
  "solution": str,
  "what_we_built": [str],
  "not_demoed": [str],
  "demo_flow": [str]
}

Rule this agent must never break: only summarize what check-ins actually
support. A planned MVP feature with zero supporting check-ins goes under
"not_demoed", never into the pitch body.
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
  "problem": "string",
  "solution": "string",
  "what_we_built": ["string"],
  "not_demoed": ["string"],
  "demo_flow": ["string"]
}"""


def _build_agent() -> Agent:
    return Agent(
        role="Hackathon Pitch Coach",
        goal="Turn a team's real daily check-ins into an honest pitch outline.",
        backstory=(
            "You are a pitch coach who has seen teams lose points for "
            "claiming features in their demo that were never actually built. "
            "You are strict about evidence: you only describe something as "
            "'what we built' if a check-in message actually supports it "
            "existing and working. If a planned MVP feature has zero "
            "supporting check-ins, it goes under 'not_demoed' — you never "
            "invent progress, metrics, or features to make the pitch sound "
            "more complete than the team's actual work."
        ),
        llm=_get_llm(),
        verbose=False,
        allow_delegation=False,
    )


def _build_task(agent: Agent, pitch_context: dict) -> Task:
    return Task(
        description=(
            "Here is a hackathon team's original concept, their planned MVP "
            "features, and every check-in message logged so far, in "
            "chronological order:\n\n"
            f"{json.dumps(pitch_context, default=str)}\n\n"
            "Draft a pitch outline using ONLY what the check-ins actually "
            "describe as built, tested, or working. Any planned MVP feature "
            "with no supporting check-in evidence must go under "
            "'not_demoed', not into 'what_we_built' or 'demo_flow'. Do not "
            "invent progress, numbers, or claims the check-ins don't "
            "support.\n\n"
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
        print(f"[pitch] JSON parse failed: {e}\nRaw response was:\n{raw_text}")
        return {
            "problem": "",
            "solution": "",
            "what_we_built": [],
            "not_demoed": [],
            "demo_flow": [],
        }


def run_pitch(team_id: int) -> dict:
    """
    Synchronous entry point — this is the only function main.py (or the
    manual /trigger-pitch/{team_id} endpoint) should call.
    """
    team = _run_async(queries.get_team_by_id(team_id))
    if team is None:
        raise ValueError(f"run_pitch called with unknown team_id={team_id}")

    checkins = _run_async(queries.get_checkins(team_id))

    pitch_context = {
        "team_name": team.get("team_name"),
        "mvp_features": team.get("mvp_features"),
        "checkins": [
            {"author": c["author"], "message": c["message"], "created_at": c["created_at"]}
            for c in checkins
        ],
    }

    agent = _build_agent()
    task = _build_task(agent, pitch_context)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)

    result = crew.kickoff()
    return _parse_json_response(str(result))



if __name__ == "__main__":
    import sys
    test_team_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    output = run_pitch(test_team_id)
    print(json.dumps(output, indent=2, default=str))