from agent.ollama_client import OllamaClient
from agent.planner import Planner
from agent.tool_router import ToolRouter
from agent.result_contract import (
    ensure_result,
    is_successful_result,
)
from agent.prompt_safety import render_tool_data

from agent.templates import (
    build_storage_prompt,
    build_battery_prompt,
    build_cpu_prompt,
    build_ram_prompt,
    build_health_prompt,
    build_cleanup_prompt,
    build_file_inspector_prompt,
    build_cloud_search_prompt,
    build_cloud_download_prompt,
    build_cloud_upload_prompt,
)


# =========================================================
# PROMPT BUILDERS
# =========================================================

PROMPT_BUILDERS = {
    # Local laptop tools
    "storage": build_storage_prompt,
    "battery": build_battery_prompt,
    "cpu": build_cpu_prompt,
    "ram": build_ram_prompt,
    "health": build_health_prompt,
    "cleanup": build_cleanup_prompt,
    "file_inspector": build_file_inspector_prompt,

    # Google Drive
    "cloud_search": build_cloud_search_prompt,
    "cloud_download": build_cloud_download_prompt,
    "cloud_upload": build_cloud_upload_prompt,
}


class AIAgent:
    """
    Main AI agent for AI Laptop Guardian.

    Responsibilities:

        - Understand user requests
        - Ask Planner for the correct action
        - Execute tools through ToolRouter
        - Remember the latest health report
        - Answer health follow-up questions
        - Maintain short-term Google Drive memory
        - Handle numbered Google Drive selections
        - Send tool results to Ollama
        - Return user-friendly responses
    """

    def __init__(self):

        # =====================================================
        # CORE COMPONENTS
        # =====================================================

        self.ai = OllamaClient()
        self.planner = Planner()
        self.router = ToolRouter()

        # =====================================================
        # SHORT-TERM GOOGLE DRIVE MEMORY
        # =====================================================

        self.last_cloud_matches = []

        # =====================================================
        # SHORT-TERM HEALTH MEMORY
        # =====================================================

        self.last_health_report = None

    # =========================================================
    # HEALTH MEMORY
    # =========================================================

    def _remember_health_report(self, tool_data):
        """
        Remember the latest successful HealthTool result.

        This allows follow-up questions such as:

            How is my laptop?
            Why is my score 86?
            Is my RAM okay?
            What should I fix first?

        without requiring the user to repeat the full
        health request.
        """

        if not isinstance(tool_data, dict):
            return

        if not tool_data.get("success", False):
            return

        if tool_data.get("tool") != "health":
            return

        data = tool_data.get("data")

        if isinstance(data, dict):
            self.last_health_report = tool_data

    # =========================================================
    # HEALTH FOLLOW-UP DETECTION
    # =========================================================

    def _is_health_followup(self, message):
        """
        Detect whether the user is asking a follow-up question
        about the previously generated laptop health report.
        """

        if not self.last_health_report:
            return False

        text = message.lower().strip()

        health_terms = [
            "health",
            "score",
            "cpu",
            "processor",
            "ram",
            "memory",
            "battery",
            "charge",
            "charging",
            "storage",
            "disk",
            "drive",
            "c drive",
            "d drive",
            "problem",
            "issue",
            "warning",
            "wrong",
            "fix",
            "recommend",
            "recommendation",
            "priority",
            "overall",
        ]

        question_terms = [
            "why",
            "what",
            "how",
            "is",
            "are",
            "should",
            "can",
            "which",
            "where",
        ]

        has_health_term = any(
            term in text
            for term in health_terms
        )

        has_question_term = any(
            term in text
            for term in question_terms
        )

        return (
            has_health_term
            and has_question_term
        )

    # =========================================================
    # HEALTH FOLLOW-UP RESPONSE
    # =========================================================

    def _answer_health_followup(self, user_message):
        """
        Answer a follow-up question using the latest remembered
        HealthTool report.
        """

        if not self.last_health_report:
            return (
                "I don't have a recent laptop health report. "
                "Please ask me to check your laptop health first."
            )

        prompt = f"""
You are AI Laptop Guardian.

The user previously asked for a laptop health check.

Here is the latest HealthTool report:

{render_tool_data(self.last_health_report)}

The user is now asking a follow-up question:

{user_message}

Answer the user's question using ONLY the health report
above.

IMPORTANT RULES:

1. Do not invent information.
2. Do not create a different health score.
3. Trust the overall score and component scores provided
   by HealthTool.
4. Explain the actual numbers when useful.
5. If the question is about RAM, use the RAM data.
6. If the question is about CPU, use the CPU data.
7. If the question is about battery, use the battery data.
8. If the question is about storage, use the storage data.
9. If the question asks what should be fixed first, use
   priority_issues.
10. If there are no issues for the requested component,
    clearly say that it is currently okay.
11. Do not claim battery degradation unless the data explicitly
    provides battery-health/degradation information.
12. Do not claim that disk usage will cause a crash unless
    the data explicitly says so.
13. Keep the answer concise and practical.

Answer naturally as a laptop assistant.
"""

        try:
            return self.ai.ask(prompt)

        except Exception as e:
            return (
                "I found the latest health information, "
                "but I couldn't generate the explanation.\n\n"
                f"AI error: {e}"
            )

    # =========================================================
    # DETERMINISTIC HEALTH REPORT
    # =========================================================

    def _format_health_report(self, tool_data):
        """
        Format the HealthTool result directly.

        HealthTool is the source of truth for:

            - Overall score
            - Overall status
            - Component scores
            - Component statuses
            - Priority issues
            - Recommendations

        Ollama is NOT used for these authoritative values.

        This prevents the AI from changing something such as:

            HealthTool -> 90/100
            Ollama     -> 86/100

        or confusing battery percentage with battery score.
        """

        if not isinstance(tool_data, dict):
            return str(tool_data)

        if not tool_data.get("success", False):
            return (
                "I couldn't complete the laptop health check.\n\n"
                f"Reason: {tool_data.get('error', 'Unknown error.')}"
            )

        data = tool_data.get("data", {})

        if not isinstance(data, dict):
            return (
                "The health tool returned an invalid result."
            )

        # =====================================================
        # OVERALL
        # =====================================================

        overall = data.get("overall", {})

        overall_score = overall.get(
            "score",
            "Unknown",
        )

        overall_status = overall.get(
            "status",
            "Unknown",
        )

        # =====================================================
        # COMPONENT SCORES
        # =====================================================

        component_scores = data.get(
            "component_scores",
            {},
        )

        cpu_score = component_scores.get(
            "cpu",
            "Unknown",
        )

        ram_score = component_scores.get(
            "ram",
            "Unknown",
        )

        battery_score = component_scores.get(
            "battery",
            "Unknown",
        )

        storage_score = component_scores.get(
            "storage",
            "Unknown",
        )

        # =====================================================
        # CPU
        # =====================================================

        cpu = data.get("cpu", {})
        cpu_data = (
            cpu.get("data", {})
            if isinstance(cpu, dict)
            else {}
        )

        cpu_status = cpu_data.get(
            "status",
            "Unknown",
        )

        cpu_usage = cpu_data.get(
            "usage_percent"
        )

        cpu_line = (
            f"- CPU: {cpu_score}/100 — "
            f"{str(cpu_status).upper()}"
        )

        if cpu_usage is not None:
            cpu_line += (
                f"\n  CPU usage is {cpu_usage}%."
            )

        # =====================================================
        # RAM
        # =====================================================

        ram = data.get("ram", {})
        ram_data = (
            ram.get("data", {})
            if isinstance(ram, dict)
            else {}
        )

        ram_status = ram_data.get(
            "status",
            "Unknown",
        )

        ram_usage = ram_data.get(
            "usage_percent"
        )

        ram_line = (
            f"- RAM: {ram_score}/100 — "
            f"{str(ram_status).upper()}"
        )

        if ram_usage is not None:
            ram_line += (
                f"\n  RAM usage is {ram_usage}%."
            )

        # =====================================================
        # BATTERY
        # =====================================================

        battery = data.get("battery", {})
        battery_data = (
            battery.get("data", {})
            if isinstance(battery, dict)
            else {}
        )

        battery_percent = battery_data.get(
            "percent"
        )

        charging = battery_data.get(
            "charging"
        )

        time_remaining = battery_data.get(
            "time_remaining"
        )

        battery_status_parts = []

        if battery_percent is not None:
            battery_status_parts.append(
                f"Battery level is {battery_percent}%."
            )

        if charging is True:
            battery_status_parts.append(
                "The battery is currently charging."
            )

        elif charging is False:
            battery_status_parts.append(
                "The battery is currently not charging."
            )

        if time_remaining is not None:
            if str(time_remaining).lower() == "unknown":
                battery_status_parts.append(
                    "Remaining time is unknown."
                )
            else:
                battery_status_parts.append(
                    f"Remaining time: {time_remaining}."
                )

        battery_line = (
            f"- Battery: {battery_score}/100"
        )

        # The battery tool does not provide a separate
        # battery health status, so do not invent one.
        if battery_status_parts:
            battery_line += (
                "\n  "
                + " ".join(battery_status_parts)
            )

        # =====================================================
        # STORAGE
        # =====================================================

        storage = data.get(
            "storage",
            {},
        )

        drives = storage.get(
            "drives",
            []
        ) if isinstance(storage, dict) else []

        storage_line = (
            f"- Storage: {storage_score}/100"
        )

        if drives:
            for drive in drives:

                if not isinstance(drive, dict):
                    continue

                drive_name = drive.get(
                    "drive",
                    "Unknown",
                )

                percent_used = drive.get(
                    "percent_used"
                )

                drive_status = drive.get(
                    "status",
                    "Unknown",
                )

                if percent_used is not None:

                    storage_line += (
                        f"\n  Drive {drive_name} "
                        f"is {percent_used}% used "
                        f"and marked "
                        f"{drive_status} by HealthTool."
                    )

                else:

                    storage_line += (
                        f"\n  Drive {drive_name} "
                        f"is marked "
                        f"{drive_status} by HealthTool."
                    )

        # =====================================================
        # PRIORITY ISSUES
        # =====================================================

        priority_issues = data.get(
            "priority_issues",
            []
        )

        priority_lines = []

        if priority_issues:

            for issue in priority_issues:

                if not isinstance(issue, dict):
                    continue

                priority = issue.get(
                    "priority",
                    "Unknown",
                )

                component = issue.get(
                    "component",
                    "Unknown",
                )

                message = issue.get(
                    "message",
                    "",
                )

                priority_lines.append(
                    f"- {priority}: "
                    f"{component}: "
                    f"{message}"
                )

        if not priority_lines:
            priority_lines.append(
                "No priority issues reported by HealthTool."
            )

        # =====================================================
        # RECOMMENDATIONS
        # =====================================================

        recommendations = data.get(
            "recommendations",
            []
        )

        recommendation_lines = []

        if recommendations:

            for recommendation in recommendations:

                recommendation_lines.append(
                    f"- {recommendation}"
                )

        else:

            recommendation_lines.append(
                "No specific recommendations reported "
                "by HealthTool."
            )

        # =====================================================
        # CONCLUSION
        # =====================================================

        if priority_issues:

            conclusion = (
                f"The laptop's overall health is "
                f"{str(overall_status).lower()} "
                f"with a score of "
                f"{overall_score}/100. "
                f"There "
                f"{'is' if len(priority_issues) == 1 else 'are'} "
                f"{len(priority_issues)} "
                f"priority issue"
                f"{'' if len(priority_issues) == 1 else 's'} "
                f"reported by HealthTool."
            )

        else:

            conclusion = (
                f"The laptop's overall health is "
                f"{str(overall_status).lower()} "
                f"with a score of "
                f"{overall_score}/100. "
                "HealthTool reports no priority issues."
            )

        # =====================================================
        # FINAL REPORT
        # =====================================================

        return (
            f"**Laptop Health: "
            f"{overall_score}/100 — "
            f"{str(overall_status).upper()}**\n\n"

            f"**Component Status**\n\n"

            f"{cpu_line}\n\n"

            f"{ram_line}\n\n"

            f"{battery_line}\n\n"

            f"{storage_line}\n\n"

            f"**Priority Issues**\n\n"

            + "\n".join(priority_lines)

            + "\n\n"

            + "**Recommendations**\n\n"

            + "\n".join(recommendation_lines)

            + "\n\n"

            + "**Overall Conclusion**\n\n"

            + conclusion
        )

    # =========================================================
    # GOOGLE DRIVE NUMBER EXTRACTION
    # =========================================================

    def _get_number_from_message(self, message):

        import re

        text = message.lower().strip()

        numeric_patterns = [
            r"\bnumber\s+(\d+)\b",
            r"\bfile\s+(\d+)\b",
            r"\b#\s*(\d+)\b",
            r"\bno\.?\s*(\d+)\b",
        ]

        for pattern in numeric_patterns:

            match = re.search(
                pattern,
                text,
            )

            if match:
                return int(match.group(1))

        word_numbers = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
        }

        for word, number in word_numbers.items():

            if re.search(
                rf"\b{word}\b",
                text,
            ):
                return number

        return None

    # =========================================================
    # CHECK NUMBERED DOWNLOAD REQUEST
    # =========================================================

    def _is_download_selection(self, message):

        text = message.lower().strip()

        phrases = [
            "download number",
            "download file",
            "download #",
            "download no",
            "download first",
            "download second",
            "download third",
            "download fourth",
            "download fifth",
            "download the first",
            "download the second",
            "download the third",
            "download the fourth",
            "download the fifth",
        ]

        return any(
            phrase in text
            for phrase in phrases
        )

    # =========================================================
    # REMEMBER GOOGLE DRIVE RESULTS
    # =========================================================

    def _remember_cloud_matches(self, tool_data):

        if not isinstance(
            tool_data,
            dict,
        ):
            self.last_cloud_matches = []
            return

        if not tool_data.get(
            "success",
            False,
        ):
            return

        matches = []

        if isinstance(
            tool_data.get("matches"),
            list,
        ):
            matches = tool_data["matches"]

        data = tool_data.get(
            "data",
            {},
        )

        if isinstance(data, dict):

            if isinstance(
                data.get("matches"),
                list,
            ):
                matches = data["matches"]

            elif isinstance(
                data.get("files"),
                list,
            ):
                matches = data["files"]

        self.last_cloud_matches = matches

    # =========================================================
    # DOWNLOAD SELECTED FILE
    # =========================================================

    def _download_selected_file(self, user_message):

        if not self.last_cloud_matches:

            return (
                "I don't have a previous Google Drive "
                "file list to refer to.\n\n"
                "Please search for the files first."
            )

        number = self._get_number_from_message(
            user_message
        )

        if number is None:

            return (
                "Please specify which file you want "
                "to download.\n\n"
                "Example: Download number 2"
            )

        index = number - 1

        if (
            index < 0
            or index >= len(
                self.last_cloud_matches
            )
        ):

            return (
                f"I found "
                f"{len(self.last_cloud_matches)} "
                f"matching files.\n\n"
                f"Please choose a number between "
                f"1 and {len(self.last_cloud_matches)}."
            )

        selected_file = (
            self.last_cloud_matches[index]
        )

        if not isinstance(
            selected_file,
            dict,
        ):

            return (
                "The selected Google Drive result "
                "has an invalid format."
            )

        file_id = selected_file.get(
            "id"
        )

        file_name = selected_file.get(
            "name",
            "selected file",
        )

        if not file_id:

            return (
                f"I couldn't find a valid Google Drive "
                f"ID for '{file_name}'."
            )

        try:

            tool_data = (
                self.router.google_drive
                .download_file_by_id(
                    file_id
                )
            )

        except Exception as e:

            return (
                f"I couldn't download "
                f"'{file_name}'.\n\n"
                f"Reason: {e}"
            )

        if not isinstance(
            tool_data,
            dict,
        ):

            return str(tool_data)

        if not tool_data.get(
            "success",
            False,
        ):

            error = tool_data.get(
                "error",
                "Unknown download error.",
            )

            return (
                f"I couldn't download "
                f"'{file_name}'.\n\n"
                f"Reason: {error}"
            )

        data = tool_data.get(
            "data",
            {},
        )

        path = data.get(
            "path",
            "Unknown location",
        )

        size = data.get(
            "size_bytes",
            "Unknown",
        )

        return (
            "Downloaded successfully.\n\n"
            f"File: {file_name}\n"
            f"Location: {path}\n"
            f"Size: {size} bytes"
        )

    # =========================================================
    # FORMAT GOOGLE DRIVE SEARCH RESULTS
    # =========================================================

    def _format_cloud_search_results(
        self,
        tool_data,
    ):

        if not isinstance(
            tool_data,
            dict,
        ):
            return str(tool_data)

        if not tool_data.get(
            "success",
            False,
        ):

            return (
                "I couldn't search Google Drive.\n\n"
                f"Reason: "
                f"{tool_data.get('error', 'Unknown error.')}"
            )

        matches = tool_data.get(
            "matches",
            [],
        )

        if not matches:

            return (
                "I couldn't find any matching files "
                "in your Google Drive."
            )

        self.last_cloud_matches = matches

        lines = [
            f"I found {len(matches)} "
            f"matching file(s) in Google Drive:",
            "",
        ]

        for index, match in enumerate(
            matches,
            start=1,
        ):

            name = match.get(
                "name",
                "Unknown file",
            )

            mime_type = match.get(
                "mime_type",
                "Unknown type",
            )

            size = match.get(
                "size_bytes"
            )

            if size is not None:

                lines.append(
                    f"{index}. {name} "
                    f"({mime_type}, {size} bytes)"
                )

            else:

                lines.append(
                    f"{index}. {name} "
                    f"({mime_type})"
                )

        lines.extend([
            "",
            "You can say:",
            "• Download number 1",
            "• Download number 2",
            "• Download the second one",
        ])

        return "\n".join(lines)

    # =========================================================
    # FORMAT GOOGLE DRIVE DOWNLOAD RESULT
    # =========================================================

    def _format_cloud_download_result(
        self,
        tool_data,
    ):

        if not isinstance(
            tool_data,
            dict,
        ):
            return str(tool_data)

        matches = tool_data.get(
            "matches"
        )

        if (
            isinstance(matches, list)
            and matches
        ):

            self.last_cloud_matches = matches

            lines = [
                "I found multiple matching "
                "files in your Google Drive:",
                "",
            ]

            for index, match in enumerate(
                matches,
                start=1,
            ):

                name = match.get(
                    "name",
                    "Unknown file",
                )

                size = match.get(
                    "size_bytes"
                )

                if size is not None:

                    lines.append(
                        f"{index}. {name} "
                        f"({size} bytes)"
                    )

                else:

                    lines.append(
                        f"{index}. {name}"
                    )

            lines.extend([
                "",
                "Tell me which one you want "
                "to download.",
                "Example: Download number 2",
            ])

            return "\n".join(lines)

        if not tool_data.get(
            "success",
            False,
        ):

            return (
                "I couldn't download the file.\n\n"
                f"Reason: "
                f"{tool_data.get('error', 'Unknown error.')}"
            )

        data = tool_data.get(
            "data",
            {},
        )

        return (
            "Downloaded successfully.\n\n"
            f"File: {data.get('name', 'Unknown file')}\n"
            f"Location: {data.get('path', 'Unknown location')}\n"
            f"Size: {data.get('size_bytes', 'Unknown')} bytes"
        )

    # =========================================================
    # FORMAT SIMPLE TOOL RESULT (NO PROMPT BUILDER)
    # =========================================================

    def _format_simple_result(self, tool_data):
        """
        User-friendly output for successful tools that have
        no prompt builder, such as cloud_delete.

        Only the tool's own message and key fields are shown;
        the raw internal result is never dumped.
        """

        message = tool_data.get("message")

        if message:
            return str(message)

        tool_name = tool_data.get(
            "tool",
            "request",
        )

        return (
            f"The {tool_name} operation completed "
            f"successfully."
        )

    # =========================================================
    # MAIN CHAT
    # =========================================================

    def chat(self, user_message):

        # -----------------------------------------------------
        # Validate input
        # -----------------------------------------------------

        if not isinstance(
            user_message,
            str,
        ):

            return (
                "Please provide your request as text."
            )

        user_message = user_message.strip()

        if not user_message:

            return (
                "Please tell me what you would like "
                "me to do."
            )

        # =====================================================
        # NUMBERED GOOGLE DRIVE DOWNLOAD
        # =====================================================

        if self._is_download_selection(
            user_message
        ):

            return self._download_selected_file(
                user_message
            )

        # =====================================================
        # HEALTH FOLLOW-UP
        # =====================================================

        if self._is_health_followup(
            user_message
        ):

            return self._answer_health_followup(
                user_message
            )

        # =====================================================
        # ASK PLANNER
        # =====================================================

        try:

            decision = self.planner.plan(
                user_message
            )

        except Exception as e:

            return (
                "I couldn't understand your request.\n\n"
                f"Planner error: {e}"
            )

        if not isinstance(
            decision,
            dict,
        ):

            return (
                "I couldn't determine what action "
                "you want me to perform."
            )

        tool = decision.get(
            "tool"
        )

        # =====================================================
        # GENERAL CHAT
        # =====================================================

        if tool == "chat":

            try:

                return self.ai.ask(
                    user_message
                )

            except Exception as e:

                return (
                    "I couldn't generate a response.\n\n"
                    f"AI error: {e}"
                )

        # =====================================================
        # INVALID PLANNER RESULT
        # =====================================================

        if not tool:

            return (
                "The planner did not specify a tool "
                "for this request."
            )

        # =====================================================
        # EXECUTE TOOL
        # =====================================================

        try:

            # -------------------------------------------------
            # File Inspector
            # -------------------------------------------------

            if tool == "file_inspector":

                tool_data = self.router.execute(
                    tool,
                    decision.get("path"),
                )

            # -------------------------------------------------
            # Google Drive Search
            # -------------------------------------------------

            elif tool == "cloud_search":

                tool_data = self.router.execute(
                    tool,
                    decision.get("query"),
                )

                return self._format_cloud_search_results(
                    tool_data
                )

            # -------------------------------------------------
            # Google Drive Download
            # -------------------------------------------------

            elif tool == "cloud_download":

                tool_data = self.router.execute(
                    tool,
                    decision.get("query"),
                )

                return self._format_cloud_download_result(
                    tool_data
                )

            # -------------------------------------------------
            # Google Drive Upload
            # -------------------------------------------------

            elif tool == "cloud_upload":

                tool_data = self.router.execute(
                    tool,
                    decision.get("path"),
                )

            # -------------------------------------------------
            # Google Drive Delete
            # -------------------------------------------------

            elif tool == "cloud_delete":

                tool_data = self.router.execute(
                    tool,
                    decision.get("query"),
                )

            # -------------------------------------------------
            # All local tools
            # -------------------------------------------------

            else:

                tool_data = self.router.execute(
                    tool
                )

        except Exception as e:

            return (
                f"Tool '{tool}' failed.\n\n"
                f"Reason: {e}"
            )

        # =====================================================
        # REMEMBER HEALTH REPORT
        # =====================================================

        if tool == "health":

            self._remember_health_report(
                tool_data
            )

            # =================================================
            # IMPORTANT:
            # HealthTool is authoritative.
            # Do NOT send the health result to Ollama for
            # score/status formatting.
            # =================================================

            return self._format_health_report(
                tool_data
            )

        # =====================================================
        # NORMALIZE TOOL RESULT
        # =====================================================

        # Malformed or non-dict tool output is wrapped as an
        # explicit failure so it can never reach Ollama as if
        # it were valid data.

        tool_data = ensure_result(tool_data, tool)

        # =====================================================
        # HANDLE TOOL FAILURE
        # =====================================================

        if not is_successful_result(tool_data):

            error = tool_data.get(
                "error",
                "Unknown tool error.",
            )

            return (
                f"I couldn't complete that request.\n\n"
                f"Reason: {error}"
            )

        # =====================================================
        # FIND PROMPT BUILDER
        # =====================================================

        builder = PROMPT_BUILDERS.get(
            tool
        )

        if builder is None:

            # Tools without a prompt builder (such as
            # cloud_delete) report their own user-facing
            # message instead of dumping raw internals.

            return self._format_simple_result(
                tool_data
            )

        # =====================================================
        # BUILD AI PROMPT
        # =====================================================

        try:

            prompt = builder(
                user_message,
                tool_data,
            )

        except Exception as e:

            return (
                "The tool completed successfully, "
                "but I couldn't build the AI explanation.\n\n"
                f"Prompt error: {e}\n\n"
                f"Raw result:\n{tool_data}"
            )

        # =====================================================
        # ASK OLLAMA
        # =====================================================

        try:

            return self.ai.ask(
                prompt
            )

        except Exception as e:

            return (
                "The tool completed successfully, "
                "but Ollama could not generate "
                "the final explanation.\n\n"
                f"AI error: {e}\n\n"
                f"Raw result:\n{tool_data}"
            )