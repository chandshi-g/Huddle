from db.connection import get_pool
import json

JSONB_FIELDS = ("skills", "mvp_features", "cut_features", "missing_pieces", "roadmap")

def init_pool(pool):
    # Pool is managed globally in db/connection.py
    pass

async def get_team(chat_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM teams WHERE chat_id = $1", chat_id
    )
    return _parse_json_fields(dict(row)) if row else None

async def get_team_by_id(team_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM teams WHERE id = $1", team_id
    )
    return _parse_json_fields(dict(row)) if row else None

async def get_or_create_team(chat_id: int):
    team = await get_team(chat_id)
    if team:
        return team
    return await create_team(chat_id)

async def create_team(chat_id: int, **fields):
    pool = await get_pool()
    skills_val = fields.get("skills", {})
    row = await pool.fetchrow(
        """INSERT INTO teams (chat_id, team_name, deadline, headcount, skills)
           VALUES ($1, $2, $3, $4, $5) RETURNING *""",
        chat_id,
        fields.get("team_name"),
        fields.get("deadline"),
        fields.get("headcount"),
        skills_val,
    )
    return _parse_json_fields(dict(row))

async def update_team(team_id: int, **fields):
    if not fields:
        return await get_team_by_id(team_id)
    pool = await get_pool()
    set_clauses = []
    values = []
    for i, (key, val) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        # If string is passed for JSONB column, attempt decoding if needed
        if key in JSONB_FIELDS and isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                pass
        values.append(val)
    values.append(team_id)
    query = f"UPDATE teams SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING *"
    row = await pool.fetchrow(query, *values)
    return _parse_json_fields(dict(row)) if row else None

async def create_task(team_id: int, title: str, assigned_to: str, reasoning: str, target_hour: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO tasks (team_id, title, assigned_to, reasoning, target_hour)
           VALUES ($1, $2, $3, $4, $5) RETURNING *""",
        team_id, title, assigned_to, reasoning, target_hour,
    )
    return dict(row)

async def get_task_by_assignee(team_id: int, author: str):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM tasks WHERE team_id = $1 AND assigned_to ILIKE $2 ORDER BY created_at DESC LIMIT 1",
        team_id, f"%{author}%"
    )
    return dict(row) if row else None

async def update_task_status(task_id: int, status: str):
    pool = await get_pool()
    row = await pool.fetchrow(
        "UPDATE tasks SET status = $1 WHERE id = $2 RETURNING *",
        status, task_id
    )
    return dict(row) if row else None

async def create_checkin(task_id: int | None, team_id: int, author: str, message: str, is_blocked: bool = False):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO checkins (task_id, team_id, author, message, is_blocked)
           VALUES ($1, $2, $3, $4, $5) RETURNING *""",
        task_id, team_id, author, message, is_blocked,
    )
    return dict(row)

async def get_checkins(team_id: int):
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM checkins WHERE team_id = $1 ORDER BY created_at", team_id
    )
    return [dict(r) for r in rows]

async def get_recent_checkins(team_id: int, limit: int = 20):
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM checkins WHERE team_id = $1 ORDER BY created_at DESC LIMIT $2",
        team_id, limit
    )
    return [dict(r) for r in rows]

async def get_tasks(team_id: int):
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM tasks WHERE team_id = $1 ORDER BY created_at", team_id
    )
    return [dict(r) for r in rows]

async def log_raw_message(team_id: int, author: str, message: str):
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO raw_messages (team_id, author, message)
           VALUES ($1, $2, $3) RETURNING *""",
        team_id, author, message
    )
    return dict(row)

def _parse_json_fields(row_dict):
    if not row_dict:
        return row_dict
    for key in JSONB_FIELDS:
        if row_dict.get(key) is not None and isinstance(row_dict[key], str):
            try:
                row_dict[key] = json.loads(row_dict[key])
            except Exception:
                pass
    return row_dict