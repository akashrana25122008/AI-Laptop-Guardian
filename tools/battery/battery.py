import psutil


class BatteryTool:
    """
    Reads battery information from the operating system.
    """

    def execute(self):

        battery = psutil.sensors_battery()

        if battery is None:
            return {
                "success": False,
                "tool": "battery",
                "message": "Battery not detected."
            }

        seconds = battery.secsleft

        if seconds in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED):
            remaining = "Unknown"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            remaining = f"{hours}h {minutes}m"

        return {
            "success": True,
            "tool": "battery",
            "data": {
                "percent": battery.percent,
                "charging": battery.power_plugged,
                "time_remaining": remaining
            }
        }