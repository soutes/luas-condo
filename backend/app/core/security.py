"""
Bearer-token authentication dependencies (fail closed, constant-time comparison).
No emojis used.
"""

import hmac
import os
from typing import Callable, Optional

from fastapi import Header, HTTPException, status


def bearer_token_dependency(env_var: str, label: str) -> Callable[..., None]:
    """
    Build a FastAPI dependency that requires `Authorization: Bearer <token>` where the
    expected token comes from the `env_var` environment variable (read per request).
    If the variable is unset or empty every request is refused (503): never open by default.
    """

    def _require(authorization: Optional[str] = Header(default=None)) -> None:
        expected = os.getenv(env_var, "").strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{label} desabilitado: {env_var} nao configurado",
            )
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            supplied.strip().encode("utf-8"), expected.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalido",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _require


require_write_token = bearer_token_dependency("API_WRITE_TOKEN", "API de escrita")
require_alert_token = bearer_token_dependency("ALERT_WEBHOOK_TOKEN", "Webhook de alertas")
