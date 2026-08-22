class CloudManager:
    """
    Manages cloud storage providers for AI Laptop Guardian.

    CloudManager acts as the layer between the AI agent
    and individual cloud providers.
    """

    def __init__(self):
        self.providers = {}
        self.active_provider = None

    # -----------------------------------------
    # Provider Management
    # -----------------------------------------

    def register_provider(self, name, provider):
        """
        Register a cloud provider.
        """

        if not name:
            raise ValueError("Provider name cannot be empty.")

        if provider is None:
            raise ValueError("Provider cannot be None.")

        self.providers[name] = provider

    def set_active_provider(self, name):
        """
        Select the active cloud provider.
        """

        if name not in self.providers:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": (
                    f"Cloud provider '{name}' is not registered."
                ),
            }

        self.active_provider = self.providers[name]

        return {
            "success": True,
            "tool": "cloud_manager",
            "provider": name,
            "message": (
                f"Cloud provider '{name}' is now active."
            ),
        }

    # -----------------------------------------
    # Provider Information
    # -----------------------------------------

    def list_providers(self):
        """
        Return all registered cloud providers.
        """

        return {
            "success": True,
            "tool": "cloud_manager",
            "providers": list(self.providers.keys()),
        }

    # -----------------------------------------
    # Authentication
    # -----------------------------------------

    def authenticate(self):
        """
        Authenticate using the active provider.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.authenticate()

    # -----------------------------------------
    # Storage Information
    # -----------------------------------------

    def get_storage_info(self):
        """
        Get storage information from the active provider.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.get_storage_info()

    # -----------------------------------------
    # Upload
    # -----------------------------------------

    def upload_file(
        self,
        local_path,
        remote_path=None,
    ):
        """
        Upload a file using the active provider.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.upload_file(
            local_path,
            remote_path,
        )

    # -----------------------------------------
    # Download
    # -----------------------------------------

    def download_file(
        self,
        remote_path,
        local_path,
    ):
        """
        Download a file using the active provider.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.download_file(
            remote_path,
            local_path,
        )

    # -----------------------------------------
    # File Existence
    # -----------------------------------------

    def file_exists(self, remote_path):
        """
        Check whether a remote file exists.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.file_exists(
            remote_path
        )

    # -----------------------------------------
    # Delete
    # -----------------------------------------

    def delete_file(self, remote_path):
        """
        Delete a remote file.

        Actual deletion remains controlled by the
        provider and future safety checks.
        """

        if self.active_provider is None:
            return {
                "success": False,
                "tool": "cloud_manager",
                "error": "No active cloud provider selected.",
            }

        return self.active_provider.delete_file(
            remote_path
        )