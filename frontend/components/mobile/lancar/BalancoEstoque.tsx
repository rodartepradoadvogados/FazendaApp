"use client";
// Sub-tela LANÇAR ▸ Balanço de estoque — duas abas: Consultar (espelha a
// página Estoque do site: KPIs clicáveis + lista filtrável) e Lançar (entrada
// ou saída de um item, com valor opcional e "gerar lançamento financeiro").
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { MobCard, MobVoltar } from "@/components/mobile/ui";
import { fetchEstoque } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, brl } from "@/components/mobile/menu/comum";
import { LinhaPills, MobPill } from "./comum";
import { FormEstoque } from "./FormEstoque";

type Item = {
  categoria: string | null; nome: string; quantidade: number | null;
  estoque_minimo: number | null; unidade: string | null;
  valor_unitario: number | null; valor_total: number | null; abaixo_minimo: boolean | null;
  principio_ativo: string | null; finalidade: string | null;
};

type Drill = "abaixo" | "categorias" | null;

export default function BalancoEstoque({ onVoltar, onIrParaFinanceiro }: { onVoltar: () => void; onIrParaFinanceiro?: (tipo: "despesa" | "receita") => void }) {
  const [aba, setAba] = useState<"consultar" | "lancar">("consultar");
  const { dados, doCache, carregando } = useCarregar<{ itens: Item[] }>("lancar_balanco_estoque", fetchEstoque);
  const [fCat, setFCat] = useState("");
  const [busca, setBusca] = useState("");
  const [soAbaixo, setSoAbaixo] = useState(false);
  const [drill, setDrill] = useState<Drill>(null);

  const itens = dados?.itens || [];

  const categorias = useMemo(() => {
    const s = new Set<string>();
    itens.forEach((i) => { if (i.categoria) s.add(i.categoria); });
    return Array.from(s).sort();
  }, [itens]);

  const filtrados = useMemo(() => itens.filter((i) =>
    (!fCat || i.categoria === fCat) &&
    (!busca || i.nome.toLowerCase().includes(busca.toLowerCase())) &&
    (!soAbaixo || i.abaixo_minimo === true)
  ), [itens, fCat, busca, soAbaixo]);

  const valorTotal = filtrados.reduce((a, i) => a + (i.valor_total || 0), 0);
  const itensAbaixo = useMemo(() => filtrados.filter((i) => i.abaixo_minimo === true), [filtrados]);

  const categoriasComContagem = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((i) => { const c = i.categoria || "(sem categoria)"; by.set(c, (by.get(c) ?? 0) + 1); });
    return Array.from(by.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtrados]);

  if (aba === "lancar") {
    return (
      <div>
        <MobVoltar titulo="Balanço de estoque" onVoltar={onVoltar} />
        <LinhaPills>
          <MobPill ativa={false} onClick={() => setAba("consultar")}>Consultar</MobPill>
          <MobPill ativa={true} onClick={() => setAba("lancar")}>Lançar</MobPill>
        </LinhaPills>
        <FormEstoque onIrParaFinanceiro={onIrParaFinanceiro} />
      </div>
    );
  }

  // ── Drill-down: abaixo do mínimo ou categorias ──────────────────────────
  if (drill === "abaixo") {
    return (
      <div>
        <MobVoltar titulo="Abaixo do mínimo" onVoltar={() => setDrill(null)} />
        {itensAbaixo.length === 0 ? (
          <Vazio>Nenhum produto abaixo do mínimo no filtro atual.</Vazio>
        ) : itensAbaixo.map((i, idx) => (
          <MobCard key={i.nome} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.92rem" }}>{i.nome}</div>
            <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
              {i.principio_ativo ? `Princípio ativo: ${i.principio_ativo} · ` : ""}{i.finalidade || "—"}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginTop: "0.3rem" }}>
              <span>Saldo: <strong style={{ color: "var(--mob-vermelho)" }}>{i.quantidade ?? "—"} {i.unidade || ""}</strong></span>
              <span style={{ color: "var(--mob-muted)" }}>Mín.: {i.estoque_minimo ?? "—"}</span>
            </div>
          </MobCard>
        ))}
      </div>
    );
  }
  if (drill === "categorias") {
    return (
      <div>
        <MobVoltar titulo="Categorias" onVoltar={() => setDrill(null)} />
        {categoriasComContagem.map(([c, n], idx) => (
          <MobCard key={c} alt={(idx % 2) as 0 | 1} style={{ marginBottom: "0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600, fontSize: "0.92rem" }}>{c}</span>
            <span style={{ fontWeight: 800, color: "var(--mob-dourado-2)" }}>{n}</span>
          </MobCard>
        ))}
      </div>
    );
  }

  return (
    <div>
      <MobVoltar titulo="Balanço de estoque" onVoltar={onVoltar} />
      <LinhaPills>
        <MobPill ativa={true} onClick={() => setAba("consultar")}>Consultar</MobPill>
        <MobPill ativa={false} onClick={() => setAba("lancar")}>Lançar</MobPill>
      </LinhaPills>
      <AvisoCopia chave="lancar_balanco_estoque" mostrar={doCache} />

      <div style={{ position: "relative", marginBottom: "0.7rem" }}>
        <Search size={18} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar produto…" style={{ paddingLeft: "2.5rem" }} />
      </div>

      {categorias.length > 0 && (
        <select className="mob-input" value={fCat} onChange={(e) => setFCat(e.target.value)} style={{ marginBottom: "0.7rem" }}>
          <option value="">Todas as categorias</option>
          {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      )}

      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", marginBottom: "0.9rem" }}>
        <input type="checkbox" checked={soAbaixo} onChange={(e) => setSoAbaixo(e.target.checked)} style={{ width: 18, height: 18 }} />
        Só abaixo do mínimo
      </label>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", marginBottom: "0.9rem" }}>
            <MobCard style={{ textAlign: "center", padding: "0.8rem 0.4rem" }}>
              <div style={{ fontSize: "1.05rem", fontWeight: 800 }}>{brl(valorTotal)}</div>
              <div style={{ fontSize: "0.68rem", color: "var(--mob-muted)", fontWeight: 700 }}>Valor total</div>
            </MobCard>
            <button type="button" className="mob-card" style={{ textAlign: "center", padding: "0.8rem 0.4rem", cursor: "pointer", border: "1px solid var(--mob-border)" }} onClick={() => setDrill("abaixo")}>
              <div style={{ fontSize: "1.2rem", fontWeight: 800, color: itensAbaixo.length ? "var(--mob-vermelho)" : "var(--mob-text)" }}>{itensAbaixo.length}</div>
              <div style={{ fontSize: "0.68rem", color: "var(--mob-muted)", fontWeight: 700 }}>Abaixo do mínimo</div>
            </button>
            <button type="button" className="mob-card" style={{ textAlign: "center", padding: "0.8rem 0.4rem", cursor: "pointer", border: "1px solid var(--mob-border)" }} onClick={() => setDrill("categorias")}>
              <div style={{ fontSize: "1.2rem", fontWeight: 800 }}>{categoriasComContagem.length}</div>
              <div style={{ fontSize: "0.68rem", color: "var(--mob-muted)", fontWeight: 700 }}>Categorias</div>
            </button>
          </div>

          {filtrados.length === 0 ? (
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
