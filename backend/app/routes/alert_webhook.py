"""
FastAPI route for Prometheus Alertmanager webhooks.
Receives firing alerts, invokes autonomous on-call agent, and executes self-healing.
No emojis used.
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.on_call import handle_incident_alert
from app.core.database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/webhook", status_code=status.HTTP_200_OK)
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
    if isinstance(alerts, list) and len(alerts) > 0:
        incidentes_result = []
        for alert_item in alerts:
            if isinstance(alert_item, dict):
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
