export type Responsabilidade = "LOCATARIO" | "LOCADOR";

export type Categoria = "ORDINARIA" | "EXTRAORDINARIA" | "FUNDOS" | "LEITURA";

export type StatusCiclo =
  | "PENDENTE_COMPROVANTE"
  | "PRONTO_PARA_ENVIO"
  | "ENVIADO"
  | "PROCESSADO_ALUGUEL";

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
  boleto_pdf_path: string;
  comprovante_pix_path?: string | null;
  status_ciclo: StatusCiclo;
  criado_em: string;
  itens: RateioItem[];
  submissoes?: Submissao[];
}
