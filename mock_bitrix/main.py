"""
Mock Bitrix24 server for Luas Condo reimbursement submission.
Replicates Bitrix24 CRM web form, validates fields, generates protocol (IBAGY-2026-XXXX),
and supports error injection for On-Call drills (x-simulate-status and x-simulate-selector).
No emojis used.
"""

from typing import Optional
import uuid

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="Mock Bitrix24 Ibagy Reimbursement Server",
    description="Mock CRM form for tenant condo reimbursement testing and on-call drills.",
    version="1.0.0",
)


def _render_form_html(contrato_field_name: str = "contrato") -> str:
    """Generate HTML form with configurable field names for DOM alteration drills."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Ibagy - Ressarcimento de Condominio</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; background: #f8fafc; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .form-group {{ margin-bottom: 1rem; display: flex; flex-direction: column; }}
    label {{ font-weight: bold; margin-bottom: 0.25rem; font-size: 0.9rem; }}
    input, textarea {{ padding: 0.5rem; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 1rem; }}
    button {{ background: #2563eb; color: #fff; padding: 0.75rem; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #1d4ed8; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Solicitacao de Ressarcimento de Condominio</h1>
    <form id="reimbursement-form" method="POST" enctype="multipart/form-data">
      <div class="form-group">
        <label for="nome">Nome do inquilino *</label>
        <input type="text" id="nome" name="nome" required>
      </div>

      <div class="form-group">
        <label for="email">E-mail *</label>
        <input type="email" id="email" name="email" required>
      </div>

      <div class="form-group">
        <label for="telefone">Telefone *</label>
        <input type="text" id="telefone" name="telefone" placeholder="55 48 99999-9999" required>
      </div>

      <div class="form-group">
        <label for="{contrato_field_name}">Numero do contrato *</label>
        <input type="text" id="{contrato_field_name}" name="{contrato_field_name}" placeholder="09638.003.03" required>
      </div>

      <div class="form-group">
        <label for="observacoes">Observacoes</label>
        <textarea id="observacoes" name="observacoes" rows="3"></textarea>
      </div>

      <div class="form-group">
        <label for="boleto">Boleto condominio *</label>
        <input type="file" id="boleto" name="boleto" accept=".pdf" required>
      </div>

      <div class="form-group">
        <label for="comprovante">Comprovante de pagamento *</label>
        <input type="file" id="comprovante" name="comprovante" accept=".pdf,.png,.jpg,.jpeg" required>
      </div>

      <button type="submit" id="submit-btn">Enviar Ressarcimento</button>
    </form>
  </div>
</body>
</html>"""


def _render_success_html(protocol: str) -> str:
    """Generate HTML confirmation page with protocol element."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Submissao Concluida - Ibagy</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; background: #f8fafc; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #fff; padding: 2rem; border-radius: 8px; text-align: center; }}
    .protocol-box {{ background: #eff6ff; border: 2px dashed #3b82f6; padding: 1.5rem; margin: 1.5rem 0; border-radius: 6px; }}
    .protocol-number {{ font-size: 1.5rem; font-weight: bold; color: #1e40af; letter-spacing: 1px; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Solicitacao Recebida!</h1>
    <p>Sua solicitacao de ressarcimento foi enviada com sucesso para analise.</p>
    <div class="protocol-box">
      <div>Numero do Protocolo:</div>
      <div id="protocolo" class="protocol-number">{protocol}</div>
    </div>
    <p>Guarde este numero para acompanhar o status do seu ressarcimento.</p>
  </div>
</body>
</html>"""


def _render_widget_html(fail: bool = False) -> str:
    """
    HTML that imitates the real Ibagy Bitrix24 CRM form widget (b24-form classes, field
    names name/email/phone, two file fields, an 'Enviar' button and success/error states).
    The real portal reports no protocol: it answers crm.site.form.fill with a CRM resultId.
    """
    fail_qs = "&fail=1" if fail else ""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Formulario do cliente (mock widget Bitrix24)</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    .b24-form-field {{ margin-bottom: 1rem; display: flex; flex-direction: column; }}
    .b24-form-control {{ padding: 0.5rem; }}
    .b24-form-state {{ display: none; padding: 1rem; margin-top: 1rem; }}
    .b24-form-state.visible {{ display: block; }}
  </style>
</head>
<body>
  <p>Segue link de orientacao do local para encontrar o numero do seu contrato.</p>
  <div class="b24-form">
    <form id="b24-form" novalidate>
      <div class="b24-form-field"><label class="b24-form-control-label">Nome do inquilino *</label>
        <input class="b24-form-control" type="text" name="name" id="b24-form-field-2"></div>
      <div class="b24-form-field"><label class="b24-form-control-label">E-mail *</label>
        <input class="b24-form-control" type="email" name="email" id="b24-form-field-3"></div>
      <div class="b24-form-field"><label class="b24-form-control-label">Telefone *</label>
        <input class="b24-form-control" type="tel" name="phone" id="b24-form-field-4"></div>
      <div class="b24-form-field"><label class="b24-form-control-label">Numero do contrato *</label>
        <input class="b24-form-control" type="text" id="b24-form-field-5"></div>
      <div class="b24-form-field"><label class="b24-form-control-label">Observacoes</label>
        <textarea class="b24-form-control" id="b24-form-field-6"></textarea></div>
      <div class="b24-form-field"><label class="b24-form-control-label">Boleto condominio*</label>
        <input type="file" id="file-boleto" class="upload"></div>
      <div class="b24-form-field"><label class="b24-form-control-label">Comprovante de pagamento*</label>
        <input type="file" id="file-comprovante" class="upload"></div>
      <button type="submit" class="b24-form-btn">Enviar</button>
    </form>
    <div class="b24-form-state b24-form-success" role="status">Obrigado! Recebemos sua solicitacao.</div>
    <div class="b24-form-state b24-form-error" role="alert">Falha ao enviar o formulario.</div>
  </div>
  <script>
    const ajax = (action, body) => fetch('/bitrix/services/main/ajax.php?action=' + action + '{fail_qs}', {{ method: 'POST', body }});
    // Like the real widget: selecting a file only lists its name; the upload happens on submit.
    document.querySelectorAll('input.upload').forEach(el => el.addEventListener('change', () => {{
      const tag = document.createElement('span'); tag.textContent = el.files[0].name;
      el.parentElement.appendChild(tag);
    }}));
    document.getElementById('b24-form').addEventListener('submit', async (ev) => {{
      ev.preventDefault();
      const ok = (id) => document.getElementById(id).value.trim() !== '';
      if (!(ok('b24-form-field-2') && ok('b24-form-field-3') && ok('b24-form-field-4') && ok('b24-form-field-5'))
          || !document.getElementById('file-boleto').files.length || !document.getElementById('file-comprovante').files.length) {{
        return;
      }}
      for (const id of ['file-boleto', 'file-comprovante']) {{
        const up = new FormData(); up.append('file', document.getElementById(id).files[0]);
        await ajax('crm.site.fileUploader.upload', up);
      }}
      const fd = new FormData();
      fd.append('name', document.getElementById('b24-form-field-2').value);
      fd.append('email', document.getElementById('b24-form-field-3').value);
      fd.append('phone', document.getElementById('b24-form-field-4').value);
      fd.append('contrato', document.getElementById('b24-form-field-5').value);
      fd.append('observacoes', document.getElementById('b24-form-field-6').value);
      const res = await ajax('crm.site.form.fill', fd);
      const data = await res.json().catch(() => ({{}}));
      if (res.ok && data.status === 'success') {{
        document.querySelector('.b24-form-success').classList.add('visible');
      }} else {{
        document.querySelector('.b24-form-error').classList.add('visible');
      }}
    }});
  </script>
</body>
</html>"""


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "mock-bitrix"}


@app.get("/")
@app.get("/condominioressarcimento/ressarcimento/")
async def get_form(
    request: Request,
    x_simulate_status: Optional[str] = Header(None, alias="x-simulate-status"),
    x_simulate_selector: Optional[str] = Header(None, alias="x-simulate-selector"),
    simulate_status: Optional[str] = Query(None),
    simulate_selector: Optional[str] = Query(None),
):
    # Error simulation check
    status_code = x_simulate_status or simulate_status
    if status_code:
        try:
            code = int(status_code)
            return Response(
                content=f"Simulated Bitrix server status error: {code}",
                status_code=code,
                media_type="text/plain",
            )
        except ValueError:
            pass

    # Selector simulation check
    selector_override = x_simulate_selector or simulate_selector
    contrato_field = "contrato"
    if selector_override:
        if selector_override.lower() in ("true", "1", "yes"):
            contrato_field = "contrato_num"
        else:
            contrato_field = selector_override

    return HTMLResponse(content=_render_form_html(contrato_field))


@app.post("/")
@app.post("/condominioressarcimento/ressarcimento/")
@app.post("/submit")
async def post_reimbursement(
    request: Request,
    x_simulate_status: Optional[str] = Header(None, alias="x-simulate-status"),
    simulate_status: Optional[str] = Query(None),
):
    # Error simulation check
    status_code = x_simulate_status or simulate_status
    if status_code:
        try:
            code = int(status_code)
            return JSONResponse(
                status_code=code,
                content={"error": f"Simulated server error HTTP {code}"},
            )
        except ValueError:
            pass

    # Read form data
    form = await request.form()
    nome = form.get("nome")
    email = form.get("email")
    telefone = form.get("telefone")
    contrato = form.get("contrato")
    observacoes = form.get("observacoes", "")
    boleto = form.get("boleto")
    comprovante = form.get("comprovante")

    # Validate mandatory text fields
    if not nome or not str(nome).strip():
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente: nome"},
        )
    if not email or "@" not in str(email):
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente ou invalido: email"},
        )
    if not telefone or not str(telefone).strip():
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente: telefone"},
        )
    if not contrato or not str(contrato).strip():
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente: contrato"},
        )

    # Validate mandatory files
    if not boleto or not hasattr(boleto, "filename") or not boleto.filename:
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente: boleto"},
        )
    if not comprovante or not hasattr(comprovante, "filename") or not comprovante.filename:
        return JSONResponse(
            status_code=400,
            content={"detail": "Campo obrigatorio ausente: comprovante"},
        )

    # Generate protocol number matching IBAGY-2026-XXXX format
    protocol = f"IBAGY-2026-{uuid.uuid4().hex[:4].upper()}"

    # Return HTML if requested by browser navigation, otherwise JSON
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header and "application/json" not in accept_header:
        return HTMLResponse(content=_render_success_html(protocol))

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "protocolo": protocol,
            "mensagem": f"Submissao realizada com sucesso. Protocolo: {protocol}",
            "contrato": str(contrato),
            "nome": str(nome),
            "observacoes": str(observacoes),
        },
    )


@app.get("/widget/ressarcimento/")
async def get_widget_form(fail: Optional[str] = Query(None)):
    """Page imitating the real Bitrix24 widget form (see _render_widget_html)."""
    return HTMLResponse(content=_render_widget_html(fail=bool(fail)))


@app.post("/bitrix/services/main/ajax.php")
async def bitrix_ajax(action: str = Query(...), fail: Optional[str] = Query(None)):
    """Imitates the two Bitrix ajax actions the widget uses (file upload, form fill)."""
    if action == "crm.site.fileUploader.upload":
        return JSONResponse({"status": "success", "data": {"file": {"id": uuid.uuid4().hex[:8]}}})
    if action == "crm.site.form.fill":
        if fail:
            return JSONResponse(status_code=500, content={"status": "error", "errors": [{"message": "simulated"}]})
        return JSONResponse({"status": "success", "data": {"resultId": 4242}})
    return JSONResponse(status_code=404, content={"status": "error", "errors": [{"message": "unknown action"}]})
