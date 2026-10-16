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
