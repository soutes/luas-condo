"""
Agents module for autonomous incident response and self-healing.
No emojis used.
"""

from app.agents.on_call import (
    get_default_http_client,
    handle_incident_alert,
    remediate_http_5xx_timeout,
    remediate_selector_mismatch,
    set_default_http_client,
)

__all__ = [
    "handle_incident_alert",
    "remediate_selector_mismatch",
    "remediate_http_5xx_timeout",
    "set_default_http_client",
    "get_default_http_client",
]

