from abc import ABC, abstractmethod


class CloudProvider(ABC):
    """
    Base interface for all cloud storage providers.

    Every cloud provider must implement these methods.
    """

    @abstractmethod
    def authenticate(self):
        """
        Authenticate the user with the cloud provider.
        """
        pass

    @abstractmethod
    def get_storage_info(self):
        """
        Return cloud storage information.
        """
        pass

    @abstractmethod
    def upload_file(self, local_path, remote_path=None):
        """
        Upload a local file to cloud storage.
        """
        pass

    @abstractmethod
    def download_file(self, remote_path, local_path):
        """
        Download a cloud file to the local machine.
        """
        pass

    @abstractmethod
    def delete_file(self, remote_path):
        """
        Delete a file from cloud storage.

        This will only be used after proper verification
        and safety checks are implemented.
        """
        pass

    @abstractmethod
    def file_exists(self, remote_path):
        """
        Check whether a file exists in cloud storage.
        """
        pass