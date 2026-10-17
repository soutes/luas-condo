export type Responsabilidade = "LOCATARIO" | "LOCADOR";

export type Categoria = "ORDINARIA" | "EXTRAORDINARIA" | "FUNDOS" | "LEITURA";

export type StatusCiclo =
  | "PENDENTE_COMPROVANTE"
  | "PRONTO_PARA_ENVIO"
  | "ENVIADO"
  | "PROCESSADO_ALUGUEL"
  | "CONCILIADO_SEM_PENDENCIA";

export type StatusSubmissao = "SUCESSO" | "ERRO" | "RETRY";

export interface RateioItem {
  id?: string;
  ciclo_id?: string;
  categoria: Categoria;
  descricao: string;
  valor_unidade: number | string;
  responsabilidade: Responsabilidade;
  justificativa_legal?: string | null;
}

export interface Submissao {
  id: string;
  ciclo_id?: string;
  contrato_numero: string;
  status: StatusSubmissao;
  protocolo_retorno?: string | null;
  screenshot_path?: string | null;
  trace_id: string;
  enviado_em: string;
}

export interface Ciclo {
  id: string;
  competencia: string;
  condominio_nome: string;
  data_vencimento: string;
  valor_total: number | string;
  valor_ordinarias: number | string;
  valor_extraordinarias: number | string;
  valor_fundos: number | string;
  valor_leituras: number | string;
  valor_ressarcimento: number | string;
  valor_desconto_aluguel?: number | string;
  valor_saldo_residual?: number | string;
  boleto_pdf_path?: string | null;
  comprovante_pix_path?: string | null;
  boleto_aluguel_path?: string | null;
  itens_abatidos_aluguel?: Array<{ descricao: string; valor: number }> | null;
  ultima_verificacao?: string | null;
  detalhes_verificacao?: string | null;
  status_ciclo: StatusCiclo;
  criado_em: string;
  itens: RateioItem[];
  submissoes?: Submissao[];
}

export interface VerificacaoChecklist {
  competencia: string;
  boleto_condominio_encontrado: boolean;
  comprovante_pix_encontrado: boolean;
  boleto_aluguel_encontrado: boolean;
  despesas_locador: number | string;
  descontos_aluguel: number | string;
  saldo_residual_devido: number | string;
  status_ciclo: StatusCiclo;
  status_envio: string;
  protocolo_retorno?: string | null;
  ultima_verificacao?: string | null;
  detalhes?: string | null;
  erros_alertas: string[];
}
