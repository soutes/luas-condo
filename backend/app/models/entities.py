from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
import uuid

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StatusCiclo(str, Enum):
    PENDENTE_COMPROVANTE = "PENDENTE_COMPROVANTE"
    PRONTO_PARA_ENVIO = "PRONTO_PARA_ENVIO"
    ENVIADO = "ENVIADO"
    PROCESSADO_ALUGUEL = "PROCESSADO_ALUGUEL"


class CategoriaItem(str, Enum):
    ORDINARIA = "ORDINARIA"
    EXTRAORDINARIA = "EXTRAORDINARIA"
    FUNDOS = "FUNDOS"
    LEITURA = "LEITURA"


class ResponsabilidadeItem(str, Enum):
    LOCATARIO = "LOCATARIO"
    LOCADOR = "LOCADOR"


class StatusSubmissao(str, Enum):
    SUCESSO = "SUCESSO"
    ERRO = "ERRO"
    RETRY = "RETRY"


class StatusIncidente(str, Enum):
    RESOLVIDO = "RESOLVIDO"
    ESCALADO_HUMANO = "ESCALADO_HUMANO"


class CicloCondominio(Base):
    __tablename__ = "ciclos_condominio"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)
    condominio_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valor_ordinarias: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    valor_extraordinarias: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    valor_fundos: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    valor_leituras: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    valor_ressarcimento: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    boleto_pdf_path: Mapped[str] = mapped_column(String(500), nullable=False)
    comprovante_pix_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        default=None,
    )
    status_ciclo: Mapped[StatusCiclo] = mapped_column(
        SAEnum(StatusCiclo, native_enum=False),
        nullable=False,
        default=StatusCiclo.PENDENTE_COMPROVANTE,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    itens: Mapped[list["ItemRateio"]] = relationship(
        "ItemRateio",
        back_populates="ciclo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    submissoes: Mapped[list["SubmissaoRessarcimento"]] = relationship(
        "SubmissaoRessarcimento",
        back_populates="ciclo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ItemRateio(Base):
    __tablename__ = "itens_rateio"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ciclo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ciclos_condominio.id", ondelete="CASCADE"),
        nullable=False,
    )
    categoria: Mapped[CategoriaItem] = mapped_column(
        SAEnum(CategoriaItem, native_enum=False),
        nullable=False,
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    valor_unidade: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valor_total_condominio: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    responsabilidade: Mapped[ResponsabilidadeItem] = mapped_column(
        SAEnum(ResponsabilidadeItem, native_enum=False),
        nullable=False,
    )
    justificativa_legal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    ciclo: Mapped["CicloCondominio"] = relationship(
        "CicloCondominio",
        back_populates="itens",
    )


class SubmissaoRessarcimento(Base):
    __tablename__ = "submissoes_ressarcimento"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ciclo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ciclos_condominio.id", ondelete="CASCADE"),
        nullable=False,
    )
    contrato_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_enviado: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[StatusSubmissao] = mapped_column(
        SAEnum(StatusSubmissao, native_enum=False),
        nullable=False,
    )
    protocolo_retorno: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    screenshot_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    tentativas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enviado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    ciclo: Mapped["CicloCondominio"] = relationship(
        "CicloCondominio",
        back_populates="submissoes",
    )


class IncidenteOnCall(Base):
    __tablename__ = "incidentes_on_call"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    alerta_nome: Mapped[str] = mapped_column(String(100), nullable=False)
    diagnostico: Mapped[str] = mapped_column(Text, nullable=False)
    acao_executada: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[StatusIncidente] = mapped_column(
        SAEnum(StatusIncidente, native_enum=False),
        nullable=False,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
