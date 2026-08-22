from agent.prompt_safety import render_tool_data


def build_cloud_upload_prompt(user_message, tool_data):
    """
    Builds the AI prompt for Google Drive upload results.
    """

    return f"""
You are Laptop Guardian, an AI laptop assistant.

The user requested:
{user_message}

Google Drive upload result:
{render_tool_data(tool_data)}

Respond clearly and concisely.

If the upload was successful:
- Tell the user the file was uploaded successfully.
- Mention the file name.
- Mention the Google Drive link if available.
- Mention the local file path if available.

If the upload failed:
- Clearly explain why it failed.
- If the file already exists, tell the user that the upload was cancelled to prevent a duplicate.
- If appropriate, suggest what the user should do next.

Do not invent information that is not present in the tool result.
"""