from agent.prompts import SYSTEM_PROMPT


def build_cpu_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool Output:
{data}

Analyze CPU information.
Only use the provided data.
"""