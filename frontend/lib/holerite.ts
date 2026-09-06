// Holerite — o documento de uma pessoa numa competência, montado UMA VEZ e
// consumido pelas duas telas de folha e pela impressão.
//
// Por que existe: até aqui a tela de Ações renderizava a discriminação de um
// jeito (lista "rótulo → valor") e o PDF montava outra coisa a partir da mesma
// lista ("Item | Valor", em duas colunas) — duas construções para o mesmo
// documento, que podiam divergir sem ninguém notar. E a tela de Contas não
// montava nada: era a mesma tabela sem o clique.
//
// Agora as três saídas leem daqui. As quatro colunas são as do recibo de papel
// da fazenda — Descrição · Referência · Vencimentos · Descontos —, sem a
// primeira coluna do papel (`Cod.`, rubrica do sistema da contabilidade, que
// não existe em tabela nenhuma deste projeto: numerar as linhas seria inventar
// um código que ninguém consegue conferir contra nada).
import {
  formatBRL, type BasesHolerite, type LinhaFolhaUnificada, type LinhaHolerite,
  type OrigemRetencao, type OrigemVale, type TotaisHolerite,
} from "./api";
import { exportarFichaPDF, exportarMultiExcel, type SecaoFicha } from "./export";

const MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

/** "2026-07" → "Julho / 2026" (título do documento, não abreviação de tabela). */
export function competenciaExtenso(competencia: string): string {
  const [ano, mes] = (competencia || "").split("-");
  const i = parseInt(mes, 10) - 1;
  if (i < 0 || i > 11) return competencia || "—";
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
 * Motivo pelo qual a impressão está bloqueada, ou null quando pode imprimir.
 * A regra é do documento, não da tela: enquanto os descontos passarem os
 * vencimentos, o que existe é um excedente, e um papel que diz que o
 * funcionário deve dinheiro à fazenda não é um comprovante de pagamento.
 */
export function bloqueioDeImpressao(h: Holerite): string | null {
  if (!h.totais.liquido_negativo) return null;
  return (
    `Os descontos excedem os vencimentos em ${formatBRL(h.totais.excedente)} — ` +
    "ajuste as parcelas de vale antes de emitir o recibo."
  );
}

const COLUNAS_HOLERITE = [
  { header: "Descrição", key: "descricao" },
  { header: "Referência", key: "referencia" },
  { header: "Vencimentos", key: "vencimentos" },
  { header: "Descontos", key: "descontos" },
];

/**
 * Uma seção de PDF/Excel por documento — as MESMAS quatro colunas da tela,
 * mais as linhas de fechamento (totais, líquido e o rodapé de bases quando
 * houver). Substitui as duas colunas "Item | Valor" de antes, em que a
 * referência simplesmente não tinha onde entrar e o dono recebia sete linhas
 * escritas "Vale" também no papel.
 */
export function secaoDoHolerite(h: Holerite): SecaoFicha {
  const linhas: Record<string, unknown>[] = linhasDoCorpo(h.linhas).map((l) => ({
    descricao: l.descricao,
    referencia: l.referencia,
    vencimentos: l.provento ? formatBRL(l.provento) : "",
    descontos: l.desconto ? formatBRL(l.desconto) : "",
  }));
  linhas.push({
    descricao: "Totais",
    referencia: "",
    vencimentos: formatBRL(h.totais.total_proventos),
    descontos: formatBRL(h.totais.total_descontos),
  });
  linhas.push({
    descricao: h.totais.liquido_negativo ? "Descontos excedem os vencimentos em" : "Líquido",
    referencia: "",
    vencimentos: "",
    descontos: formatBRL(h.totais.liquido_negativo ? h.totais.excedente : h.totais.liquido),
  });
  // Rodapé honesto: só o que o banco sustenta. Nada de "Base Calc. IRRF"
  // (inderivável aqui) nem de campo vazio — num documento de aparência
  // oficial, célula em branco lê como zero.
  if (h.bases) {
    if (h.bases.base_inss != null) {
      linhas.push({ descricao: "Base do INSS informada", referencia: "", vencimentos: formatBRL(h.bases.base_inss), descontos: "" });
    }
    if (h.bases.fgts_projetado != null) {
      linhas.push({
        descricao: "FGTS projetado (encargo do empregador)",
        referencia: h.bases.percentual_fgts ? `${h.bases.percentual_fgts}% sobre ${formatBRL(h.bases.salario_base)}` : "",
        vencimentos: formatBRL(h.bases.fgts_projetado),
        descontos: "",
      });
    }
  }
  return { titulo: `${h.pessoaNome} — ${h.competenciaLabel}`, colunas: COLUNAS_HOLERITE, linhas };
}

const NOTA_DE_ESCOPO =
  "Recibo interno de controle da fazenda — não substitui o holerite emitido pela contabilidade " +
  "e não apura bases fiscais (INSS, FGTS, IRRF).";

function nomeArquivo(base: string): string {
  return base.replace(/[^\w-]+/g, "_").replace(/_+/g, "_").toLowerCase();
}

/**
 * Impressão INDIVIDUAL — o holerite de uma pessoa numa competência. Reusa
 * `exportarFichaPDF`/`exportarMultiExcel`, a mesma infraestrutura de todos os
 * documentos do sistema (cabeçalho da fazenda, marca, autor e data), em vez de
 * um caminho de impressão próprio.
 */
export async function imprimirHolerite(h: Holerite, formato: "pdf" | "excel"): Promise<void> {
  const titulo = h.especie === "holerite" ? "Recibo de pagamento mensal" : "Recibo de pagamento";
  const subtitulo = `${h.pessoaNome} — ${h.competenciaLabel} · ${NOTA_DE_ESCOPO}`;
  const base = nomeArquivo(`holerite_${h.pessoaNome}_${h.competencia || h.chave}`);
  if (formato === "pdf") await exportarFichaPDF(titulo, subtitulo, [secaoDoHolerite(h)], base);
  else await exportarMultiExcel(titulo, [secaoDoHolerite(h)], base);
}

/** Impressão em LOTE — uma seção por pessoa, mesma folha de estilo. */
export async function imprimirHolerites(
  lista: Holerite[], subtitulo: string, base: string, formato: "pdf" | "excel",
): Promise<void> {
  const secoes = lista.map(secaoDoHolerite);
  const titulo = "Recibos de pagamento";
  const legenda = `${subtitulo} · ${NOTA_DE_ESCOPO}`;
  if (formato === "pdf") await exportarFichaPDF(titulo, legenda, secoes, nomeArquivo(base));
  else await exportarMultiExcel(titulo, secoes, nomeArquivo(base));
}
