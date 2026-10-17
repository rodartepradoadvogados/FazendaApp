// Qualidade do leite — regras puras da tela (índices, faixas, classificação, payload).
// A tela (components/FormQualidadeLeite.tsx) só desenha; quem valida e monta o corpo do POST é este módulo.
import { lerNumero } from "./producaoGerencial.ts";

export type ChaveIndice = "ccs" | "cbt" | "gordura" | "proteina" | "st" | "esd" | "lactose" | "nul";
export type CampoApi = "ccs" | "cbt" | "gordura_pct" | "proteina_pct" | "solidos_totais_pct" | "esd_pct" | "lactose_pct" | "nul";
export type Situacao = "ok" | "atencao" | "fora" | "invalido";
export type AlvoQualidade = "tanque" | "vaca" | "planilha";

export type Indice = {
  chave: ChaveIndice; campo: CampoApi; sigla: string; nome: string; unidade: string; casas: number;
  /** Faixa SUGERIDA (valores comuns no setor, a confirmar com o dono): dentro de `ok` = na faixa; dentro de `atencao` = atenção; fora = fora. */
  ok: [number, number]; atencao: [number, number]; foraRotulo: string; refOk: string; refAtencao: string;
};

export const INDICES: Indice[] = [
  { chave: "ccs", campo: "ccs", sigla: "CCS", nome: "Contagem de células somáticas", unidade: "mil céls./mL", casas: 0, ok: [0, 200], atencao: [0, 400], foraRotulo: "Alto", refOk: "≤ 200", refAtencao: "atenção de 200 a 400 · alto acima de 400" },
  { chave: "cbt", campo: "cbt", sigla: "CBT", nome: "Contagem bacteriana total", unidade: "mil UFC/mL", casas: 0, ok: [0, 100], atencao: [0, 300], foraRotulo: "Alto", refOk: "≤ 100", refAtencao: "atenção de 100 a 300 · alto acima de 300" },
  { chave: "gordura", campo: "gordura_pct", sigla: "Gordura", nome: "Gordura do leite", unidade: "%", casas: 2, ok: [3.4, 4.4], atencao: [3.0, 5.0], foraRotulo: "Fora da faixa", refOk: "3,4 a 4,4", refAtencao: "atenção de 3,0 a 3,4 e de 4,4 a 5,0" },
  { chave: "proteina", campo: "proteina_pct", sigla: "Proteína", nome: "Proteína do leite", unidade: "%", casas: 2, ok: [3.1, 3.6], atencao: [2.9, 3.8], foraRotulo: "Fora da faixa", refOk: "3,1 a 3,6", refAtencao: "atenção de 2,9 a 3,1 e de 3,6 a 3,8" },
  { chave: "st", campo: "solidos_totais_pct", sigla: "ST", nome: "Sólidos totais", unidade: "%", casas: 2, ok: [12.0, 13.5], atencao: [11.4, 14.5], foraRotulo: "Fora da faixa", refOk: "12,0 a 13,5", refAtencao: "atenção de 11,4 a 12,0 e de 13,5 a 14,5" },
  { chave: "esd", campo: "esd_pct", sigla: "ESD", nome: "Extrato seco desengordurado", unidade: "%", casas: 2, ok: [8.6, 9.2], atencao: [8.4, 9.6], foraRotulo: "Fora da faixa", refOk: "8,6 a 9,2", refAtencao: "atenção de 8,4 a 8,6 e de 9,2 a 9,6" },
  { chave: "lactose", campo: "lactose_pct", sigla: "Lactose", nome: "Lactose", unidade: "%", casas: 2, ok: [4.4, 4.9], atencao: [4.2, 5.1], foraRotulo: "Fora da faixa", refOk: "4,4 a 4,9", refAtencao: "atenção de 4,2 a 4,4 e de 4,9 a 5,1" },
  { chave: "nul", campo: "nul", sigla: "NUL", nome: "Nitrogênio ureico (ureia)", unidade: "mg/dL", casas: 1, ok: [10, 14], atencao: [8, 18], foraRotulo: "Fora da faixa", refOk: "10 a 14", refAtencao: "atenção de 8 a 10 e de 14 a 18" },
];

/** Faixa de bonificação do laticínio (Configurações › Parâmetros) — só CCS, CBT, gordura e proteína. */
export type FaixaBonificacao = {
  indicador: string; valor_min: number | null; valor_max: number | null; ajuste_por_litro: number; ativo: boolean;
};

export type Classificacao = {
  situacao: Situacao;
  rotulo: string;
  /** "laticinio" = veio da tabela de bonificação cadastrada; "sugerida" = faixa sugerida do sistema. */
  origem: "laticinio" | "sugerida";
  /** Ajuste em R$/litro da faixa do laticínio em que o valor caiu (só com origem "laticinio"). */
  ajuste?: number;
};

/** Mesma regra do backend (rules/bonificacao_qualidade._faixa_bate): mínimo e máximo inclusivos; ausente = sem limite. */
export function faixaBate(valor: number, f: FaixaBonificacao): boolean {
  if (f.valor_min !== null && valor < f.valor_min) return false;
  if (f.valor_max !== null && valor > f.valor_max) return false;
  return true;
}

export function faixasAtivasDoIndice(faixas: FaixaBonificacao[], i: Indice): FaixaBonificacao[] {
  return faixas.filter((f) => f.ativo && f.indicador === i.campo)
    .sort((a, b) => (a.valor_min ?? -Infinity) - (b.valor_min ?? -Infinity));
}

function rotuloSugerida(i: Indice, s: Situacao): string {
  return s === "ok" ? "Na faixa" : s === "atencao" ? "Atenção" : s === "fora" ? i.foraRotulo : "Número inválido";
}

/** Classificação pela faixa SUGERIDA. `null` = sem valor. */
export function classificarSugerida(i: Indice, v: number | null): Classificacao | null {
  if (v === null) return null;
  if (!Number.isFinite(v)) return { situacao: "invalido", rotulo: rotuloSugerida(i, "invalido"), origem: "sugerida" };
  const s: Situacao = v >= i.ok[0] && v <= i.ok[1] ? "ok" : v >= i.atencao[0] && v <= i.atencao[1] ? "atencao" : "fora";
  return { situacao: s, rotulo: rotuloSugerida(i, s), origem: "sugerida" };
}

/**
 * Classifica um valor. Com `faixas` do laticínio (só para a coleta do TANQUE, que é o que o laticínio paga), a faixa cadastrada em que o
 * valor cai manda: ajuste positivo = "Bonifica", zero = "Na faixa", negativo = "Penaliza". Valor que não cai em nenhuma faixa cadastrada,
 * ou índice sem faixa (ST, ESD, lactose, NUL), cai na faixa sugerida. O selo só INFORMA: nunca bloqueia o Salvar.
 */
export function classificar(i: Indice, v: number | null, faixas: FaixaBonificacao[] = []): Classificacao | null {
  if (v === null) return null;
  if (Number.isFinite(v)) {
    const doLaticinio = faixasAtivasDoIndice(faixas, i).find((f) => faixaBate(v, f));
    if (doLaticinio) {
      const a = doLaticinio.ajuste_por_litro;
      return a > 0 ? { situacao: "ok", rotulo: "Bonifica", origem: "laticinio", ajuste: a }
        : a < 0 ? { situacao: "fora", rotulo: "Penaliza", origem: "laticinio", ajuste: a }
        : { situacao: "ok", rotulo: "Na faixa", origem: "laticinio", ajuste: 0 };
    }
  }
  return classificarSugerida(i, v);
}

/** Texto curto das faixas do laticínio de um índice (para a coluna de referência). Vazio se não houver. */
export function descreverFaixasLaticinio(faixas: FaixaBonificacao[], i: Indice): string {
  const fmt = (x: number) => x.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  const reais = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}R$ ${Math.abs(x).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}/L`;
  return faixasAtivasDoIndice(faixas, i).map((f) => {
    const lim = f.valor_min !== null && f.valor_max !== null ? `${fmt(f.valor_min)} a ${fmt(f.valor_max)}`
      : f.valor_min !== null ? `≥ ${fmt(f.valor_min)}` : f.valor_max !== null ? `≤ ${fmt(f.valor_max)}` : "qualquer valor";
    return `${lim}: ${reais(f.ajuste_por_litro)}`;
  }).join(" · ");
}

export type RegistroQualidade = { numero_matriz?: string | null; data_coleta: string } & Partial<Record<CampoApi, number | null>>;

/** Última coleta do alvo: do tanque (numero_matriz vazio) ou da vaca escolhida. `null` se não houver. */
export function ultimaColeta(registros: RegistroQualidade[], alvo: "tanque" | "vaca", vaca: string): RegistroQualidade | null {
  const doAlvo = registros.filter((r) => (alvo === "tanque" ? !r.numero_matriz : !!vaca && r.numero_matriz === vaca));
  if (!doAlvo.length) return null;
  return doAlvo.reduce((a, b) => (b.data_coleta > a.data_coleta ? b : a));
}

export type DadosQualidadeLeite = {
  numero_matriz: string | null; data_coleta: string;
  ccs: number | null; cbt: number | null; gordura_pct: number | null; proteina_pct: number | null;
  solidos_totais_pct: number | null; esd_pct: number | null; lactose_pct: number | null; nul: number | null;
  observacao?: string;
};

export type EntradaQualidade = {
  alvo: "tanque" | "vaca"; vaca: string; data: string; valores: Record<ChaveIndice, string>; observacao: string;
};

/** Valida e monta o corpo do POST /producao/qualidade-leite. Vaca (se "Uma vaca") e data são obrigatórias; os 8 índices são opcionais. */
export function montarPayloadQualidade(e: EntradaQualidade): { erro: string } | { dados: DadosQualidadeLeite } {
  if (e.alvo === "vaca" && !e.vaca) return { erro: "Selecione a vaca." };
  if (!e.data) return { erro: "Informe a data da coleta." };
  const lidos = INDICES.map((i) => ({ i, v: lerNumero(e.valores[i.chave]) }));
  const ruins = lidos.filter((l) => l.v !== null && Number.isNaN(l.v));
  if (ruins.length) return { erro: `Corrija ${ruins.map((l) => l.i.sigla).join(", ")}: use só números, por exemplo 3,82.` };
  const por = (c: ChaveIndice) => lidos.find((l) => l.i.chave === c)?.v ?? null;
  return {
    dados: {
      numero_matriz: e.alvo === "vaca" ? e.vaca : null,
      data_coleta: e.data,
      ccs: por("ccs"), cbt: por("cbt"), gordura_pct: por("gordura"), proteina_pct: por("proteina"),
      solidos_totais_pct: por("st"), esd_pct: por("esd"), lactose_pct: por("lactose"), nul: por("nul"),
      observacao: e.observacao.trim() || undefined,
    },
  };
}
