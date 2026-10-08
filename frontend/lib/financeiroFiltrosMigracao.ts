import { criarFiltroSalvo, fetchFiltrosSalvos, getFazendaAtual } from "@/lib/api";

import { filtroAntigoParaConsultas } from "@/lib/financeiroFiltrosMapa";
type Filtros = Record<string, unknown>;

const ROTULO: Record<string, string> = { pagas: "Contas pagas", recebidas: "Contas recebidas", extrato: "Extrato", todas_contas: "Todas", livro: "Livro caixa" };

/** Uma vez por fazenda e navegador: copia os filtros salvos das telas que viraram Consultas. Nunca apaga os antigos. */
export async function migrarFiltrosSalvosAntigos(): Promise<void> {
  const fazenda = getFazendaAtual()?.id ?? "x";
  const marca = `fin_filtros_migrados_v1_${fazenda}`;
  try {
    if (localStorage.getItem(marca)) return;
    for (const origem of Object.keys(ROTULO) as (keyof typeof ROTULO)[]) {
      const antigos = await fetchFiltrosSalvos(`financeiro_${origem}`);
      for (const f of antigos) {
        await criarFiltroSalvo({
          tela: "financeiro_consultas",
          nome: `${f.nome} (${ROTULO[origem]})`,
          filtros: filtroAntigoParaConsultas(f.filtros as Filtros, origem as "pagas"),
        });
      }
    }
    localStorage.setItem(marca, "1");
  } catch { /* sem rede ou sem permissão: tenta de novo na próxima visita */ }
}
