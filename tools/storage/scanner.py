import os
import psutil


class StorageScanner:
    """
    Handles all storage related scanning.
    """

    def get_drive_info(self):
        """
        Returns information about all accessible drives.
        """

        drives = []

        for partition in psutil.disk_partitions():

            try:
                usage = psutil.disk_usage(partition.mountpoint)

                drive = {
                    "drive": partition.device,
                    "mount": partition.mountpoint,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent_used": round(usage.percent, 1),
                    "status": self.get_drive_status(usage.percent)
                }

                drives.append(drive)

            except (
                PermissionError,
                FileNotFoundError,
                OSError
            ):
                continue

        return drives

    def get_drive_status(self, usage_percent):
        """
        Returns drive health based on usage.
        """

        if usage_percent >= 90:
            return "Critical"

        elif usage_percent >= 70:
            return "Warning"

        return "Healthy"

    def get_folder_size(self, folder_path):
        """
        Calculates folder size in GB.
        """

        total_size = 0

        if not folder_path:
            return 0

        if not os.path.exists(folder_path):
            return 0

        for root, _, files in os.walk(folder_path):

            for file in files:

                try:
                    file_path = os.path.join(root, file)

                    total_size += os.path.getsize(file_path)

                except (
                    PermissionError,
                    FileNotFoundError,
                    OSError
                ):
                    continue

        return round(total_size / (1024 ** 3), 2)

    def get_temp_files_size(self):
        """
        Returns temporary folder sizes.
        """

        user_temp = os.environ.get("TEMP")
        windows_temp = r"C:\Windows\Temp"

        return {
            "user_temp_gb": self.get_folder_size(user_temp),
            "windows_temp_gb": self.get_folder_size(windows_temp)
        }