// "Fluxo de caixa" (Relatórios › Caixa, Fase C1): modelo de tela da resposta de
// GET /financeiro/fluxo-caixa-mensal — o dinheiro que passou no banco, mês a mês,
// com o que ainda está previsto. O servidor soma; aqui só se alinha a
// comparação mês a mês, monta a frase e decide gráfico × resumo numérico.
// PURO (só import de tipo) — testes em relatorioFluxo.test.ts.
import type { Delta, Periodo } from "@/lib/relatorioContexto";

export type MesFluxo = {
  competencia: string; entradas: number; saidas: number; sobra: number;
  previsto_entradas: number; previsto_saidas: number; sobra_prevista: number; vencidos: number;
  quantidade: number; situacao: "realizado" | "em_curso" | "projetado";
};
export type DiaFluxo = { data: string; entradas: number; saidas: number; previsto_entradas: number; previsto_saidas: number; sobra: number; acumulado: number };
export type ContaFluxo = { codigo: string | null; nome: string; entradas: number; saidas: number; liquido: number };
export type RespostaFluxo = {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; hoje: string; regras_v2: boolean;
  meses: MesFluxo[]; totais: Omit<MesFluxo, "competencia" | "quantidade" | "situacao">;
  contas: ContaFluxo[]; dias?: DiaFluxo[]; meses_com_movimento: number;
  compromissos_sem_vencimento: number; agendado_no_periodo: number; avisos: string[];
};

/** Com menos de 3 meses com movimento, um gráfico de barras engana mais do que ajuda: resumo numérico. */
export const usaResumoNumerico = (r: RespostaFluxo | null) => !r || r.meses.length < 3 || r.meses_com_movimento < 3;

export const temMovimento = (r: RespostaFluxo | null) =>
  !!r && (r.totais.entradas > 0 || r.totais.saidas > 0 || r.totais.previsto_entradas > 0 || r.totais.previsto_saidas > 0);

/** Valor do mês no gráfico/tabela: o realizado; mês em curso ou futuro soma o que ainda está previsto. */
export const sobraDoMes = (m: MesFluxo) => (m.situacao === "realizado" ? m.sobra : m.sobra_prevista);
export const entradasDoMes = (m: MesFluxo) => (m.situacao === "realizado" ? m.entradas : m.entradas + m.previsto_entradas);
export const saidasDoMes = (m: MesFluxo) => (m.situacao === "realizado" ? m.saidas : m.saidas + m.previsto_saidas);

export type LinhaFluxo = {
  competencia: string; situacao: MesFluxo["situacao"];
  entradas: number; saidas: number; sobra: number;
  /** O mês correspondente da comparação (mesma posição no período), ou null. */
  cmpCompetencia: string | null; cmpSobra: number | null;
  /** Linha do ano anterior no gráfico: sobra do mesmo mês um ano antes (null sem dado). */
  anoAnterior: number | null;
  previsto: boolean;
};
const r2 = (v: number) => Math.round(v * 100) / 100 + 0;

export function linhasFluxo(atual: RespostaFluxo | null, cmp: RespostaFluxo | null, anoAnt: RespostaFluxo | null): LinhaFluxo[] {
  if (!atual) return [];
  const doAnoAnt = new Map((anoAnt?.meses ?? []).map((m) => [m.competencia, m]));
  return atual.meses.map((m, i) => {
    const q = cmp?.meses[i] ?? null;
    const ymAnt = `${Number(m.competencia.slice(0, 4)) - 1}${m.competencia.slice(4)}`;
    const a = doAnoAnt.get(ymAnt);
    return {
      competencia: m.competencia, situacao: m.situacao,
      entradas: r2(entradasDoMes(m)), saidas: r2(saidasDoMes(m)), sobra: r2(sobraDoMes(m)),
      // Mês da comparação sem nenhum movimento é "sem dado", não zero.
      cmpCompetencia: q ? q.competencia : null, cmpSobra: q && q.quantidade > 0 ? r2(sobraDoMes(q)) : null,
      anoAnterior: a && a.quantidade > 0 ? r2(sobraDoMes(a)) : null,
      previsto: m.situacao !== "realizado" && (m.previsto_entradas > 0 || m.previsto_saidas > 0 || m.situacao === "projetado"),
    };
  });
}

export type Trecho = { t: string; b?: boolean };
export function fraseFluxo(o: {
  periodo: Periodo; r: RespostaFluxo; cmp: RespostaFluxo | null; rotuloCmp: string | null;
  brl: (v: number) => string; delta: (a: number, b: number) => Delta | null;
}): Trecho[] {
  const t = o.r.totais;
  const out: Trecho[] = [
    { t: `Em ${o.periodo.label} entraram ` }, { t: o.brl(t.entradas), b: true }, { t: " e saíram " }, { t: o.brl(t.saidas), b: true },
    { t: " do banco: " }, { t: t.sobra >= 0 ? "sobraram " : "faltaram " }, { t: o.brl(Math.abs(t.sobra)), b: true },
  ];
  if (o.cmp && o.rotuloCmp) {
    const d = o.delta(t.sobra, o.cmp.totais.sobra);
    if (d && d.igual) out.push({ t: `, igual a ${o.rotuloCmp}` });
    else if (d) out.push({ t: `, ${o.brl(Math.abs(d.abs))} ${d.abs > 0 ? "a mais" : "a menos"} que em ${o.rotuloCmp}` });
  }
  out.push({ t: "." });
  if (t.previsto_entradas || t.previsto_saidas) {
    out.push({ t: " Ainda estão previstos " }, { t: o.brl(t.previsto_entradas), b: true }, { t: " de entrada e " },
      { t: o.brl(t.previsto_saidas), b: true }, { t: " de saída até o fim do período" });
    if (t.vencidos > 0) out.push({ t: `, dos quais ${o.brl(t.vencidos)} já venceram` });
    out.push({ t: "." });
  }
  return out;
}
