import json
from agent.prompts import SYSTEM_PROMPT


def build_storage_prompt(user_message, data):

    return f"""
{SYSTEM_PROMPT}

User Request:
{user_message}

Tool:
Storage Analyzer

Tool Output:
{json.dumps(data, indent=2)}

Analyze the storage information.

Focus on:

- Disk usage
- Free space
- Temporary files
- Large files
- Recommendations

Do not invent information.
"""