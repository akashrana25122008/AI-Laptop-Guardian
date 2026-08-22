from tools.storage import StorageScanner, LargeFileScanner


class ConsoleUI:

    def show_drive_info(self, scanner):
        drives = scanner.get_drive_info()

        print("\n========== Drive Information ==========\n")

        if len(drives) == 0:
            print("No drives found.")
            return

        for drive in drives:

            print(f"Drive        : {drive['drive']}")
            print(f"Total Space  : {drive['total_gb']} GB")
            print(f"Used Space   : {drive['used_gb']} GB")
            print(f"Free Space   : {drive['free_gb']} GB")
            print(f"Usage        : {drive['percent_used']}%")
            print(f"Status       : {drive['status']}")
            print("-" * 45)

    def show_temp_info(self, scanner):

        temp = scanner.get_temp_files_size()

        print("\n========== Temporary Files ==========\n")

        print(f"User Temp    : {temp['user_temp_gb']} GB")
        print(f"Windows Temp : {temp['windows_temp_gb']} GB")

    def show_large_files(self):

        scanner = LargeFileScanner()

        files = scanner.scan()

        print("\n========== Large Files ==========\n")

        if len(files) == 0:
            print("No files larger than 500 MB found.")
            return

        for index, file in enumerate(files, start=1):

            print(f"{index}. {file['name']}")
            print(f"   Size : {file['size_gb']} GB")
            print(f"   Path : {file['path']}")
            print()


def main():

    print("\n========== AI Laptop Guardian ==========")

    storage = StorageScanner()

    ui = ConsoleUI()

    ui.show_drive_info(storage)
    ui.show_temp_info(storage)
    ui.show_large_files()
    show_downloads()


if __name__ == "__main__":
    main()


def show_downloads():
    from tools.storage import DownloadsAnalyzer

    analyzer = DownloadsAnalyzer()

    data = analyzer.scan()

    print("\n========== Downloads Categories ==========\n")

    if not data:
        print("Downloads folder is empty.")
        return

    for category, count in sorted(data.items()):
        print(f"{category:<12} : {count}")    