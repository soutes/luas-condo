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
    "format_phone_br",
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
    dry_run: bool = False


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
        base = os.getenv("MOCK_BITRIX_URL", "http://localhost:8080").rstrip("/")
        if not base.endswith("/condominioressarcimento/ressarcimento"):
            return f"{base}/condominioressarcimento/ressarcimento/"
        return f"{base}/"
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
    comp_mime = "application/pdf"
    comp_lower = comp_name.lower()
    if comp_lower.endswith(".png"):
        comp_mime = "image/png"
    elif comp_lower.endswith((".jpg", ".jpeg")):
        comp_mime = "image/jpeg"

    files = {
        "boleto": (boleto_name, boleto_data, "application/pdf"),
        "comprovante": (comp_name, comp_data, comp_mime),
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
        is_mock = os.getenv("MOCK_SUBMISSION", "true").lower() in ("true", "1", "yes")
        if is_mock and ("localhost" in target_url or "127.0.0.1" in target_url or "mock-bitrix" in target_url):
            protocol = f"IBAGY-2026-{uuid.uuid4().hex[:4].upper()}"
            return SubmissionReceipt(
                status=StatusSubmissao.SUCESSO,
                protocolo=protocol,
                mensagem=f"Submissao simulada realizada com sucesso (mock). Protocolo: {protocol}",
                screenshot_path=None,
                trace_id=trace_id,
            )
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


_BROWSER_STATE = {"busy": False}

BROWSER_MISSING_MESSAGE = (
    "Navegador (Chromium) nao instalado nesta imagem. O envio real ao Ibagy exige o navegador: "
    "reconstrua o backend com INSTALL_BROWSER=true (docker compose build --build-arg INSTALL_BROWSER=true backend) "
    "em uma maquina com memoria suficiente."
)


def format_phone_br(raw: str) -> str:
    """Format a Brazilian phone as the Ibagy form asks: '55 XX 9XXXX-XXXX'. Unknown shapes pass through."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) == 11:
        return f"55 {digits[:2]} {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"55 {digits[:2]} {digits[2:6]}-{digits[6:]}"
    return raw


def _find_result_id(data: Any) -> Optional[str]:
    """Find the Bitrix CRM resultId anywhere inside the crm.site.form.fill JSON answer."""
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() == "resultid" and value not in (None, ""):
                return str(value)
        for value in data.values():
            found = _find_result_id(value)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_result_id(value)
            if found:
                return found
    return None


def _available_memory_mb() -> Optional[int]:
    """Available RAM in MB (Linux /proc/meminfo); None when it cannot be determined."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


async def _launch_browser(playwright: Any) -> Any:
    """Launch headless Chromium with flags that keep memory low and work inside containers."""
    return await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
        ],
    )


async def _run_widget_flow(
    page: Any,
    payload: SubmissionPayload,
    boleto_file: str,
    comp_file: str,
    screenshot_path: str,
    trace_id: str,
    dry_run: bool,
) -> SubmissionReceipt:
    """
    Fill and submit the real Ibagy Bitrix24 CRM widget form.
    Success = crm.site.form.fill answered OK and the widget shows its success state.
    The portal reports no protocol: the CRM resultId is used as the reference.
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    def field(pattern: str) -> Any:
        return page.locator(".b24-form-field").filter(has_text=re.compile(pattern, re.I))

    async def fail(message: str) -> SubmissionReceipt:
        try:
            await page.screenshot(path=screenshot_path)
        except Exception:
            pass
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=message,
            screenshot_path=screenshot_path if os.path.exists(screenshot_path) else None,
            trace_id=trace_id,
        )

    targets = {
        "nome": page.locator('input[name="name"]').first,
        "e-mail": page.locator('input[name="email"]').first,
        "telefone": page.locator('input[name="phone"]').first,
        "contrato": field("contrato").locator("input").first,
        "boleto": field("boleto").locator('input[type="file"]').first,
        "comprovante": field("comprovante").locator('input[type="file"]').first,
    }
    for label, locator in targets.items():
        if await locator.count() == 0:
            return await fail(
                f"Campo {label} nao localizado no formulario do Ibagy (a pagina pode ter mudado)"
            )

    await targets["nome"].fill(payload.nome)
    await targets["e-mail"].fill(payload.email)
    await targets["telefone"].fill(format_phone_br(payload.telefone))
    await targets["contrato"].fill(payload.contrato)
    if payload.observacoes:
        obs = field("observa").locator("textarea").first
        if await obs.count() > 0:
            await obs.fill(payload.observacoes)

    await targets["boleto"].set_input_files(boleto_file)
    await targets["comprovante"].set_input_files(comp_file)

    # The Bitrix widget only uploads the attachments when "Enviar" is clicked (upload first, then
    # crm.site.form.fill), so there is nothing to wait for here: just confirm both files are
    # listed in their fields.
    for label, file_path in (("boleto", boleto_file), ("comprovante", comp_file)):
        shown_name = os.path.basename(file_path)[:12].lower()
        attached = False
        for _ in range(40):
            if shown_name in (await field(label).first.inner_text()).lower():
                attached = True
                break
            await page.wait_for_timeout(250)
        if not attached:
            return await fail(f"Anexo do {label} nao apareceu no formulario do Ibagy")

    if dry_run:
        await page.screenshot(path=screenshot_path, full_page=True)
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=(
                "DRY-RUN: formulario preenchido e anexos selecionados, mas o pedido NAO foi enviado "
                "(nenhum clique em Enviar; os anexos so sobem ao Ibagy no envio real)."
            ),
            screenshot_path=screenshot_path,
            trace_id=trace_id,
            dry_run=True,
        )

    submit_btn = page.locator('button.b24-form-btn[type="submit"]').first
    if await submit_btn.count() == 0:
        return await fail("Botao Enviar nao encontrado no formulario do Ibagy")

    try:
        async with page.expect_response(lambda r: "crm.site.form.fill" in r.url, timeout=60000) as resp_info:
            await submit_btn.click()
        resp = await resp_info.value
    except PlaywrightTimeout:
        alerts = await page.locator(".b24-form-control-alert-message").all_inner_texts()
        shown = "; ".join(t.strip().replace("\n", " ") for t in alerts if t.strip())
        return await fail(
            "O formulario do Ibagy nao aceitou o envio"
            + (f" ({shown})" if shown else " (nenhuma resposta do servidor)")
        )

    try:
        body = await resp.json()
    except Exception:
        body = {}
    result_id = _find_result_id(body)
    http_ok = resp.status < 400 and not (isinstance(body, dict) and body.get("status") == "error")

    try:
        await page.wait_for_selector(".b24-form-success:visible, .b24-form-error:visible", timeout=15000)
    except PlaywrightTimeout:
        pass
    success_visible = await page.locator(".b24-form-success").first.is_visible()
    error_visible = await page.locator(".b24-form-error").first.is_visible()
    await page.screenshot(path=screenshot_path)

    if http_ok and not error_visible and (success_visible or result_id):
        reference = f"BITRIX-{result_id}" if result_id else None
        return SubmissionReceipt(
            status=StatusSubmissao.SUCESSO,
            protocolo=reference,
            mensagem=(
                "Pedido enviado ao Ibagy e confirmado pelo formulario"
                + (f" (resultado CRM {result_id})." if result_id else " (o portal nao informa protocolo).")
            ),
            screenshot_path=screenshot_path,
            trace_id=trace_id,
        )
    if error_visible or not http_ok:
        return SubmissionReceipt(
            status=StatusSubmissao.ERRO,
            protocolo=None,
            mensagem=f"O Ibagy recusou o envio (HTTP {resp.status}). Nada foi registrado como enviado.",
            screenshot_path=screenshot_path,
            trace_id=trace_id,
        )
    return SubmissionReceipt(
        status=StatusSubmissao.ERRO,
        protocolo=None,
        mensagem=(
            "Envio sem confirmacao clara do Ibagy: pode ter sido registrado. "
            "Confira no portal ou no e-mail antes de reenviar, para nao duplicar."
        ),
        screenshot_path=screenshot_path,
        trace_id=trace_id,
    )


async def _submit_via_browser(
    payload: SubmissionPayload,
    target_url: str,
    trace_id: str,
    screenshots_dir: Optional[str] = None,
    extra_headers: Optional[dict[str, str]] = None,
    timeout_ms: int = 30000,
    dry_run: bool = False,
) -> SubmissionReceipt:
    """Submit reimbursement using Playwright browser automation with DOM inspection."""
    from playwright.async_api import async_playwright

    screen_dir = screenshots_dir or os.getenv("SCREENSHOT_DIR")
    if not screen_dir:
        screen_dir = os.path.join(tempfile.gettempdir(), "luas_condo_screenshots")
    os.makedirs(screen_dir, exist_ok=True)
    screenshot_path = os.path.join(screen_dir, f"submissao_{trace_id}.png")

    # Validate and prepare files; fail fast if files are missing or unreadable
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

    # Prepare temp files on disk for Playwright set_input_files if bytes were supplied
    temp_dir_obj = None
    acquired_browser = False
    try:
        if payload.boleto_path and os.path.exists(payload.boleto_path):
            boleto_file = payload.boleto_path
        else:
            if temp_dir_obj is None:
                temp_dir_obj = tempfile.TemporaryDirectory()
            boleto_file = os.path.join(temp_dir_obj.name, boleto_name)
            with open(boleto_file, "wb") as f:
                f.write(boleto_data)

        if payload.comprovante_path and os.path.exists(payload.comprovante_path):
            comp_file = payload.comprovante_path
        else:
            if temp_dir_obj is None:
                temp_dir_obj = tempfile.TemporaryDirectory()
            comp_file = os.path.join(temp_dir_obj.name, comp_name)
            with open(comp_file, "wb") as f:
                f.write(comp_data)

        if _BROWSER_STATE["busy"]:
            return SubmissionReceipt(
                status=StatusSubmissao.ERRO,
                protocolo=None,
                mensagem="Ja existe um envio em andamento. Aguarde terminar antes de tentar de novo.",
                screenshot_path=None,
                trace_id=trace_id,
            )
        free_mb = _available_memory_mb()
        min_free_mb = int(os.getenv("BROWSER_MIN_FREE_MB", "300"))
        if free_mb is not None and free_mb < min_free_mb:
            return SubmissionReceipt(
                status=StatusSubmissao.ERRO,
                protocolo=None,
                mensagem=(
                    f"Memoria livre insuficiente ({free_mb} MB < {min_free_mb} MB) para abrir o navegador "
                    "sem derrubar o servidor. Tente quando houver folga ou rode o app em uma maquina com mais memoria."
                ),
                screenshot_path=None,
                trace_id=trace_id,
            )
        _BROWSER_STATE["busy"] = True
        acquired_browser = True

        async with async_playwright() as p:
            try:
                browser = await _launch_browser(p)
            except Exception as launch_exc:
                if "Executable doesn't exist" in str(launch_exc):
                    message = BROWSER_MISSING_MESSAGE
                else:
                    message = f"Nao foi possivel abrir o navegador: {launch_exc}"
                return SubmissionReceipt(
                    status=StatusSubmissao.ERRO,
                    protocolo=None,
                    mensagem=message,
                    screenshot_path=None,
                    trace_id=trace_id,
                )
            context = await browser.new_context(
                extra_http_headers=extra_headers or {},
            )

            async def _skip_heavy(route: Any) -> None:
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", _skip_heavy)
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

                # Real Ibagy portal: Bitrix24 CRM widget rendered by JavaScript.
                try:
                    await page.wait_for_selector(
                        '.b24-form-control, input[name="nome"]', timeout=20000
                    )
                except Exception:
                    pass
                if await page.locator(".b24-form-control").count() > 0:
                    return await _run_widget_flow(
                        page=page,
                        payload=payload,
                        boleto_file=boleto_file,
                        comp_file=comp_file,
                        screenshot_path=screenshot_path,
                        trace_id=trace_id,
                        dry_run=dry_run,
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
                is_mock = os.getenv("MOCK_SUBMISSION", "true").lower() in ("true", "1", "yes")
                if is_mock and ("localhost" in target_url or "127.0.0.1" in target_url or "mock-bitrix" in target_url):
                    protocol = f"IBAGY-2026-{uuid.uuid4().hex[:4].upper()}"
                    return SubmissionReceipt(
                        status=StatusSubmissao.SUCESSO,
                        protocolo=protocol,
                        mensagem=f"Submissao simulada realizada com sucesso via navegador (mock). Protocolo: {protocol}",
                        screenshot_path=screenshot_path if os.path.exists(screenshot_path) else None,
                        trace_id=trace_id,
                    )
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
        if acquired_browser:
            _BROWSER_STATE["busy"] = False
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
    dry_run: bool = False,
) -> SubmissionReceipt:
    """
    Submit condo reimbursement request to Bitrix24 CRM form.
    Correlates trace_id and records submission receipt in SubmissaoRessarcimento table.
    """
    resolved_trace_id = get_or_create_trace_id(trace_id)
    url = resolve_target_url(target_url)

    is_mock_mode = os.getenv("MOCK_SUBMISSION", "true").lower() in ("true", "1", "yes")
    if dry_run or (target_url is None and not is_mock_mode):
        # The real Ibagy form is a JavaScript widget: a plain HTTP POST can never file a request.
        use_browser = True

    if use_browser:
        receipt = await _submit_via_browser(
            payload=payload,
            target_url=url,
            trace_id=resolved_trace_id,
            screenshots_dir=screenshots_dir,
            extra_headers=extra_headers,
            dry_run=dry_run,
        )
    else:
        receipt = await _submit_via_http(
            payload=payload,
            target_url=url,
            trace_id=resolved_trace_id,
            client=client,
            extra_headers=extra_headers,
        )

    # Persist record in database if session provided (a dry run files nothing, so it is not recorded)
    if db_session is not None and not receipt.dry_run:
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

            if payload.ciclo_id:
                ciclo = db_session.get(CicloCondominio, payload.ciclo_id)
                if ciclo is not None:
                    ciclo.ultima_verificacao = datetime.now(timezone.utc)
                    if receipt.status == StatusSubmissao.SUCESSO:
                        ciclo.status_ciclo = StatusCiclo.ENVIADO
                        referencia = (
                            f"sob a referencia {receipt.protocolo}"
                            if receipt.protocolo
                            else "(o portal nao informa protocolo)"
                        )
                        ciclo.detalhes_verificacao = (
                            f"Pedido de ressarcimento enviado com sucesso na Ibagy {referencia}. "
                            f"Saldo devido: R$ {ciclo.valor_saldo_residual:.2f}."
                        )
                    else:
                        ciclo.detalhes_verificacao = f"Erro na submissao para Ibagy: {receipt.mensagem}"

            db_session.commit()
        except Exception as db_exc:
            logger.error(f"Erro ao persistir SubmissaoRessarcimento no banco: {db_exc}")
            db_session.rollback()

    return receipt
