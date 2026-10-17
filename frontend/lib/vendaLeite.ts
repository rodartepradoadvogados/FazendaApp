// Venda mensal do leite — regras puras da tela (conversão kg/L, validação, payload, balanço).
// A tela (components/FormEntregaLeite.tsx) só desenha; quem valida e monta o corpo do POST/PUT é este módulo.
import { lerNumero } from "./producaoGerencial.ts";

export type UnidadeEntrega = "kg" | "L";

/** Densidade do leite usada pelo servidor (rules/unidades.DENSIDADE_LEITE_KG_POR_L): 1 L = 1,029 kg. */
export const KG_POR_L = 1.029;

/** `quantidade_litros` é só o NOME do campo da API: guarda o número na unidade escolhida (kg ou L). */
export type RegistroEntrega = {
  id: number; competencia: string; quantidade_litros: number; unidade?: string | null; observacao: string | null; usuario_nome?: string | null;
};

export type DadosEntrega = { competencia: string; quantidade_litros: number; unidade: UnidadeEntrega; observacao?: string };

export const ehUnidade = (u: string | null | undefined): UnidadeEntrega => ((u || "kg").trim().toUpperCase() === "L" ? "L" : "kg");

/** "2026-09" → "09/2026". */
export function mesBR(competencia: string): string {
  const [a, m] = competencia.split("-");
  return m && a ? `${m}/${a}` : competencia;
}

export const emKg = (q: number, u: UnidadeEntrega): number => (u === "L" ? q * KG_POR_L : q);

const nbBR = (v: number, casas: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
export const casasDe = (q: number): number => (Number.isInteger(q) ? 0 : 1);
export const textoQtd = (q: number, u: UnidadeEntrega): string => `${nbBR(q, casasDe(q))} ${u}`;

export const COMPETENCIA_VALIDA = /^\d{4}-(0[1-9]|1[0-2])$/;

/** Primeiro e último dia do mês da competência ("2026-09" → 2026-09-01 e 2026-09-30), para o relatório Controle × Entregue. */
export function intervaloDoMes(competencia: string): { inicio: string; fim: string } | null {
  if (!COMPETENCIA_VALIDA.test(competencia)) return null;
  const a = Number(competencia.slice(0, 4)), m = Number(competencia.slice(5, 7));
  const ultimo = new Date(Date.UTC(a, m, 0)).getUTCDate();
  return { inicio: `${competencia}-01`, fim: `${competencia}-${String(ultimo).padStart(2, "0")}` };
}

/** Do mais recente para o mais antigo. */
export function ordenarEntregas<T extends { competencia: string }>(lista: T[]): T[] {
  return [...lista].sort((a, b) => b.competencia.localeCompare(a.competencia));
}

export type EntradaEntrega = { competencia: string; quantidade: string; unidade: UnidadeEntrega; observacao: string };

/** Valida (mês AAAA-MM e quantidade > 0, vírgula decimal aceita) e monta o corpo do POST/PUT /producao/entrega-leite. */
export function montarPayloadEntrega(e: EntradaEntrega): { erro: string } | { dados: DadosEntrega } {
  if (!e.competencia || !COMPETENCIA_VALIDA.test(e.competencia)) return { erro: "Selecione o mês." };
  const q = lerNumero(e.quantidade);
  if (q === null) return { erro: "Informe a quantidade entregue." };
  if (Number.isNaN(q) || q <= 0) return { erro: "A quantidade precisa ser um número maior que zero." };
  return { dados: { competencia: e.competencia, quantidade_litros: q, unidade: e.unidade, observacao: e.observacao.trim() || undefined } };
}

/** Controle × entregue do mês (kg). Positivo = sobrou leite fora da entrega; negativo = entregou acima do que o controle produziu. */
export function balancoDoMes(entregueKg: number | null, controleKg: number | null): { dif: number; pct: number } | null {
  if (entregueKg === null || controleKg === null) return null;
  const dif = controleKg - entregueKg;
  return { dif, pct: controleKg ? (dif / controleKg) * 100 : 0 };
}
