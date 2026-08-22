from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_duplicates_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Duplicate File Scanner (read-only)

Tool Output:
{render_tool_data(data)}

Explain the duplicate-group report.

Strict rules:

- Duplicate does not mean disposable; the user decides.
- Never choose which copy to keep or remove.
- Never delete, move, or modify anything.
- Only mention groups and files from the tool output.
- File contents were never read by any AI; only hashes
  were compared deterministically.
- Do not invent duplicates, hashes, or paths.
"""

