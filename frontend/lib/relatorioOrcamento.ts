// "Orçamento" (Relatórios › Plano, Fase C): modelo de tela da resposta de
// GET /planejamento/orcamento/relatorio (comparativo do PR 8 conta a conta,
// orçado × realizado por LINHA DA DRE e em R$/L — números do servidor) e a
// planilha conta × 12 meses (montar, copiar o ano anterior, +x%, preencher a
// linha, o que mudou para salvar). Também o orçado como "comparação" da DRE.
// PURO (só import de tipo) — testes em relatorioOrcamento.test.ts.
import type { Delta, Periodo } from "@/lib/relatorioContexto";
import type { IndicadoresLitro } from "@/lib/relatorioLitro";

export type Situacao = "favoravel" | "desfavoravel" | "no_orcado" | "sem_orcamento" | "coberta_pelo_grupo" | "fora_do_resultado";
export type Grupo = "receita" | "deducao" | "despesa_operacional" | "fora_do_resultado";
export type LinhaConta = {
  codigo_conta_gerencial: string; nome_conta_gerencial: string; tipo: string; orcado: number; realizado: number;
  grupo: Grupo; coberta_por: string | null; cobre: string[]; desvio: number | null; desvio_pct: number | null;
  situacao: Situacao; linha_dre: string | null;
};
export type TotalGrupo = { rotulo: string; orcado: number; realizado: number; desvio: number | null; desvio_pct: number | null; situacao: Situacao };
export type LinhaDreOrc = {
  chave: string; rotulo: string; operador: string; eh_subtotal: boolean; realizado: number; orcado: number | null;
  origem_orcado: "orcamento" | "patrimonio" | null; realizado_l: number | null; orcado_l: number | null;
};
export type ContaCascata = { codigo: string | null; nome: string | null; valor: number };
export type LinhaCascataOrc = {
  chave: string; rotulo: string; operador: string; eh_subtotal: boolean; valor: number; contas: ContaCascata[];
  orcado: boolean; origem: "orcamento" | "patrimonio";
};
export type ComparativoAntigo = {
  linhas: { codigo_conta_gerencial: string; nome_conta_gerencial: string; tipo: string; orcado: number; realizado: number; desvio: number; desvio_pct: number | null }[];
  total_orcado: number; total_realizado: number;
};
export type RespostaOrcamento = {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; regime: string;
  tem_orcamento: boolean; meses: string[]; meses_com_orcamento: string[]; regras_v2: boolean;
  // Flag desligada:
  comparativo_antigo?: ComparativoAntigo | null; travado?: string | null;
  // Flag ligada:
  linhas?: LinhaConta[]; totais?: Record<Grupo, TotalGrupo>; linhas_dre?: LinhaDreOrc[]; cascata_orcada?: LinhaCascataOrc[];
  orcado_sem_linha?: { total: number; contas: ContaCascata[] }; orcado_fora_da_dre?: number;
  nao_classificado_dre?: { total: number; total_receita?: number; total_despesa?: number };
  litros?: number; litro_orcado?: IndicadoresLitro | null; conferencia?: { fecha: boolean; maior_diferenca: number };
};

// ── Nomes em português de dono de fazenda (os mesmos da DRE da fazenda) ──
export const NOME_LINHA: Record<string, string> = {
  RECEITA_VENDAS: "Receita de vendas", DEDUCAO_IMPOSTOS: "Funrural, Senar e descontos", RECEITA_LIQUIDA: "Receita líquida",
  CUSTO_VARIAVEL: "Custo variável", MARGEM_BRUTA: "Margem bruta", DESPESA_VARIAVEL: "Despesas variáveis",
  MARGEM_CONTRIBUICAO: "Margem de contribuição", GASTOS_PESSOAL: "Pessoal", DESPESAS_OPERACIONAIS: "Despesas operacionais",
  EBITDA: "Geração de caixa da atividade", DEPRECIACAO_AMORT_EXAUSTAO: "Desgaste dos bens", OUTRAS_REC_DESP: "Resultado financeiro e outras",
  RESULTADO_OPERACIONAL: "Resultado operacional", TRIBUTOS_IR_CSLL: "Tributos sobre o lucro", RESULTADO_LIQUIDO: "Resultado",
};

/** O orçamento é mensal: o período precisa começar no dia 1 e terminar no último dia de um mês. */
export function periodoDeMesesInteiros(p: Periodo): boolean {
  if (p.ini.slice(8) !== "01") return false;
  const [a, m] = p.fim.split("-").map(Number);
  return Number(p.fim.slice(8)) === new Date(a, m, 0).getDate();
}

// ── Avaliação do desvio (texto + sentido; nunca só cor) ──
export type Avaliacao = { texto: string; melhor: boolean | null; desvio: number | null };
/** A situação vem do servidor (PR 8); aqui só vira texto. Sem orçado não há desvio. */
export function avaliar(l: { grupo: Grupo | string; situacao: Situacao | string; desvio: number | null }): Avaliacao {
  const receita = l.grupo === "receita";
  switch (l.situacao) {
    case "favoravel": return { texto: receita ? "receita acima do plano · melhor" : "gasto abaixo do plano · melhor", melhor: true, desvio: l.desvio };
    case "desfavoravel": return { texto: receita ? "receita abaixo do plano · pior" : "gasto acima do plano · pior", melhor: false, desvio: l.desvio };
    case "no_orcado": return { texto: "no plano", melhor: null, desvio: 0 };
    case "coberta_pelo_grupo": return { texto: "no orçamento do grupo", melhor: null, desvio: null };
    case "fora_do_resultado": return { texto: "fora do resultado", melhor: null, desvio: null };
    default: return { texto: "sem orçamento", melhor: null, desvio: null };
  }
}

// ── Tabela conta a conta: por grupo, sem misturar receita com despesa ──
export type SecaoContas = { grupo: Grupo; rotulo: string; orcadas: LinhaConta[]; semOrcamento: LinhaConta[]; total: TotalGrupo };
const ordem = (x: LinhaConta, y: LinhaConta) => Math.abs(y.orcado) - Math.abs(x.orcado) || Math.abs(y.realizado) - Math.abs(x.realizado)
  || x.nome_conta_gerencial.localeCompare(y.nome_conta_gerencial, "pt-BR");

/** Seções Receitas, Deduções e Despesas (+ fora do resultado à parte). As contas cobertas
 *  pelo orçamento do grupo ficam logo abaixo do grupo; o total de cada seção é o do servidor. */
export function secoesContas(r: RespostaOrcamento | null): SecaoContas[] {
  if (!r?.linhas || !r.totais) return [];
  const grupos: Grupo[] = ["receita", "deducao", "despesa_operacional", "fora_do_resultado"];
  return grupos.map((g) => {
    const doGrupo = r.linhas!.filter((l) => l.grupo === g && !l.coberta_por);
    const filhas = (pai: LinhaConta) => r.linhas!.filter((l) => l.coberta_por === pai.codigo_conta_gerencial).sort(ordem);
    const orcadas = doGrupo.filter((l) => l.orcado !== 0).sort(ordem).flatMap((l) => [l, ...filhas(l)]);
    const semOrcamento = doGrupo.filter((l) => l.orcado === 0 && Math.abs(l.realizado) >= 0.005).sort(ordem);
    return { grupo: g, rotulo: r.totais![g].rotulo, orcadas, semOrcamento, total: r.totais![g] };
  }).filter((s) => s.orcadas.length || s.semOrcamento.length);
}

export function contasForaDoPlano(r: RespostaOrcamento | null): LinhaConta[] {
  return (r?.linhas ?? []).filter((l) => l.situacao === "sem_orcamento" && Math.abs(l.realizado) >= 0.005 && !l.coberta_por);
}

// ── Desvio por linha da DRE (barras para os dois lados) ──
export type DesvioLinha = {
  chave: string; nome: string; operador: string; orcado: number | null; realizado: number;
  /** realizado − orçado (R$ ou R$/L): positivo = acima do plano. */
  desvio: number | null; desvioL: number | null; melhor: boolean | null; texto: string;
  orcadoL: number | null; realizadoL: number | null; origem: LinhaDreOrc["origem_orcado"];
};
/** As linhas de receita e custo da DRE (sem subtotais e sem o desgaste dos bens, que não é orçado). */
export function desvioPorLinha(r: RespostaOrcamento | null): DesvioLinha[] {
  return (r?.linhas_dre ?? [])
    .filter((l) => !l.eh_subtotal && l.chave !== "DEPRECIACAO_AMORT_EXAUSTAO" && (l.orcado != null || Math.abs(l.realizado) >= 0.005))
    .map((l) => {
      const custo = l.operador === "-";
      const d = l.orcado == null ? null : Math.round((l.realizado - l.orcado) * 100) / 100;
      const dL = l.orcado_l == null || l.realizado_l == null ? null : Math.round((l.realizado_l - l.orcado_l) * 10000) / 10000;
      const igual = d != null && Math.abs(d) < 0.5;
      const melhor = d == null || igual ? null : custo ? d < 0 : d > 0;
      const texto = d == null ? "sem orçamento" : igual ? "no plano"
        : custo ? (d > 0 ? "gasto acima do plano · pior" : "gasto abaixo do plano · melhor")
          : (d > 0 ? "acima do plano · melhor" : "abaixo do plano · pior");
      return {
        chave: l.chave, nome: NOME_LINHA[l.chave] ?? l.rotulo, operador: l.operador, orcado: l.orcado, realizado: l.realizado,
        desvio: d, desvioL: dL, melhor, texto, orcadoL: l.orcado_l, realizadoL: l.realizado_l, origem: l.origem_orcado,
      };
    });
}

export const linhaDre = (r: RespostaOrcamento | null, chave: string) => r?.linhas_dre?.find((l) => l.chave === chave) ?? null;

// ── Frase-resumo ──
export type Trecho = { t: string; b?: boolean };
export function fraseOrcamento(o: { periodo: Periodo; r: RespostaOrcamento; brl: (v: number) => string; delta: (a: number, b: number, bom: "sobe" | "desce") => Delta | null }): Trecho[] {
  const { r } = o;
  if (!r.totais) return [];
  const rec = r.totais.receita, des = r.totais.despesa_operacional, res = linhaDre(r, "RESULTADO_LIQUIDO");
  const out: Trecho[] = [{ t: `Em ${o.periodo.label} as receitas ficaram ` }];
  const dr = rec.realizado - rec.orcado, dd = des.realizado - des.orcado;
  out.push({ t: o.brl(Math.abs(dr)), b: true }, { t: ` ${dr >= 0 ? "acima" : "abaixo"} do orçado e as despesas ` }, { t: o.brl(Math.abs(dd)), b: true }, { t: ` ${dd >= 0 ? "acima" : "abaixo"}.` });
  const fora = contasForaDoPlano(r).length;
  if (fora) out.push({ t: " " }, { t: `${fora} ${fora === 1 ? "conta teve" : "contas tiveram"} movimento sem orçamento`, b: true }, { t: " (à parte, sem desvio)." });
  if (res && res.orcado != null) {
    const d = o.delta(res.realizado, res.orcado, "sobe");
    out.push({ t: " Resultado: " }, { t: o.brl(res.realizado), b: true }, { t: " contra " }, { t: o.brl(res.orcado), b: true },
      { t: ` planejados${d && !d.igual ? ` — ${d.melhor ? "melhor" : "pior"} que o plano` : ""}.` });
  }
  return out;
}

// ── A DRE com o orçado como comparação ──
type LinhaComB = { chave: string; subtotal: boolean; b: number | null; contas: { codigo: string | null; b: number | null }[] };
/** Linha sem nenhuma conta orçada fica sem comparação (b = null: "—", nada vermelho);
 *  conta que não está no orçado daquela linha também. Os subtotais comparam sempre. */
export function aplicarSemOrcamento<T extends LinhaComB>(linhas: T[], cascata: LinhaCascataOrc[]): T[] {
  const porChave = new Map(cascata.map((l) => [l.chave, l]));
  return linhas.map((l) => {
    const o = porChave.get(l.chave);
    if (!o || l.subtotal) return l;
    if (!o.orcado) return { ...l, b: null, contas: l.contas.map((c) => ({ ...c, b: null })) };
    const comOrcado = new Set(o.contas.map((c) => c.codigo));
    return { ...l, contas: l.contas.map((c) => (comOrcado.has(c.codigo) ? c : { ...c, b: null })) };
  });
}

// ── Planilha conta × 12 meses ──
export type ItemOrcamento = { id: number; ano: number; mes: number; codigo_conta_gerencial: string; centro_custo: string | null; tipo: string; valor_orcado: number; nome_conta_gerencial?: string };
export type LinhaGrade = { chave: string; codigo: string; centro: string | null; tipo: "receita" | "despesa"; nome: string; valores: number[]; itensPorMes: number[] };
export const chaveGrade = (codigo: string, centro: string | null) => `${codigo}|${centro ?? ""}`;

export function montarGrade(itens: ItemOrcamento[], nomes: Map<string, string> = new Map()): LinhaGrade[] {
  const linhas = new Map<string, LinhaGrade>();
  for (const i of itens) {
    const k = chaveGrade(i.codigo_conta_gerencial, i.centro_custo || null);
    const l = linhas.get(k) ?? {
      chave: k, codigo: i.codigo_conta_gerencial, centro: i.centro_custo || null, tipo: i.tipo === "receita" ? "receita" : "despesa",
      nome: nomes.get(i.codigo_conta_gerencial) || i.nome_conta_gerencial || i.codigo_conta_gerencial,
      valores: Array(12).fill(0), itensPorMes: Array(12).fill(0),
    };
    l.valores[i.mes - 1] = Math.round((l.valores[i.mes - 1] + i.valor_orcado) * 100) / 100;
    l.itensPorMes[i.mes - 1] += 1;
    linhas.set(k, l);
  }
  return ordenarGrade([...linhas.values()]);
}

export function ordenarGrade(ls: LinhaGrade[]): LinhaGrade[] {
  return [...ls].sort((a, b) => (a.tipo === b.tipo ? 0 : a.tipo === "receita" ? -1 : 1) || a.codigo.localeCompare(b.codigo, "pt-BR", { numeric: true }) || (a.centro ?? "").localeCompare(b.centro ?? ""));
}

const arred = (v: number) => Math.round(v);

/** Copia o orçamento do ano anterior (mesmas contas e centros), com +x% em tudo. Mantém as linhas
 *  que já existem neste ano (o valor delas vira o do ano anterior, onde houver). */
export function copiarAnoAnterior(atual: LinhaGrade[], anterior: LinhaGrade[], pct = 0): LinhaGrade[] {
  const out = new Map(atual.map((l) => [l.chave, { ...l, valores: [...l.valores] }]));
  for (const l of anterior) {
    const base = out.get(l.chave) ?? { ...l, itensPorMes: Array(12).fill(0) };
    out.set(l.chave, { ...base, valores: l.valores.map((v) => arred(v * (1 + pct / 100))) });
  }
  return ordenarGrade([...out.values()]);
}

export function aplicarPercentual(ls: LinhaGrade[], pct: number): LinhaGrade[] {
  return ls.map((l) => ({ ...l, valores: l.valores.map((v, m) => (l.itensPorMes[m] > 1 ? v : arred(v * (1 + pct / 100)))) }));
}

export function preencherLinha(ls: LinhaGrade[], chave: string, valor: number): LinhaGrade[] {
  return ls.map((l) => (l.chave === chave ? { ...l, valores: l.valores.map((v, m) => (l.itensPorMes[m] > 1 ? v : valor)) } : l));
}

export function totaisGrade(ls: LinhaGrade[]): { receitas: number[]; despesas: number[]; resultado: number[] } {
  const soma = (tipo: string) => Array.from({ length: 12 }, (_, m) => Math.round(ls.filter((l) => l.tipo === tipo).reduce((s, l) => s + l.valores[m], 0) * 100) / 100);
  const receitas = soma("receita"), despesas = soma("despesa");
  return { receitas, despesas, resultado: receitas.map((v, m) => Math.round((v - despesas[m]) * 100) / 100) };
}

export type CelulaGrade = { codigo_conta_gerencial: string; centro_custo: string | null; tipo: "receita" | "despesa"; mes: number; valor: number };
/** Só o que mudou (célula com mais de um item não é mexida — ajusta-se item a item). */
export function celulasAlteradas(original: LinhaGrade[], atual: LinhaGrade[]): CelulaGrade[] {
  const antes = new Map(original.map((l) => [l.chave, l]));
  const out: CelulaGrade[] = [];
  for (const l of atual) {
    const o = antes.get(l.chave);
    l.valores.forEach((v, m) => {
      if (l.itensPorMes[m] > 1) return;
      const anterior = o ? o.valores[m] : 0;
      if (Math.abs(v - anterior) >= 0.005 || (o && o.tipo !== l.tipo && v)) {
        out.push({ codigo_conta_gerencial: l.codigo, centro_custo: l.centro, tipo: l.tipo, mes: m + 1, valor: v });
      }
    });
  }
  // Linha removida da grade: zera o que ela tinha.
  for (const o of original) {
    if (atual.some((l) => l.chave === o.chave)) continue;
    o.valores.forEach((v, m) => { if (v && o.itensPorMes[m] <= 1) out.push({ codigo_conta_gerencial: o.codigo, centro_custo: o.centro, tipo: o.tipo, mes: m + 1, valor: 0 }); });
  }
  return out;
}

/** Texto de célula ("1.234" ou "1234,50") → número; vazio = 0; inválido = null. */
export function lerValor(txt: string): number | null {
  const s = txt.trim().replace(/\s|R\$/g, "");
  if (!s) return 0;
  const normal = s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : /^\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, "") : s;
  const v = Number(normal);
  return Number.isFinite(v) ? Math.round(v * 100) / 100 : null;
}
