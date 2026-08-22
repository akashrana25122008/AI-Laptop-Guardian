import psutil


class RAMTool:
    """
    Provides information about system RAM usage.
    """

    def execute(self):
        """
        Get current RAM usage and system memory information.
        """

        try:
            memory = psutil.virtual_memory()

            total_gb = round(
                memory.total / (1024 ** 3),
                2,
            )

            used_gb = round(
                memory.used / (1024 ** 3),
                2,
            )

            available_gb = round(
                memory.available / (1024 ** 3),
                2,
            )

            usage_percent = round(
                memory.percent,
                1,
            )

            # Determine RAM status
            if usage_percent >= 90:
                status = "critical"
            elif usage_percent >= 80:
                status = "high"
            elif usage_percent >= 60:
                status = "moderate"
            else:
                status = "normal"

            return {
                "success": True,
                "tool": "ram",
                "data": {
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "available_gb": available_gb,
                    "usage_percent": usage_percent,
                    "status": status,
                },
            }

        except Exception as error:
            return {
                "success": False,
                "tool": "ram",
                "error": str(error),
            }