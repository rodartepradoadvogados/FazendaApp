// Relatórios › Registros (Fase C): "Compra e venda de animais" e "Compra de
// sêmen". Modelos de tela das respostas de GET /relatorio-compra-venda-animais/resumo
// e GET /relatorio-compra-semen/resumo — os totais (por cabeça, por categoria,
// por natureza, custo por prenhez) vêm do servidor. PURO — testes em
// relatorioRegistros.test.ts.
import type { Periodo } from "@/lib/relatorioContexto";

export type Natureza = "OPERACIONAL" | "INVESTIMENTO" | "FINANCIAMENTO" | "CAPITAL" | "TRANSFERENCIA" | "ADIANTAMENTO" | "OBRIGACAO" | "NAO_INFORMADA";

export type LinhaAnimal = {
  tipo: "compra" | "venda"; numero_animal: string; contraparte: string; data: string; valor: number; tipo_valor: string;
  gta: string | null; numero_lancamento: string | null; numero_documento: string | null; centro_custo: string | null;
  codigo_conta: string | null; categorias: string | null; motivo_venda: string | null; usuario_nome?: string | null;
  natureza: Natureza | null; natureza_rotulo: string; categoria: string; origem_categoria: "nota" | "animal" | null;
};
export type TotaisAnimais = {
  vendas: number; compras: number; saldo: number; cab_vendidas: number; cab_compradas: number;
  venda_por_cabeca: number | null; compra_por_cabeca: number | null; compras_operacionais: number; compras_investimento: number;
  sem_lancamento: number;
};
export type CategoriaAnimais = {
  categoria: string; cab_vendidas: number; vendas: number; venda_por_cabeca: number | null;
  cab_compradas: number; compras: number; compra_por_cabeca: number | null;
};
export type NaturezaAnimais = { natureza: Natureza | null; rotulo: string; cab_vendidas: number; vendas: number; cab_compradas: number; compras: number };
export type RespostaAnimais = {
  periodo: { inicio: string | null; fim: string | null }; centro_custo: string | null; regras_v2: boolean;
  linhas: LinhaAnimal[]; totais: TotaisAnimais; por_categoria: CategoriaAnimais[]; por_natureza: NaturezaAnimais[];
};

export type LinhaSemen = {
  touro_nome: string; naab: string | null; origem: string; tipo: string; doses: number; valor_unitario: number; valor_total: number;
  vendedor: string; data_compra: string; numero_lancamento: string | null; numero_documento: string | null; centro_custo: string | null;
  codigo_conta: string | null; usuario_nome?: string | null; natureza: Natureza | null; natureza_rotulo: string;
};
export type Prenhez = {
  preco_dose: { preco: number | null; doses: number; valor: number; base: "12_meses" | "historico" | null };
  inseminacoes: number; diagnosticadas: number; aguardando_diagnostico: number; prenhezes: number;
  taxa_concepcao_pct: number | null; custo_semen_usado: number | null; custo_semen_diagnosticadas: number | null; custo_por_prenhez: number | null;
};
export type RespostaSemen = {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; regras_v2: boolean;
  linhas: LinhaSemen[]; totais: { gasto: number; doses: number; compras: number; preco_medio_dose: number | null; sem_lancamento: number };
  prenhez: Prenhez; serie: (Prenhez & { competencia: string })[];
};

/** Busca por número do animal, documento ou GTA olha TODO o histórico (como a busca global do Financeiro). */
export type BuscaRegistro = { numero?: string; documento?: string; gta?: string; touro?: string; vendedor?: string };
export const buscaGlobal = (b: BuscaRegistro) => !!(b.numero?.trim() || b.documento?.trim() || b.gta?.trim());

/** Natureza curta para o selo da linha (o rótulo longo fica no title). */
export function seloNatureza(n: Natureza | null): { texto: string; investimento: boolean } {
  if (!n) return { texto: "sem lançamento", investimento: false };
  if (n === "OPERACIONAL") return { texto: "operacional", investimento: false };
  if (n === "INVESTIMENTO") return { texto: "investimento", investimento: true };
  return { texto: n.toLowerCase().replace("_", " "), investimento: false };
}

const plural = (n: number, um: string, varios: string) => `${n.toLocaleString("pt-BR")} ${n === 1 ? um : varios}`;

export function fraseAnimais(o: { periodo: Periodo | null; r: RespostaAnimais; brl: (v: number) => string }): { t: string; b?: boolean }[] {
  const t = o.r.totais;
  const onde = o.periodo ? `Em ${o.periodo.label}` : "No histórico buscado";
  const out: { t: string; b?: boolean }[] = [
    { t: `${onde} a fazenda vendeu ` }, { t: plural(t.cab_vendidas, "cabeça", "cabeças"), b: true },
    { t: " por " }, { t: o.brl(t.vendas), b: true }, { t: " e comprou " }, { t: plural(t.cab_compradas, "cabeça", "cabeças"), b: true },
    { t: " por " }, { t: o.brl(t.compras), b: true }, { t: "." },
  ];
  if (t.compras_investimento > 0.005) {
    out.push({ t: ` Destas compras, ${o.brl(t.compras_investimento)} são ` }, { t: "investimento", b: true },
      { t: " (matriz ou reprodutor para o plantel): ficam fora da DRE e dos custos com as regras novas." });
  }
  return out;
}

/** Custo do sêmen por prenhez: existe só com inseminação diagnosticada, prenhez e preço de dose. Diz o que falta. */
export function porqueSemCustoPrenhez(p: Prenhez | null | undefined): string | null {
  if (!p) return null;
  if (p.custo_por_prenhez != null) return null;
  if (p.inseminacoes === 0) return "Nenhuma inseminação lançada no período (Reprodutivo).";
  if (p.diagnosticadas === 0) return `${plural(p.inseminacoes, "inseminação", "inseminações")} ainda sem diagnóstico de gestação.`;
  if (p.prenhezes === 0) return "Nenhuma prenhez confirmada entre as inseminações diagnosticadas.";
  if (p.preco_dose.preco == null) return "Sem compra de sêmen registrada para saber o preço da dose.";
  return null;
}

export function fraseSemen(o: { periodo: Periodo; r: RespostaSemen; brl: (v: number) => string }): { t: string; b?: boolean }[] {
  const p = o.r.prenhez, t = o.r.totais;
  const out: { t: string; b?: boolean }[] = [];
  if (p.inseminacoes > 0) {
    out.push({ t: `Em ${o.periodo.label} foram ` }, { t: plural(p.inseminacoes, "inseminação", "inseminações"), b: true },
      { t: " e " }, { t: plural(p.prenhezes, "prenhez confirmada", "prenhezes confirmadas"), b: true });
    if (p.custo_por_prenhez != null) out.push({ t: ": cada prenhez custou " }, { t: o.brl(p.custo_por_prenhez), b: true }, { t: " só de sêmen" });
    out.push({ t: "." });
    if (p.aguardando_diagnostico > 0) out.push({ t: ` ${plural(p.aguardando_diagnostico, "inseminação aguarda", "inseminações aguardam")} o diagnóstico e fica${p.aguardando_diagnostico === 1 ? "" : "m"} fora da conta.` });
  }
  if (t.compras > 0) {
    out.push({ t: out.length ? " Foram compradas " : `Em ${o.periodo.label} foram compradas ` }, { t: plural(t.doses, "dose", "doses"), b: true },
      { t: " por " }, { t: o.brl(t.gasto), b: true }, { t: t.preco_medio_dose != null ? ` (${o.brl(t.preco_medio_dose)} por dose).` : "." });
  }
  return out;
}
