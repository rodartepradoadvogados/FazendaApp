/**
 * Produção do animal, e de onde ela veio — implementação única.
 *
 * `Animal.ult_cl_kg` é o campo congelado do CSV do Ideagri: seu único ponto
 * de escrita era `parsers/geral.py`, aposentado. Quem lança um controle
 * leiteiro pelo app não vê esse número mudar. `producao_kg` vem ao vivo do
 * ControleLeiteiro mais recente, com `ult_cl_kg` sobrando só como fallback
 * para quem nunca teve controle lançado — e a decisão do produto foi manter
 * o fallback, mas **deixar a origem visível**.
 *
 * Isto vive aqui, e não repetido em cada tela, porque a repetição já
 * divergiu: cinco cópias do mesmo par de funções nasceram com duas
 * semânticas diferentes de `origemDe` no mesmo dia. Uma delas devolvia
 * `null` no fallback puro, e a marca de "dado parado" sumia exatamente
 * para os animais que mais precisam dela.
 */
import type { AnimalProducaoAoVivo, ProducaoOrigem } from "./api";

/** O mínimo que uma tela precisa expor para usar estes helpers. */
export type ComProducao = { ult_cl_kg?: number | null } & Partial<AnimalProducaoAoVivo>;

/** Produção a exibir: a do controle mais recente, senão a congelada. */
export function producaoDe(a: ComProducao): number | null {
  return a.producao_kg ?? a.ult_cl_kg ?? null;
}

/**
 * De onde veio o número que `producaoDe` devolveu.
 *
 * Prefere o que o backend afirma. Sem isso (backend antigo, ou tela lendo um
 * payload que não passa pelo endpoint novo), deduz do próprio caminho do
 * fallback: se o valor exibido saiu de `ult_cl_kg`, ele **é** o campo
 * congelado — não há incerteza a preservar aí, e calar nesse caso é
 * justamente o silêncio que esta etapa veio corrigir.
 */
export function origemDe(a: ComProducao): ProducaoOrigem | null {
  if (a.producao_origem) return a.producao_origem;
  if (a.producao_kg != null) return "controle";
  if (a.ult_cl_kg != null) return "congelado";
  return null;
}

/** Atalho de leitura: o valor exibido não anda mais. */
export function producaoCongelada(a: ComProducao): boolean {
  return origemDe(a) === "congelado";
}
