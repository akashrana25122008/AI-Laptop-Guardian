"""
Desktop UI for AI Laptop Guardian.

This package is presentation only:

    UI (customtkinter)
      -> ui.app_controller.GuardianController (thin glue)
        -> agent.ai_agent.AIAgent / ToolRouter
          -> deterministic tools and cloud services

No business logic lives here: health scoring, storage
scanning, cleanup classification, cloud analytics, OAuth,
and all safety decisions stay in the existing backend.
"""
