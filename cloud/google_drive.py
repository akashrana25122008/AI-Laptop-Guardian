
import os
import mimetypes
from pathlib import Path

import requests

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


class GoogleDriveProvider:
    """
    Google Drive provider for AI Laptop Guardian.

    Supports:
        - Google Drive authentication
        - File search
        - File metadata
        - Download by file ID
        - Download by search query
        - File upload
        - Duplicate upload protection
        - File deletion by ID
        - File deletion by search query
        - Recent files
    """

    SCOPES = [
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(
        self,
        credentials_file="credentials.json",
        token_file="token.json",
        download_dir="downloads",
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.download_dir = Path(download_dir)

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.service = None
        self.credentials = None

        self.authenticate()

    # =========================================================
    # AUTHENTICATION
    # =========================================================

    def authenticate(self):
        """Authenticate with Google Drive."""

        creds = None

        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(
                    self.token_file,
                    self.SCOPES,
                )
            except Exception:
                creds = None

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:

            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(
                    "Google credentials file not found: "
                    f"{self.credentials_file}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file,
                self.SCOPES,
            )

            creds = flow.run_local_server(
                port=0
            )

            with open(
                self.token_file,
                "w",
                encoding="utf-8",
            ) as token:
                token.write(
                    creds.to_json()
                )

        self.credentials = creds

        self.service = build(
            "drive",
            "v3",
            credentials=creds,
        )

        return True

    # =========================================================
    # SEARCH FILES
    # =========================================================

    def search_files(self, query):
        """Search Google Drive files by name."""

        if not query:
            return {
                "success": False,
                "tool": "cloud_search",
                "error": (
                    "No Google Drive search query provided."
                ),
            }

        if self.service is None:
            self.authenticate()

        safe_query = query.replace(
            "'",
            "\\'",
        )

        drive_query = (
            "trashed = false and "
            f"name contains '{safe_query}'"
        )

        try:
            response = (
                self.service.files()
                .list(
                    q=drive_query,
                    spaces="drive",
                    fields=(
                        "files("
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "createdTime,"
                        "modifiedTime,"
                        "webViewLink"
                        ")"
                    ),
                    orderBy="modifiedTime desc",
                    pageSize=50,
                )
                .execute()
            )

            files = response.get(
                "files",
                [],
            )

            matches = []

            for file in files:
                matches.append(
                    {
                        "id": file.get("id"),
                        "name": file.get("name"),
                        "mime_type": file.get(
                            "mimeType"
                        ),
                        "size_bytes": int(
                            file.get(
                                "size",
                                0,
                            )
                        ),
                        "created_time": file.get(
                            "createdTime"
                        ),
                        "modified_time": file.get(
                            "modifiedTime"
                        ),
                        "web_view_link": file.get(
                            "webViewLink"
                        ),
                    }
                )

            return {
                "success": True,
                "tool": "cloud_search",
                "query": query,
                "count": len(matches),
                "matches": matches,
                "message": (
                    f"Found {len(matches)} matching file(s)."
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_search",
                "query": query,
                "error": str(e),
            }

    # =========================================================
    # GET FILE
    # =========================================================

    def get_file_by_id(self, file_id):
        """Get metadata for a Google Drive file."""

        if not file_id:
            return {
                "success": False,
                "tool": "cloud_file",
                "error": "No file ID provided.",
            }

        if self.service is None:
            self.authenticate()

        try:
            file = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields=(
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "createdTime,"
                        "modifiedTime,"
                        "webViewLink"
                    ),
                )
                .execute()
            )

            return {
                "success": True,
                "tool": "cloud_file",
                "data": {
                    "id": file.get("id"),
                    "name": file.get("name"),
                    "mime_type": file.get(
                        "mimeType"
                    ),
                    "size_bytes": int(
                        file.get(
                            "size",
                            0,
                        )
                    ),
                    "created_time": file.get(
                        "createdTime"
                    ),
                    "modified_time": file.get(
                        "modifiedTime"
                    ),
                    "web_view_link": file.get(
                        "webViewLink"
                    ),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_file",
                "error": str(e),
            }

    # =========================================================
    # DOWNLOAD BY ID
    # =========================================================

    def download_file_by_id(self, file_id):
        """
        Download a Google Drive file by ID.

        Uses the authenticated Google Drive REST endpoint
        directly so the actual binary file is retrieved.
        """

        if not file_id:
            return {
                "success": False,
                "tool": "cloud_download",
                "error": (
                    "No Google Drive file ID provided."
                ),
            }

        if self.service is None:
            self.authenticate()

        try:
            metadata = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields=(
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "createdTime,"
                        "modifiedTime"
                    ),
                )
                .execute()
            )

            file_name = metadata.get(
                "name",
                "downloaded_file",
            )

            mime_type = metadata.get(
                "mimeType",
                "application/octet-stream",
            )

            expected_size = int(
                metadata.get(
                    "size",
                    0,
                )
            )

            if mime_type.startswith(
                "application/vnd.google-apps."
            ):
                return {
                    "success": False,
                    "tool": "cloud_download",
                    "error": (
                        "Google Workspace files require "
                        "export instead of direct download."
                    ),
                    "file_id": file_id,
                    "mime_type": mime_type,
                }

            if (
                self.credentials.expired
                and self.credentials.refresh_token
            ):
                self.credentials.refresh(
                    Request()
                )

                with open(
                    self.token_file,
                    "w",
                    encoding="utf-8",
                ) as token:
                    token.write(
                        self.credentials.to_json()
                    )

            access_token = self.credentials.token

            url = (
                "https://www.googleapis.com/"
                "drive/v3/files/"
                f"{file_id}"
            )

            headers = {
                "Authorization": (
                    f"Bearer {access_token}"
                )
            }

            response = requests.get(
                url,
                headers=headers,
                params={"alt": "media"},
                stream=True,
                timeout=120,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "tool": "cloud_download",
                    "error": (
                        "Google Drive download request failed."
                    ),
                    "status_code": response.status_code,
                    "response": response.text[:500],
                }

            data = response.content
            actual_size = len(data)

            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            if (
                "application/json" in content_type
                and actual_size != expected_size
            ):
                return {
                    "success": False,
                    "tool": "cloud_download",
                    "error": (
                        "Google Drive returned metadata "
                        "instead of the actual file."
                    ),
                    "expected_size": expected_size,
                    "actual_size": actual_size,
                    "content_type": content_type,
                    "response_preview": (
                        data[:500].decode(
                            "utf-8",
                            errors="replace",
                        )
                    ),
                }

            if (
                expected_size > 0
                and actual_size != expected_size
            ):
                return {
                    "success": False,
                    "tool": "cloud_download",
                    "error": (
                        "Downloaded file size does not "
                        "match Google Drive."
                    ),
                    "expected_size": expected_size,
                    "actual_size": actual_size,
                    "content_type": content_type,
                }

            local_path = (
                self.download_dir
                / file_name
            )

            local_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                local_path,
                "wb",
            ) as file_handle:
                file_handle.write(data)

            disk_size = (
                local_path.stat().st_size
            )

            if (
                expected_size > 0
                and disk_size != expected_size
            ):

                try:
                    local_path.unlink()
                except Exception:
                    pass

                return {
                    "success": False,
                    "tool": "cloud_download",
                    "error": (
                        "Downloaded file was not written "
                        "correctly."
                    ),
                    "expected_size": expected_size,
                    "actual_size": disk_size,
                }

            return {
                "success": True,
                "tool": "cloud_download",
                "data": {
                    "file_id": file_id,
                    "name": file_name,
                    "path": str(local_path),
                    "mime_type": mime_type,
                    "size_bytes": disk_size,
                },
                "message": (
                    f"Successfully downloaded "
                    f"'{file_name}'."
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_download",
                "error": str(e),
                "file_id": file_id,
            }

    # =========================================================
    # DOWNLOAD BY QUERY
    # =========================================================

    def download_file(
        self,
        query,
        local_path=None,
    ):
        """
        Search for a Google Drive file and download it.

        Multiple matches are returned so AIAgent can ask
        the user to choose one.
        """

        if not query:
            return {
                "success": False,
                "tool": "cloud_download",
                "error": (
                    "No download query provided."
                ),
            }

        search_result = (
            self.search_files(query)
        )

        if not search_result.get(
            "success"
        ):
            return search_result

        matches = search_result.get(
            "matches",
            [],
        )

        if not matches:
            return {
                "success": False,
                "tool": "cloud_download",
                "query": query,
                "error": (
                    "No Google Drive files matched the query."
                ),
                "message": (
                    f"No files found for '{query}'."
                ),
            }

        if len(matches) > 1:
            return {
                "success": False,
                "tool": "cloud_download",
                "query": query,
                "error": (
                    "Multiple Google Drive files "
                    "matched the query."
                ),
                "matches": matches,
                "message": (
                    "Please select one of the matching files."
                ),
            }

        file_id = matches[0].get(
            "id"
        )

        return self.download_file_by_id(
            file_id
        )

    # =========================================================
    # UPLOAD
    # =========================================================

    def upload_file(self, local_path):
        """Upload a local file to Google Drive."""

        if not local_path:
            return {
                "success": False,
                "tool": "cloud_upload",
                "error": (
                    "No local file path provided."
                ),
            }

        path = Path(local_path)

        if not path.is_absolute():
            path = Path.cwd() / path

        path = path.resolve()

        if not path.exists():
            return {
                "success": False,
                "tool": "cloud_upload",
                "error": (
                    f"Local file not found: {path}"
                ),
            }

        if not path.is_file():
            return {
                "success": False,
                "tool": "cloud_upload",
                "error": (
                    f"Path is not a file: {path}"
                ),
            }

        if self.service is None:
            self.authenticate()

        file_name = path.name

        mime_type, _ = mimetypes.guess_type(
            str(path)
        )

        if not mime_type:
            mime_type = (
                "application/octet-stream"
            )

        safe_name = file_name.replace(
            "'",
            "\\'",
        )

        duplicate_query = (
            "trashed = false and "
            f"name = '{safe_name}'"
        )

        try:
            existing = (
                self.service.files()
                .list(
                    q=duplicate_query,
                    spaces="drive",
                    fields=(
                        "files("
                        "id,"
                        "name,"
                        "mimeType,"
                        "size"
                        ")"
                    ),
                    pageSize=20,
                )
                .execute()
            )

            duplicates = existing.get(
                "files",
                [],
            )

            if duplicates:

                matches = []

                for file in duplicates:
                    matches.append(
                        {
                            "id": file.get(
                                "id"
                            ),
                            "name": file.get(
                                "name"
                            ),
                            "mime_type": file.get(
                                "mimeType"
                            ),
                            "size_bytes": int(
                                file.get(
                                    "size",
                                    0,
                                )
                            ),
                        }
                    )

                return {
                    "success": False,
                    "tool": "cloud_upload",
                    "error": (
                        "A file with the same name "
                        "already exists in Google Drive."
                    ),
                    "name": file_name,
                    "matches": matches,
                    "message": (
                        "Upload cancelled to prevent "
                        "an accidental duplicate."
                    ),
                }

            from googleapiclient.http import (
                MediaFileUpload
            )

            metadata = {
                "name": file_name,
            }

            media = MediaFileUpload(
                str(path),
                mimetype=mime_type,
                resumable=True,
            )

            uploaded = (
                self.service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields=(
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "createdTime,"
                        "modifiedTime,"
                        "webViewLink"
                    ),
                )
                .execute()
            )

            uploaded_size = int(
                uploaded.get(
                    "size",
                    path.stat().st_size,
                )
            )

            return {
                "success": True,
                "tool": "cloud_upload",
                "data": {
                    "file_id": uploaded.get(
                        "id"
                    ),
                    "name": uploaded.get(
                        "name"
                    ),
                    "mime_type": uploaded.get(
                        "mimeType"
                    ),
                    "size_bytes": uploaded_size,
                    "created_time": uploaded.get(
                        "createdTime"
                    ),
                    "modified_time": uploaded.get(
                        "modifiedTime"
                    ),
                    "web_view_link": uploaded.get(
                        "webViewLink"
                    ),
                    "local_path": str(path),
                },
                "message": (
                    f"Successfully uploaded "
                    f"'{file_name}' to Google Drive."
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_upload",
                "error": str(e),
                "local_path": str(path),
            }

    # =========================================================
    # DELETE BY ID
    # =========================================================

    def delete_file_by_id(
        self,
        file_id,
        permanent=False,
    ):
        """
        Delete a Google Drive file by ID.

        By default the file is moved to the Google Drive
        trash instead of being permanently deleted.

        permanent=True permanently deletes the file.
        """

        if not file_id:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": "No Google Drive file ID provided.",
            }

        if self.service is None:
            self.authenticate()

        try:
            # -------------------------------------------------
            # Get metadata first
            # -------------------------------------------------

            metadata_result = self.get_file_by_id(
                file_id
            )

            if not metadata_result.get("success"):
                return {
                    "success": False,
                    "tool": "cloud_delete",
                    "error": (
                        "Could not find the Google Drive file."
                    ),
                    "file_id": file_id,
                    "details": metadata_result,
                }

            file_data = metadata_result.get(
                "data",
                {},
            )

            file_name = file_data.get(
                "name",
                "unknown file",
            )

            # -------------------------------------------------
            # Permanent deletion
            # -------------------------------------------------

            if permanent:
                (
                    self.service.files()
                    .delete(
                        fileId=file_id
                    )
                    .execute()
                )

                return {
                    "success": True,
                    "tool": "cloud_delete",
                    "data": {
                        "file_id": file_id,
                        "name": file_name,
                        "permanent": True,
                    },
                    "message": (
                        f"Permanently deleted "
                        f"'{file_name}' from Google Drive."
                    ),
                }

            # -------------------------------------------------
            # Move to Google Drive trash
            # -------------------------------------------------

            (
                self.service.files()
                .update(
                    fileId=file_id,
                    body={
                        "trashed": True
                    },
                    fields="id,name,trashed",
                )
                .execute()
            )

            return {
                "success": True,
                "tool": "cloud_delete",
                "data": {
                    "file_id": file_id,
                    "name": file_name,
                    "permanent": False,
                    "trashed": True,
                },
                "message": (
                    f"Moved '{file_name}' to "
                    "Google Drive trash."
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": str(e),
                "file_id": file_id,
            }

    # =========================================================
    # DELETE BY QUERY
    # =========================================================

    def delete_file(
        self,
        query,
        permanent=False,
    ):
        """
        Search for a Google Drive file and delete it.

        If multiple files match, no deletion is performed.
        The matching files are returned so the agent can ask
        the user to select one.
        """

        if not query:
            return {
                "success": False,
                "tool": "cloud_delete",
                "error": (
                    "No Google Drive delete query provided."
                ),
            }

        search_result = self.search_files(
            query
        )

        if not search_result.get(
            "success"
        ):
            return search_result

        matches = search_result.get(
            "matches",
            [],
        )

        # -----------------------------------------------------
        # No match
        # -----------------------------------------------------

        if not matches:
            return {
                "success": False,
                "tool": "cloud_delete",
                "query": query,
                "error": (
                    "No Google Drive files matched "
                    "the delete query."
                ),
                "message": (
                    f"No files found for '{query}'."
                ),
            }

        # -----------------------------------------------------
        # Multiple matches
        # -----------------------------------------------------

        if len(matches) > 1:
            return {
                "success": False,
                "tool": "cloud_delete",
                "query": query,
                "error": (
                    "Multiple Google Drive files "
                    "matched the delete query."
                ),
                "matches": matches,
                "message": (
                    "Multiple files matched. "
                    "Please select one before deletion."
                ),
            }

        # -----------------------------------------------------
        # Exactly one match
        # -----------------------------------------------------

        file_id = matches[0].get(
            "id"
        )

        return self.delete_file_by_id(
            file_id=file_id,
            permanent=permanent,
        )

    # =========================================================
    # RECENT FILES
    # =========================================================

    def list_recent_files(self, limit=20):
        """List recently modified Google Drive files."""

        if self.service is None:
            self.authenticate()

        try:
            response = (
                self.service.files()
                .list(
                    q="trashed = false",
                    spaces="drive",
                    fields=(
                        "files("
                        "id,"
                        "name,"
                        "mimeType,"
                        "size,"
                        "createdTime,"
                        "modifiedTime,"
                        "webViewLink"
                        ")"
                    ),
                    orderBy="modifiedTime desc",
                    pageSize=limit,
                )
                .execute()
            )

            files = response.get(
                "files",
                [],
            )

            result = []

            for file in files:
                result.append(
                    {
                        "id": file.get("id"),
                        "name": file.get("name"),
                        "mime_type": file.get(
                            "mimeType"
                        ),
                        "size_bytes": int(
                            file.get(
                                "size",
                                0,
                            )
                        ),
                        "created_time": file.get(
                            "createdTime"
                        ),
                        "modified_time": file.get(
                            "modifiedTime"
                        ),
                        "web_view_link": file.get(
                            "webViewLink"
                        ),
                    }
                )

            return {
                "success": True,
                "tool": "cloud_recent",
                "count": len(result),
                "files": result,
            }

        except Exception as e:
            return {
                "success": False,
                "tool": "cloud_recent",
                "error": str(e),
            }
