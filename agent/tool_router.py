from agent.result_contract import (
    ensure_result,
    sanitize_error,
)

from cloud.google_drive import GoogleDriveProvider

from tools.battery.battery import BatteryTool
from tools.cpu.cpu import CPUTool
from tools.ram.ram import RAMTool
from tools.health.health import HealthTool
from tools.file_inspector.inspector import FileInspector
from tools.storage.scanner import StorageScanner


class ToolRouter:
    """
    Central tool router for AI Laptop Guardian.

    Supported tools:

        Local:
            - storage
            - battery
            - cpu
            - ram
            - health
            - file_inspector

        Google Drive:
            - cloud_search
            - cloud_upload
            - cloud_download
            - cloud_delete

    Every dispatched tool returns a normalized result:

        {
            "success": bool,
            "tool": str,
            "data": ...,
            "error": str,
        }

    A failed tool call is never converted into a fake
    success, and unexpected tool exceptions are caught here
    instead of propagating to the caller.
    """

    def __init__(self):
        # =====================================================
        # LOCAL TOOLS
        # =====================================================

        self.storage_tool = StorageScanner()
        self.battery_tool = BatteryTool()
        self.cpu_tool = CPUTool()
        self.ram_tool = RAMTool()
        self.health_tool = HealthTool()
        self.file_inspector = FileInspector()

        # =====================================================
        # GOOGLE DRIVE
        # =====================================================

        self.google_drive = GoogleDriveProvider()

    # =========================================================
    # RESULT NORMALIZATION
    # =========================================================

    def _finalize(self, tool_name, raw_result):
        """
        Normalize any tool or provider return value into the
        result contract.

        Valid results pass through unchanged. Failures always
        carry predictable error information.
        """

        result = ensure_result(raw_result, tool_name)

        if not result.get("success") and not result.get("error"):

            message = result.get("message")

            result["error"] = (
                sanitize_error(message)
                if message
                else "Tool reported failure without details."
            )

        return result

    def _run_tool(self, tool_name, func, *args, **kwargs):
        """
        Execute one tool call and normalize its result.

        Expected tool failures (returned as failure results)
        and unexpected exceptions are both converted into the
        normalized failure shape.
        """

        try:
            return self._finalize(
                tool_name,
                func(*args, **kwargs),
            )

        except Exception as e:
            return {
                "success": False,
                "tool": tool_name,
                "error": sanitize_error(e),
            }

    # =========================================================
    # MAIN ROUTER
    # =========================================================

    def execute(self, tool, argument=None):
        """
        Execute a tool selected by Planner.

        Parameters
        ----------
        tool : str
            Name of the tool.

        argument : optional
            Tool-specific argument.
        """

        if not tool:
            return {
                "success": False,
                "tool": None,
                "error": "No tool specified.",
            }

        tool = str(tool).strip().lower()

        # =====================================================
        # GOOGLE DRIVE - SEARCH
        # =====================================================

        if tool == "cloud_search":
            return self._run_tool(
                "cloud_search",
                self.google_drive.search_files,
                argument,
            )

        # =====================================================
        # GOOGLE DRIVE - UPLOAD
        # =====================================================

        if tool == "cloud_upload":
            return self._run_tool(
                "cloud_upload",
                self.google_drive.upload_file,
                argument,
            )

        # =====================================================
        # GOOGLE DRIVE - DOWNLOAD
        # =====================================================

        if tool == "cloud_download":
            return self._run_tool(
                "cloud_download",
                self.google_drive.download_file,
                argument,
            )

        # =====================================================
        # GOOGLE DRIVE - DELETE
        # =====================================================

        if tool == "cloud_delete":
            return self._run_tool(
                "cloud_delete",
                self._delete_google_drive_file,
                argument,
            )

        # =====================================================
        # BATTERY
        # =====================================================

        if tool == "battery":
            return self._execute_battery()

        # =====================================================
        # CPU
        # =====================================================

        if tool == "cpu":
            return self._execute_cpu()

        # =====================================================
        # RAM
        # =====================================================

        if tool == "ram":
            return self._execute_ram()

        # =====================================================
        # HEALTH
        # =====================================================

        if tool == "health":
            return self._execute_health()

        # =====================================================
        # STORAGE
        # =====================================================

        if tool == "storage":
            return self._execute_storage()

        # =====================================================
        # FILE INSPECTOR
        # =====================================================

        if tool == "file_inspector":
            return self._execute_file_inspector(argument)

        # =====================================================
        # UNKNOWN TOOL
        # =====================================================

        return {
            "success": False,
            "tool": tool,
            "error": f"Unknown tool: {tool}",
        }

    # =========================================================
    # GOOGLE DRIVE DELETE (CONFIRMED TARGET ONLY)
    # =========================================================

    def execute_delete_by_id(self, file_id, name=None):
        """
        Delete one exact Google Drive file by ID.

        This method is intentionally reachable ONLY through
        agent.action_safety confirmation. It never searches
        by name again, so a confirmation can never be applied
        to a different file.
        """

        if not file_id or not str(file_id).strip():
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "No confirmed Google Drive "
                    "file ID provided."
                ),
            }

        return self._run_tool(
            "cloud_delete",
            self.google_drive.delete_file_by_id,
            str(file_id).strip(),
        )

    # =========================================================
    # BATTERY
    # =========================================================

    def _execute_battery(self):
        """Execute BatteryTool."""

        return self._run_tool(
            "battery",
            self.battery_tool.execute,
        )

    # =========================================================
    # CPU
    # =========================================================

    def _execute_cpu(self):
        """Execute CPUTool."""

        return self._run_tool(
            "cpu",
            self.cpu_tool.execute,
        )

    # =========================================================
    # RAM
    # =========================================================

    def _execute_ram(self):
        """Execute RAMTool."""

        return self._run_tool(
            "ram",
            self.ram_tool.execute,
        )

    # =========================================================
    # HEALTH
    # =========================================================

    def _execute_health(self):
        """Execute HealthTool."""

        return self._run_tool(
            "health",
            self.health_tool.execute,
        )

    # =========================================================
    # STORAGE
    # =========================================================

    def _execute_storage(self):
        """
        Execute StorageScanner.

        StorageScanner does not have execute().
        We therefore use its existing methods.

        Important:
            get_drive_status() requires usage_percent.

        The previous implementation called:

            get_drive_status()

        without an argument, which caused:

            missing 1 required positional argument:
            'usage_percent'
        """

        try:
            # -------------------------------------------------
            # Get drive information
            # -------------------------------------------------

            drive_info = self.storage_tool.get_drive_info()

            # -------------------------------------------------
            # Get temporary file information
            # -------------------------------------------------

            temp_files_size = (
                self.storage_tool.get_temp_files_size()
            )

            # -------------------------------------------------
            # Normalize drive information
            # -------------------------------------------------

            drives = []

            if isinstance(drive_info, list):
                drives = drive_info

            elif isinstance(drive_info, dict):

                # Some implementations may return:
                #
                # {"drives": [...]}

                if isinstance(
                    drive_info.get("drives"),
                    list,
                ):
                    drives = drive_info["drives"]

                else:
                    drives = [drive_info]

            # -------------------------------------------------
            # Add / calculate drive status
            # -------------------------------------------------

            normalized_drives = []

            for drive in drives:

                if not isinstance(drive, dict):
                    continue

                drive_data = dict(drive)

                usage_percent = drive_data.get(
                    "percent_used"
                )

                # Some implementations may use
                # usage_percent instead.
                if usage_percent is None:
                    usage_percent = drive_data.get(
                        "usage_percent"
                    )

                # If we have a percentage, ask
                # StorageScanner for the status.
                if usage_percent is not None:

                    try:
                        drive_data["status"] = (
                            self.storage_tool.get_drive_status(
                                usage_percent
                            )
                        )

                    except Exception:
                        # Preserve an existing status
                        # if the scanner already supplied one.
                        if "status" not in drive_data:
                            drive_data["status"] = (
                                "Unknown"
                            )

                elif "status" not in drive_data:
                    drive_data["status"] = "Unknown"

                normalized_drives.append(
                    drive_data
                )

            # -------------------------------------------------
            # Return unified storage result
            # -------------------------------------------------

            return {
                "success": True,
                "tool": "storage",
                "data": {
                    "drives": normalized_drives,
                    "temp_files": temp_files_size,
                },
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "storage",
                "error": str(e),
            }

    # =========================================================
    # FILE INSPECTOR
    # =========================================================

    def _execute_file_inspector(self, path):
        """Inspect a local file."""

        if not path:
            return {
                "success": False,
                "tool": "file_inspector",
                "error": "No file path provided.",
            }

        try:
            return self._finalize(
                "file_inspector",
                self.file_inspector.inspect(path),
            )

        except Exception as e:
            return {
                "success": False,
                "tool": "file_inspector",
                "error": sanitize_error(e),
                "path": path,
            }

    # =========================================================
    # GOOGLE DRIVE DELETE
    # =========================================================

    def _delete_google_drive_file(self, query):
        """
        Safely delete a Google Drive file.

        Safety flow:

            Search
               |
            0 matches
               -> cancel

            2+ matches
               -> cancel

            1 match
               -> delete by ID
        """

        if not query or not str(query).strip():
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "No Google Drive file name "
                    "or search query provided."
                ),
            }

        query = str(query).strip()

        # -----------------------------------------------------
        # Search first
        # -----------------------------------------------------

        search_result = (
            self.google_drive.search_files(query)
        )

        if not search_result.get("success"):
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "Could not search Google Drive "
                    "before deleting."
                ),
                "details": search_result,
            }

        matches = search_result.get(
            "matches",
            [],
        )

        # -----------------------------------------------------
        # No matches
        # -----------------------------------------------------

        if not matches:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    f"No Google Drive file matched "
                    f"'{query}'."
                ),
                "query": query,
                "matches": [],
            }

        # -----------------------------------------------------
        # Multiple matches
        # -----------------------------------------------------

        if len(matches) > 1:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "Multiple Google Drive files "
                    "matched the query."
                ),
                "query": query,
                "matches": matches,
                "message": (
                    "Delete cancelled for safety. "
                    "Please specify the exact file."
                ),
            }

        # -----------------------------------------------------
        # Exactly one match
        # -----------------------------------------------------

        file_info = matches[0]

        file_id = file_info.get("id")

        file_name = file_info.get(
            "name",
            query,
        )

        if not file_id:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "The matching Google Drive file "
                    "does not contain a valid file ID."
                ),
                "match": file_info,
            }

        # -----------------------------------------------------
        # Delete by ID
        # -----------------------------------------------------

        try:
            result = (
                self.google_drive.delete_file_by_id(
                    file_id
                )
            )

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": str(e),
                "file_id": file_id,
                "name": file_name,
            }

        if not result.get("success"):
            return result

        return {
            "success": True,
            "tool": "cloud_delete",
            "data": {
                "file_id": file_id,
                "name": file_name,
            },
            "message": (
                f"Successfully deleted "
                f"'{file_name}' from Google Drive."
            ),
        }