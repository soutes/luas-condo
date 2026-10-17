"""
API routes module for Luas Condo backend service.
No emojis used.
"""

from app.routes.alert_webhook import router as alert_router
from app.routes.ciclos import router as ciclos_router

__all__ = ["alert_router", "ciclos_router"]
