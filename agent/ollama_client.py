from ollama import chat


class OllamaClient:
    """
    Handles communication with the local Ollama model.
    """

    def __init__(self, model="llama3.2:3b"):
        self.model = model

    def ask(self, prompt):
        """
        Sends a prompt to Ollama and returns the response text.
        """

        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response["message"]["content"]