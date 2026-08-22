from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_cleanup_preview_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Cleanup Preview (read-only, nothing was deleted)

Tool Output:
{render_tool_data(data)}

Summarize what could be cleaned after explicit user
confirmation.

Strict rules:

- Files marked protected, locked, review, or unknown are
  NOT approved for deletion. Never override their status.
- Never delete anything and never claim anything was
  deleted.
- Deletion requires an explicit user confirmation in a
  separate message; say this when candidates exist.
- Do not invent candidates or sizes.
"""

