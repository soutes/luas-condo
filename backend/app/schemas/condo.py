from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.entities import (
    CategoriaItem,
    ResponsabilidadeItem,
    StatusCiclo,
    StatusIncidente,
    StatusSubmissao,
)


# ItemRateio Schemas
class ItemRateioBase(BaseModel):
    categoria: CategoriaItem
    descricao: str
    valor_unidade: Decimal
    valor_total_condominio: Optional[Decimal] = None
    responsabilidade: ResponsabilidadeItem
    justificativa_legal: Optional[str] = None


class ItemRateioCreate(ItemRateioBase):
    ciclo_id: Optional[uuid.UUID] = None


class ItemRateioResponse(ItemRateioBase):
    id: uuid.UUID
    ciclo_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


# CicloCondominio Schemas
class CicloCondominioBase(BaseModel):
    competencia: str
    condominio_nome: str
    data_vencimento: date
    valor_total: Decimal
    valor_ordinarias: Decimal = Decimal("0.00")
    valor_extraordinarias: Decimal = Decimal("0.00")
    valor_fundos: Decimal = Decimal("0.00")
    valor_leituras: Decimal = Decimal("0.00")
    valor_ressarcimento: Decimal = Decimal("0.00")
    boleto_pdf_path: str
    comprovante_pix_path: Optional[str] = None
    status_ciclo: StatusCiclo = StatusCiclo.PENDENTE_COMPROVANTE


class CicloCondominioCreate(CicloCondominioBase):
    itens: Optional[list[ItemRateioBase]] = None


class CicloCondominioUpdate(BaseModel):
    competencia: Optional[str] = None
    condominio_nome: Optional[str] = None
    data_vencimento: Optional[date] = None
    valor_total: Optional[Decimal] = None
    valor_ordinarias: Optional[Decimal] = None
    valor_extraordinarias: Optional[Decimal] = None
    valor_fundos: Optional[Decimal] = None
    valor_leituras: Optional[Decimal] = None
    valor_ressarcimento: Optional[Decimal] = None
    boleto_pdf_path: Optional[str] = None
    comprovante_pix_path: Optional[str] = None
    status_ciclo: Optional[StatusCiclo] = None


# SubmissaoRessarcimento Schemas
class SubmissaoRessarcimentoBase(BaseModel):
    contrato_numero: str
    payload_enviado: dict[str, Any]
    status: StatusSubmissao
    protocolo_retorno: Optional[str] = None
    screenshot_path: Optional[str] = None
    tentativas: int = 1
    trace_id: str


class SubmissaoRessarcimentoCreate(SubmissaoRessarcimentoBase):
    ciclo_id: Optional[uuid.UUID] = None


class SubmissaoRessarcimentoResponse(SubmissaoRessarcimentoBase):
    id: uuid.UUID
    ciclo_id: Optional[uuid.UUID] = None
    enviado_em: datetime

    model_config = ConfigDict(from_attributes=True)


class CicloCondominioResponse(CicloCondominioBase):
    id: uuid.UUID
    criado_em: datetime
    itens: list[ItemRateioResponse] = []
    submissoes: list[SubmissaoRessarcimentoResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CicloSubmissaoRequest(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    contrato: Optional[str] = None
    observacoes: Optional[str] = None
    use_browser: bool = False


class CicloSubmissaoResponse(BaseModel):
    status: StatusSubmissao
    protocolo: Optional[str] = None
    mensagem: str
    screenshot_path: Optional[str] = None
    trace_id: str
    ciclo_id: uuid.UUID


# IncidenteOnCall Schemas
class IncidenteOnCallBase(BaseModel):
    trace_id: str
    alerta_nome: str
    diagnostico: str
    acao_executada: str
    status: StatusIncidente


class IncidenteOnCallCreate(IncidenteOnCallBase):
    pass


class IncidenteOnCallResponse(IncidenteOnCallBase):
    id: uuid.UUID
    criado_em: datetime

    model_config = ConfigDict(from_attributes=True)


# Parsed Condo Bill Schemas
class ParsedItemRateio(BaseModel):
    descricao: str
    valor_unidade: Decimal
    valor_total_condominio: Optional[Decimal] = None
    categoria: CategoriaItem


class ParsedCondoBill(BaseModel):
    condominio_nome: str
    competencia: str
    data_vencimento: date
    valor_total: Decimal
    valor_ordinarias: Decimal
    valor_extraordinarias: Decimal
    valor_fundos: Decimal
    valor_leituras: Decimal
    linha_digitavel: Optional[str] = None
    itens: list[ParsedItemRateio] = []


# Audit Schemas
class ItemAuditado(BaseModel):
    descricao: str
    valor: Decimal
    categoria: CategoriaItem
    responsabilidade: ResponsabilidadeItem
    justificativa_legal: Optional[str] = None

    @property
    def valor_unidade(self) -> Decimal:
        return self.valor


class AuditReport(BaseModel):
    competencia: str
    condominio_nome: str
    data_vencimento: date
    valor_total_boleto: Decimal
    valor_locatario: Decimal
    valor_locador: Decimal
    total_reimbursement: Decimal
    itens_auditados: list[ItemAuditado] = []
    formatted_observations: str
    revisao_necessaria: bool = False
