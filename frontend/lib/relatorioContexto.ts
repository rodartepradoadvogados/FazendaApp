// Contexto dos Relatórios do Financeiro (Fase B do redesenho): período,
// comparação, regime e centro de custo — o estado INTEIRO da barra de
// contexto, que vive na URL (link compartilhável; Voltar do navegador volta
// ao contexto anterior). Funções PURAS, sem import de runtime, para rodar no
// runner nativo do Node (`npm test`, ver relatorioContexto.test.ts).
//
// Período (`per`):  m:AAAA-MM · t:AAAA-Tn · s:AAAA (safra jul/AAAA–jun/AAAA+1)
//                   · a:AAAA · l:AAAA-MM-DD~AAAA-MM-DD (livre)
// Comparar (`cmp`): ant (período anterior) · aa (mesmo período do ano passado)
//                   · outro (+ `cmpp` com outro período) · orc (orçado) · nada
// Regime (`reg`):   comp (competência, mês do gasto) · caixa (dia do pagamento)
// Centro (`cc`):    nome do centro de custo, ou "todos"
//
// "Hoje" sempre vem de fora (hojeLocal(), fuso local) — nunca toISOString().

export type TipoPeriodo = "m" | "t" | "s" | "a" | "l";
export type ModoComparacao = "ant" | "aa" | "outro" | "orc" | "nada";
export type Regime = "comp" | "caixa";

export type EstadoContexto = {
  per: string;
  cmp: ModoComparacao;
  /** Só com cmp = "outro": o período escolhido para comparar. */
  cmpp: string;
  reg: Regime;
  /** Nome do centro de custo ou "todos". */
  cc: string;
};

export type Periodo = {
  tipo: TipoPeriodo;
  /** Valor sem o prefixo (ex.: "2026-09", "2026-T3", "2025", "2026-08-01~2026-09-30"). */
  val: string;
  /** Código completo (ex.: "m:2026-09"). */
  cod: string;
  ini: string;
  fim: string;
  /** "setembro/2026", "3º trimestre de 2026", "safra 2025/26", "ano de 2025", "01/08/2026 a 30/09/2026". */
  label: string;
  /** "set/26", "3º tri/26", "safra 25/26", "2025", "01/08–30/09/26". */
  curto: string;
};

export type Comparacao =
  | { tipo: "periodo"; periodo: Periodo; escolhido: boolean; rotulo: string }
  | { tipo: "orcado"; rotulo: "orçado" };

export const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
export const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
export const TIPOS_PERIODO: { v: TipoPeriodo; rotulo: string }[] = [
  { v: "m", rotulo: "Mês" }, { v: "t", rotulo: "Trimestre" }, { v: "s", rotulo: "Safra (jul–jun)" },
  { v: "a", rotulo: "Ano" }, { v: "l", rotulo: "Livre (datas)" },
];
export const MODOS_COMPARACAO: { v: ModoComparacao; rotulo: string }[] = [
  { v: "ant", rotulo: "Período anterior" }, { v: "aa", rotulo: "Mesmo período do ano passado" },
  { v: "outro", rotulo: "Outro período…" }, { v: "orc", rotulo: "Orçado" }, { v: "nada", rotulo: "Sem comparação" },
];
export const REGIME_NOME: Record<Regime, string> = { comp: "pelo mês do gasto (competência)", caixa: "pelo dia do pagamento (caixa)" };
export const REGIME_CURTO: Record<Regime, string> = { comp: "mês do gasto", caixa: "dia do pagamento" };
/** Regime no vocabulário do backend (`/financeiro/dre?regime=`). */
export const REGIME_API: Record<Regime, "competencia" | "caixa"> = { comp: "competencia", caixa: "caixa" };

const p2 = (n: number) => String(n).padStart(2, "0");
const RE_DATA = /^\d{4}-\d{2}-\d{2}$/;

/** Último dia do mês (AAAA-MM-DD), sem passar por UTC. */
export function fimDoMes(ym: string): string {
  const [a, m] = ym.split("-").map(Number);
  return `${ym}-${p2(new Date(a, m, 0).getDate())}`;
}

/** Soma `k` meses a AAAA-MM. */
export function somaMeses(ym: string, k: number): string {
  const [a, m] = ym.split("-").map(Number);
  const idx = a * 12 + (m - 1) + k;
  return `${Math.floor(idx / 12)}-${p2((idx % 12) + 1)}`;
}

/** Soma `k` dias a AAAA-MM-DD (fuso local). */
export function somaDiasIso(iso: string, k: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const x = new Date(a, m - 1, d + k);
  return `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}`;
}

/** Mesma data, `k` meses para trás/frente (dia limitado ao fim do mês: 31/03 − 1 mês = 28/02). */
function somaMesesData(iso: string, k: number): string {
  const ym = somaMeses(iso.slice(0, 7), k);
  const ultimo = Number(fimDoMes(ym).slice(8));
  return `${ym}-${p2(Math.min(Number(iso.slice(8)), ultimo))}`;
}

const dmy = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
const dm = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)}`;

export function mesLongo(ym: string): string {
  return `${MESES_LONGOS[Number(ym.slice(5, 7)) - 1]}/${ym.slice(0, 4)}`;
}
export function mesCurto(ym: string): string {
  return `${MESES_CURTOS[Number(ym.slice(5, 7)) - 1]}/${ym.slice(2, 4)}`;
}

function dataValida(s: string): boolean {
  if (!RE_DATA.test(s)) return false;
  const [a, m, d] = s.split("-").map(Number);
  const x = new Date(a, m - 1, d);
  return x.getFullYear() === a && x.getMonth() === m - 1 && x.getDate() === d;
}

/** Interpreta o código do período; null se inválido. */
export function periodoDe(cod: string | null | undefined): Periodo | null {
  if (!cod || cod[1] !== ":") return null;
  const tipo = cod[0] as TipoPeriodo, val = cod.slice(2);
  if (tipo === "m" && /^\d{4}-(0[1-9]|1[0-2])$/.test(val)) {
    return { tipo, val, cod, ini: `${val}-01`, fim: fimDoMes(val), label: mesLongo(val), curto: mesCurto(val) };
  }
  if (tipo === "t" && /^\d{4}-T[1-4]$/.test(val)) {
    const a = val.slice(0, 4), q = Number(val.slice(6)), m0 = (q - 1) * 3 + 1;
    return { tipo, val, cod, ini: `${a}-${p2(m0)}-01`, fim: fimDoMes(`${a}-${p2(m0 + 2)}`), label: `${q}º trimestre de ${a}`, curto: `${q}º tri/${a.slice(2)}` };
  }
  if (tipo === "s" && /^\d{4}$/.test(val)) {
    const a = Number(val), b = a + 1;
    return { tipo, val, cod, ini: `${a}-07-01`, fim: `${b}-06-30`, label: `safra ${a}/${String(b).slice(2)}`, curto: `safra ${String(a).slice(2)}/${String(b).slice(2)}` };
  }
  if (tipo === "a" && /^\d{4}$/.test(val)) {
    return { tipo, val, cod, ini: `${val}-01-01`, fim: `${val}-12-31`, label: `ano de ${val}`, curto: val };
  }
  if (tipo === "l") {
    let [i, f] = val.split("~");
    if (!i || !f || !dataValida(i) || !dataValida(f)) return null;
    if (f < i) [i, f] = [f, i];
    const v = `${i}~${f}`;
    return { tipo, val: v, cod: `l:${v}`, ini: i, fim: f, label: `${dmy(i)} a ${dmy(f)}`, curto: `${dm(i)}–${dm(f)}/${f.slice(2, 4)}` };
  }
  return null;
}

/** O período "fechado" mais recente de cada tipo (o padrão ao trocar de tipo). */
export function periodoPadrao(tipo: TipoPeriodo, hoje: string): Periodo {
  const ym = hoje.slice(0, 7), ano = Number(hoje.slice(0, 4)), mes = Number(hoje.slice(5, 7));
  switch (tipo) {
    case "t": {
      const q = Math.floor((mes - 1) / 3); // trimestre corrente − 1 (0 = o último do ano passado)
      return periodoDe(q === 0 ? `t:${ano - 1}-T4` : `t:${ano}-T${q}`)!;
    }
    case "s": return periodoDe(`s:${mes >= 7 ? ano - 1 : ano - 2}`)!;
    case "a": return periodoDe(`a:${ano - 1}`)!;
    case "l": { const ini = `${somaMeses(ym, -2)}-01`; return periodoDe(`l:${ini}~${fimDoMes(somaMeses(ym, -1))}`)!; }
    default: return periodoDe(`m:${somaMeses(ym, -1)}`)!;
  }
}

/** Desloca o período `k` unidades do seu tipo (livre: um bloco de mesmo tamanho). */
export function deslocar(p: Periodo, k: number): Periodo {
  switch (p.tipo) {
    case "m": return periodoDe(`m:${somaMeses(p.val, k)}`)!;
    case "t": {
      const idx = Number(p.val.slice(0, 4)) * 4 + (Number(p.val.slice(6)) - 1) + k;
      return periodoDe(`t:${Math.floor(idx / 4)}-T${(idx % 4) + 1}`)!;
    }
    case "s": case "a": return periodoDe(`${p.tipo}:${Number(p.val) + k}`)!;
    default: {
      const n = Math.round((new Date(p.fim).getTime() - new Date(p.ini).getTime()) / 864e5) + 1;
      const ini = somaDiasIso(p.ini, n * k), fim = somaDiasIso(p.fim, n * k);
      return periodoDe(`l:${ini}~${fim}`)!;
    }
  }
}

/** O mesmo período, um ano antes. */
export function anoAnterior(p: Periodo): Periodo {
  switch (p.tipo) {
    case "m": return deslocar(p, -12);
    case "t": return deslocar(p, -4);
    case "s": case "a": return deslocar(p, -1);
    default: return periodoDe(`l:${somaMesesData(p.ini, -12)}~${somaMesesData(p.fim, -12)}`)!;
  }
}

/** O período de comparação (null = sem comparação). */
export function comparacaoDe(p: Periodo, cmp: ModoComparacao, cmpp?: string): Comparacao | null {
  if (cmp === "nada") return null;
  if (cmp === "orc") return { tipo: "orcado", rotulo: "orçado" };
  if (cmp === "outro") {
    const q = periodoDe(cmpp);
    if (q) return { tipo: "periodo", periodo: q, escolhido: true, rotulo: q.curto };
  }
  const q = cmp === "aa" ? anoAnterior(p) : deslocar(p, -1);
  return { tipo: "periodo", periodo: q, escolhido: false, rotulo: q.curto };
}

export const ESTADO_INICIAL = (hoje: string, ccPadrao: string): EstadoContexto => ({
  per: periodoPadrao("m", hoje).cod, cmp: "aa", cmpp: "", reg: "comp", cc: ccPadrao || "todos",
});

const CHAVES = ["per", "cmp", "cmpp", "reg", "cc"] as const;

/** Lê o contexto da query string (o que faltar ou vier inválido cai no padrão). */
export function lerContexto(busca: string, padrao: EstadoContexto): EstadoContexto {
  const q = new URLSearchParams(busca);
  const per = periodoDe(q.get("per"));
  const cmp = q.get("cmp") as ModoComparacao | null;
  const cmpp = periodoDe(q.get("cmpp"));
  const reg = q.get("reg");
  const cc = (q.get("cc") || "").trim();
  return {
    per: per ? per.cod : padrao.per,
    cmp: cmp && MODOS_COMPARACAO.some((m) => m.v === cmp) ? cmp : padrao.cmp,
    cmpp: cmpp ? cmpp.cod : "",
    reg: reg === "caixa" || reg === "comp" ? reg : padrao.reg,
    cc: cc || padrao.cc,
  };
}

/** Escreve o contexto na query string, preservando os outros parâmetros (ex.: `sub`). */
export function escreverContexto(busca: string, e: EstadoContexto): string {
  const q = new URLSearchParams(busca);
  for (const k of CHAVES) q.delete(k);
  q.set("per", e.per);
  q.set("cmp", e.cmp);
  if (e.cmp === "outro" && e.cmpp) q.set("cmpp", e.cmpp);
  q.set("reg", e.reg);
  q.set("cc", e.cc || "todos");
  return q.toString();
}

/** Opções do seletor "Qual …" para um tipo de período: do mais recente ao mais antigo, sempre com o atual. */
export function opcoesPeriodo(tipo: TipoPeriodo, hoje: string, atual?: string): { v: string; rotulo: string }[] {
  const ym = hoje.slice(0, 7), ano = Number(hoje.slice(0, 4));
  let cods: string[] = [];
  if (tipo === "m") cods = Array.from({ length: 37 }, (_, i) => `m:${somaMeses(ym, -i)}`);
  else if (tipo === "t") {
    const idx = ano * 4 + Math.floor((Number(hoje.slice(5, 7)) - 1) / 3);
    cods = Array.from({ length: 13 }, (_, i) => `t:${Math.floor((idx - i) / 4)}-T${((idx - i) % 4) + 1}`);
  } else if (tipo === "s") {
    const s0 = Number(hoje.slice(5, 7)) >= 7 ? ano : ano - 1;
    cods = Array.from({ length: 5 }, (_, i) => `s:${s0 - i}`);
  } else if (tipo === "a") cods = Array.from({ length: 5 }, (_, i) => `a:${ano - i}`);
  const out = cods.map((c) => periodoDe(c)!).map((p) => ({ v: p.cod, rotulo: p.ini <= hoje && hoje <= p.fim ? `${p.label} (em curso)` : p.label }));
  if (atual && atual[0] === tipo && !out.some((o) => o.v === atual)) {
    const p = periodoDe(atual);
    if (p) out.unshift({ v: p.cod, rotulo: p.label });
  }
  return out;
}

/** O período contém hoje (ainda em curso)? */
export const emCurso = (p: Periodo, hoje: string) => p.ini <= hoje && hoje <= p.fim;

// ── Variação com sentido ──────────────────────────────────────────────────

/** "sobe" = maior é melhor (receita, margem); "desce" = menor é melhor (custo); "neutro" = sem juízo. */
export type SentidoBom = "sobe" | "desce" | "neutro";
export type Delta = { abs: number; pct: number | null; igual: boolean; melhor: boolean | null };

export function delta(a: number | null | undefined, b: number | null | undefined, bom: SentidoBom = "sobe"): Delta | null {
  if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) return null;
  const abs = a - b;
  const pct = Math.abs(b) > 1e-9 ? abs / Math.abs(b) : null;
  const igual = Math.abs(abs) < 0.005 || (pct != null && Math.abs(pct) < 0.0005);
  return { abs, pct, igual, melhor: igual || bom === "neutro" ? null : bom === "sobe" ? abs > 0 : abs < 0 };
}

// ── Formatação (pt-BR, sinal de menos tipográfico, espaço que não quebra) ──

export const MENOS = "−";
const NB = " ";
export function num(v: number, casas = 2): string {
  return Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
const ehZero = (v: number, casas: number) => num(v, casas) === num(0, casas);
export function brl(v: number, casas = 2): string {
  return `${v < 0 && !ehZero(v, casas) ? MENOS : ""}R$${NB}${num(v, casas)}`;
}
/** Com sinal explícito (+/−), para variações. */
export function brlSinal(v: number, casas = 2): string {
  return `${ehZero(v, casas) ? "" : v > 0 ? "+" : MENOS}R$${NB}${num(v, casas)}`;
}
export function pct(fracao: number, casas = 1): string {
  return `${fracao < 0 && !ehZero(fracao * 100, casas) ? MENOS : ""}${num(fracao * 100, casas)}%`;
}
export function pctSinal(fracao: number, casas = 1): string {
  return `${ehZero(fracao * 100, casas) ? "" : fracao > 0 ? "+" : MENOS}${num(fracao * 100, casas)}%`;
}
export function litros(v: number): string {
  return `${num(v, 0)}${NB}L`;
}

/** `num0`: número inteiro sem unidade (ex.: dias de fôlego — a unidade vai à parte). */
export type FormatoNumero = "brl" | "brl0" | "brlL" | "pct" | "litros" | "num0";
export function formatar(v: number, f: FormatoNumero): string {
  if (f === "brl0") return brl(v, 0);
  if (f === "brlL") return brl(v, 2);
  if (f === "pct") return `${v < 0 ? MENOS : ""}${num(v, 1)}%`; // já em pontos percentuais
  if (f === "litros") return litros(v);
  if (f === "num0") return `${v < 0 && Math.round(v) !== 0 ? MENOS : ""}${num(v, 0)}`;
  return brl(v, 2);
}
/** Variação absoluta no formato do número (pct vira "p.p."). */
export function formatarDelta(abs: number, f: FormatoNumero): string {
  const s = abs > 0 ? "+" : MENOS;
  if (f === "pct") return `${s}${num(abs, 1)} p.p.`;
  if (f === "litros") return `${s}${litros(abs)}`;
  if (f === "num0") return `${s}${num(abs, 0)}`;
  if (f === "brl0") return brlSinal(abs, 0);
  return brlSinal(abs, 2);
}

/** Resumo de uma linha do contexto: "set/26 · vs set/25 · mês do gasto · Pecuária Leiteira". */
export function resumoContexto(p: Periodo, c: Comparacao | null, reg: Regime, cc: string): string {
  return [p.curto, c ? `vs ${c.rotulo}` : null, REGIME_CURTO[reg], cc === "todos" ? "todos os centros" : cc].filter(Boolean).join(" · ");
}
