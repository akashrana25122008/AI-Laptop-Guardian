from agent.ai_agent import AIAgent


def main():

    agent = AIAgent()

    print("\nAnalyzing laptop...\n")

    response = agent.analyze_laptop()

    print(response)


if __name__ == "__main__":
    main()