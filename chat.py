from agent.ai_agent import AIAgent

agent = AIAgent()

print("=" * 50)
print("AI Laptop Guardian")
print("Type 'exit' to quit")
print("=" * 50)

while True:

    question = input("\nYou: ")

    if question.lower() == "exit":
        break

    answer = agent.chat(question)

    print("\nAI:", answer)