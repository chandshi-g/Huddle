"""
telegram_client.py

Thin wrapper around python-telegram-bot. main.py and scheduler.py should
only ever send messages through send_message() here, not construct a Bot
object themselves — keeps the token/init logic in one place.
"""

import os
from telegram import Bot
# Deliberately not using parse_mode=Markdown here: LLM-generated text can
# contain characters (*, _, [, ]) that break Telegram's markdown parser and
# cause send_message to raise. Plain text is safer under time pressure.

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        _bot = Bot(token=token)
    return _bot


async def send_message(chat_id: int, text: str) -> None:
    """Sends a plain text message. Truncates to Telegram's 4096 char limit
    so a long agent response never crashes the send."""
    bot = get_bot()
    if len(text) > 4000:
        text = text[:4000] + "\n\n[...truncated]"
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(f"[telegram_client] failed to send message to {chat_id}: {e}")


def format_critic_result(result: dict) -> str:
    lines = ["🔍 *Scope Review*\n"]
    lines.append("*MVP features:*")
    for f in result.get("mvp_features", []):
        lines.append(f"• {f.get('feature')} — {f.get('why_mvp')}")
    lines.append("\n*Cut for now:*")
    for f in result.get("cut_features", []):
        lines.append(f"• {f.get('feature')} — {f.get('why_cut')}")
    lines.append("\n*Missing pieces:*")
    for g in result.get("missing_pieces", []):
        lines.append(f"• {g.get('gap')} — {g.get('why_it_matters')}")
    if result.get("risk_note"):
        lines.append(f"\n⚠️ {result['risk_note']}")
    return "\n".join(lines)


def format_planner_result(result: dict) -> str:
    lines = ["🗂️ *Tasks & Roadmap*\n", "*Tasks:*"]
    for t in result.get("tasks", []):
        lines.append(f"• {t.get('title')} → {t.get('assigned_to')} (by hr {t.get('target_hour')}) — {t.get('reasoning')}")
    lines.append("\n*Roadmap:*")
    for m in result.get("roadmap", []):
        lines.append(f"• Hr {m.get('target_hour')}: {m.get('milestone')}")
    return "\n".join(lines)


def format_pitch_result(result: dict) -> str:
    lines = [
        "🎤 *Pitch Outline*\n",
        f"*Problem:* {result.get('problem')}",
        f"*Solution:* {result.get('solution')}",
        "\n*What we built:*",
    ]
    lines += [f"• {x}" for x in result.get("what_we_built", [])]
    if result.get("not_demoed"):
        lines.append("\n*Not demoed (be honest about these):*")
        lines += [f"• {x}" for x in result["not_demoed"]]
    lines.append("\n*Demo flow:*")
    lines += [f"{i+1}. {x}" for i, x in enumerate(result.get("demo_flow", []))]
    return "\n".join(lines)
