"use client";
// Ordenação de listas no APP MÓVEL — padrão a seguir nas próximas telas.
//
// CONTEXTO: no site (desktop), listas viram <table> e a ordenação usa
// `useOrdenacao` (components/Ordenavel.tsx) + `<ThOrdenavel>` — clique no
// cabeçalho da coluna. O app móvel não tem tabela nenhuma (é tudo
// cartão/<details>/<div> com `.map()`), então não existe "cabeçalho" pra
// clicar. Este arquivo reaproveita o MOTOR de ordenação do desktop
// (`useOrdenacao`, mesma lógica de comparação numérica/texto, coluna+direção)
// e troca só a APRESENTAÇÃO: em vez de `<th>` clicável, uma barra compacta
// "Ordenar por: [campo ▾] [↑↓]" que fica ACIMA da lista de cartões.
//
// COMO APLICAR EM UMA TELA NOVA (3 passos):
//   1. `const ord = useOrdenacao(minhasLinhas);` (import de "@/components/Ordenavel")
//      — `minhasLinhas` é o array (já filtrado/paginado como preferir) ANTES
//      de ordenar. Ordene por último: filtro → useOrdenacao → paginação.
//   2. Renderize `<SeletorOrdenacao campos={[...]} coluna={ord.coluna}
//      dir={ord.dir} ordenar={ord.ordenar} />` acima da lista.
//      `campos` é a lista de { chave, rotulo } que aparecem no <select> —
//      escolha só os campos que fazem sentido ordenar (data, valor, nome do
//      animal, etc.), não precisa (nem deve) listar todo o objeto.
//   3. Troque o `.map()` da lista de `minhasLinhas` para `ord.linhasOrdenadas`.
//
// IMPORTANTE — a chave de cada campo precisa ser o valor "cru" e comparável:
//   - números: `peso`, `dias_inseminada` (não a string já formatada);
//   - datas: use o campo ISO (`"2026-07-31"`), NÃO a versão já formatada com
//     `formatDate` (`"31/07/2026"`) — comparar string ISO ordena certo,
//     comparar "dd/mm/aaaa" como texto NÃO ordena por data de verdade.
// Se a tela só tem a data formatada à mão, mantenha os dois campos no objeto
// (ex.: `data_iso` cru + `data_fmt` só para exibir) e ordene pelo `data_iso`.
//
// Sem seleção ainda (coluna === null): a lista aparece na ordem que veio da
// API (mesmo comportamentode uma tabela sem clique no cabeçalho) e o botão de
// direção fica desabilitado.
import type { CSSProperties } from "react";
import { ArrowUpWideNarrow, ArrowDownWideNarrow, ArrowUpDown } from "lucide-react";

export type CampoOrdenacao = { chave: string; rotulo: string };

const barra: CSSProperties = {
  display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.8rem", flexWrap: "wrap",
};
const rotuloEstilo: CSSProperties = {
  fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", flexShrink: 0,
};
const selectEstilo: CSSProperties = {
  flex: "1 1 auto", minWidth: "8rem", width: "auto",
  background: "var(--mob-surface)", color: "var(--mob-text)",
  border: "1px solid var(--mob-border)", borderRadius: 12,
  padding: "0.55rem 0.7rem", fontSize: "0.88rem", fontWeight: 600,
};
const botaoDirEstilo = (ativo: boolean): CSSProperties => ({
  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
  width: "2.4rem", height: "2.4rem", borderRadius: 12, cursor: ativo ? "pointer" : "default",
  border: `1px solid ${ativo ? "var(--mob-vinho)" : "var(--mob-border)"}`,
  background: ativo ? "color-mix(in srgb, var(--mob-vinho) 14%, var(--mob-surface))" : "var(--mob-surface)",
  color: ativo ? "var(--mob-vinho)" : "var(--mob-muted)",
  opacity: ativo ? 1 : 0.6,
});

/**
 * Seletor visual de ordenação para listas do app móvel (cartões, não tabela):
 * "Ordenar por: [select de campo] [botão crescente/decrescente]".
 * Motor de ordenação: `useOrdenacao` (components/Ordenavel.tsx) — passe aqui
 * `coluna`, `dir` e `ordenar` exatamente como o hook devolve.
 */
export function SeletorOrdenacao({
  campos, coluna, dir, ordenar, label = "Ordenar por",
}: {
  campos: CampoOrdenacao[];
  coluna: string | null;
  dir: 1 | -1;
  ordenar: (c: string) => void;
  label?: string;
}) {
  if (!campos.length) return null;
  const Icone = coluna == null ? ArrowUpDown : dir === 1 ? ArrowUpWideNarrow : ArrowDownWideNarrow;
  const tituloBotao = coluna == null
    ? "Escolha um campo para ordenar"
    : dir === 1 ? "Crescente — toque para inverter" : "Decrescente — toque para inverter";

  return (
    <div style={barra}>
      <span style={rotuloEstilo}>{label}:</span>
      <select
        className="mob-input"
        style={selectEstilo}
        value={coluna ?? ""}
        onChange={(e) => { if (e.target.value) ordenar(e.target.value); }}
      >
        <option value="">Padrão</option>
        {campos.map((c) => (
          <option key={c.chave} value={c.chave}>{c.rotulo}</option>
        ))}
      </select>
      <button
        type="button"
        aria-label={tituloBotao}
        title={tituloBotao}
        disabled={coluna == null}
        onClick={() => { if (coluna != null) ordenar(coluna); }}
        style={botaoDirEstilo(coluna != null)}
      >
        <Icone size={17} />
      </button>
    </div>
  );
}
