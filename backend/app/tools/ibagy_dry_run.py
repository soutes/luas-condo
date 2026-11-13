"""
Dry run of the real Ibagy submission: opens the portal form, fills every field and attaches the
two PDFs, saves a screenshot and STOPS before clicking "Enviar". Nothing is filed.

Note: the Bitrix widget only uploads the attachments when "Enviar" is clicked, so a dry run
sends nothing to Ibagy: files are merely selected in the browser.

Usage (needs Chromium: build with INSTALL_BROWSER=true or run `playwright install chromium`):
    python -m app.tools.ibagy_dry_run --boleto boleto.pdf --comprovante comprovante.pdf
Reads IBAGY_TENANT_NAME / IBAGY_TENANT_EMAIL / IBAGY_TENANT_PHONE / IBAGY_CONTRACT_NUM.
No emojis used.
"""

import argparse
import asyncio
import os
import sys

from app.services.bitrix_submitter import SubmissionPayload, submit_reimbursement


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill the real Ibagy form without submitting it")
    parser.add_argument("--boleto", required=True, help="path to the condominium boleto PDF")
    parser.add_argument("--comprovante", required=True, help="path to the payment receipt (PDF/PNG/JPG)")
    parser.add_argument("--url", default=None, help="override the form URL (default: IBAGY_BITRIX_URL)")
    parser.add_argument("--observacoes", default="Teste de preenchimento (dry run), nao enviar.")
    args = parser.parse_args()

    # A dry run always targets the real portal unless --url is given.
    os.environ["MOCK_SUBMISSION"] = "false"

    payload = SubmissionPayload(
        nome=os.getenv("IBAGY_TENANT_NAME", ""),
        email=os.getenv("IBAGY_TENANT_EMAIL", ""),
        telefone=os.getenv("IBAGY_TENANT_PHONE", ""),
        contrato=os.getenv("IBAGY_CONTRACT_NUM", ""),
        observacoes=args.observacoes,
        boleto_path=args.boleto,
        comprovante_path=args.comprovante,
    )
    missing = [k for k in ("nome", "email", "telefone", "contrato") if not getattr(payload, k)]
    if missing:
        print(f"Defina as variaveis IBAGY_TENANT_* / IBAGY_CONTRACT_NUM (faltando: {', '.join(missing)})", file=sys.stderr)
        return 2

    receipt = asyncio.run(submit_reimbursement(payload=payload, target_url=args.url, dry_run=True))
    print(receipt.mensagem)
    if receipt.screenshot_path:
        print(f"Screenshot: {receipt.screenshot_path}")
    return 0 if receipt.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
