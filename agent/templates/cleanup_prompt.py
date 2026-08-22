from agent.prompts import SYSTEM_PROMPT


def build_cleanup_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool Output:
{data}

Recommend cleanup actions.

Never delete files automatically.

Always ask for confirmation.
"""