from agent.tool_router import ToolRouter


def main():

    router = ToolRouter()

    report = router.execute("storage")

    print(report)


if __name__ == "__main__":
    main()