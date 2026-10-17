// Fase do ciclo de diagnóstico (a tocar / a reconfirmar / reconfirmada) — helpers puros da Agenda Reprodutiva.
// A classificação em si vem do backend (rules/fase_toque.py); aqui só se conta, filtra e ordena o que ele devolveu.
export type FaseToque = "a_tocar" | "a_reconfirmar" | "reconfirmada";
export const FASES: FaseToque[] = ["a_tocar", "a_reconfirmar", "reconfirmada"];
export const ROTULO_FASE: Record<FaseToque, string> = { a_tocar: "A tocar", a_reconfirmar: "A reconfirmar", reconfirmada: "Reconfirmada" };
export const ROTULO_FASE_PLURAL: Record<FaseToque, string> = { a_tocar: "A tocar", a_reconfirmar: "A reconfirmar", reconfirmada: "Reconfirmadas" };

export type ItemComFase = {
  numero_matriz: string; fase?: FaseToque | null; ainda_nao?: boolean; dias_para_prazo?: number | null;
};

/** Quantos ANIMAIS há em cada fase — cada animal conta uma vez, mesmo que apareça em mais de um card. */
export function contarPorFase(itensPorCard: Record<string, ItemComFase[]>): Record<FaseToque, number> {
  const vistos: Record<FaseToque, Set<string>> = { a_tocar: new Set(), a_reconfirmar: new Set(), reconfirmada: new Set() };
  for (const itens of Object.values(itensPorCard)) {
    for (const it of itens) if (it.fase) vistos[it.fase].add(it.numero_matriz);
  }
  return { a_tocar: vistos.a_tocar.size, a_reconfirmar: vistos.a_reconfirmar.size, reconfirmada: vistos.reconfirmada.size };
}

/** Sem fase escolhida = todos os itens (inclusive os que não têm fase, como PEV e vazias). Com fase(s), só quem casa. */
export function filtrarPorFases<T extends ItemComFase>(itens: T[], fases: ReadonlySet<FaseToque>): T[] {
  if (fases.size === 0) return itens;
  return itens.filter((it) => !!it.fase && fases.has(it.fase));
}

/** No prazo primeiro; os AINDA NÃO ao final, do que está mais perto de ficar apto para o que está mais longe.
 * Ordenação estável: dentro de cada grupo mantém a ordem recebida (o backend já ordena pelo número). */
export function ordenarNoPrazoPrimeiro<T extends ItemComFase>(itens: T[]): T[] {
  const noPrazo = itens.filter((it) => !it.ainda_nao);
  const ainda = itens.filter((it) => it.ainda_nao).sort((a, b) => (a.dias_para_prazo ?? 0) - (b.dias_para_prazo ?? 0));
  return [...noPrazo, ...ainda];
}

export function textoFaltam(dias: number | null | undefined): string {
  return dias == null ? "" : `faltam ${dias} d`;
}

/** O neon pulsa só quando a hora está chegando (3 dias ou menos); antes disso o contorno dourado é fixo. */
export const DIAS_PULSO_SELO = 3;
export function seloBreve(dias: number | null | undefined): boolean {
  return dias != null && dias <= DIAS_PULSO_SELO;
}

/** Uma linha de legenda explicando de onde vem o prazo, com os números da fazenda. */
export function regraDoPrazo(p: { dias_toque: number; dias_reconfirmacao: number } | null | undefined): string {
  if (!p) return "prazo de Parâmetros (Dias para toque / Dias para reconfirmação)";
  return `Dias para toque ${p.dias_toque} · Dias para reconfirmação ${p.dias_reconfirmacao} (Parâmetros)`;
}
