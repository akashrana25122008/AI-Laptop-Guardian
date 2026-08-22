import os

from agent.ollama_client import OllamaClient
from agent.planner import Planner
from agent.tool_router import ToolRouter
from agent.result_contract import (
    ensure_result,
    is_successful_result,
)
from agent.prompt_safety import render_tool_data
from agent.action_safety import (
    ActionSafety,
    is_cancellation,
)
from cloud.cloud_intelligence import format_size

from agent.templates import (
    build_storage_prompt,
    build_large_files_prompt,
    build_duplicates_prompt,
    build_cleanup_preview_prompt,
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
    "cleanup_preview": build_cleanup_preview_prompt,
    "large_files": build_large_files_prompt,
    "duplicates": build_duplicates_prompt,
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
        # DETERMINISTIC SAFETY LAYER
        #
        # Holds pending destructive actions. Natural language
        # can propose a destructive action, but only an
        # explicit confirmation phrase authorized through this
        # layer may execute it.
        # =====================================================

        self.safety = ActionSafety()

        # =====================================================
        # SHORT-TERM GOOGLE DRIVE MEMORY
        # =====================================================

        self.last_cloud_matches = []

        # =====================================================
        # SHORT-TERM HEALTH MEMORY
        # =====================================================

        self.last_health_report = None

        # =====================================================
        # PENDING DISCONNECT (EXPLICIT CONFIRMATION)
        #
        # A disconnect request never executes immediately.
        # The exact target is remembered here and the user
        # must confirm in a separate message. This state is
        # single-use and holds no secrets.
        # =====================================================

        self.pending_disconnect = None

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

            account_id = selected_file.get(
                "account_id"
            )

            if account_id:

                # The numbered pick carries its exact
                # account: the download can only hit
                # that account's isolated session.

                tool_data = (
                    self.router.execute_download_bound(
                        account_id,
                        file_id,
                    )
                )

            else:

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
    # PENDING DESTRUCTIVE ACTION HANDLING
    # =========================================================

    def _handle_pending_action(self, user_message):
        """
        Resolve a pending destructive action.

        Returns a response string when the message resolves
        the pending action (confirmation or cancellation),
        and None when the action should expire and normal
        processing should continue.
        """

        if not self.safety.has_pending():
            return None

        if is_cancellation(user_message):

            cancelled = self.safety.cancel()

            return (
                f"Cancelled. I will not delete "
                f"'{cancelled.target_name}'.\n\n"
                f"No files were changed."
            )

        confirmation = (
            self.safety.validate_confirmation(
                user_message
            )
        )

        if confirmation is not None:
            return self._execute_confirmed_deletion()

        # Any unrelated message expires the pending action
        # so stale confirmations can never be reused.

        self.safety.clear()

        return None

    def _execute_confirmed_deletion(self):
        """
        Execute a confirmed destructive action exactly once,
        against the exact confirmed target or target set.
        """

        pending = self.safety.get_pending()

        # Invalidate immediately: one confirmation is
        # valid for exactly one execution attempt.

        self.safety.clear()

        if pending.action_type == "cleanup_delete":

            return self._execute_cleanup_deletion(
                pending
            )

        try:

            result = self.router.execute_delete_by_id(
                pending.target_id,
                pending.target_name,
                account_id=pending.account_id,
            )

        except Exception as e:

            return (
                f"I couldn't delete "
                f"'{pending.target_name}'.\n\n"
                f"Reason: {e}"
            )

        result = ensure_result(
            result,
            "cloud_delete",
        )

        if is_successful_result(result):

            message = result.get("message")

            return str(message) or (
                f"Deleted '{pending.target_name}' "
                f"from Google Drive."
            )

        error = result.get(
            "error",
            "Unknown error.",
        )

        return (
            f"I couldn't delete "
            f"'{pending.target_name}'.\n\n"
            f"Reason: {error}"
        )

    def _execute_cleanup_deletion(self, pending):
        """
        Execute a confirmed local cleanup against the exact
        approved file snapshots.
        """

        approved = [dict(i) for i in pending.items]

        try:

            result = (
                self.router.execute_cleanup_deletion(
                    approved
                )
            )

        except Exception as e:

            return (
                "The cleanup could not be executed.\n\n"
                f"Reason: {e}"
            )

        result = ensure_result(
            result,
            "cleanup_delete",
        )

        data = result.get("data") or {}

        if is_successful_result(result):

            message = result.get("message")

            if message:
                return str(message)

            return (
                f"Cleanup finished. Deleted "
                f"{data.get('deleted_count', 0)} "
                f"file(s)."
            )

        error = result.get(
            "error",
            "Unknown error.",
        )

        return (
            "The cleanup was not executed.\n\n"
            f"Reason: {error}"
        )

    def _propose_local_cleanup(self):
        """
        Build a deterministic cleanup proposal WITHOUT
        deleting anything.

        The exact candidate set (path, size, mtime) is
        snapshotted now; only an explicit confirmation in a
        following message can delete exactly this set.
        """

        preview_data = self.router.execute(
            "cleanup_preview"
        )

        preview_data = ensure_result(
            preview_data,
            "cleanup_preview",
        )

        if not is_successful_result(preview_data):

            return (
                "I couldn't scan for cleanup "
                "candidates.\n\n"
                f"Reason: "
                f"{preview_data.get('error', 'Unknown error.')}"
            )

        candidates = (
            preview_data.get("data", {}).get(
                "candidates",
                [],
            )
        )

        if not candidates:

            return (
                "I found no safe temporary-file "
                "candidates to clean right now.\n\n"
                "Nothing was deleted."
            )

        # -----------------------------------------------------
        # Snapshot the exact approved set (fail-safe):
        # files that cannot be verified are excluded.
        # -----------------------------------------------------

        snapshots = []
        excluded = 0

        for candidate in candidates:

            path = candidate.get("path")

            try:
                stat = os.stat(path)

                snapshots.append(
                    {
                        "path": str(path),
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )

            except OSError:

                excluded += 1

        if not snapshots:

            return (
                "The temporary files could not be "
                "verified safely, so I will not "
                "propose any deletion.\n\n"
                "Nothing was deleted."
            )

        total_mb = round(
            sum(
                s["size_bytes"]
                for s in snapshots
            )
            / (1024 ** 2),
            2,
        )

        self.safety.propose_cleanup(snapshots)

        lines = [
            "⚠️ Proposed destructive action:\n",
            "These files can be removed:",
            "",
        ]

        for index, snapshot in enumerate(
            snapshots,
            start=1,
        ):

            size_mb = round(
                snapshot["size_bytes"] / (1024 ** 2),
                2,
            )

            lines.append(
                f"{index}. {snapshot['path']} — "
                f"{size_mb} MB"
            )

        lines.extend([
            "",
            f"Space to free: {total_mb} MB",
            "",
            "This cannot be undone.",
            "Reply 'confirm delete' to permanently "
            "delete exactly these files, or 'cancel' "
            "to stop.",
        ])

        if excluded:

            lines.append(
                f"({excluded} additional file(s) could "
                f"not be verified and were not included.)"
            )

        return "\n".join(lines)

    # =========================================================
    # MULTI-ACCOUNT CLOUD HELPERS
    # =========================================================

    def _list_accounts_message(self, intro):
        """
        Deterministic listing of connected accounts for
        disambiguation. Never selects an account.
        """

        lines = [intro, "", "Connected accounts:", ""]

        accounts = (
            self.router.describe_connected_accounts()
        )

        if not accounts:

            lines.append(
                "(No connected Google Drive accounts "
                "are registered.)"
            )

        else:

            for index, account in enumerate(
                accounts,
                start=1,
            ):

                lines.append(
                    f"{index}. "
                    f"{account.get('label', account.get('id'))}"
                )

        lines.extend([
            "",
            "Example: Search account 1",
        ])

        return "\n".join(lines)

    def _explain_account_download(self, selector):
        """
        An account-referenced download without a previous
        exact search result never guesses; it explains the
        safe path instead.
        """

        return (
            "To download from that account, first search "
            "so the file is exact, then pick it by "
            "number.\n\n"
            "Example:\n"
            f"  Search {selector} for report.pdf\n"
            "  Download number 1"
        )

    def _handle_cloud_search(self, decision):
        """
        Execute a cloud search with deterministic account
        scoping and format the result.

            - explicit account reference -> only that
              account,
            - 'all ... drives' wording -> every connected
              account,
            - exactly one connected account -> that one,
            - multiple connected accounts, none named ->
              needs_selection prompt,
            - no registered accounts -> legacy
              single-provider behavior.
        """

        refs = decision.get("account_refs") or []

        selector = refs[0] if refs else None

        scope_all = (
            decision.get("scope") == "all"
        )

        tool_data = (
            self.router.execute_cloud_search_scoped(
                decision.get("query"),
                selector=selector,
                scope_all=scope_all,
            )
        )

        tool_data = ensure_result(
            tool_data,
            "cloud_search",
        )

        self._remember_cloud_matches(tool_data)

        # -----------------------------------------------------
        # Multiple connected accounts, none named:
        # ask which one instead of guessing.
        # -----------------------------------------------------

        if tool_data.get("needs_selection"):

            lines = [
                "I found multiple connected Google Drive "
                "accounts.",
                "",
                "Which account should I use?",
                "",
            ]

            for index, account in enumerate(
                tool_data.get("accounts", []),
                start=1,
            ):

                lines.append(
                    f"{index}. "
                    f"{account.get('label', account.get('id'))}"
                )

            lines.extend([
                "",
                "You can also say: Search all my drives",
            ])

            return "\n".join(lines)

        if not is_successful_result(tool_data):

            reason = tool_data.get(
                "error",
                "Unknown error.",
            )

            return (
                "I couldn't search Google Drive.\n\n"
                f"Reason: {reason}"
            )

        matches = tool_data.get("matches", [])

        if not matches:

            data = tool_data.get("data")

            if isinstance(data, dict):

                matches = data.get("matches", [])

        if not matches:

            return (
                "I couldn't find any matching files in "
                "your Google Drive."
            )

        lines = [
            f"I found {len(matches)} matching file(s):",
            "",
        ]

        for index, match in enumerate(
            matches,
            start=1,
        ):

            name = match.get("name", "Unknown file")

            mime = match.get(
                "mime_type",
                "Unknown type",
            )

            line = f"{index}. {name} ({mime}"

            size_bytes = match.get("size_bytes")

            if size_bytes is not None:

                line += f", {size_bytes} bytes"

            line += ")"

            label = (
                match.get("account_email")
                or match.get("account_id")
            )

            if label:

                line += f" - {label}"

            lines.append(line)

        lines.extend([
            "",
            "You can say:",
            "- Download number 1",
        ])

        return "\n".join(lines)

    # =========================================================
    # CLOUD STORAGE INTELLIGENCE (READ-ONLY, DETERMINISTIC)
    # =========================================================
    # Storage facts are authoritative numbers. Like health
    # reports, they are formatted deterministically and are
    # NEVER sent to the AI for calculation, so the AI can
    # never invent quotas, sizes, or accounts.
    # =========================================================

    def _cloud_entry_line(self, entry):
        """
        Deterministic one-line description of one
        account's storage entry.
        """

        label = entry.get(
            "label",
            entry.get("account_id", "unknown account"),
        )

        status = entry.get("status")

        if status == "failed":

            error = entry.get("error") or (
                "could not be read"
            )

            return f"{label}: failed ({error})"

        if status == "unavailable":

            return (
                f"{label}: storage information "
                f"unavailable"
            )

        storage = entry.get("storage") or {}

        used = storage.get("used_bytes")

        free = storage.get("free_bytes")

        total = storage.get("total_bytes")

        parts = []

        if used is not None:

            line_part = f"{format_size(used)} used"

            if (
                total is not None
                and total > 0
            ):

                percent = (used * 100.0) / total

                line_part += (
                    f" ({percent:.0f}% used)"
                )

            parts.append(line_part)

        if free is not None:

            parts.append(
                f"{format_size(free)} free"
            )

        if total is not None:

            parts.append(
                f"of {format_size(total)} total"
            )

        if not parts:

            return (
                f"{label}: storage information "
                f"unavailable"
            )

        return f"{label}: " + ", ".join(parts)

    def _cloud_totals_lines(self, totals):
        """
        Deterministic lines describing known totals and
        explicitly excluded accounts.
        """

        lines = []

        known_used = totals.get("known_used_bytes")

        known_free = totals.get("known_free_bytes")

        excluded = totals.get("excluded_accounts") or []

        if not excluded:

            if known_used is not None:

                lines.append(
                    "Known total used: "
                    f"{format_size(known_used)}"
                )

            if known_free is not None:

                lines.append(
                    "Known total free space: "
                    f"{format_size(known_free)}"
                )

        else:

            # Incomplete data must never look complete.

            included_count = len(
                totals.get("included_account_ids") or []
            )

            lines.append(
                f"Known free space "
                f"(from {included_count} available "
                f"account(s)): "
                + (
                    format_size(known_free)
                    if known_free is not None
                    else "unknown"
                )
            )

            for account in excluded:

                reason = account.get("error") or (
                    account.get("status", "unavailable")
                )

                lines.append(
                    f"Not included: "
                    f"{account.get('label', account.get('account_id'))} "
                    f"({reason})"
                )

        return lines

    def _handle_cloud_storage(self, decision):
        """
        Deterministic cloud storage quota/summary answer.
        """

        selector = decision.get("selector")

        if selector:

            tool_data = (
                self.router.execute_cloud_storage(
                    selector=selector,
                )
            )

        else:

            tool_data = (
                self.router.execute_cloud_storage()
            )

        tool_data = ensure_result(
            tool_data,
            "cloud_storage",
        )

        if tool_data.get("needs_selection"):

            return self._list_accounts_message(
                "I found multiple connected Google "
                "Drive accounts."
            )

        if not is_successful_result(tool_data):

            reason = tool_data.get(
                "error",
                "Unknown error.",
            )

            message = (
                "I couldn't read your Google Drive "
                f"storage.\n\nReason: {reason}"
            )

            accounts = tool_data.get("accounts")

            if accounts:

                listed = self._list_accounts_message(
                    ""
                )

                message += "\n\n" + listed.strip()

            return message

        # Single-account result vs multi-account summary.

        if "entry" in tool_data:

            entries = [tool_data["entry"]]

            totals = {
                "known_used_bytes": entries[0][
                    "storage"
                ]["used_bytes"],
                "known_free_bytes": entries[0][
                    "storage"
                ]["free_bytes"],
                "included_account_ids": [
                    entries[0]["account_id"]
                ],
                "excluded_accounts": [],
            }

            insights = {}

        else:

            entries = tool_data.get("accounts", [])

            totals = tool_data.get("totals") or {}

            insights = (
                tool_data.get("insights") or {}
            )

        lines = ["Cloud Storage Summary", ""]

        for entry in entries:

            lines.append(
                self._cloud_entry_line(entry)
            )

        lines.append("")

        lines.extend(
            self._cloud_totals_lines(totals)
        )

        most_free = insights.get(
            "most_free_account"
        )

        largest_used = insights.get(
            "largest_used_account"
        )

        if most_free:

            lines.append(
                f"Most free space: "
                f"{most_free.get('label')} "
                f"({format_size(most_free.get('free_bytes'))} "
                f"free)"
            )

        if largest_used:

            lines.append(
                f"Largest storage use: "
                f"{largest_used.get('label')} "
                f"({format_size(largest_used.get('used_bytes'))} "
                f"used)"
            )

        return "\n".join(lines)

    def _handle_cloud_large_files(self, decision):
        """
        Deterministic cross-account large-file report.

        Metadata only: nothing is ever downloaded to
        measure sizes.
        """

        tool_data = ensure_result(
            self.router.execute_cloud_large_files(
                min_mb=decision.get("min_mb"),
                selector=decision.get("selector"),
            ),
            "cloud_large_files",
        )

        if tool_data.get("needs_selection"):

            return self._list_accounts_message(
                "I found multiple connected Google "
                "Drive accounts."
            )

        if not is_successful_result(tool_data):

            reason = tool_data.get(
                "error",
                "Unknown error.",
            )

            return (
                "I couldn't analyze large files in "
                f"your Google Drive.\n\nReason: {reason}"
            )

        min_mb = tool_data.get("min_mb")

        files = tool_data.get("files", [])

        succeeded = tool_data.get(
            "succeeded_accounts",
            [],
        )

        header_threshold = (
            f"{min_mb:g} MB"
            if isinstance(min_mb, (int, float))
            else "the selected size"
        )

        lines = [
            f"Large cloud files over "
            f"{header_threshold} "
            f"(metadata only):",
            "",
        ]

        if not files:

            lines.append(
                "No matching large files were found."
            )

        shown = 0

        for file in files[:10]:

            shown += 1

            label = (
                file.get("account_email")
                or file.get("account_id")
                or "unknown account"
            )

            modified = file.get("modified_time")

            line = (
                f"{shown}. {file.get('name', 'Unknown file')} - "
                f"{format_size(file.get('size_bytes'))} - "
                f"{label}"
            )

            if modified:
                line += f" (modified {modified})"

            lines.append(line)

        hidden_count = len(files) - shown

        if hidden_count > 0:

            lines.append(
                f"...and {hidden_count} more."
            )

        errors = tool_data.get("account_errors") or []

        if errors:

            lines.append("")

            for error in errors:

                lines.append(
                    f"Not included: "
                    f"{error.get('account_id')} "
                    f"({error.get('error')})"
                )

        lines.extend([
            "",
            "This analysis is read-only; no files were "
            "downloaded or changed.",
        ])

        return "\n".join(lines)

    def _handle_cloud_duplicates(self, decision):
        """
        Deterministic duplicate-candidate report.

        Candidates come from name + exact size metadata
        matching. They are never called confirmed and
        nothing is ever deleted.
        """

        tool_data = ensure_result(
            self.router.execute_cloud_duplicates(
                selector=decision.get("selector"),
            ),
            "cloud_duplicates",
        )

        if tool_data.get("needs_selection"):

            return self._list_accounts_message(
                "I found multiple connected Google "
                "Drive accounts."
            )

        if not is_successful_result(tool_data):

            reason = tool_data.get(
                "error",
                "Unknown error.",
            )

            return (
                "I couldn't analyze duplicate "
                f"candidates.\n\nReason: {reason}"
            )

        groups = tool_data.get("groups", [])

        scanned = tool_data.get("files_scanned", 0)

        lines = [
            f"Possible duplicates "
            f"(scanned {scanned} file(s) by name + size):",
            "",
        ]

        if not groups:

            lines.append(
                "No duplicate candidates were found."
            )

        shown = 0

        for group in groups[:10]:

            shown += 1

            lines.append(
                f"{shown}. '{group.get('name')}' - "
                f"{format_size(group.get('size_bytes'))} - "
                f"{group.get('count')} copies "
                f"(possible duplicate)"
            )

            for copy in group.get("copies", [])[:4]:

                copy_label = (
                    copy.get("account_email")
                    or copy.get("account_id")
                    or "unknown account"
                )

                lines.append(
                    f"   - {copy_label} "
                    f"(file id {copy.get('file_id')})"
                )

            extra_copies = (
                group.get("count", 0)
                - min(len(group.get("copies", [])), 4)
            )

            if extra_copies > 0:

                lines.append(
                    f"   - ...and {extra_copies} more "
                    f"copy/copies"
                )

        hidden_groups = len(groups) - shown

        if hidden_groups > 0:

            lines.append(
                f"...and {hidden_groups} more group(s)."
            )

        total_reclaim = tool_data.get(
            "potential_reclaim_bytes"
        )

        lines.append("")

        if total_reclaim:

            lines.append(
                f"Potential duplicate space: "
                f"{format_size(total_reclaim)}"
            )

        errors = tool_data.get("account_errors") or []

        for error in errors:

            lines.append(
                f"Not included: "
                f"{error.get('account_id')} "
                f"({error.get('error')})"
            )

        lines.extend([
            "",
            "These are candidates based on name and "
            "size only - NOT confirmed duplicates.",
            "Nothing was deleted or modified.",
        ])

        return "\n".join(lines)

    def _handle_storage_overview(self):
        """
        Unified LOCAL + CLOUD storage view.

        Local disks and cloud quotas are separate
        resources; they are always reported as separate
        sections and never merged into one number.
        """

        local_result = ensure_result(
            self.router.execute("storage"),
            "storage",
        )

        cloud_result = ensure_result(
            self.router.execute_cloud_storage(),
            "cloud_storage",
        )

        lines = ["Storage Overview", "", "LOCAL"]

        if is_successful_result(local_result):

            data = local_result.get("data") or {}

            drives = data.get("drives") or []

            if not drives:

                lines.append(
                    "No local drive information was "
                    "reported."
                )

            for drive in drives:

                if not isinstance(drive, dict):
                    continue

                name = drive.get(
                    "drive",
                    drive.get("device", "drive"),
                )

                percent = drive.get(
                    "percent_used",
                    drive.get("usage_percent"),
                )

                free_gb = drive.get("free_gb")

                total_gb = drive.get("total_gb")

                line = f"{name}: "

                if percent is not None:

                    try:
                        line += (
                            f"{float(percent):.0f}% used"
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        line += "usage unknown"

                if free_gb is not None:

                    line += (
                        f" ({free_gb} GB free"
                    )

                    if total_gb is not None:

                        line += (
                            f" of {total_gb} GB"
                        )

                    line += ")"

                if percent is None and free_gb is None:

                    line += "usage unknown"

                lines.append(line)

        else:

            lines.append(
                "Local storage could not be read "
                f"({local_result.get('error', 'unknown error')})."
            )

        lines.append("")
        lines.append("CLOUD")

        if is_successful_result(cloud_result):

            entries = cloud_result.get(
                "accounts",
                [],
            )

            if not entries:

                lines.append(
                    "No connected Google Drive "
                    "accounts."
                )

            for entry in entries:

                lines.append(
                    self._cloud_entry_line(entry)
                )

            lines.append("")

            lines.extend(
                self._cloud_totals_lines(
                    cloud_result.get("totals") or {}
                )
            )

        elif cloud_result.get("needs_selection"):

            lines.append(
                self._list_accounts_message(
                    "Multiple Google Drive accounts "
                    "are connected:"
                )
            )

        else:

            lines.append(
                "Cloud storage could not be read "
                f"({cloud_result.get('error', 'unknown error')})."
            )

        lines.extend([
            "",
            "Local disks and cloud quota are separate "
            "resources and are reported separately.",
        ])

        return "\n".join(lines)

    # =========================================================
    # GOOGLE ACCOUNT MANAGEMENT
    #
    # Listing is offline. Connecting opens Google's official
    # OAuth consent flow ONLY on an explicit user request.
    # Disconnecting always requires a separate explicit
    # confirmation message before anything is removed.
    # =========================================================

    def _handle_cloud_accounts(self):
        """
        Offline listing of connected Google accounts.

        No authentication is triggered here, ever: accounts
        whose stored authorization is missing are reported
        honestly instead of silently re-authenticating.
        """

        status = ensure_result(
            self.router.execute("cloud_accounts"),
            "cloud_accounts",
        )

        if not is_successful_result(status):

            return (
                "I couldn't read the account list.\n\n"
                f"Reason: "
                f"{status.get('error', 'unknown error')}"
            )

        accounts = status.get("accounts") or []

        if not accounts:

            return (
                "No Google accounts are connected yet.\n\n"
                "Say 'Connect my Google account' and I will "
                "open Google's official sign-in flow."
            )

        lines = [
            f"You have {len(accounts)} connected Google "
            f"account{'s' if len(accounts) != 1 else ''}:",
            "",
        ]

        for index, account in enumerate(accounts, 1):

            if not isinstance(account, dict):
                continue

            label = (
                account.get("label")
                or f"account {index}"
            )

            email = account.get("email", "")

            provider = account.get(
                "provider",
                "google_drive",
            )

            state = account.get(
                "status",
                "connected",
            )

            lines.append(
                f"{index}. {label} - {email} "
                f"({provider}, {state})"
            )

        return "\n".join(lines)

    def _handle_cloud_connect(self):
        """
        Connect ONE new Google account through Google's
        official OAuth consent flow.

        Reached ONLY through an explicit user request. The
        user picks their Google identity on Google's own
        screen; this application never sees a password.
        """

        result = ensure_result(
            self.router.execute("cloud_connect"),
            "cloud_connect",
        )

        if not is_successful_result(result):

            if (
                result.get("error_code")
                == "missing_credentials"
            ):

                return (
                    "Google OAuth is not set up yet.\n\n"
                    "This app needs a Google OAuth client "
                    "file named 'credentials.json'. See "
                    "DEVELOPMENT.md, Phase 17 for one-time "
                    "setup instructions."
                )

            return (
                "I couldn't connect a new Google "
                "account.\n\n"
                f"Reason: "
                f"{result.get('error', 'unknown error')}"
            )

        account = result.get("account") or {}

        label = account.get("label", "Google account")

        email = account.get("email", "")

        created_new = result.get("created_new")

        if created_new:

            intro = "Connected a new Google account"

        else:

            intro = (
                "Re-connected an existing Google "
                "account"
            )

        total = result.get("total_accounts")

        lines = [
            f"{intro}: {label} ({email}).",
        ]

        if total is not None:

            lines.extend([
                "",
                f"Connected accounts: {total}",
            ])

        return "\n".join(lines)

    def _handle_cloud_disconnect(self, decision):
        """
        Propose disconnecting exactly ONE named account.

        Nothing is disconnected here. The exact account is
        remembered and executed only after a separate
        explicit confirmation message.
        """

        selector = decision.get("selector")

        if (
            not selector
            or not str(selector).strip()
        ):

            listing = self._list_accounts_message(
                "Which account should be "
                "disconnected?"
            )

            return (
                f"{listing}\n\n"
                "Example: Disconnect account 2"
            )

        resolved = (
            self.router.drive_manager.registry
            .resolve_selector(str(selector).strip())
        )

        if (
            resolved is None
            or not resolved.is_connected()
        ):

            listing = self._list_accounts_message(
                f"I couldn't find a connected account "
                f"for '{selector}'."
            )

            return (
                f"{listing}\n\n"
                "Nothing was disconnected."
            )

        self.pending_disconnect = {
            "account_id": resolved.id,
            "label": resolved.safe_label(),
            "email": resolved.email,
        }

        label = resolved.safe_label()

        email = resolved.email

        return (
            f"Disconnect {label} ({email})?\n\n"
            "This removes THIS application's stored "
            "authorization for that account only. It never "
            "deletes files from Google Drive or from this "
            "computer, and it never touches your other "
            "accounts.\n\n"
            "Reply 'confirm disconnect' to proceed or "
            "'cancel' to keep it connected."
        )

    def _handle_pending_disconnect_response(
        self,
        user_message,
    ):
        """
        Resolve a pending disconnect request.

        Only an explicit confirmation phrase executes the
        disconnect of the EXACT remembered account. Any
        other reply cancels; nothing ambiguous ever runs.

        Returns None when no disconnect is pending.
        """

        if self.pending_disconnect is None:

            return None

        target = self.pending_disconnect

        # Single-use: consumed whether confirmed or not.

        self.pending_disconnect = None

        text = user_message.strip().lower()

        confirmed = text in {
            "confirm disconnect",
            "yes disconnect",
            "yes",
            "confirm",
            "proceed",
            "disconnect",
        }

        if not confirmed:

            return (
                "Cancelled. Nothing was disconnected; "
                f"{target['label']} stays connected."
            )

        result = ensure_result(
            self.router.execute(
                "cloud_disconnect",
                target["account_id"],
            ),
            "cloud_disconnect",
        )

        if not is_successful_result(result):

            return (
                "I couldn't complete the disconnect.\n\n"
                f"Reason: "
                f"{result.get('error', 'unknown error')}"
            )

        local_removed = result.get(
            "local_authorization_removed"
        )

        lines = [
            f"Disconnected {target['label']} "
            f"({target['email']}).",
        ]

        if local_removed:

            lines.extend([
                "",
                "Its stored authorization was removed "
                "from this computer.",
            ])

        else:

            lines.extend([
                "",
                "Note: a leftover authorization file could "
                "not be removed automatically.",
            ])

        lines.extend([
            "",
            "Your other accounts were not affected, and no "
            "files were deleted.",
        ])

        return "\n".join(lines)

    def _propose_cloud_delete(
        self,
        query,
        selector=None,
    ):
        """
        Handle a natural-language delete request WITHOUT
        deleting anything.

        The request only produces a deterministic proposal;
        deletion requires an explicit confirmation phrase in
        a following message.
        """

        query = (
            str(query).strip()
            if query and str(query).strip()
            else ""
        )

        if not query:

            return (
                "Please tell me the exact name of the "
                "Google Drive file you want to delete.\n\n"
                "Example: Delete notes.txt from Drive"
            )

        # -----------------------------------------------------
        # Deterministic account scoping
        # -----------------------------------------------------
        # When an account is named, the search (and later
        # the confirmed deletion) is bound to exactly that
        # account. An unknown account never falls back to
        # a different one.
        #
        # With no accounts registered at all, this keeps
        # the legacy single-provider behavior.
        # -----------------------------------------------------

        account = None

        if selector is not None:

            account = self.router.resolve_account(
                selector
            )

            if account is None:

                return (
                    self._list_accounts_message(
                        "I couldn't find that "
                        "Google Drive account."
                    )
                )

            scoped = (
                self.router.execute_cloud_search_scoped(
                    query,
                    selector=selector,
                )
            )

        elif (
            self.router.drive_manager.registry.count()
            == 1
        ):

            # Exactly one connected managed account:
            # deterministic, no ambiguity possible.

            scoped = (
                self.router.execute_cloud_search_scoped(
                    query,
                )
            )

        elif (
            self.router.drive_manager.registry.count()
            > 1
        ):

            # Multiple connected accounts and none was
            # named: refuse to guess which drive to
            # delete from.

            return (
                self._list_accounts_message(
                    "Several Google Drive accounts are "
                    "connected. Please name one before "
                    "deleting anything."
                )
            )

        else:

            scoped = self.router.execute(
                "cloud_search",
                query,
            )

        search_data = ensure_result(
            scoped,
            "cloud_search",
        )

        if not is_successful_result(search_data):

            return (
                "I couldn't search Google Drive before "
                "preparing that deletion.\n\n"
                f"Reason: "
                f"{search_data.get('error', 'Unknown error.')}"
            )

        matches = search_data.get(
            "matches",
            [],
        )

        # -----------------------------------------------------
        # Zero matches stay safe
        # -----------------------------------------------------

        if not matches:

            return (
                f"I couldn't find any Google Drive file "
                f"matching '{query}'.\n\n"
                f"No files were changed."
            )

        # -----------------------------------------------------
        # Multiple matches stay safe
        # -----------------------------------------------------

        if len(matches) > 1:

            lines = [
                "Multiple Google Drive files matched. "
                "Please specify the exact file name:",
                "",
            ]

            for match in matches[:10]:

                lines.append(
                    f"• {match.get('name', 'Unknown file')}"
                )

            lines.extend([
                "",
                "Nothing has been deleted.",
            ])

            return "\n".join(lines)

        # -----------------------------------------------------
        # Exactly one match -> proposal, NOT deletion
        # -----------------------------------------------------

        target = matches[0]

        file_id = target.get("id")

        name = target.get(
            "name",
            query,
        )

        if not file_id:

            return (
                f"I found '{name}' but it does not have a "
                f"valid Google Drive ID, so I will not "
                f"delete it."
            )

        self.safety.propose_delete(
            file_id,
            name,
            account_id=(
                target.get("account_id")
                or (account["id"] if account else None)
            ),
        )

        if account:

            label = (
                account.get("email")
                or account.get("id")
            )

            return (
                f"⚠️ Proposed destructive action:\n\n"
                f"Delete '{name}' from Google Drive "
                f"account {label}.\n\n"
                f"This cannot be undone.\n\n"
                f"Reply 'confirm delete' to permanently delete "
                f"this exact file, or 'cancel' to stop."
            )

        return (
            f"⚠️ Proposed destructive action:\n\n"
            f"Delete '{name}' from Google Drive.\n\n"
            f"This cannot be undone.\n\n"
            f"Reply 'confirm delete' to permanently delete "
            f"this exact file, or 'cancel' to stop."
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
        # PENDING DESTRUCTIVE ACTION (CONFIRM / CANCEL)
        # =====================================================

        pending_response = (
            self._handle_pending_action(
                user_message
            )
        )

        if pending_response is not None:

            return pending_response

        # =====================================================
        # PENDING DISCONNECT (CONFIRM / CANCEL)
        #
        # A proposed disconnect is executed only by an
        # explicit confirmation phrase in a separate
        # message. Any other reply cancels it.
        # =====================================================

        disconnect_response = (
            self._handle_pending_disconnect_response(
                user_message
            )
        )

        if disconnect_response is not None:

            return disconnect_response

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
            #
            # Account-scoped when the request names an
            # account or asks for ALL connected accounts;
            # otherwise unchanged single-provider behavior
            # (or a needs_selection prompt when multiple
            # accounts are connected and none is named).
            # -------------------------------------------------

            elif tool == "cloud_search":

                return self._handle_cloud_search(
                    decision
                )

            # -------------------------------------------------
            # Google Drive Download
            #
            # An account-referenced download never guesses
            # which file is meant; it asks for an exact
            # numbered pick instead. Numbered picks carry
            # their account identity end to end.
            # -------------------------------------------------

            elif tool == "cloud_download":

                refs = decision.get("account_refs")

                if refs:

                    return (
                        self._explain_account_download(
                            refs[0]
                        )
                    )

                tool_data = self.router.execute(
                    tool,
                    decision.get("query"),
                )

                return self._format_cloud_download_result(
                    tool_data
                )

            # -------------------------------------------------
            # Google Drive Upload
            #
            # With an explicit account reference the
            # destination is exact. Without one, behavior is
            # unchanged (default provider). Uploading to an
            # ambiguous account never silently picks.
            # -------------------------------------------------

            elif tool == "cloud_upload":

                refs = decision.get("account_refs")

                if refs:

                    destination = (
                        self.router.resolve_account(
                            refs[0]
                        )
                    )

                    if destination is None:

                        return (
                            self._list_accounts_message(
                                "I couldn't find "
                                "that Google Drive "
                                "account."
                            )
                        )

                    tool_data = (
                        self.router.drive_manager
                        .upload_to_account(
                            destination["id"],
                            decision.get("path"),
                        )
                    )

                else:

                    tool_data = self.router.execute(
                        tool,
                        decision.get("path"),
                    )

            # -------------------------------------------------
            # Google Drive Delete
            #
            # Natural language NEVER deletes directly.
            # This only proposes the deletion and waits for
            # an explicit confirmation phrase handled by
            # agent.action_safety.
            # -------------------------------------------------

            elif tool == "cloud_delete":

                refs = decision.get("account_refs")

                selector = refs[0] if refs else None

                return self._propose_cloud_delete(
                    decision.get("query"),
                    selector=selector,
                )

            # -------------------------------------------------
            # Local Cleanup Delete
            #
            # Same principle: propose only, never delete.
            # The exact candidate set is snapshotted and the
            # user must confirm explicitly.
            # -------------------------------------------------

            elif tool == "cleanup_delete":

                return self._propose_local_cleanup()

            # -------------------------------------------------
            # Cloud Storage Intelligence (READ-ONLY)
            #
            # Deterministic analytics: quota summaries,
            # large-file metadata, duplicate candidates,
            # and the unified local+cloud overview.
            # These never mutate cloud or local data, so
            # they are answered deterministically without
            # AI calculation.
            # -------------------------------------------------

            elif tool == "cloud_storage":

                return self._handle_cloud_storage(
                    decision
                )

            elif tool == "cloud_large_files":

                return self._handle_cloud_large_files(
                    decision
                )

            elif tool == "cloud_duplicates":

                return self._handle_cloud_duplicates(
                    decision
                )

            elif tool == "storage_overview":

                return self._handle_storage_overview()

            # -------------------------------------------------
            # Google Account Management (EXPLICIT ONLY)
            #
            # Listing is offline. Connecting runs Google's
            # official OAuth flow only because the user
            # explicitly asked. Disconnecting only proposes;
            # it executes after a separate confirmation.
            # -------------------------------------------------

            elif tool == "cloud_accounts":

                return self._handle_cloud_accounts()

            elif tool == "cloud_connect":

                return self._handle_cloud_connect()

            elif tool == "cloud_disconnect":

                return self._handle_cloud_disconnect(
                    decision
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