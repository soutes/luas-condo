"""
FastAPI route for Prometheus Alertmanager webhooks.
Receives firing alerts, invokes autonomous on-call agent, and executes self-healing.
No emojis used.
"""

import hmac
import os
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.on_call import handle_incident_alert
from app.core.database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def require_alert_token(authorization: Optional[str] = Header(default=None)) -> None:
    """
    Authenticate the Alertmanager webhook with a shared bearer token (ALERT_WEBHOOK_TOKEN).
    Fails closed: if no token is configured on the server, every request is refused.
    """
    expected = os.getenv("ALERT_WEBHOOK_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook de alertas desabilitado: ALERT_WEBHOOK_TOKEN nao configurado",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.strip().encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de webhook invalido",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/webhook", status_code=status.HTTP_200_OK, dependencies=[Depends(require_alert_token)])
def receive_alert_webhook(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Alertmanager webhook receiver endpoint.
    Parses alert payload, invokes On-Call responder agent, and returns incident status.
    """
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be a valid JSON dictionary",
        )

    alerts = payload.get("alerts")
    # If standard Alertmanager payload with list of alerts
    if isinstance(alerts, list):
        incidentes_result = []
        for alert_item in alerts:
            if not isinstance(alert_item, dict):
                continue
            if alert_item.get("status") == "resolved":
                continue
            incidente = handle_incident_alert(alert_item, db_session=db)
            incidentes_result.append({
                "id": str(incidente.id),
                "trace_id": incidente.trace_id,
                "alerta_nome": incidente.alerta_nome,
                "status": incidente.status.value,
                "diagnostico": incidente.diagnostico,
                "acao_executada": incidente.acao_executada,
            })
        return {
            "status": "processed",
            "count": len(incidentes_result),
            "incidentes": incidentes_result,
        }

    # Handle direct single alert payload
    if payload.get("status") == "resolved":
        return {
            "status": "processed",
            "count": 0,
            "incidentes": [],
        }

    incidente = handle_incident_alert(payload, db_session=db)

    return {
        "status": "processed",
        "count": 1,
        "incidentes": [
            {
                "id": str(incidente.id),
                "trace_id": incidente.trace_id,
                "alerta_nome": incidente.alerta_nome,
                "status": incidente.status.value,
                "diagnostico": incidente.diagnostico,
                "acao_executada": incidente.acao_executada,
            }
        ],
    }
