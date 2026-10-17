"""
Background poller service for IMAP condo email ingestion and optional auto-submission.
Active once per day during the window from day 07 to day 12 of each month.
Also supports manual synchronization triggered via API.
No emojis used.
"""

import asyncio
from datetime import date, datetime
import logging
import os
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.entities import CicloCondominio, StatusCiclo
from app.services.bitrix_submitter import SubmissionPayload, submit_reimbursement
from app.services.email_worker import (
    fetch_new_condo_emails,
    sync_condo_cycle,
)

logger = logging.getLogger(__name__)

_last_poll_date: Optional[date] = None
_poller_task: Optional[asyncio.Task] = None


def is_active_polling_window(target_date: Optional[date] = None) -> bool:
    """
    Returns True if target date is between day 07 and 12 of the month.
    Configurable via POLL_WINDOW_START_DAY and POLL_WINDOW_END_DAY.
    """
    d = target_date or datetime.now().date()
    start_day = int(os.getenv("POLL_WINDOW_START_DAY", "7"))
    end_day = int(os.getenv("POLL_WINDOW_END_DAY", "12"))
    return start_day <= d.day <= end_day


async def execute_email_sync(
    db: Optional[Session] = None,
    force: bool = False,
    imap_client: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Executes IMAP inbox sync, document extraction, and optional auto-submission.
    Returns status summary dictionary.
    """
    imap_user = os.getenv("IMAP_USER", "").strip()
    imap_password = os.getenv("IMAP_PASSWORD", "").strip()

    if (not imap_user or not imap_password) and imap_client is None:
        return {
            "status": "skipped",
            "detail": "IMAP_USER or IMAP_PASSWORD not configured",
            "synced_cycles": 0,
            "submitted_cycles": [],
        }

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        host = os.getenv("IMAP_SERVER", "imap.gmail.com")
        port = int(os.getenv("IMAP_PORT", "993"))
        storage_dir = os.getenv("STORAGE_DIR", "/data/storage")

        # Fetch new messages using read-only EXAMINE mode
        docs = fetch_new_condo_emails(
            imap_client=imap_client,
            host=host,
            port=port,
            user=imap_user,
            password=imap_password,
        )

        if not docs:
            pending_cycles = (
                db.query(CicloCondominio)
                .filter(
                    CicloCondominio.status_ciclo.in_([
                        StatusCiclo.PENDENTE_COMPROVANTE,
                        StatusCiclo.PRONTO_PARA_ENVIO,
                    ])
                )
                .all()
            )
            for c in pending_cycles:
                c.ultima_verificacao = datetime.now(timezone.utc)
            db.commit()
            return {
                "status": "ok",
                "detail": "Nenhum novo documento de condominio ou comprovante localizado",
                "synced_cycles": 0,
                "submitted_cycles": [],
            }

        # Synchronize into database cycles
        cycles = sync_condo_cycle(db, docs, storage_dir=storage_dir)

        # Check if auto-submit is enabled
        auto_submit = os.getenv("AUTO_SUBMIT", "false").lower() in ("true", "1", "yes")
        submitted_cycles = []

        if auto_submit:
            for ciclo in cycles:
                if ciclo.status_ciclo == StatusCiclo.PRONTO_PARA_ENVIO:
                    payload = SubmissionPayload(
                        nome=os.getenv("IBAGY_TENANT_NAME", "Luiz Augusto Soutes"),
                        email=os.getenv("IBAGY_TENANT_EMAIL", "luizsoutes@gmail.com"),
                        telefone=os.getenv("IBAGY_TENANT_PHONE", "48999999999"),
                        contrato=os.getenv("IBAGY_CONTRACT_NUM", "09638.003.03"),
                        ciclo_id=ciclo.id,
                        boleto_path=ciclo.boleto_pdf_path,
                        comprovante_path=ciclo.comprovante_pix_path,
                    )
                    receipt = await submit_reimbursement(payload=payload, db_session=db)
                    submitted_cycles.append({
                        "ciclo_id": str(ciclo.id),
                        "competencia": ciclo.competencia,
                        "status": receipt.status.value,
                        "protocolo": receipt.protocolo,
                    })

        return {
            "status": "ok",
            "detail": f"{len(docs)} documento(s) processado(s) com sucesso",
            "synced_cycles": len(cycles),
            "submitted_cycles": submitted_cycles,
        }
    except Exception as exc:
        logger.error(f"Erro durante sincronizacao de email: {exc}")
        return {
            "status": "error",
            "detail": str(exc),
            "synced_cycles": 0,
            "submitted_cycles": [],
        }
    finally:
        if close_db:
            db.close()


async def email_poller_loop(check_interval_seconds: int = 3600) -> None:
    """
    Background worker loop waking up periodically to execute email sync once per day
    during the active window between day 07 and day 12.
    """
    global _last_poll_date
    logger.info("Email poller loop iniciado (janela ativa: dias 07 a 12 de cada mes)")

    while True:
        try:
            today = datetime.now().date()
            if is_active_polling_window(today):
                if _last_poll_date != today:
                    logger.info(f"Executando polling diario de e-mails para {today}")
                    res = await execute_email_sync()
                    logger.info(f"Resultado do polling: {res}")
                    _last_poll_date = today
            else:
                logger.debug(f"Fora da janela de polling (hoje e dia {today.day})")
        except asyncio.CancelledError:
            logger.info("Email poller loop cancelado")
            break
        except Exception as exc:
            logger.error(f"Erro no loop do poller de e-mails: {exc}")

        await asyncio.sleep(check_interval_seconds)


def start_poller(check_interval_seconds: int = 3600) -> Optional[asyncio.Task]:
    """Start background poller task if an event loop is currently active."""
    global _poller_task
    try:
        loop = asyncio.get_running_loop()
        if _poller_task is None or _poller_task.done():
            _poller_task = loop.create_task(email_poller_loop(check_interval_seconds))
    except RuntimeError:
        pass
    return _poller_task


def stop_poller() -> None:
    """Cancel running background poller task."""
    global _poller_task
    if _poller_task is not None and not _poller_task.done():
        _poller_task.cancel()
        _poller_task = None
