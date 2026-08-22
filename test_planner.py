from agent.planner import Planner

planner = Planner()

questions = [
    "Analyze my storage",
    "Why is my C drive full?",
    "Check my battery health",
    "How much RAM am I using?",
    "Is my CPU overheating?",
    "Hello"
]

for question in questions:

    result = planner.plan(question)

    print("-" * 40)
    print("Question :", question)
    print("Decision :", result)