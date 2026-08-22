import json
from agent.prompts import SYSTEM_PROMPT


def build_battery_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Battery Analyzer

Tool Output:
{json.dumps(data, indent=2)}

Analyze the battery information.

Explain:

- Battery percentage
- Charging status
- Remaining time

Do not guess battery health.
Only use the provided information.
"""