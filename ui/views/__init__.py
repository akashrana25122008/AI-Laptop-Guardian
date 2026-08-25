"""
View registry — maps navigation keys to view classes.
"""


def register_views():
    """
    Lazy import so the package never imports
    customtkinter until a view is actually constructed.
    """

    from ui.views.dashboard import DashboardView
    from ui.views.health_view import HealthView
    from ui.views.storage_view import StorageView
    from ui.views.cleanup_view import CleanupView
    from ui.views.cloud_view import CloudView
    from ui.views.accounts_view import AccountsView
    from ui.views.settings_view import SettingsView

    return {
        "dashboard": DashboardView,
        "health": HealthView,
        "storage": StorageView,
        "cleanup": CleanupView,
        "cloud": CloudView,
        "accounts": AccountsView,
        "settings": SettingsView,
    }
