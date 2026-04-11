"""Claude AI integration for FinAgent."""
import json
import logging
from typing import Optional, Tuple
import anthropic
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_client: Optional[anthropic.AsyncAnthropic] = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


MODEL = "claude-sonnet-4-20250514"


async def extract_tasks_from_email(
    subject: str,
    body: str,
    sender: str,
    recipients: list[str],
    known_users: list[dict],
) -> dict:
    """
    Analyze an email and extract tasks, follow-ups, deadlines, and commitments.
    Returns a structured dict.
    """
    client = get_client()

    users_str = "\n".join(f"- {u['name']} <{u['email']}> ({u['role_type']})" for u in known_users)

    prompt = f"""You are FinAgent, an AI office manager for the Financial Division of the Bank of Israel.
Analyze the following email and extract any tasks, follow-ups, commitments, or deadlines mentioned.

Known team members:
{users_str}

Email:
From: {sender}
To/CC: {', '.join(recipients)}
Subject: {subject}
Body:
{body}

Return a JSON object with the following structure:
{{
  "tasks": [
    {{
      "title": "task title",
      "description": "details",
      "assignee_email": "email or null",
      "deadline": "YYYY-MM-DD or null",
      "priority": "critical|high|medium|low",
      "type": "task|followup|reminder"
    }}
  ],
  "implicit_commitments": ["description of commitment"],
  "mentioned_deadlines": ["deadline description"],
  "summary": "One-paragraph summary of the email's purpose"
}}

Only include items that are clearly actionable or trackable. If nothing actionable is found, return empty arrays."""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        # Extract JSON from response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception as e:
        logger.error(f"Claude email extraction error: {e}")

    return {"tasks": [], "implicit_commitments": [], "mentioned_deadlines": [], "summary": ""}


async def generate_item_summary(
    title: str,
    description: str,
    activity_log: list[str],
    item_type: str,
) -> str:
    """Generate an AI summary for a work item's current state."""
    client = get_client()

    log_text = "\n".join(activity_log[-20:]) if activity_log else "No activity yet."

    prompt = f"""Summarize the current state of this {item_type} in 2-3 sentences.

Title: {title}
Description: {description or "N/A"}
Recent activity:
{log_text}

Be concise and focus on current status, what has been done, and what remains.
Write in Hebrew if the title/description is in Hebrew, otherwise in English."""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude summary error: {e}")
        return ""


async def score_report(
    report_text: str,
    open_tasks: list[str],
    user_name: str,
) -> Tuple[int, str]:
    """
    Score a submitted status report on a 1-5 scale.
    Returns (score, reasoning).
    """
    client = get_client()

    tasks_str = "\n".join(f"- {t}" for t in open_tasks) if open_tasks else "No open tasks."

    prompt = f"""You are evaluating a status report submitted by {user_name}.

Their open tasks:
{tasks_str}

Their report:
{report_text}

Score the report on a 1-5 scale:
5 - Excellent: Covers all open tasks; specific progress described; blockers named; next steps stated
4 - Good: Covers most tasks with reasonable detail; minor gaps
3 - Adequate: Basic updates given; some tasks missing; vague language
2 - Weak: Minimal content; only one-word statuses; most tasks not addressed
1 - Missing/Empty: No report submitted or report content is empty/irrelevant

Respond with a JSON object:
{{"score": <number 1-5>, "reasoning": "<one or two sentences explaining the score>"}}"""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return int(data.get("score", 3)), data.get("reasoning", "")
    except Exception as e:
        logger.error(f"Claude report scoring error: {e}")

    return 3, "Could not score automatically."


async def parse_finagent_command(
    body: str,
    known_users: list[dict],
) -> Optional[dict]:
    """
    Parse a @FinAgent command from an email body.
    Returns structured command dict or None.
    """
    client = get_client()
    if "@finagent" not in body.lower() and "@פינאגנט" not in body:
        return None

    users_str = "\n".join(f"- {u['name']} <{u['email']}>" for u in known_users)

    prompt = f"""Parse the following email body for @FinAgent commands (the system supports Hebrew commands).

Known users:
{users_str}

Email body:
{body}

Identify the command and return JSON:
{{
  "command": "followup|create_task|create_project|reminder|set_deadline|summarize|complete|request_status|link_project|create_subtask",
  "target_person": "email or null",
  "title": "task/project title or null",
  "deadline": "YYYY-MM-DD or null",
  "project_name": "project name or null",
  "message": "reminder message or null"
}}

If no clear @FinAgent command found, return {{"command": null}}."""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception as e:
        logger.error(f"Claude command parse error: {e}")

    return None


async def generate_weekly_digest(
    stats: dict,
    completed_items: list[dict],
    overdue_items: list[dict],
    top_insights: list[str],
) -> str:
    """Generate a weekly digest email body for the Division Head."""
    client = get_client()

    prompt = f"""Generate a weekly division activity digest in Hebrew for the Division Head.

Statistics:
- Total open tasks: {stats.get('total_open', 0)}
- Completed this week: {stats.get('completed_this_week', 0)}
- Overdue: {stats.get('overdue', 0)}
- New tasks created: {stats.get('new_tasks', 0)}

Recently completed:
{chr(10).join(f"- {i['title']}" for i in completed_items[:5]) or "None"}

Overdue items:
{chr(10).join(f"- {i['title']} (assigned to {i.get('assignee', 'N/A')})" for i in overdue_items[:5]) or "None"}

Key insights:
{chr(10).join(f"- {i}" for i in top_insights) or "None"}

Write a professional, concise digest in Hebrew (2-3 paragraphs). Use clear formatting with bullet points where appropriate."""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude weekly digest error: {e}")
        return "שגיאה ביצירת הסיכום השבועי."
