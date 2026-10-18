"""
FastAPI routes for Condominium Cycles and Reimbursement Submissions.
Exposes endpoints to list cycles, view details, and trigger Bitrix24 submission.
No emojis used.
"""

from datetime import date
import logging
import os
from pathlib import Path
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
import httpx
from decimal import Decimal
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import (
    CicloCondominio,
    ResponsabilidadeItem,
    StatusCiclo,
)
from app.schemas.condo import (
    CicloCondominioResponse,
    CicloSubmissaoRequest,
    CicloSubmissaoResponse,
    ItemAuditado,
    VerificacaoChecklistResponse,
)
from app.services.audit_engine import generate_formatted_observations
from app.services.bitrix_submitter import (
    SubmissionPayload,
    submit_reimbursement,
)

router = APIRouter(prefix="/api/ciclos", tags=["ciclos"])

logger = logging.getLogger(__name__)

# Optional default client injection for in-memory integration testing
_default_http_client: Optional[httpx.AsyncClient] = None


def set_default_http_client(client: Optional[httpx.AsyncClient]) -> None:
    """Set global HTTP client used for Bitrix submissions (used in test suites)."""
    global _default_http_client
    _default_http_client = client


def build_checklist_response(ciclo: CicloCondominio) -> VerificacaoChecklistResponse:
    boleto_encontrado = bool(ciclo.boleto_pdf_path)
    comprovante_encontrado = bool(ciclo.comprovante_pix_path)
    aluguel_encontrado = bool(ciclo.boleto_aluguel_path)

    erros_alertas: list[str] = []
    if not boleto_encontrado:
        erros_alertas.append("Boleto de condominio nao localizado para esta competencia")
    if not aluguel_encontrado:
        erros_alertas.append("Boleto de aluguel Ibagy nao localizado para esta competencia")
    if not comprovante_encontrado:
        erros_alertas.append("Comprovante de pagamento PIX nao localizado para esta competencia")

    status_envio = "NAO_ENVIADO"
    protocolo_retorno = None
    if ciclo.submissoes:
        sub_sorted = sorted(ciclo.submissoes, key=lambda s: s.enviado_em, reverse=True)
        latest_sub = sub_sorted[0]
        status_envio = latest_sub.status.value
        protocolo_retorno = latest_sub.protocolo_retorno
    elif ciclo.status_ciclo == StatusCiclo.CONCILIADO_SEM_PENDENCIA:
        status_envio = "DISPENSADO_CONCILIADO"

    if ciclo.status_ciclo == StatusCiclo.CONCILIADO_SEM_PENDENCIA:
        erros_alertas.append("Todas as despesas do locador foram compensadas automaticamente no aluguel (R$ 0,00 a ressarcir)")

    saldo_devido = ciclo.valor_saldo_residual
    if saldo_devido == Decimal("0.00") and (ciclo.valor_desconto_aluguel or Decimal("0.00")) == Decimal("0.00") and ciclo.valor_ressarcimento > Decimal("0.00"):
        saldo_devido = ciclo.valor_ressarcimento

    return VerificacaoChecklistResponse(
        competencia=ciclo.competencia,
        boleto_condominio_encontrado=boleto_encontrado,
        comprovante_pix_encontrado=comprovante_encontrado,
        boleto_aluguel_encontrado=aluguel_encontrado,
        despesas_locador=ciclo.valor_ressarcimento,
        descontos_aluguel=ciclo.valor_desconto_aluguel or Decimal("0.00"),
        saldo_residual_devido=saldo_devido,
        status_ciclo=ciclo.status_ciclo,
        status_envio=status_envio,
        protocolo_retorno=protocolo_retorno,
        ultima_verificacao=ciclo.ultima_verificacao or ciclo.criado_em,
        detalhes=ciclo.detalhes_verificacao,
        erros_alertas=erros_alertas,
    )


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


@router.get("/checklist/mensal", response_model=list[VerificacaoChecklistResponse])
def get_monthly_checklist(db: Session = Depends(get_db)) -> list[VerificacaoChecklistResponse]:
    """
    Get verification checklist for all monthly cycles, reporting missing documents,
    reconciliation balances, and submission protocol status.
    """
    ciclos = (
        db.query(CicloCondominio)
        .order_by(desc(CicloCondominio.data_vencimento), desc(CicloCondominio.criado_em))
        .all()
    )
    return [build_checklist_response(c) for c in ciclos]


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


@router.get("/{ciclo_id}/checklist", response_model=VerificacaoChecklistResponse)
def get_cycle_checklist(ciclo_id: uuid.UUID, db: Session = Depends(get_db)) -> VerificacaoChecklistResponse:
    """
    Get detailed verification checklist and document audit for a specific condominium cycle.
    """
    ciclo = db.get(CicloCondominio, ciclo_id)
    if not ciclo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ciclo {ciclo_id} nao encontrado",
        )
    return build_checklist_response(ciclo)


@router.post("/sync-email")
async def trigger_email_sync(db: Session = Depends(get_db)):
    """
    Manually trigger IMAP email inbox check, document extraction, and cycle synchronization.
    """
    from app.services.poller import execute_email_sync
    res = await execute_email_sync(db=db, force=True)
    return res


@router.post("/seed-demo", response_model=CicloCondominioResponse)
def seed_demo_cycle(db: Session = Depends(get_db)) -> CicloCondominioResponse:
    """
    Create the reference Villa Salomy demo cycle so the dashboard has submittable
    data before real ingestion happens. Only available while MOCK_SUBMISSION=true:
    sample data must never enter a production database filing real claims.
    """
    from app.seed import seed_production_cycle

    mock_submission = os.getenv("MOCK_SUBMISSION", "true").strip().lower() == "true"
    if not mock_submission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Seed demo bloqueado: MOCK_SUBMISSION=false (modo producao). "
                "Dados de amostra nao podem ser inseridos no banco de producao."
            ),
        )

    ciclo = seed_production_cycle(
        db=db, storage_dir=os.getenv("STORAGE_DIR", "/data/storage"), reset_existing=False
    )
    db.refresh(ciclo)
    return ciclo


@router.post("/documentos")
def upload_documentos(
    files: list[UploadFile] = File(...),
    competencia: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Manual retroactive document intake (condo bills, rental bills, PIX receipts).
    Reuses the email-flow classifier and sync engine unchanged: same attachment
    classification, same dedupe by competencia, same PIX pairing. Files classified
    as UNKNOWN are reported and ignored. Optional competencia hint (YYYY-MM) is
    carried into the pairing corpus so PIX receipts bind to the intended month
    instead of the most recent pending cycle.
    """
    from app.services.email_worker import (
        DocumentType,
        EmailAttachment,
        IngestedDocument,
        classify_attachment,
        sync_condo_cycle,
    )

    hint = ""
    if competencia:
        comp = competencia.strip()
        parts = comp.split("-")
        if len(parts) == 2 and len(parts[0]) == 4:
            comp_slash = f"{parts[1]}/{parts[0]}"
        else:
            comp_slash = comp
        hint = f"upload manual competencia {comp} {comp_slash}"

    max_files = 30
    max_file_bytes = 20 * 1024 * 1024

    docs: list[IngestedDocument] = []
    report: list[dict] = []
    for upload in files[:max_files]:
        content = upload.file.read()
        if len(content) > max_file_bytes:
            report.append({
                "arquivo": upload.filename,
                "tipo": "MUITO_GRANDE",
                "arquivado": False,
            })
            continue
        attachment = EmailAttachment(
            upload.filename or "documento",
            upload.content_type or "application/octet-stream",
            content,
        )
        doc_type = classify_attachment(attachment)
        archived = doc_type != DocumentType.UNKNOWN
        report.append({"arquivo": upload.filename, "tipo": doc_type.value, "arquivado": archived})
        if archived:
            docs.append(
                IngestedDocument(
                    doc_type=doc_type,
                    filename=upload.filename or "documento",
                    content=content,
                    content_type=upload.content_type or "application/octet-stream",
                    email_subject=hint,
                )
            )

    ciclos_afetados: list[dict] = []
    falhas: list[dict] = []
    if docs:
        storage_dir = os.getenv("STORAGE_DIR", "/data/storage")
        # Mirror the engine batch order (bills, rental bills, receipts) and sync
        # ONE document per call: a document that fails to parse is reported in
        # "falhas" without aborting the remaining files.
        order = {
            DocumentType.CONDO_BILL: 0,
            DocumentType.RENTAL_BILL: 1,
            DocumentType.PIX_RECEIPT: 2,
        }
        docs.sort(key=lambda d: order.get(d.doc_type, 3))
        for doc in docs:
            try:
                ciclos = sync_condo_cycle(db, [doc], storage_dir=storage_dir)
                for c in ciclos:
                    status_value = (
                        c.status_ciclo.value if hasattr(c.status_ciclo, "value") else str(c.status_ciclo)
                    )
                    existing = next(
                        (x for x in ciclos_afetados if x["id"] == str(c.id)), None
                    )
                    if existing is None:
                        ciclos_afetados.append({
                            "id": str(c.id),
                            "competencia": c.competencia,
                            "status_ciclo": status_value,
                        })
                    else:
                        existing["status_ciclo"] = status_value
            except Exception as exc:
                logger.warning("Falha ao processar documento %s: %s", doc.filename, exc)
                falhas.append({"arquivo": doc.filename, "erro": str(exc)})
                db.rollback()

    return {"arquivos": report, "ciclos_afetados": ciclos_afetados, "falhas": falhas}


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

    effective_saldo = ciclo.valor_saldo_residual
    if effective_saldo == Decimal("0.00") and (ciclo.valor_desconto_aluguel or Decimal("0.00")) == Decimal("0.00") and ciclo.valor_ressarcimento > Decimal("0.00"):
        effective_saldo = ciclo.valor_ressarcimento

    # Block submission if residual balance is zero (fully reconciled on rental invoice) unless forced
    if effective_saldo <= Decimal("0.00") and not req.force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Ciclo conciliado sem pendencia. Todos os valores devidos pelo locador "
                "ja foram compensados no boleto de aluguel (saldo residual R$ 0,00)."
            ),
        )

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
        if ciclo.valor_desconto_aluguel > Decimal("0.00"):
            obs_text += (
                f"\n\n[CONCILIACAO DE ALUGUEL]:\n"
                f"- Despesas totais do locador apuradas no condominio: R$ {ciclo.valor_ressarcimento:.2f}\n"
                f"- Creditos/descontos ja concedidos na fatura de aluguel: R$ {ciclo.valor_desconto_aluguel:.2f}\n"
                f"- Saldo residual pendente solicitado neste protocolo: R$ {ciclo.valor_saldo_residual:.2f}"
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
