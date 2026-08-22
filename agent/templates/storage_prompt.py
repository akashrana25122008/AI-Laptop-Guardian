from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_storage_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Storage Analyzer

Tool Output:
{render_tool_data(data)}

Analyze the storage information.

Focus on:

- Disk usage
- Free space
- Temporary files
- Large files
- Recommendations

Do not invent information.
"""