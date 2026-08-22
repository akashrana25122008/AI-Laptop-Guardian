from agent.tool_router import ToolRouter


def main():

    router = ToolRouter()

    report = router.get_storage_report()

    print(report)


if __name__ == "__main__":
    main()