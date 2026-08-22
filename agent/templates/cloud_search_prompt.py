def build_cloud_search_prompt(user_message, tool_data):
    """
    Build a prompt for Google Drive search results.
    """

    return f"""
You are AI Laptop Guardian.

The user asked:

{user_message}

Google Drive search returned the following data:

{tool_data}

Analyze the search results and answer the user's request clearly.

Rules:

- Tell the user how many matching files were found.
- List the matching file names.
- Mention useful file information such as file type when available.
- Do not invent files or information.
- If no files were found, clearly say that no matching files were found.
- Keep the response concise and useful.
"""