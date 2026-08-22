from agent.ollama_client import OllamaClient


def main():

    ai = OllamaClient()

    print("\nLoading AI...\n")

    answer = ai.ask(
        "Introduce yourself in two short sentences. Tell me you are the AI Laptop Guardian."
    )

    print(answer)


if __name__ == "__main__":
    main()