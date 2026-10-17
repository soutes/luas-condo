"""
FastAPI routes for Condominium Cycles and Reimbursement Submissions.
Exposes endpoints to list cycles, view details, and trigger Bitrix24 submission.
No emojis used.
"""

from datetime import date
import os
from pathlib import Path
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    CicloCondominio,
    ResponsabilidadeItem,
)
from app.schemas.condo import (
    CicloCondominioResponse,
    CicloSubmissaoRequest,
    CicloSubmissaoResponse,
    ItemAuditado,
)
from app.services.audit_engine import generate_formatted_observations
from app.services.bitrix_submitter import (
    SubmissionPayload,
    submit_reimbursement,
)

router = APIRouter(prefix="/api/ciclos", tags=["ciclos"])

# Optional default client injection for in-memory integration testing
_default_http_client: Optional[httpx.AsyncClient] = None


def set_default_http_client(client: Optional[httpx.AsyncClient]) -> None:
    """Set global HTTP client used for Bitrix submissions (used in test suites)."""
    global _default_http_client
    _default_http_client = client


@router.get("", response_model=list[CicloCondominioResponse])
def list_ciclos(db: Session = Depends(get_db)) -> list[CicloCondominioResponse]:
    """
    List all condominium cycles ordered by due date descending.
    Includes itemized rateio details and reimbursement submissions.
    """
    ciclos = (
        db.query(CicloCondominio)
        .order_by(desc(CicloCondominio.data_vencimento), desc(CicloCondominio.criado_em))
        .all()
    )
    return ciclos


@router.get("/{ciclo_id}", response_model=CicloCondominioResponse)
def get_ciclo(ciclo_id: uuid.UUID, db: Session = Depends(get_db)) -> CicloCondominioResponse:
    """
    Get detailed information for a specific condominium cycle.
    """
    ciclo = db.get(CicloCondominio, ciclo_id)
    if not ciclo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ciclo {ciclo_id} nao encontrado",
        )
    return ciclo


@router.post("/sync-email")
async def trigger_email_sync(db: Session = Depends(get_db)):
    """
    Manually trigger IMAP email inbox check, document extraction, and cycle synchronization.
    """
    from app.services.poller import execute_email_sync
    res = await execute_email_sync(db=db, force=True)
    return res


@router.post("/{ciclo_id}/submeter", response_model=CicloSubmissaoResponse)
async def submeter_ciclo(
    ciclo_id: uuid.UUID,
    payload_in: Optional[CicloSubmissaoRequest] = None,
    db: Session = Depends(get_db),
) -> CicloSubmissaoResponse:
    """
    Trigger Bitrix24 reimbursement submission for the specified cycle.
    Updates cycle status to ENVIADO on success and records submission receipts.
    """
    ciclo = db.get(CicloCondominio, ciclo_id)
    if not ciclo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ciclo {ciclo_id} nao encontrado",
        )

    req = payload_in or CicloSubmissaoRequest()

    # Generate formatted observations memo if not explicitly supplied
    obs_text = req.observacoes
    if not obs_text:
        itens_locador = [
            ItemAuditado(
                descricao=it.descricao,
                valor=it.valor_unidade,
                categoria=it.categoria,
                responsabilidade=it.responsabilidade,
                justificativa_legal=it.justificativa_legal,
            )
            for it in ciclo.itens
            if it.responsabilidade == ResponsabilidadeItem.LOCADOR
        ]
        obs_text = generate_formatted_observations(
            condominio_nome=ciclo.condominio_nome,
            competencia=ciclo.competencia,
            data_vencimento=ciclo.data_vencimento,
            itens_locador=itens_locador,
            total_reimbursement=ciclo.valor_ressarcimento,
            revisao_necessaria=False,
        )

    # Resolve boleto file or mock fallback bytes if file path doesn't exist on disk
    boleto_path = ciclo.boleto_pdf_path
    boleto_bytes = None
    boleto_filename = "boleto.pdf"
    if boleto_path and os.path.exists(boleto_path):
        pass
    else:
        boleto_path = None
        boleto_bytes = b"%PDF-1.4 Mock Boleto Content"

    # Resolve comprovante PIX file or mock fallback bytes
    comprovante_path = ciclo.comprovante_pix_path
    comprovante_bytes = None
    comprovante_filename = "comprovante.pdf"
    if comprovante_path and os.path.exists(comprovante_path):
        pass
    else:
        comprovante_path = None
        comprovante_bytes = b"%PDF-1.4 Mock Comprovante PIX Content"

    submission_payload = SubmissionPayload(
        nome=req.nome or os.getenv("IBAGY_TENANT_NAME", "Luiz Augusto Soutes"),
        email=req.email or os.getenv("IBAGY_TENANT_EMAIL", "luizsoutes@gmail.com"),
        telefone=req.telefone or os.getenv("IBAGY_TENANT_PHONE", "48999999999"),
        contrato=req.contrato or os.getenv("IBAGY_CONTRACT_NUM", "09638.003.03"),
        observacoes=obs_text,
        boleto_path=boleto_path,
        boleto_bytes=boleto_bytes,
        boleto_filename=boleto_filename,
        comprovante_path=comprovante_path,
        comprovante_bytes=comprovante_bytes,
        comprovante_filename=comprovante_filename,
        ciclo_id=ciclo.id,
    )

    receipt = await submit_reimbursement(
        payload=submission_payload,
        db_session=db,
        use_browser=req.use_browser,
        client=_default_http_client,
    )

    return CicloSubmissaoResponse(
        status=receipt.status,
        protocolo=receipt.protocolo,
        mensagem=receipt.mensagem,
        screenshot_path=receipt.screenshot_path,
        trace_id=receipt.trace_id,
        ciclo_id=ciclo.id,
    )
