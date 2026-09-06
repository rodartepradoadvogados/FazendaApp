// Regras puras do holerite — sem nenhum import de runtime (só tipos, que o
// compilador apaga). É o que permite testá-las com o runner nativo do Node,
// igual a lib/pessoaPapel.ts: `lib/api.ts` e `lib/export.ts` arrastam Intl,
// fetch e Capacitor, e não sobem fora do navegador.
//
// Tudo o que decide COMO o documento se comporta mora aqui — quais linhas
// entram no corpo, qual selo o documento leva, se ele pode ser emitido — e
// `lib/holerite.ts` fica só com o que precisa formatar dinheiro e gerar
// arquivo. Ver lib/holeriteRegras.test.ts.
import type {
  BasesHolerite, LinhaFolhaUnificada, LinhaHolerite, OrigemRetencao, OrigemRubrica, OrigemVale,
  TotaisHolerite,
} from "./api";

const MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

/** "2026-07" → "Julho / 2026" (título do documento, não abreviação de tabela). */
export function competenciaExtenso(competencia: string): string {
  const [ano, mes] = (competencia || "").split("-");
  const i = parseInt(mes, 10) - 1;
  // `Number.isNaN` explícito: uma string sem "-" devolve mes=undefined e i=NaN,
  // que passa por `i < 0 || i > 11` (toda comparação com NaN é falsa) e
  // quebraria ao indexar o mês.
  if (!ano || Number.isNaN(i) || i < 0 || i > 11) return competencia || "—";
  const nome = MESES[i];
  return `${nome[0].toUpperCase()}${nome.slice(1)} / ${ano}`;
}

export function dataBR(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : iso;
}

export const FORMA_PAGAMENTO_VALE: Record<string, string> = {
  dinheiro: "Dinheiro",
  pix: "Pix",
  transferencia: "Transferência",
  desconto_integral_folha: "Desconto integral em folha",
};

export type Holerite = {
  chave: string;
  pessoaId: number;
  /** Id da `FolhaPagamento` — só o holerite de funcionário tem rubricas
   *  editáveis; férias/13º são recibos de composição própria, e por isso o
   *  campo é null neles (a tela esconde os botões em vez de abrir um
   *  formulário que o servidor recusaria). */
  folhaId: number | null;
  pessoaNome: string;
  competencia: string;
  competenciaLabel: string;
  linhas: LinhaHolerite[];
  totais: TotaisHolerite;
  bases: BasesHolerite | null;
  status: "pendente" | "pago";
  dataVencimento: string | null;
  dataPagamento: string | null;
  numeroLancamento: string | null;
  observacao: string | null;
  /** Espécie do documento: só funcionário tem composição bruto→retenções→
   *  vale→líquido; férias/13º são recibos com referência própria. */
  especie: "holerite" | "recibo";
  vencido: boolean;
};

/** Só as linhas que aparecem nas colunas — o líquido é rodapé, não linha. */
export function linhasDoCorpo(linhas: LinhaHolerite[]): LinhaHolerite[] {
  return linhas.filter((l) => l.tipo !== "liquido");
}

export function ehOrigemVale(origem: LinhaHolerite["origem"]): origem is OrigemVale {
  return !!origem && origem.tipo === "vale";
}

export function ehOrigemRetencao(origem: LinhaHolerite["origem"]): origem is OrigemRetencao {
  return !!origem && origem.tipo === "retencao";
}

export function ehOrigemRubrica(origem: LinhaHolerite["origem"]): origem is OrigemRubrica {
  return !!origem && origem.tipo === "rubrica";
}

/**
 * Filtro de SITUAÇÃO DO PAGAMENTO — "pagos", "a pagar" ou "todos".
 *
 * É a categoria que o dono pediu por nome, e ela substitui o antigo select
 * "Status" (que tinha exatamente este predicado sob outro rótulo). Dois
 * controles com a mesma regra podiam se contradizer — escolher "Pago" num e
 * "A vencer" no outro esvaziava a tela sem explicar por quê.
 *
 * "A pagar" é TUDO o que ainda não foi pago, vencido ou não: a pergunta do
 * dono aqui é de caixa ("o que ainda devo?"), e o atraso continua sendo dito
 * pelo selo VENCIDO em cada linha e pelo destaque da tabela — informação que
 * se soma a esta, em vez de fatiá-la em duas listas.
 */
export type SituacaoPagamento = "todos" | "pagos" | "a_pagar";

export function filtrarPorSituacao<T extends { status: "pendente" | "pago" }>(
  linhas: T[], situacao: SituacaoPagamento,
): T[] {
  if (situacao === "pagos") return linhas.filter((l) => l.status === "pago");
  if (situacao === "a_pagar") return linhas.filter((l) => l.status !== "pago");
  return linhas;
}

/**
 * Converte uma linha do ledger unificado no documento. Devolve null para os
 * tipos que não têm discriminação (empreita, contrato, diária): eles têm
 * recibo de valor único, não holerite — forçá-los no formato de colunas fixas
 * produziria um documento vazio em quatro dos cinco tipos.
 */
export function holeriteDaLinha(l: LinhaFolhaUnificada): Holerite | null {
  if (!l.detalhe || !l.detalhe.length || !l.totais) return null;
  const competencia = l.competencia || (l.data_vencimento || "").slice(0, 7);
  return {
    chave: `${l.tipo}-${l.origem_subtipo}-${l.origem_id}`,
    pessoaId: l.pessoa_id,
    folhaId: l.tipo === "funcionario" && l.origem_subtipo === "folha" ? l.origem_id : null,
    pessoaNome: l.pessoa_nome,
    competencia,
    competenciaLabel: l.tipo === "funcionario" ? competenciaExtenso(competencia) : l.descricao,
    linhas: l.detalhe,
    totais: l.totais,
    bases: l.bases || null,
    status: l.status,
    dataVencimento: l.data_vencimento,
    dataPagamento: l.data_pagamento,
    numeroLancamento: l.numero_lancamento_gerado ?? null,
    observacao: l.observacao ?? null,
    especie: l.tipo === "funcionario" ? "holerite" : "recibo",
    vencido: l.vencido,
  };
}

/** Selo do documento, no canto do cabeçalho. "Não emitido" é deliberado: um
 *  recibo cujos descontos passam os vencimentos não é um recibo. */
export function seloDocumento(h: Holerite): { texto: string; cor: string; fundo: string } {
  if (h.totais.liquido_negativo) {
    return { texto: "NÃO EMITIDO", cor: "var(--red)", fundo: "color-mix(in srgb, var(--red) 12%, transparent)" };
  }
  if (h.status === "pago") {
    return { texto: "PAGO", cor: "var(--green-light)", fundo: "color-mix(in srgb, var(--green) 16%, transparent)" };
  }
  if (h.vencido) {
    return { texto: "VENCIDO", cor: "var(--red)", fundo: "color-mix(in srgb, var(--red) 12%, transparent)" };
  }
  return { texto: "PRÉVIA", cor: "var(--text-muted)", fundo: "var(--surface-2)" };
}

/**
 * O documento pode ser emitido? A regra é do documento, não da tela: enquanto
 * os descontos passarem os vencimentos, o que existe não é um líquido e sim um
 * excedente — e um papel dizendo que o funcionário deve dinheiro à fazenda não
 * é comprovante de pagamento. Devolve o excedente para quem chama formatar.
 */
export function podeEmitir(h: Holerite): { ok: true } | { ok: false; excedente: number } {
  return h.totais.liquido_negativo ? { ok: false, excedente: h.totais.excedente } : { ok: true };
}
