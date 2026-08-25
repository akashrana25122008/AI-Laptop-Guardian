"""
Navigation model for the desktop UI.

Pure data: no widget imports, no application logic.
"""

# Sidebar items shown in left-to-right, top-to-bottom
# order.  Keys match view classes under ui.views.

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("health", "Health"),
    ("storage", "Storage"),
    ("cleanup", "Cleanup"),
    ("cloud", "Cloud"),
    ("accounts", "Accounts"),
    ("settings", "Settings"),
]
