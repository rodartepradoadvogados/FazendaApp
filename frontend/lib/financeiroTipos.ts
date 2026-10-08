/** Lançamento financeiro como volta de GET /financeiro/lancamentos (compartilhado entre as telas do Financeiro). */
export type Lanc = {
  id: number; numero_lancamento: string | null;
  tipo: string; valor: number; valor_pago: number | null; desconto_acrescimo: number | null;
  centro_custo: string; classificacao?: string | null; codigo_conta: string; conta_completa: string;
  descricao: string; fornecedor: string; responsavel: string | null;
  tipo_documento: string | null; numero_documento: string | null; numero_os_orcamento: string | null; numero_documento_pagamento: string | null;
  numero_boleto?: string | null;
  // Tem comprovante/anexo em arquivo — inclusive o comprovante único de um
  // pagamento em lote, que é o mesmo arquivo para todas as notas da remessa.
  tem_comprovante?: boolean;
  // Conta nascida de um agendamento preventivo (Protocolos): link de volta ao agendamento.
  origem_preventivo?: { cronograma_id: number; protocolo: string; subtipo: "honorario" | "produto" | null; data_evento: string } | null;
  conta_bancaria: string | null; forma_pagamento: string | null; data_vencimento_cartao: string | null; entregue: boolean | null;
  parcela_num: number | null; parcela_total: number | null;
  data_competencia: string | null; data_pagamento: string | null; data_vencimento: string | null; data_emissao: string | null;
  mes_competencia: string | null; mes_caixa: string | null;
  itens?: { id: number; produto: string; tipo_item?: string | null; valor_total: number; descricao?: string | null;
            eh_vale: boolean; vale_tipo: "funcionario" | "avulso" | null; vale_id: number | null;
            vale_pessoa_id: number | null; vale_pessoa_nome: string | null;
            // Natureza econômica só deste item (null = a da nota). Ver lib/naturezaFin.ts.
            natureza_fin?: string | null }[];
  usuario_nome?: string | null;
  patrimonio_id?: number | null;
  fatura_id?: number | null;
  // Natureza econômica (Fase A, lib/naturezaFin.ts): `natureza_fin` é a
  // informada na nota (null = automática); `natureza_resolvida` é a que os
  // relatórios usam com as regras novas ligadas (pode vir "MISTA").
  natureza_fin?: string | null;
  natureza_resolvida?: string | null;
};
