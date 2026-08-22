from pathlib import Path


class DownloadsAnalyzer:
    """
    Analyzes the user's Downloads folder.
    """

    FILE_TYPES = {
        "Video": {".mp4", ".mkv", ".avi", ".mov"},
        "Archive": {".zip", ".rar", ".7z"},
        "ISO": {".iso"},
        "Installer": {".exe", ".msi"},
        "Image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
        "Document": {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".txt"},
        "Audio": {".mp3", ".wav", ".aac"},
    }

    def __init__(self):
        self.downloads = Path.home() / "Downloads"

    def categorize_file(self, extension):
        """
        Returns the category for a file extension.
        """
        extension = extension.lower()

        for category, extensions in self.FILE_TYPES.items():
            if extension in extensions:
                return category

        return "Other"

    def scan(self):
        """
        Returns a count of files by category.
        """
        result = {}

        if not self.downloads.exists():
            return result

        for file in self.downloads.rglob("*"):

            if not file.is_file():
                continue

            category = self.categorize_file(file.suffix)

            result[category] = result.get(category, 0) + 1

        return result