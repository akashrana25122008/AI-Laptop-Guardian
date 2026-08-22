from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_battery_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Battery Analyzer

Tool Output:
{render_tool_data(data)}

Analyze the battery information.

Explain:

- Battery percentage
- Charging status
- Remaining time

Do not guess battery health.
Only use the provided information.
"""