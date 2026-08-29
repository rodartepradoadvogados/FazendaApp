"use client";
// Menu ▸ Estoque — pílulas Alimentação / Medicamentos / Sêmen / Outros. As 3
// primeiras filtram Estoque (Estoque.finalidade), só leitura; "Outros" pega
// o que sobra (Material/Insumo, Equipamento, Outro ou sem finalidade). Sêmen
// mostra o Estoque de Sêmen (touros com doses, com botão excluir) e, como
// segunda pílula interna, o catálogo NAAB (banco de dados de touros, só leitura).
import { useMemo, useState } from "react";
import { Search, Warehouse, Database, Trash2, Wheat, Pill, Dna, Package } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { LinhaPills, MobPill, GradeAcoes } from "@/components/mobile/lancar/comum";
import { fetchEstoque, fetchEstoqueSemen, fetchTouros, excluirEstoqueSemen, type Touro } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, brl, usePaginacao, PaginacaoMob } from "@/components/mobile/menu/comum";
import { casaBusca } from "@/lib/busca";

type ItemEstoque = {
  nome: string; categoria: string | null; finalidade: string | null; quantidade: number | null;
  estoque_minimo: number | null; unidade: string | null; valor_unitario: number | null; valor_total: number | null;
  abaixo_minimo: boolean | null;
};
type ItemSemen = {
  id: number; touro_nome: string; codigo?: string | null; naab?: string | null; central?: string | null;
  tipo: string; doses: number; valor_unitario?: number | null;
};

// "Ração/Alimento" é a finalidade padrão, mas a finalidade de Estoque é
// cadastro livre (Configurações > Cadastro > Estoque > Finalidade) — uma
// fazenda pode ter cadastrado o alimento com finalidade própria (ex.:
// "Nutrição"). Um filtro por igualdade exata escondia esses itens da pílula
// Alimentação (produto existia, mas "não há" na busca) — mesmo bug já
// corrigido no seletor de estoque de Alimentos, no picker de Nova dieta
// (site) e em Lançar Dieta (app); ver `_finalidade_indica_alimento` no
// backend (fazenda/api/routers/alimentacao.py) e o critério idêntico em
// LancarDieta.tsx. Vira lista de EXCLUSÃO por termo, não de permissão por
// valor exato — cobre "Ração/Alimento" e qualquer variação customizada.
const TERMOS_ALIMENTACAO = ["aliment", "nutri", "racao"];
function ehFinalidadeAlimentacao(finalidade: string | null): boolean {
  return !!finalidade && TERMOS_ALIMENTACAO.some((t) => casaBusca(finalidade, t));
}
type CategoriaChave = "alimentacao" | "medicamentos" | "semen" | "outros";

const ROTULOS_CATEGORIA: Record<CategoriaChave, string> = {
  alimentacao: "Alimentação", medicamentos: "Medicamentos", semen: "Sêmen", outros: "Outros",
};

export default function Estoque({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<CategoriaChave | null>(null);
  const { dados, doCache, carregando } = useCarregar<{ itens: ItemEstoque[] }>("menu_estoque", fetchEstoque);
  const [busca, setBusca] = useState("");
  // Dois filtros independentes de saldo: positivo/negativo e abaixo do mínimo
  // — mesma ideia do Balanço de estoque (Lançar) e do filtro do site.
  const [filtroSaldo, setFiltroSaldo] = useState<"todos" | "positivo" | "negativo">("todos");
  const [soAbaixo, setSoAbaixo] = useState(false);

  const itens = dados?.itens || [];

  const filtrados = useMemo(() => {
    let base: ItemEstoque[];
    if (aba === "alimentacao") {
      base = itens.filter((i) => ehFinalidadeAlimentacao(i.finalidade));
    } else if (aba === "medicamentos") {
      base = itens.filter((i) => (i.finalidade || "") === "Medicamento");
    } else if (aba === "outros") {
      base = itens.filter((i) => !ehFinalidadeAlimentacao(i.finalidade) && (i.finalidade || "") !== "Medicamento");
    } else {
      base = [];
    }
    return base
      .filter((i) => casaBusca(i.nome, busca))
      .filter((i) => filtroSaldo === "todos" || (filtroSaldo === "positivo" ? (i.quantidade ?? 0) > 0 : (i.quantidade ?? 0) <= 0))
      .filter((i) => !soAbaixo || i.abaixo_minimo === true);
  }, [itens, aba, busca, filtroSaldo, soAbaixo]);

  if (!aba) {
    return (
      <div>
        <MobVoltar titulo="Estoque" onVoltar={onVoltar} />
        <GradeAcoes
          opcoes={[
            { id: "alimentacao", label: "Alimentação", icone: <Wheat size={28} />, cor: "var(--mob-laranja)" },
            { id: "medicamentos", label: "Medicamentos", icone: <Pill size={28} />, cor: "var(--mob-azul)" },
            { id: "semen", label: "Sêmen", icone: <Dna size={28} />, cor: "var(--mob-roxo)" },
            { id: "outros", label: "Outros", icone: <Package size={28} />, cor: "var(--mob-amarelo)" },
          ]}
          onEscolher={(id) => setAba(id as CategoriaChave)}
        />
      </div>
    );
  }

  return (
    <div>
      <MobVoltar titulo={ROTULOS_CATEGORIA[aba]} onVoltar={() => { setAba(null); setBusca(""); }} />

      {aba === "semen" ? (
        <SemenView />
      ) : (
        <>
          <AvisoCopia chave="menu_estoque" mostrar={doCache} />
          <div style={{ position: "relative", marginBottom: "0.9rem" }}>
            <Search size={18} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
            <input className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar produto…" style={{ paddingLeft: "2.5rem" }} />
          </div>

          <LinhaPills>
            <MobPill ativa={filtroSaldo === "todos"} onClick={() => setFiltroSaldo("todos")}>Todos</MobPill>
            <MobPill ativa={filtroSaldo === "positivo"} onClick={() => setFiltroSaldo("positivo")}>Saldo positivo</MobPill>
            <MobPill ativa={filtroSaldo === "negativo"} onClick={() => setFiltroSaldo("negativo")}>Saldo negativo</MobPill>
          </LinhaPills>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", margin: "0.6rem 0 0.9rem" }}>
            <input type="checkbox" checked={soAbaixo} onChange={(e) => setSoAbaixo(e.target.checked)} style={{ width: 18, height: 18 }} />
            Só abaixo do mínimo
          </label>

          {carregando && !dados ? (
            <Carregando />
          ) : !dados ? (
            <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
          ) : filtrados.length === 0 ? (
            <Vazio>Nenhum produto encontrado nesse filtro.</Vazio>
          ) : (
            filtrados.map((i, idx) => (
              <MobCard key={i.nome} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.nome}</span>
                  <strong style={{ whiteSpace: "nowrap" }}>{brl(i.valor_total)}</strong>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>{i.categoria || "(sem categoria)"}</div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginTop: "0.3rem" }}>
                  <span>Saldo: <strong style={{ color: i.abaixo_minimo ? "var(--mob-vermelho)" : "var(--mob-verde)" }}>{i.quantidade ?? "—"} {i.unidade || ""}</strong></span>
                  <span style={{ color: "var(--mob-muted)" }}>Mín.: {i.estoque_minimo ?? "—"}</span>
                </div>
              </MobCard>
            ))
          )}
        </>
      )}
    </div>
  );
}

/** Pílula "Sêmen": touros em estoque (doses cadastradas) × banco de dados
 * NAAB — mesma dupla fonte do site (Rebanho > Touros), só leitura. */
function SemenView() {
  const [origem, setOrigem] = useState<"estoque" | "naab">("estoque");
  const estoqueReq = useCarregar<ItemSemen[]>("menu_estoque_semen", fetchEstoqueSemen);
  const naabReq = useCarregar<Touro[]>("menu_touros_naab", fetchTouros);
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState("");

  const emEstoque = useMemo(
    () => (estoqueReq.dados || []).filter((e) => e.tipo !== "fazenda"),
    [estoqueReq.dados],
  );
  const estoqueFiltrado = useMemo(
    () => emEstoque.filter((e) => casaBusca(`${e.touro_nome} ${e.codigo || ""} ${e.naab || ""} ${e.central || ""}`, busca)),
    [emEstoque, busca],
  );
  const naabFiltrado = useMemo(() => {
    const base = naabReq.dados || [];
    return base.filter((t) => casaBusca(`${t.nome || ""} ${t.naab} ${t.central || ""} ${t.raca || ""}`, busca));
  }, [naabReq.dados, busca]);
  const pagNaab = usePaginacao(naabFiltrado);

  async function excluir(e: ItemSemen) {
    if (!window.confirm(`Excluir "${e.touro_nome}" do estoque de sêmen?`)) return;
    setErro("");
    try {
      await excluirEstoqueSemen(e.id);
      estoqueReq.recarregar();
    } catch (err: any) {
      setErro(err.message || "Erro ao excluir sêmen do estoque");
    }
  }

  return (
    <div>
      <LinhaPills>
        <MobPill ativa={origem === "estoque"} onClick={() => { setOrigem("estoque"); setBusca(""); }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}><Warehouse size={14} /> Em estoque</span>
        </MobPill>
        <MobPill ativa={origem === "naab"} onClick={() => { setOrigem("naab"); setBusca(""); }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}><Database size={14} /> Banco NAAB</span>
        </MobPill>
      </LinhaPills>

      <div style={{ position: "relative", marginBottom: "0.9rem" }}>
        <Search size={18} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)}
          placeholder={origem === "estoque" ? "Buscar touro, código, NAAB…" : "Buscar touro, NAAB, central, raça…"} style={{ paddingLeft: "2.5rem" }} />
      </div>

      {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}

      {origem === "estoque" ? (
        <>
          <AvisoCopia chave="menu_estoque_semen" mostrar={estoqueReq.doCache} />
          {estoqueReq.carregando && !estoqueReq.dados ? (
            <Carregando />
          ) : !estoqueReq.dados ? (
            <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
          ) : estoqueFiltrado.length === 0 ? (
            <Vazio>Nenhum touro em estoque encontrado.</Vazio>
          ) : (
            estoqueFiltrado.map((e, idx) => (
              <MobCard key={e.id} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{e.touro_nome}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>{e.doses} dose{e.doses !== 1 ? "s" : ""}</span>
                    <button type="button" onClick={() => excluir(e)} aria-label="Excluir do estoque"
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--mob-vermelho)", padding: 0, display: "flex" }}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  {e.naab ? `NAAB ${e.naab} · ` : ""}{e.central || "—"} · <span style={{ textTransform: "capitalize" }}>{e.tipo}</span>
                </div>
              </MobCard>
            ))
          )}
        </>
      ) : (
        <>
          <AvisoCopia chave="menu_touros_naab" mostrar={naabReq.doCache} />
          {naabReq.carregando && !naabReq.dados ? (
            <Carregando />
          ) : !naabReq.dados ? (
            <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
          ) : naabFiltrado.length === 0 ? (
            <Vazio>Nenhum touro do catálogo NAAB encontrado.</Vazio>
          ) : (
            pagNaab.linhasPagina.map((t, idx) => (
              <MobCard key={t.id ?? t.naab} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{t.nome || t.naab}</span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-dourado-2)" }}>TPI {t.tpi ?? "—"}</span>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  NAAB {t.naab} · {t.central || "—"} · {t.raca || "—"}
                </div>
              </MobCard>
            ))
          )}
          {naabReq.dados && (
            <PaginacaoMob pagina={pagNaab.pagina} totalPaginas={pagNaab.totalPaginas} totalLinhas={pagNaab.totalLinhas} onMudarPagina={pagNaab.setPagina} />
          )}
        </>
      )}
    </div>
  );
}
