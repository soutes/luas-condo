"""
Seed script for populating realistic production condominium cycle data.
Executes the deterministic parser and legal audit engine on the reference Villa Salomy bill.
No emojis used.
"""

import os
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine, init_db
from app.models.entities import (
    CategoriaItem,
    CicloCondominio,
    ItemRateio,
    ResponsabilidadeItem,
    StatusCiclo,
)
from app.services.audit_engine import audit_condo_bill
from app.services.parser_boleto import parse_condo_text

SAMPLE_BILL_TEXT = """CONDOMINIO EDIFICIO VILLA SALOMY
CNPJ: 08.123.456/0001-89
DEMONSTRATIVO DE RATEIO DE 01/09/2026 ATÉ 30/09/2026
VENCIMENTO: 10/10/2026
UNIDADE: 802 - APARTAMENTO
FRAÇÃO IDEAL: 0,04166

DESCRIÇÃO DAS DESPESAS                           TOTAL CONDOMÍNIO    VALOR UNIDADE

DESPESAS ORDINÁRIAS
Manutenção e Conservação de Elevadores                   1.500,00           150,00
Energia Elétrica Áreas Comuns                            1.205,00           120,50
Serviços de Limpeza e Portaria                           2.107,70           210,77
Honorários de Administração                              1.150,00           115,00
SUBTOTAL ORDINÁRIAS                                                         596,27

DESPESAS EXTRAORDINÁRIAS
Seguro Obrigatório Predial Parc 2/6                        442,56            18,44
Tarifa Bancária                                             54,96             2,29
Laudo Bombeiro Parc 2/3                                    263,04            10,96
Rateio Manutenção Fachada Parc 6/10                      4.998,96           208,29
Rateio fiscalização obra da fachada                      1.317,36            54,89
SUBTOTAL EXTRAORDINÁRIAS                                                    294,87

LEITURAS
GÁS                                                         62,21             62,21
ÁGUA                                                       141,33            141,33
SUBTOTAL LEITURAS                                                           203,54

FUNDOS
Fundo de Reserva 10,00%                                    596,30             59,63
SUBTOTAL FUNDOS                                                              59,63

RESUMO DO RATEIO
Total Ordinárias: 596,27
Total Extraordinárias: 294,87
Total Leituras: 203,54
Total Fundos: 59,63
VALOR TOTAL: 1.154,31

13691.10802 00102.557006 00000.514034 2 15950000115431
"""


def seed_production_cycle(
    db: Session | None = None,
    storage_dir: str = "/data/storage",
    reset_existing: bool = True,
) -> CicloCondominio:
    """Parse reference bill, audit legal expenses, and persist cycle to database."""
    close_on_exit = False
    if db is None:
        init_db()
        db = SessionLocal()
        close_on_exit = True

    try:
        storage_path = Path(storage_dir)
        storage_path.mkdir(parents=True, exist_ok=True)

        boleto_path = storage_path / "villa_salomy_2026_09.pdf"
        if not boleto_path.exists():
            boleto_path.write_bytes(b"%PDF-1.4 Mock Villa Salomy 2026-09 Boleto Content")

        pix_path = storage_path / "comprovante_pix_2026_09.pdf"
        if not pix_path.exists():
            pix_path.write_bytes(b"%PDF-1.4 Mock Comprovante PIX 2026-09 Payment Content")

        parsed_bill = parse_condo_text(SAMPLE_BILL_TEXT)
        audit_report = audit_condo_bill(parsed_bill)

        existing = (
            db.query(CicloCondominio)
            .filter_by(competencia=parsed_bill.competencia)
            .first()
        )

        if existing and reset_existing:
            db.delete(existing)
            db.commit()
            existing = None

        if not existing:
            ciclo = CicloCondominio(
                competencia=parsed_bill.competencia,
                condominio_nome=parsed_bill.condominio_nome,
                data_vencimento=parsed_bill.data_vencimento,
                valor_total=parsed_bill.valor_total,
                valor_ordinarias=parsed_bill.valor_ordinarias,
                valor_extraordinarias=parsed_bill.valor_extraordinarias,
                valor_fundos=parsed_bill.valor_fundos,
                valor_leituras=parsed_bill.valor_leituras,
                valor_ressarcimento=audit_report.total_reimbursement,
                boleto_pdf_path=str(boleto_path),
                comprovante_pix_path=str(pix_path),
                status_ciclo=StatusCiclo.PRONTO_PARA_ENVIO,
            )
            db.add(ciclo)
            db.flush()

            for item in audit_report.itens_auditados:
                orig_item = next(
                    (i for i in parsed_bill.itens if i.descricao == item.descricao),
                    None,
                )
                total_condo = orig_item.valor_total_condominio if orig_item else None

                item_record = ItemRateio(
                    ciclo_id=ciclo.id,
                    categoria=item.categoria,
                    descricao=item.descricao,
                    valor_unidade=item.valor,
                    valor_total_condominio=total_condo,
                    responsabilidade=item.responsabilidade,
                    justificativa_legal=item.justificativa_legal,
                )
                db.add(item_record)

            db.commit()
            db.refresh(ciclo)
            return ciclo
        else:
            return existing
    finally:
        if close_on_exit:
            db.close()


if __name__ == "__main__":
    target_storage = os.getenv("STORAGE_DIR", "./data/storage")
    ciclo = seed_production_cycle(storage_dir=target_storage)
    print("Ciclo populado com sucesso no banco de dados:")
    print(f"  ID: {ciclo.id}")
    print(f"  Competencia: {ciclo.competencia}")
    print(f"  Condominio: {ciclo.condominio_nome}")
    print(f"  Vencimento: {ciclo.data_vencimento}")
    print(f"  Valor Total: R$ {ciclo.valor_total}")
    print(f"  Valor Ressarcimento (Locador): R$ {ciclo.valor_ressarcimento}")
    print(f"  Status: {ciclo.status_ciclo.value}")
    print(f"  Total de Itens: {len(ciclo.itens)}")
