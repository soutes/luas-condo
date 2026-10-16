"""
Bitrix24 reimbursement submitter service.
Supports both HTTP multipart/form-data submission and Playwright browser automation.
Persists submission receipts and correlates OpenTelemetry traces.
No emojis used.
"""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Optional
import uuid

import httpx
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from app.models.entities import (
    CicloCondominio,
    StatusCiclo,
    StatusSubmissao,
    SubmissaoRessarcimento,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SubmissionPayload",
    "SubmissionReceipt",
    "get_or_create_trace_id",
    "resolve_target_url",
    "submit_reimbursement",
]


class SubmissionPayload(BaseModel):
    """Payload for submitting condo reimbursement to Bitrix24."""

    nome: str
    email: str
    telefone: str
    contrato: str = "09638.003.03"
    observacoes: Optional[str] = ""
    boleto_path: Optional[str] = None
    boleto_bytes: Optional[bytes] = None
    boleto_filename: Optional[str] = "boleto.pdf"
    comprovante_path: Optional[str] = None
    comprovante_bytes: Optional[bytes] = None
    comprovante_filename: Optional[str] = "comprovante.pdf"
    ciclo_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def handle_field_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Accept boleto_pdf_path from CicloCondominio
            if "boleto_pdf_path" in data and "boleto_path" not in data:
                data["boleto_path"] = data["boleto_pdf_path"]
            # Accept comprovante_pix_path from CicloCondominio
            if "comprovante_pix_path" in data and "comprovante_path" not in data:
                data["comprovante_path"] = data["comprovante_pix_path"]
        return data


class SubmissionReceipt(BaseModel):
    """Receipt returned upon completion of reimbursement submission."""

    status: StatusSubmissao
    protocolo: Optional[str] = None
    mensagem: str
    screenshot_path: Optional[str] = None
    trace_id: str


def get_or_create_trace_id(trace_id: Optional[str] = None) -> str:
    """Retrieve active OpenTelemetry trace ID or generate a new unique identifier."""
    if trace_id:
        return trace_id
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        span_ctx = span.get_span_context()
        if span_ctx and span_ctx.is_valid:
            return f"{span_ctx.trace_id:032x}"
    except Exception:
        pass
    return f"trace-{uuid.uuid4().hex[:16]}"


def resolve_target_url(target_url: Optional[str] = None) -> str:
    """
    Resolve destination URL based on environment settings.
    Defaults to mock-bitrix in development/CI, or real Ibagy CRM form when MOCK_SUBMISSION=false.
    """
    if target_url:
        return target_url
    is_mock = os.getenv("MOCK_SUBMISSION", "true").lower() in ("true", "1", "yes")
    if is_mock:
        base = os.getenv("MOCK_BITRIX_URL", "http://localhost:8080")
        if not base.endswith("/condominioressarcimento/ressarcimento/") and not base.endswith("/"):
            return f"{base}/condominioressarcimento/ressarcimento/"
        return base
    return os.getenv(
        "IBAGY_BITRIX_URL",
        "https://ibagy.bitrix24.site/condominioressarcimento/ressarcimento/",
    )


def _prepare_file_content(
    file_path: Optional[str],
    file_bytes: Optional[bytes],
    default_filename: str,
) -> tuple[str, bytes]:
    """Extract filename and raw byte content from path or bytes."""
    if file_bytes is not None:
        filename = default_filename
        if file_path:
            filename = os.path.basename(file_path)
        return filename, file_bytes
    if file_path:
        p = Path(file_path)
        if p.exists():
            return p.name, p.read_bytes()
        raise FileNotFoundError(f"Arquivo nao encontrado: {file_path}")
    raise ValueError(f"Nenhum arquivo fornecido para {default_filename}")


async def _submit_via_http(
    payload: SubmissionPayload,
    target_url: str,
    trace_id: str,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout_sec: float = 30.0,
) -> SubmissionReceipt:
    """Submit reimbursement via HTTP multipart/form-data."""
    try:
        boleto_name, boleto_data = _prepare_file_content(
            payload.boleto_path,
            payload.boleto_bytes,
            payload.boleto_filename or "boleto.pdf",
        )
        comp_name, comp_data = _prepare_file_content(
            payload.comprovante_path,
            payload.comprovante_bytes,
            payload.comprovante_filename or "comprovante.pdf",
        )
    except Exception as exc:
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=f"Erro ao preparar arquivos para submissao: {str(exc)}",
            screenshot_path=None,
            trace_id=trace_id,
        )

    data = {
        "nome": payload.nome,
        "email": payload.email,
        "telefone": payload.telefone,
        "contrato": payload.contrato,
        "observacoes": payload.observacoes or "",
    }
    files = {
        "boleto": (boleto_name, boleto_data, "application/pdf"),
        "comprovante": (comp_name, comp_data, "application/pdf"),
    }
    headers = {
        "x-trace-id": trace_id,
        "Accept": "application/json, text/html, */*",
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        if client is not None:
            resp = await client.post(target_url, data=data, files=files, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=timeout_sec) as http_client:
                resp = await http_client.post(target_url, data=data, files=files, headers=headers)
    except Exception as exc:
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=f"Falha de conexao com Bitrix24: {str(exc)}",
            screenshot_path=None,
            trace_id=trace_id,
        )

    if resp.status_code >= 400:
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=f"Erro na submissao Bitrix24 (HTTP {resp.status_code}): {resp.text[:300]}",
            screenshot_path=None,
            trace_id=trace_id,
        )

    # Extract protocol from JSON or HTML text
    protocol = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            protocol = body.get("protocolo")
    except Exception:
        pass

    if not protocol:
        match = re.search(r"IBAGY-\d{4}-[A-Z0-9]+", resp.text)
        if match:
            protocol = match.group(0)

    if protocol:
        return SubmissionReceipt(
            status=StatusSubmissao.SUCESSO,
            protocolo=protocol,
            mensagem=f"Submissao realizada com sucesso. Protocolo: {protocol}",
            screenshot_path=None,
            trace_id=trace_id,
        )
    return SubmissionReceipt(
        status=StatusSubmissao.ERRO,
        protocolo=None,
        mensagem="Resposta Bitrix24 recebida mas protocolo nao localizado",
        screenshot_path=None,
        trace_id=trace_id,
    )


async def _submit_via_browser(
    payload: SubmissionPayload,
    target_url: str,
    trace_id: str,
    screenshots_dir: Optional[str] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout_ms: int = 30000,
) -> SubmissionReceipt:
    """Submit reimbursement using Playwright browser automation with DOM inspection."""
    from playwright.async_api import async_playwright

    screen_dir = screenshots_dir or os.getenv("SCREENSHOT_DIR")
    if not screen_dir:
        screen_dir = os.path.join(tempfile.gettempdir(), "luas_condo_screenshots")
    os.makedirs(screen_dir, exist_ok=True)
    screenshot_path = os.path.join(screen_dir, f"submissao_{trace_id}.png")

    # Prepare temp files on disk for Playwright set_input_files if needed
    temp_dir_obj = None
    try:
        boleto_file = payload.boleto_path
        if not boleto_file or not os.path.exists(boleto_file):
            if temp_dir_obj is None:
                temp_dir_obj = tempfile.TemporaryDirectory()
            boleto_file = os.path.join(temp_dir_obj.name, payload.boleto_filename or "boleto.pdf")
            with open(boleto_file, "wb") as f:
                f.write(payload.boleto_bytes or b"")

        comp_file = payload.comprovante_path
        if not comp_file or not os.path.exists(comp_file):
            if temp_dir_obj is None:
                temp_dir_obj = tempfile.TemporaryDirectory()
            comp_file = os.path.join(temp_dir_obj.name, payload.comprovante_filename or "comprovante.pdf")
            with open(comp_file, "wb") as f:
                f.write(payload.comprovante_bytes or b"")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                extra_http_headers=extra_headers or {},
            )
            page = await context.new_page()

            try:
                response = await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response and response.status >= 400:
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem=f"Erro ao carregar formulario Bitrix24 (HTTP {response.status})",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )

                # Validate selector presence
                nome_el = page.locator('input[name="nome"]')
                if await nome_el.count() == 0:
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem="Campo obrigatorio nome nao localizado na pagina",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )
                await nome_el.fill(payload.nome)

                email_el = page.locator('input[name="email"]')
                if await email_el.count() == 0:
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem="Campo obrigatorio email nao localizado na pagina",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )
                await email_el.fill(payload.email)

                tel_el = page.locator('input[name="telefone"]')
                if await tel_el.count() == 0:
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem="Campo obrigatorio telefone nao localizado na pagina",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )
                await tel_el.fill(payload.telefone)

                contrato_el = page.locator('input[name="contrato"]')
                if await contrato_el.count() == 0:
                    # Altered selector scenario detected by On-Call DOM inspection
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem="Campo contrato nao encontrado no formulario (seletor alterado ou ausente)",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )
                await contrato_el.fill(payload.contrato)

                if payload.observacoes:
                    obs_el = page.locator('textarea[name="observacoes"], input[name="observacoes"]')
                    if await obs_el.count() > 0:
                        await obs_el.fill(payload.observacoes)

                # Upload files
                await page.locator('input[name="boleto"]').set_input_files(boleto_file)
                await page.locator('input[name="comprovante"]').set_input_files(comp_file)

                # Click submit button
                submit_btn = page.locator('#submit-btn, button[type="submit"]')
                if await submit_btn.count() == 0:
                    await page.screenshot(path=screenshot_path)
                    return SubmissionReceipt(
                        status=StatusSubmissao.ERRO,
                        protocolo=None,
                        mensagem="Botao de submissao (#submit-btn) nao encontrado",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )

                await submit_btn.click()

                # Wait for protocol result
                try:
                    await page.wait_for_selector(
                        '#protocolo, :text-matches("IBAGY-2026-[A-Z0-9]+")',
                        timeout=15000,
                    )
                except Exception:
                    pass

                await page.screenshot(path=screenshot_path)
                page_text = await page.content()

                match = re.search(r"IBAGY-2026-[A-Z0-9]+", page_text)
                if match:
                    protocol = match.group(0)
                    return SubmissionReceipt(
                        status=StatusSubmissao.SUCESSO,
                        protocolo=protocol,
                        mensagem=f"Submissao realizada com sucesso via navegador. Protocolo: {protocol}",
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                    )
                return SubmissionReceipt(
                    status=StatusSubmissao.ERRO,
                    protocolo=None,
                    mensagem="Formulario enviado via navegador porem protocolo nao localizado",
                    screenshot_path=screenshot_path,
                    trace_id=trace_id,
                )

            except Exception as exc:
                try:
                    await page.screenshot(path=screenshot_path)
                except Exception:
                    pass
                return SubmissionReceipt(
                    status=StatusSubmissao.ERRO,
                    protocolo=None,
                    mensagem=f"Erro durante execucao do navegador Playwright: {str(exc)}",
                    screenshot_path=screenshot_path if os.path.exists(screenshot_path) else None,
                    trace_id=trace_id,
                )
            finally:
                await browser.close()
    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()


async def submit_reimbursement(
    payload: SubmissionPayload,
    db_session: Optional[Session] = None,
    trace_id: Optional[str] = None,
    target_url: Optional[str] = None,
    use_browser: bool = False,
    client: Optional[httpx.AsyncClient] = None,
    extra_headers: Optional[dict[str, str]] = None,
    screenshots_dir: Optional[str] = None,
) -> SubmissionReceipt:
    """
    Submit condo reimbursement request to Bitrix24 CRM form.
    Correlates trace_id and records submission receipt in SubmissaoRessarcimento table.
    """
    resolved_trace_id = get_or_create_trace_id(trace_id)
    url = resolve_target_url(target_url)

    if use_browser:
        receipt = await _submit_via_browser(
            payload=payload,
            target_url=url,
            trace_id=resolved_trace_id,
            screenshots_dir=screenshots_dir,
            extra_headers=extra_headers,
        )
    else:
        receipt = await _submit_via_http(
            payload=payload,
            target_url=url,
            trace_id=resolved_trace_id,
            client=client,
            extra_headers=extra_headers,
        )

    # Persist record in database if session provided
    if db_session is not None:
        try:
            submissao = SubmissaoRessarcimento(
                ciclo_id=payload.ciclo_id,
                contrato_numero=payload.contrato,
                payload_enviado={
                    "nome": payload.nome,
                    "email": payload.email,
                    "telefone": payload.telefone,
                    "contrato": payload.contrato,
                    "observacoes": payload.observacoes,
                },
                status=receipt.status,
                protocolo_retorno=receipt.protocolo,
                screenshot_path=receipt.screenshot_path,
                tentativas=1,
                trace_id=resolved_trace_id,
                enviado_em=datetime.now(timezone.utc),
            )
            db_session.add(submissao)

            if payload.ciclo_id and receipt.status == StatusSubmissao.SUCESSO:
                ciclo = db_session.get(CicloCondominio, payload.ciclo_id)
                if ciclo is not None:
                    ciclo.status_ciclo = StatusCiclo.ENVIADO

            db_session.commit()
        except Exception as db_exc:
            logger.error(f"Erro ao persistir SubmissaoRessarcimento no banco: {db_exc}")
            db_session.rollback()

    return receipt
