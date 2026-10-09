// Cálculos PUROS da tela Consultas do Financeiro (só o realizado).
//
// Sem import de runtime de propósito: só tipos (apagados na execução), para o
// arquivo rodar direto no runner nativo do Node (`node --experimental-strip-types
// --test`, ver consultasCalculo.test.ts) sem depender do alias "@/". A busca
// por texto (casaBusca de lib/busca.ts) entra por parâmetro.
//
// REGRA DE DOMÍNIO: realizado = `valor_pago`, nunca `valor`. `valor` é o
// valor original da nota/parcela; numa baixa parcial com reparcelamento da
// diferença, `valor_pago` < `valor` e a diferença virou outra conta (ainda em
// aberto). `valor` só entra como reserva quando `valor_pago` vier null.
import type { Lanc } from "@/lib/financeiroTipos";

export type Movimento = "pagamento" | "recebimento" | "ambos";
export type CampoPeriodo = "emissao" | "vencimento" | "pagamento" | "competencia";
export type ModoConsulta = "lista" | "livro";

export type FiltrosConsulta = {
  movimento: Movimento;
  periodoPor: CampoPeriodo;
  de: string;
  ate: string;
  centro: string;
  banco: string;
  documento: string;
  produto: string;
  fornecedor: string;
  conta: string;     // código da conta gerencial (casa ela e a subárvore)
  contaNome: string; // só para exibir no seletor
};

export type CasaTexto = (alvo: string | null | undefined, termo: string | null | undefined) => boolean;

/** Arredonda em centavos (evita 0,1 + 0,2). */
export const r2 = (v: number) => Math.round(v * 100) / 100;

const pad = (n: number) => String(n).padStart(2, "0");

/** Primeiro e último dia do mês de `hoje` (AAAA-MM-DD, sem passar por UTC). */
export function periodoMesCorrente(hoje: string): { de: string; ate: string } {
  const [a, m] = hoje.split("-").map(Number);
  const ultimo = new Date(a, m, 0).getDate(); // dia 0 do mês seguinte = último dia deste
  return { de: `${a}-${pad(m)}-01`, ate: `${a}-${pad(m)}-${pad(ultimo)}` };
}

/** Padrão da tela: ambos os movimentos, período por pagamento no mês corrente. */
export function filtrosPadrao(hoje: string): FiltrosConsulta {
  return {
    movimento: "ambos", periodoPor: "pagamento", ...periodoMesCorrente(hoje),
    centro: "", banco: "", documento: "", produto: "", fornecedor: "", conta: "", contaNome: "",
  };
}

/**
 * Filtro vindo de fora (link da Agenda, do Resumo, de uma busca global):
 * com nº de documento, abre o período (a nota pode ter sido paga em outro
 * mês); com conta bancária, já filtra por ela.
 */
export type FiltroInicial = {
  documento?: string; banco?: string;
  /** Drill de um relatório (Fase B): o mesmo período, regime, centro e conta da linha clicada. */
  de?: string; ate?: string; periodoPor?: CampoPeriodo; conta?: string; contaNome?: string; centro?: string;
};
export function aplicarFiltroInicial(padrao: FiltrosConsulta, ini?: FiltroInicial | null): FiltrosConsulta {
  let f = { ...padrao };
  if (ini?.documento) f = { ...f, de: "", ate: "", documento: ini.documento };
  if (ini?.banco) f = { ...f, banco: ini.banco };
  if (ini?.de || ini?.ate) f = { ...f, de: ini.de || "", ate: ini.ate || "" };
  if (ini?.periodoPor) f = { ...f, periodoPor: ini.periodoPor };
  if (ini?.conta) f = { ...f, conta: ini.conta, contaNome: ini.contaNome || ini.conta };
  if (ini?.centro) f = { ...f, centro: ini.centro };
  return f;
}

/** Valor realizado de um lançamento: o que de fato saiu ou entrou. */
export function realizado(l: Lanc): number {
  return l.valor_pago ?? l.valor;
}

const normProduto = (s: string | null | undefined) => (s || "").trim().toLocaleLowerCase("pt-BR");

/** O item é do produto/serviço filtrado (mesmo nome, sem diferença de caixa/espaços nas pontas). */
export function itemCasaProduto(produtoItem: string | null | undefined, filtro: string): boolean {
  return !!filtro && normProduto(produtoItem) === normProduto(filtro);
}

/**
 * Parte realizada que cabe aos ITENS do produto filtrado.
 *
 * Os itens são da NOTA inteira (o backend agrupa por numero_lancamento, então
 * cada parcela traz todos os itens da nota); por isso a soma dos itens que
 * casam vira uma FRAÇÃO da nota (itens casados ÷ todos os itens) aplicada ao
 * realizado desta linha. Nota de um item só = realizado inteiro; nota paga
 * cheia = exatamente a soma de `itens[].valor_total` que casam; parcela ou
 * baixa parcial = a mesma proporção do que foi pago nela.
 */
export function valorDoItem(l: Lanc, produto: string): number {
  const itens = l.itens || [];
  const casados = itens.filter((it) => itemCasaProduto(it.produto, produto));
  if (!casados.length) return 0;
  const somaCasados = casados.reduce((s, it) => s + (it.valor_total || 0), 0);
  const somaTodos = itens.reduce((s, it) => s + (it.valor_total || 0), 0);
  if (somaTodos <= 0) return casados.length === itens.length ? r2(realizado(l)) : 0;
  return r2(realizado(l) * (somaCasados / somaTodos));
}

/** Data usada pelo filtro de período, conforme "Período por". */
export function dataDoPeriodo(l: Lanc, campo: CampoPeriodo): string | null {
  if (campo === "emissao") return l.data_emissao;
  if (campo === "vencimento") return l.data_vencimento;
  // Competência (o mês do gasto): é por ela que a DRE de competência soma.
  if (campo === "competencia") return l.data_competencia;
  return l.data_pagamento;
}

/** Conta selecionada casa com o próprio código e com toda a subárvore ("3.01" casa "3.01.02"). */
export function casaContaGerencial(l: Lanc, sel: string): boolean {
  if (!sel) return true;
  const c = l.conta_completa || l.codigo_conta || "";
  return c === sel || c.startsWith(sel + ".");
}

const tipoDoMovimento = (m: Movimento) => (m === "pagamento" ? "despesa" : m === "recebimento" ? "receita" : null);

export type LinhaConsulta = {
  l: Lanc;
  /** Valor que a tela soma e mostra: realizado, ou só a parte do item quando há filtro de produto. */
  valor: number;
  /** true quando `valor` é só a parte do(s) item(ns) filtrado(s), não a nota inteira. */
  soItem: boolean;
};

/** Só o realizado (com data de pagamento) que passa em todos os filtros. */
export function filtrarRealizados(regs: Lanc[], f: FiltrosConsulta, casaTexto: CasaTexto): LinhaConsulta[] {
  const tipo = tipoDoMovimento(f.movimento);
  const out: LinhaConsulta[] = [];
  for (const l of regs) {
    if (!l.data_pagamento) continue; // nada em aberto, nunca
    if (tipo && l.tipo !== tipo) continue;
    if (f.de || f.ate) {
      const d = dataDoPeriodo(l, f.periodoPor);
      if (!d) continue;
      if (f.de && d < f.de) continue;
      if (f.ate && d > f.ate) continue;
    }
    if (f.centro && l.centro_custo !== f.centro) continue;
    if (f.banco && (l.conta_bancaria || "") !== f.banco) continue;
    if (f.documento && !casaTexto(`${l.numero_documento || ""} ${l.numero_lancamento || ""} ${l.numero_os_orcamento || ""}`, f.documento)) continue;
    if (f.produto && !(l.itens || []).some((it) => itemCasaProduto(it.produto, f.produto))) continue;
    if (f.fornecedor && l.fornecedor !== f.fornecedor) continue;
    if (!casaContaGerencial(l, f.conta)) continue;
    out.push(f.produto ? { l, valor: valorDoItem(l, f.produto), soItem: true } : { l, valor: r2(realizado(l)), soItem: false });
  }
  return out;
}

export type ResumoConsulta = {
  totalPago: number;
  totalRecebido: number;
  resultado: number;
  quantidade: number;
  qtdPagamentos: number;
  qtdRecebimentos: number;
  descontoAcrescimo: number; // soma de desconto_acrescimo (positivo = acréscimo, negativo = desconto)
  acrescimos: number;
  descontos: number; // em módulo
  topBase: "despesa" | "receita";
  topContas: { codigo: string; valor: number }[];
};

/** Cards: totais por tipo, resultado, desconto/acréscimo e as 3 maiores contas gerenciais. */
export function resumir(linhas: LinhaConsulta[], movimento: Movimento): ResumoConsulta {
  let totalPago = 0, totalRecebido = 0, qtdPagamentos = 0, qtdRecebimentos = 0, acrescimos = 0, descontos = 0;
  for (const { l, valor } of linhas) {
    if (l.tipo === "receita") { totalRecebido += valor; qtdRecebimentos++; }
    else { totalPago += valor; qtdPagamentos++; }
    const da = l.desconto_acrescimo ?? 0;
    if (da > 0) acrescimos += da; else if (da < 0) descontos += -da;
  }
  // Top contas: de receitas só quando o filtro é Recebimento; senão, de despesas.
  const topBase = movimento === "recebimento" ? "receita" : "despesa";
  const porConta = new Map<string, number>();
  for (const { l, valor } of linhas) {
    if (l.tipo !== topBase) continue;
    const c = l.conta_completa || l.codigo_conta || "";
    porConta.set(c, (porConta.get(c) || 0) + valor);
  }
  const topContas = Array.from(porConta, ([codigo, valor]) => ({ codigo, valor: r2(valor) }))
    .sort((a, b) => b.valor - a.valor || a.codigo.localeCompare(b.codigo))
    .slice(0, 3);
  return {
    totalPago: r2(totalPago), totalRecebido: r2(totalRecebido), resultado: r2(totalRecebido - totalPago),
    quantidade: linhas.length, qtdPagamentos, qtdRecebimentos,
    descontoAcrescimo: r2(acrescimos - descontos), acrescimos: r2(acrescimos), descontos: r2(descontos),
    topBase, topContas,
  };
}

/** Quantos filtros estão fora do padrão (movimento e período contam 1 cada). */
export function contarFiltrosAtivos(f: FiltrosConsulta, padrao: FiltrosConsulta): number {
  let n = (["centro", "banco", "documento", "produto", "fornecedor", "conta"] as const).filter((k) => !!f[k]).length;
  if (f.movimento !== padrao.movimento) n++;
  if (f.periodoPor !== padrao.periodoPor || f.de !== padrao.de || f.ate !== padrao.ate) n++;
  return n;
}

export type LinhaLivro = { l: Lanc; entrada: number; saida: number; saldo: number | null };
export type LivroCaixa = {
  /** Conta do livro; "" = sem conta escolhida (lista sem saldo). */
  banco: string;
  /** Saldo do movimento realizado na conta antes de `de` — null sem conta escolhida. */
  saldoAnterior: number | null;
  saldoFinal: number | null;
  totalEntradas: number;
  totalSaidas: number;
  linhas: LinhaLivro[];
};

const ordemLivro = (a: Lanc, b: Lanc) =>
  (a.data_pagamento || "").localeCompare(b.data_pagamento || "") ||
  (a.tipo === b.tipo ? 0 : a.tipo === "receita" ? -1 : 1) ||
  a.id - b.id;

/**
 * Livro caixa: cronológico por data de pagamento, entrada/saída.
 *
 * SALDO ACUMULADO SÓ COM CONTA BANCÁRIA ESCOLHIDA: somar o saldo de contas
 * diferentes não fecha com extrato nenhum. Com conta, o livro usa só a conta
 * e o De/Até pela data de pagamento (ignora os demais filtros, senão o saldo
 * fica "furado") e parte do saldo do movimento realizado antes do período.
 * Sem conta, mostra as linhas já filtradas da lista, sem saldo.
 *
 * Regras v2 (Fase A, PR 6): com `abertura` (o saldo do extrato conferido numa
 * data, cadastrado na conta corrente), o livro parte dele e só soma o que foi
 * pago DEPOIS dessa data — o mesmo saldo do servidor. Nota que só classifica a
 * DRE (`gerado_por = "backfill_cartao"`: o dinheiro já está na nota genérica
 * da fatura) nunca entra no livro.
 */
export function montarLivro(
  regs: Lanc[], filtradas: LinhaConsulta[], f: FiltrosConsulta, abertura?: { saldo: number; data: string } | null,
): LivroCaixa {
  if (!f.banco) {
    const linhas = [...filtradas].sort((a, b) => ordemLivro(a.l, b.l)).map(({ l, valor }) => ({
      l, entrada: l.tipo === "receita" ? valor : 0, saida: l.tipo === "receita" ? 0 : valor, saldo: null,
    }));
    return {
      banco: "", saldoAnterior: null, saldoFinal: null, linhas,
      totalEntradas: r2(linhas.reduce((s, x) => s + x.entrada, 0)), totalSaidas: r2(linhas.reduce((s, x) => s + x.saida, 0)),
    };
  }
  const daConta = regs.filter((l) =>
    l.data_pagamento && (l.conta_bancaria || "") === f.banco && l.gerado_por !== "backfill_cartao"
    && !(abertura && l.data_pagamento <= abertura.data)).sort(ordemLivro);
  const liquido = (l: Lanc) => (l.tipo === "receita" ? realizado(l) : -realizado(l));
  let saldo = abertura ? abertura.saldo : 0;
  for (const l of daConta) if (f.de && l.data_pagamento! < f.de) saldo += liquido(l);
  const saldoAnterior = r2(saldo);
  let entradas = 0, saidas = 0;
  const linhas: LinhaLivro[] = [];
  for (const l of daConta) {
    const d = l.data_pagamento!;
    if ((f.de && d < f.de) || (f.ate && d > f.ate)) continue;
    const v = r2(realizado(l));
    saldo += liquido(l);
    if (l.tipo === "receita") entradas += v; else saidas += v;
    linhas.push({ l, entrada: l.tipo === "receita" ? v : 0, saida: l.tipo === "receita" ? 0 : v, saldo: r2(saldo) });
  }
  return { banco: f.banco, saldoAnterior, saldoFinal: r2(saldo), totalEntradas: r2(entradas), totalSaidas: r2(saidas), linhas };
}

export type ChaveOrdem = "data" | "numero" | "descricao" | "fornecedor" | "banco" | "valor";
export type Ordem = { chave: ChaveOrdem; dir: "asc" | "desc" };

/** Ordena as linhas da lista (cópia). Empate sempre cai na data de pagamento e no id. */
export function ordenarLinhas(linhas: LinhaConsulta[], o: Ordem): LinhaConsulta[] {
  const txt = (s: string | null | undefined) => (s || "").toLocaleLowerCase("pt-BR");
  const get: Record<ChaveOrdem, (x: LinhaConsulta) => string | number> = {
    data: (x) => x.l.data_pagamento || "",
    numero: (x) => txt(x.l.numero_lancamento),
    descricao: (x) => txt(x.l.descricao),
    fornecedor: (x) => txt(x.l.fornecedor),
    banco: (x) => txt(x.l.conta_bancaria),
    valor: (x) => x.valor,
  };
  const g = get[o.chave];
  const s = o.dir === "asc" ? 1 : -1;
  return [...linhas].sort((a, b) => {
    const va = g(a), vb = g(b);
    const c = typeof va === "number" && typeof vb === "number"
      ? va - vb
      : String(va).localeCompare(String(vb), "pt-BR", { numeric: true, sensitivity: "base" });
    return c * s || (a.l.data_pagamento || "").localeCompare(b.l.data_pagamento || "") * s || (a.l.id - b.l.id) * s;
  });
}
