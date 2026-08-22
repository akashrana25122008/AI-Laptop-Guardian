import psutil


class CPUTool:
    """
    Collect CPU information and usage statistics.

    This tool only reads system information.
    It NEVER modifies system settings or files.
    """

    def execute(self):
        """
        Return current CPU information.
        """

        try:
            cpu_percent = psutil.cpu_percent(interval=1)

            cpu_count_logical = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)

            frequency = psutil.cpu_freq()

            data = {
                "usage_percent": round(cpu_percent, 2),
                "logical_cores": cpu_count_logical,
                "physical_cores": cpu_count_physical,
            }

            if frequency:
                data["frequency_mhz"] = round(frequency.current, 2)
                data["min_frequency_mhz"] = round(frequency.min, 2)
                data["max_frequency_mhz"] = round(frequency.max, 2)

            if cpu_percent >= 90:
                data["status"] = "critical"

            elif cpu_percent >= 75:
                data["status"] = "high"

            elif cpu_percent >= 50:
                data["status"] = "moderate"

            else:
                data["status"] = "normal"

            return {
                "success": True,
                "tool": "cpu",
                "data": data,
            }

        except Exception as error:

            return {
                "success": False,
                "tool": "cpu",
                "error": str(error),
            }