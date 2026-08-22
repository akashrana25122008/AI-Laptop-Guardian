from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_large_files_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Large File Scanner (read-only)

Tool Output:
{render_tool_data(data)}

Explain the large-file report.

Strict rules:

- Large does not mean disposable; never claim a file is
  safe to delete.
- Only mention files from the tool output.
- Never invent paths, sizes, or files.
- File contents were not read.
"""

