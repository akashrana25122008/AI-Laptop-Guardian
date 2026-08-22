from agent.prompts import SYSTEM_PROMPT
from agent.prompt_safety import render_tool_data


def build_cleanup_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool Output:
{render_tool_data(data)}

Recommend cleanup actions.

Never delete files automatically.

Always ask for confirmation.
"""