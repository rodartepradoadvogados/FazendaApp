// Holerite — impressão do documento de uma pessoa numa competência.
//
// As REGRAS do documento (o que entra no corpo, qual selo leva, se pode ser
// emitido) moram em lib/holeriteRegras.ts, sem nenhum import de runtime, para
// poderem ser testadas fora do navegador; aqui fica só o que precisa formatar
// dinheiro e gerar arquivo — e o re-export, para as telas importarem de um
// lugar só.
//
// Por que este módulo existe: a tela de Ações renderizava a discriminação de
// um jeito (lista "rótulo → valor") e o PDF montava outra coisa a partir da
// mesma lista ("Item | Valor", em duas colunas) — duas construções para o
// mesmo documento, que podiam divergir sem ninguém notar. E a tela de Contas
// não montava nada: era a mesma tabela sem o clique. Agora as três saídas leem
// daqui.
//
// As quatro colunas são as do recibo de papel da fazenda — Descrição ·
// Referência · Vencimentos · Descontos —, sem a primeira coluna do papel
// (`Cod.`, rubrica do sistema da contabilidade, que não existe em tabela
// nenhuma deste projeto: numerar as linhas seria inventar um código que
// ninguém consegue conferir contra nada).
import { formatBRL } from "./api";
import { exportarFichaPDF, exportarMultiExcel, type SecaoFicha } from "./export";
import { linhasDoCorpo, podeEmitir, type Holerite } from "./holeriteRegras";

export * from "./holeriteRegras";

/**
 * Motivo pelo qual a impressão está bloqueada, ou null quando pode imprimir —
 * a frase pronta para a tela, a partir da regra de `podeEmitir`.
 */
export function bloqueioDeImpressao(h: Holerite): string | null {
  const veredito = podeEmitir(h);
  if (veredito.ok) return null;
  return (
    `Os descontos excedem os vencimentos em ${formatBRL(veredito.excedente)} — ` +
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
