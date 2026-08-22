from tools.cpu import CPUTool
from tools.ram import RAMTool
from tools.battery import BatteryTool
from tools.storage import StorageScanner, LargeFileScanner


class HealthTool:
    """
    Combines CPU, RAM, battery, and storage information
    into a single system health report.

    The tool also calculates:

        - Overall health score
        - Overall health status
        - Component scores
        - Priority issues
        - Recommendations

    This keeps the important health decisions deterministic
    instead of relying on the AI model to calculate them.
    """

    def __init__(self):
        self.cpu = CPUTool()
        self.ram = RAMTool()
        self.battery = BatteryTool()
        self.storage = StorageScanner()
        self.large = LargeFileScanner()

    # =========================================================
    # CPU SCORE
    # =========================================================

    def _score_cpu(self, cpu_data):
        """
        Calculate CPU health score.

        90-100 -> Excellent
        75-89  -> Good
        50-74  -> Moderate
        0-49   -> Warning
        """

        usage = cpu_data.get("usage_percent", 0)

        if usage < 50:
            return 100

        if usage < 70:
            return 85

        if usage < 85:
            return 70

        if usage < 95:
            return 50

        return 25

    # =========================================================
    # RAM SCORE
    # =========================================================

    def _score_ram(self, ram_data):
        """
        Calculate RAM health score based on memory usage.
        """

        usage = ram_data.get("usage_percent", 0)

        if usage < 60:
            return 100

        if usage < 75:
            return 85

        if usage < 85:
            return 70

        if usage < 95:
            return 50

        return 25

    # =========================================================
    # BATTERY SCORE
    # =========================================================

    def _score_battery(self, battery_data):
        """
        Calculate battery condition score.

        Note:
        This measures current battery level/availability,
        not long-term battery capacity or battery wear.
        """

        percent = battery_data.get("percent")

        if percent is None:
            return 50

        charging = battery_data.get(
            "charging",
            False,
        )

        # -----------------------------------------------------
        # Battery level
        # -----------------------------------------------------

        if percent >= 60:
            score = 100

        elif percent >= 40:
            score = 85

        elif percent >= 20:
            score = 65

        elif percent >= 10:
            score = 40

        else:
            score = 20

        # -----------------------------------------------------
        # Low battery while not charging
        # -----------------------------------------------------

        if not charging and percent < 30:
            score -= 20

        return max(0, score)

    # =========================================================
    # STORAGE SCORE
    # =========================================================

    def _score_storage(self, drives):
        """
        Calculate storage score from the worst drive.

        The most-used drive determines the storage health
        because a nearly-full system drive can affect the
        overall laptop experience.
        """

        if not drives:
            return 50

        scores = []

        for drive in drives:

            usage = drive.get(
                "percent_used",
                0,
            )

            if usage < 70:
                score = 100

            elif usage < 80:
                score = 90

            elif usage < 85:
                score = 75

            elif usage < 90:
                score = 60

            elif usage < 95:
                score = 40

            else:
                score = 20

            scores.append(score)

        return min(scores)

    # =========================================================
    # SCORE LABEL
    # =========================================================

    def _score_status(self, score):
        """
        Convert a numeric score into a readable status.
        """

        if score >= 90:
            return "Excellent"

        if score >= 75:
            return "Good"

        if score >= 60:
            return "Moderate"

        if score >= 40:
            return "Warning"

        return "Critical"

    # =========================================================
    # PRIORITY ISSUES
    # =========================================================

    def _find_priority_issues(
        self,
        cpu_data,
        ram_data,
        battery_data,
        drives,
    ):
        """
        Identify the most important current issues.
        """

        issues = []

        # -----------------------------------------------------
        # CPU
        # -----------------------------------------------------

        cpu_usage = cpu_data.get(
            "usage_percent",
            0,
        )

        if cpu_usage >= 90:

            issues.append({
                "priority": "High",
                "component": "CPU",
                "message": (
                    f"CPU usage is very high "
                    f"({cpu_usage}%)."
                ),
            })

        elif cpu_usage >= 75:

            issues.append({
                "priority": "Medium",
                "component": "CPU",
                "message": (
                    f"CPU usage is elevated "
                    f"({cpu_usage}%)."
                ),
            })

        # -----------------------------------------------------
        # RAM
        # -----------------------------------------------------

        ram_usage = ram_data.get(
            "usage_percent",
            0,
        )

        if ram_usage >= 90:

            issues.append({
                "priority": "High",
                "component": "RAM",
                "message": (
                    f"RAM usage is very high "
                    f"({ram_usage}%)."
                ),
            })

        elif ram_usage >= 80:

            issues.append({
                "priority": "Medium",
                "component": "RAM",
                "message": (
                    f"RAM usage is high "
                    f"({ram_usage}%)."
                ),
            })

        # -----------------------------------------------------
        # BATTERY
        # -----------------------------------------------------

        battery_percent = battery_data.get(
            "percent"
        )

        charging = battery_data.get(
            "charging",
            False,
        )

        if (
            battery_percent is not None
            and battery_percent <= 15
            and not charging
        ):

            issues.append({
                "priority": "High",
                "component": "Battery",
                "message": (
                    f"Battery is critically low "
                    f"({battery_percent}%) and "
                    f"the laptop is not charging."
                ),
            })

        elif (
            battery_percent is not None
            and battery_percent <= 30
            and not charging
        ):

            issues.append({
                "priority": "Medium",
                "component": "Battery",
                "message": (
                    f"Battery is low "
                    f"({battery_percent}%) and "
                    f"the laptop is not charging."
                ),
            })

        # -----------------------------------------------------
        # STORAGE
        # -----------------------------------------------------

        for drive in drives:

            usage = drive.get(
                "percent_used",
                0,
            )

            drive_name = drive.get(
                "drive",
                "Unknown",
            )

            if usage >= 95:

                issues.append({
                    "priority": "High",
                    "component": "Storage",
                    "message": (
                        f"Drive {drive_name} is "
                        f"critically full "
                        f"({usage}% used)."
                    ),
                })

            elif usage >= 85:

                issues.append({
                    "priority": "Medium",
                    "component": "Storage",
                    "message": (
                        f"Drive {drive_name} has "
                        f"high disk usage "
                        f"({usage}% used)."
                    ),
                })

            elif usage >= 80:

                issues.append({
                    "priority": "Low",
                    "component": "Storage",
                    "message": (
                        f"Drive {drive_name} is "
                        f"getting full "
                        f"({usage}% used)."
                    ),
                })

        # -----------------------------------------------------
        # Sort issues by priority
        # -----------------------------------------------------

        priority_order = {
            "High": 1,
            "Medium": 2,
            "Low": 3,
        }

        issues.sort(
            key=lambda item: priority_order.get(
                item.get("priority"),
                99,
            )
        )

        return issues

    # =========================================================
    # RECOMMENDATIONS
    # =========================================================

    def _build_recommendations(
        self,
        issues,
    ):
        """
        Generate deterministic recommendations based
        on detected issues.
        """

        recommendations = []

        for issue in issues:

            component = issue.get(
                "component"
            )

            priority = issue.get(
                "priority"
            )

            # -------------------------------------------------
            # CPU
            # -------------------------------------------------

            if component == "CPU":

                recommendations.append(
                    "Check Task Manager for applications "
                    "causing high CPU usage."
                )

            # -------------------------------------------------
            # RAM
            # -------------------------------------------------

            elif component == "RAM":

                recommendations.append(
                    "Close unnecessary applications "
                    "and browser tabs to reduce memory usage."
                )

            # -------------------------------------------------
            # Battery
            # -------------------------------------------------

            elif component == "Battery":

                if priority == "High":

                    recommendations.append(
                        "Connect the laptop to a charger "
                        "soon because the battery is critically low."
                    )

                else:

                    recommendations.append(
                        "Consider charging the laptop "
                        "before the battery becomes too low."
                    )

            # -------------------------------------------------
            # Storage
            # -------------------------------------------------

            elif component == "Storage":

                recommendations.append(
                    "Review large files, temporary files, "
                    "and unused applications on the affected drive."
                )

        # -----------------------------------------------------
        # Remove duplicate recommendations
        # -----------------------------------------------------

        unique = []

        for recommendation in recommendations:

            if recommendation not in unique:
                unique.append(recommendation)

        return unique

    # =========================================================
    # MAIN EXECUTION
    # =========================================================

    def execute(self):
        """
        Collect current system health information and
        calculate a deterministic health score.
        """

        try:

            # =================================================
            # COLLECT RAW DATA
            # =================================================

            cpu = self.cpu.execute()

            ram = self.ram.execute()

            battery = self.battery.execute()

            drives = self.storage.get_drive_info()

            temp_files = (
                self.storage.get_temp_files_size()
            )

            large_files = self.large.scan()

            storage = {
                "drives": drives,
                "temp_files": temp_files,
                "large_files": large_files,
            }

            # =================================================
            # EXTRACT DATA
            # =================================================

            cpu_data = cpu.get(
                "data",
                {},
            )

            ram_data = ram.get(
                "data",
                {},
            )

            battery_data = battery.get(
                "data",
                {},
            )

            # =================================================
            # COMPONENT SCORES
            # =================================================

            cpu_score = self._score_cpu(
                cpu_data
            )

            ram_score = self._score_ram(
                ram_data
            )

            battery_score = self._score_battery(
                battery_data
            )

            storage_score = self._score_storage(
                drives
            )

            # =================================================
            # OVERALL SCORE
            # =================================================

            overall_score = round(
                (
                    cpu_score
                    + ram_score
                    + battery_score
                    + storage_score
                ) / 4
            )

            overall_status = self._score_status(
                overall_score
            )

            # =================================================
            # PRIORITY ISSUES
            # =================================================

            priority_issues = (
                self._find_priority_issues(
                    cpu_data,
                    ram_data,
                    battery_data,
                    drives,
                )
            )

            # =================================================
            # RECOMMENDATIONS
            # =================================================

            recommendations = (
                self._build_recommendations(
                    priority_issues
                )
            )

            # =================================================
            # RETURN RESULT
            # =================================================

            return {
                "success": True,
                "tool": "health",
                "data": {
                    "overall": {
                        "score": overall_score,
                        "status": overall_status,
                    },

                    "component_scores": {
                        "cpu": cpu_score,
                        "ram": ram_score,
                        "battery": battery_score,
                        "storage": storage_score,
                    },

                    "cpu": cpu,
                    "ram": ram,
                    "battery": battery,
                    "storage": storage,

                    "priority_issues": priority_issues,

                    "recommendations": recommendations,
                },
            }

        except Exception as error:

            return {
                "success": False,
                "tool": "health",
                "error": str(error),
            }