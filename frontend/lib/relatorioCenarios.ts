// "Cenários — E se…?" (Relatórios › Plano, Fase C). O dono preenche valores
// ABSOLUTOS (preço, litros, vacas, % da comida, custos, parcelas, retirada,
// saldo, reserva, compra à vista) em até 3 cenários; a coluna "Real" vem do
// servidor — Resultado por litro (média dos últimos 3 meses fechados, centro
// Leite), DRE pelo dia do pagamento (parcelas e retirada), Caixa real (saldo
// de hoje e reserva) e Rebanho (vacas em lactação). O modelo projeta 12 meses
// de saldo. Com os valores reais, reproduz o COE/L e a sobra/L do servidor
// (conferência na tela). PURO — testes em relatorioCenarios.test.ts.
import type { IndicadoresLitro } from "@/lib/relatorioLitro";

// (Cópias de relatorioContexto.ts: o runner nativo do Node não resolve "@/" em import de runtime.)
const p2 = (n: number) => String(n).padStart(2, "0");
function somaMeses(ym: string, k: number): string {
  const [a, m] = ym.split("-").map(Number);
  const idx = a * 12 + (m - 1) + k;
  return `${Math.floor(idx / 12)}-${p2((idx % 12) + 1)}`;
}
const fimDoMes = (ym: string) => { const [a, m] = ym.split("-").map(Number); return `${ym}-${p2(new Date(a, m, 0).getDate())}`; };

export type ChaveCampo = "preco" | "Ldia" | "lact" | "rmca" | "gente" | "outros" | "parc" | "ret" | "saldo" | "res" | "compra" | "mes";
export type Valores = Record<Exclude<ChaveCampo, "mes">, number> & { mes: string };
export type Campo = { k: ChaveCampo; nome: string; un: string; casas: number; pct?: boolean; grupo: "Leite" | "Custos" | "Caixa"; tipo?: "mes" };

export const CAMPOS: Campo[] = [
  { k: "preco", nome: "Preço líquido do leite", un: "R$/L", casas: 2, grupo: "Leite" },
  { k: "Ldia", nome: "Litros por dia", un: "L/dia", casas: 0, grupo: "Leite" },
  { k: "lact", nome: "Vacas em lactação", un: "cab.", casas: 0, grupo: "Leite" },
  { k: "rmca", nome: "Comida ÷ receita do leite (RMCA)", un: "%", casas: 1, pct: true, grupo: "Custos" },
  { k: "gente", nome: "Mão de obra (folha, encargos, diárias)", un: "R$/mês", casas: 0, grupo: "Custos" },
  { k: "outros", nome: "Outros custeios (sanidade, energia, manutenção…)", un: "R$/mês", casas: 0, grupo: "Custos" },
  { k: "parc", nome: "Parcelas da dívida (principal + juros)", un: "R$/mês", casas: 0, grupo: "Caixa" },
  { k: "ret", nome: "Retirada particular", un: "R$/mês", casas: 0, grupo: "Caixa" },
  { k: "saldo", nome: "Saldo inicial de caixa", un: "R$", casas: 0, grupo: "Caixa" },
  { k: "res", nome: "Reserva desejada", un: "R$", casas: 0, grupo: "Caixa" },
  { k: "compra", nome: "Compra à vista", un: "R$", casas: 0, grupo: "Caixa" },
  { k: "mes", nome: "Mês da compra", un: "", casas: 0, grupo: "Caixa", tipo: "mes" },
];
export const MAX_CENARIOS = 3;

// ── A base "Real" ─────────────────────────────────────────────────────────
/** Os 3 meses fechados antes de hoje (jul–set quando hoje é outubro). */
export function periodoBaseReal(hoje: string): { ini: string; fim: string; cod: string } {
  const ym = hoje.slice(0, 7);
  const ini = `${somaMeses(ym, -3)}-01`, fim = fimDoMes(somaMeses(ym, -1));
  return { ini, fim, cod: `l:${ini}~${fim}` };
}
/** Os 12 meses da projeção: do mês que vem em diante. */
export const mesesProjecao = (hoje: string) => Array.from({ length: 12 }, (_, i) => somaMeses(hoje.slice(0, 7), i + 1));

const diasEntre = (ini: string, fim: string) => {
  const [a1, m1, d1] = ini.split("-").map(Number), [a2, m2, d2] = fim.split("-").map(Number);
  return Math.round((new Date(a2, m2 - 1, d2).getTime() - new Date(a1, m1 - 1, d1).getTime()) / 864e5) + 1;
};

type GrupoFora = { natureza: string; total: number; total_receita?: number; total_despesa?: number };
export type FontesReal = {
  ini: string; fim: string;
  /** `atual` do Resultado por litro dos 3 meses (centro Leite, mês do gasto). */
  litro: IndicadoresLitro | null;
  /** DRE dos 3 meses pelo dia do pagamento, fazenda inteira (o dinheiro que saiu: parcelas e retirada). */
  dreCaixa: { cascata: { chave: string; valor: number }[]; fora_da_dre: { grupos?: GrupoFora[] } } | null;
  /** Caixa real (hoje): saldo das contas e a reserva do parâmetro. */
  caixa: { saldo_inicial: number; fundo_reserva: number } | null;
  /** Rebanho (hoje): vacas em lactação. */
  vacasLactacao: number | null;
};
export type Real = {
  v: Partial<Valores>;
  /** De onde veio cada número (ou por que falta). */
  origem: Partial<Record<ChaveCampo, string>>;
  /** Dias por mês do período base e a relação receita bruta ÷ líquida do leite (Funrural/Senar). */
  diasMes: number; fatorBruto: number; meses: number;
  /** O que o servidor diz (para a conferência). */
  coeL: number | null; sobraL: number | null;
};

const r = (v: number, casas: number) => Math.round(v * 10 ** casas) / 10 ** casas;

export function realDe(f: FontesReal, hoje: string): Real {
  const dias = diasEntre(f.ini, f.fim), meses = Math.max(1, Math.round(dias / 30.44));
  const diasMes = dias / meses;
  const v: Partial<Valores> = {}, origem: Real["origem"] = {};
  const L = f.litro;
  const temLitro = !!L && L.litros > 0 && L.preco_liquido_l != null && L.receita_leite_liquida > 0;
  let fatorBruto = 1;
  if (temLitro) {
    // Sem o arredondamento de 4 casas do preço por litro: receita líquida ÷ litros (os dois do servidor).
    v.preco = L!.receita_leite_liquida / L!.litros;
    v.Ldia = L!.litros / dias;
    fatorBruto = L!.receita_leite_bruta > 0 ? L!.receita_leite_bruta / L!.receita_leite_liquida : 1;
    v.rmca = L!.receita_leite_bruta > 0 ? L!.comida / L!.receita_leite_bruta : 0;
    v.gente = L!.pessoal / meses;
    v.outros = L!.outros_custeio / meses;
    for (const k of ["preco", "Ldia", "rmca", "gente", "outros"] as const) origem[k] = "Resultado por litro (média dos 3 meses)";
  } else {
    for (const k of ["preco", "Ldia", "rmca", "gente", "outros"] as const) origem[k] = "Sem leite e custo nos 3 meses: preencha no cenário";
  }
  if (f.vacasLactacao != null && f.vacasLactacao > 0) { v.lact = f.vacasLactacao; origem.lact = "Rebanho, hoje"; }
  else origem.lact = "Nenhuma vaca em lactação no Rebanho";
  // Só as regras novas separam o que fica fora da DRE por natureza (financiamento, capital).
  if (f.dreCaixa && f.dreCaixa.fora_da_dre.grupos) {
    const grupos = f.dreCaixa.fora_da_dre.grupos;
    const saida = (nat: string) => { const g = grupos.find((x) => x.natureza === nat); return g ? (g.total_despesa ?? g.total) : 0; };
    const outras = f.dreCaixa.cascata.find((l) => l.chave === "OUTRAS_REC_DESP")?.valor ?? 0;
    v.parc = (saida("FINANCIAMENTO") + Math.max(0, -outras)) / meses;
    v.ret = saida("CAPITAL") / meses;
    origem.parc = "Pago nos 3 meses: principal do financiamento + juros (fora da DRE e resultado financeiro)";
    origem.ret = "Pago nos 3 meses: saídas de capital (retirada)";
  } else if (f.dreCaixa) {
    origem.parc = origem.ret = "Com as regras antigas a DRE não separa financiamento e retirada: preencha no cenário";
  } else { origem.parc = origem.ret = "Sem a DRE pelo dia do pagamento: preencha no cenário"; }
  if (f.caixa) {
    v.saldo = f.caixa.saldo_inicial; v.res = f.caixa.fundo_reserva;
    origem.saldo = "Caixa real: saldo de hoje"; origem.res = f.caixa.fundo_reserva ? "Parâmetro do fundo de reserva" : "Sem fundo de reserva no parâmetro";
  } else { origem.saldo = origem.res = "Caixa real indisponível (só administradores): preencha no cenário"; }
  v.compra = 0; v.mes = mesesProjecao(hoje)[4];
  return {
    v, origem, diasMes, fatorBruto, meses,
    coeL: temLitro ? L!.coe_l : null, sobraL: temLitro ? L!.margem_l : null,
  };
}

/** Valores completos (o que faltar no real vira 0 — o dono preenche). Arredondados no formato de
 *  cada campo para começar um cenário; `cheios` = sem arredondar (a coluna Real e a conferência). */
export function valoresBase(real: Real, hoje: string, cheios = false): Valores {
  const b = {} as Valores;
  for (const c of CAMPOS) {
    if (c.tipo === "mes") { b.mes = real.v.mes ?? mesesProjecao(hoje)[4]; continue; }
    const k = c.k as Exclude<ChaveCampo, "mes">;
    b[k] = cheios ? real.v[k] ?? 0 : arredondar(real.v[k] ?? 0, c);
  }
  return b;
}
export const arredondar = (v: number, c: Campo) => (c.pct ? r(v, c.casas + 2) : r(v, c.casas));

// ── O modelo ──────────────────────────────────────────────────────────────
export type Resultado = {
  recL: number; comida: number; coe: number; coeL: number | null; sobraL: number | null; sobraMes: number; comidaRec: number | null;
  Lvaca: number | null; empate: number | null; cob: number | null; caixaMes: number; mnS: number; mnYm: string;
  fim: number; abaixo: number; negYm: string | null; pts: { ym: string; s: number }[];
};

export function calcular(v: Valores, real: Pick<Real, "diasMes" | "fatorBruto">, meses: string[]): Resultado {
  const Lmes = v.Ldia * real.diasMes, recL = v.preco * Lmes, recB = recL * real.fatorBruto;
  const comida = v.rmca * recB, coe = comida + v.gente + v.outros;
  const coeL = Lmes > 0 ? coe / Lmes : null, sobraL = coeL == null ? null : v.preco - coeL;
  const sobraMes = recL - coe;
  const contribuicao = v.preco * (1 - v.rmca * real.fatorBruto);
  const empate = contribuicao > 0 && real.diasMes > 0 ? (v.gente + v.outros) / contribuicao / real.diasMes : null;
  const caixaMes = sobraMes - v.parc - v.ret;
  const pts: { ym: string; s: number }[] = [];
  let s = v.saldo;
  for (const ym of meses) { s = Math.round((s + caixaMes - (ym === v.mes ? v.compra : 0)) * 100) / 100; pts.push({ ym, s }); }
  const mn = pts.reduce((m, p) => (p.s < m.s ? p : m), pts[0] ?? { ym: "", s: v.saldo });
  return {
    recL, comida, coe, coeL, sobraL, sobraMes, comidaRec: recB > 0 ? comida / recB : null,
    Lvaca: v.lact > 0 ? v.Ldia / v.lact : null, empate, cob: v.parc > 0 ? sobraMes / v.parc : null, caixaMes,
    mnS: mn.s, mnYm: mn.ym, fim: pts.length ? pts[pts.length - 1].s : v.saldo,
    abaixo: pts.filter((p) => p.s < v.res).length, negYm: pts.find((p) => p.s < 0)?.ym ?? null, pts,
  };
}

export type Saida = { k: keyof Resultado; nome: string; f: "brl0" | "brl" | "pct" | "n1" | "n0" | "x"; bom: "sobe" | "desce"; main?: boolean };
export const SAIDAS: Saida[] = [
  { k: "recL", nome: "Receita do leite (líquida) por mês", f: "brl0", bom: "sobe" },
  { k: "comida", nome: "Comida por mês", f: "brl0", bom: "desce" },
  { k: "coe", nome: "Custo de custeio (COE) por mês", f: "brl0", bom: "desce" },
  { k: "coeL", nome: "Custo de custeio por litro (COE/L)", f: "brl", bom: "desce" },
  { k: "sobraL", nome: "Sobra do custeio por litro", f: "brl", bom: "sobe", main: true },
  { k: "sobraMes", nome: "Sobra do custeio por mês", f: "brl0", bom: "sobe", main: true },
  { k: "Lvaca", nome: "Litros por vaca/dia", f: "n1", bom: "sobe" },
  { k: "empate", nome: "Litros por dia para empatar", f: "n0", bom: "desce" },
  { k: "cob", nome: "Cobertura da dívida (sobra ÷ parcelas)", f: "x", bom: "sobe" },
  { k: "caixaMes", nome: "Sobra de caixa por mês (após parcelas e retirada)", f: "brl0", bom: "sobe" },
  { k: "mnS", nome: "Menor saldo em 12 meses", f: "brl0", bom: "sobe", main: true },
  { k: "fim", nome: "Saldo no fim dos 12 meses", f: "brl0", bom: "sobe" },
  { k: "abaixo", nome: "Meses abaixo da reserva", f: "n0", bom: "desce" },
];

// ── Os cenários do dono ───────────────────────────────────────────────────
export type Cenario = { nome: string; v: Valores };

export function cenariosExemplo(base: Valores): Cenario[] {
  const c = (o: Partial<Valores>) => ({ ...base, ...o });
  return [
    { nome: "Realista", v: c({}) },
    { nome: "Otimista", v: c({ preco: r(base.preco + 0.12, 2), Ldia: Math.round(base.Ldia * 1.06), lact: Math.round(base.lact + 4) }) },
    { nome: "Pessimista", v: c({ preco: r(Math.max(0, base.preco - 0.25), 2), rmca: r(base.rmca + 0.04, 3) }) },
  ];
}

/** Os cenários ficam no navegador, por fazenda (o PlanejamentoCenario do servidor guarda linhas de
 *  conta × mês para a projeção antiga e o "Importar para Pedidos" — não tem onde guardar estes campos). */
export const chaveArmazenamento = (fazendaId: number | string | null | undefined) => `cowdata:cenarios:v1:${fazendaId ?? "sem-fazenda"}`;

export function lerCenarios(json: string | null): Cenario[] | null {
  if (!json) return null;
  try {
    const x = JSON.parse(json);
    if (!Array.isArray(x) || !x.length || x.length > MAX_CENARIOS) return null;
    const ok = x.every((c) => c && typeof c.nome === "string" && c.v && typeof c.v.mes === "string"
      && CAMPOS.every((f) => f.tipo === "mes" || (typeof c.v[f.k] === "number" && Number.isFinite(c.v[f.k]))));
    return ok ? x.map((c) => ({ nome: c.nome.slice(0, 24), v: c.v as Valores })) : null;
  } catch { return null; }
}

/** O mês da compra precisa estar dentro dos 12 meses mostrados (cenário salvo há meses cai no 5º mês). */
export function ajustarMes(cs: Cenario[], meses: string[]): Cenario[] {
  return cs.map((c) => (meses.includes(c.v.mes) ? c : { ...c, v: { ...c.v, mes: meses[4] } }));
}

/** Valor digitado ("2,65", "1.234", "54%") → número no formato do campo; inválido = null. */
export function lerCampo(txt: string, c: Campo): number | null {
  const s = txt.trim().replace(/\s|R\$|%/g, "");
  if (!s) return 0;
  const normal = s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : /^-?\d{1,3}(\.\d{3})+$/.test(s) ? s.replace(/\./g, "") : s;
  const v = Number(normal);
  if (!Number.isFinite(v)) return null;
  return arredondar(c.pct ? v / 100 : v, c);
}
