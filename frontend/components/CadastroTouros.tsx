"use client";
import { useEffect, useMemo, useState } from "react";
import { Dna, Trash2, Search, RefreshCw } from "lucide-react";
import { fetchTouros, excluirTouro, type Touro } from "@/lib/api";

const fmt = (v?: number | null, dec = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });

export default function CadastroTouros() {
  const [touros, setTouros] = useState<Touro[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");

  async function carregar() {
    setCarregando(true);
    setErro("");
    try {
      setTouros(await fetchTouros());
    } catch (e: any) {
      setErro(e.message || "Falha ao carregar touros");
    } finally {
      setCarregando(false);
    }
  }
  useEffect(() => { carregar(); }, []);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return touros;
    return touros.filter((t) =>
      (t.naab || "").toLowerCase().includes(q) ||
      (t.nome || "").toLowerCase().includes(q) ||
      (t.central || "").toLowerCase().includes(q) ||
      (t.raca || "").toLowerCase().includes(q));
  }, [touros, busca]);

  async function remover(t: Touro) {
    if (!t.id) return;
    if (!confirm(`Excluir o touro ${t.naab}${t.nome ? " — " + t.nome : ""}?`)) return;
    try {
      await excluirTouro(t.id);
      setTouros((prev) => prev.filter((x) => x.id !== t.id));
    } catch (e: any) {
      alert(e.message || "Falha ao excluir");
    }
  }

  const th: React.CSSProperties = { textAlign: "left", padding: "0.5rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.03em", color: "var(--text-muted)", whiteSpace: "nowrap", borderBottom: "1px solid var(--border)" };
  const td: React.CSSProperties = { padding: "0.45rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-3">
        <h2 className="text-lg font-bold flex items-center gap-2"><Dna size={18} style={{ color: "var(--dourado)" }} /> Touros (NAAB)</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
          Banco de touros importado do catálogo do fornecedor (código NAAB, central e provas genéticas). A importação é feita em
          Configurações › Importar dados › Touros (NAAB), e é lembrada na Agenda a cada 3 meses.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 16rem", maxWidth: "22rem" }}>
          <Search size={15} style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por NAAB, nome, central ou raça..."
            style={{ width: "100%", padding: "0.5rem 0.6rem 0.5rem 2rem", borderRadius: "8px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
        </div>
        <button onClick={carregar} className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <RefreshCw size={14} /> Atualizar
        </button>
        <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{filtrados.length} touro(s)</span>
      </div>

      {erro && <p style={{ color: "var(--vermelho, #d33)", fontSize: "0.85rem" }}>{erro}</p>}
      {carregando ? (
        <p style={{ color: "var(--text-muted)" }}>Carregando...</p>
      ) : filtrados.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
          Nenhum touro cadastrado ainda. Importe o catálogo em Configurações › Importar dados › Touros (NAAB).
        </p>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "10px" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "56rem" }}>
            <thead>
              <tr>
                <th style={th}>NAAB</th>
                <th style={th}>Nome</th>
                <th style={th}>Central</th>
                <th style={th}>Raça</th>
                <th style={{ ...th, textAlign: "right" }}>Leite (kg)</th>
                <th style={{ ...th, textAlign: "right" }}>Gord.</th>
                <th style={{ ...th, textAlign: "right" }}>Prot.</th>
                <th style={{ ...th, textAlign: "right" }}>TPI</th>
                <th style={{ ...th, textAlign: "right" }}>NM$</th>
                <th style={{ ...th, textAlign: "right" }}>Fert. filhas</th>
                <th style={{ ...th, textAlign: "right" }}>Fac. parto</th>
                <th style={th}>Fonte / rodada</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((t) => (
                <tr key={t.id}>
                  <td style={{ ...td, fontWeight: 700, color: "var(--dourado-light)" }}>{t.naab}</td>
                  <td style={td}>{t.nome || "—"}</td>
                  <td style={td}>{t.central || "—"}</td>
                  <td style={td}>{t.raca || "—"}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(t.leite_kg)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(t.gordura_kg)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(t.proteina_kg)}</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 600 }}>{fmt(t.tpi)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{t.nm_dolar == null ? "—" : `$${fmt(t.nm_dolar)}`}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(t.fertilidade_filhas, 1)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(t.facilidade_parto, 1)}</td>
                  <td style={{ ...td, fontSize: "0.74rem", color: "var(--text-muted)" }}>{[t.fonte, t.rodada_prova].filter(Boolean).join(" · ") || "—"}</td>
                  <td style={{ ...td, textAlign: "right" }}>
                    <button onClick={() => remover(t)} title="Excluir touro"
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
