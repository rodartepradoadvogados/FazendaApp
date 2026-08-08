"use client";
// Etapa 1, "Importar do cadastro" — lista os Alimentos já cadastrados na
// fazenda (tela normal de Alimentação) e resolve cada um escolhido em cascata
// biblioteca → análise bromatológica → template (GET /alimentos/{id}/resolver).
import { useEffect, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { AlimentoCadastradoResumo, ItemGrade, itemGradeDeResolucao, listarAlimentos, resolverAlimento } from "@/lib/dietas";

export function ImportarAlimentoModal({
  onFechar, onImportar,
}: {
  onFechar: () => void; onImportar: (itens: ItemGrade[]) => void;
}) {
  const [busca, setBusca] = useState("");
  const [cadastrados, setCadastrados] = useState<AlimentoCadastradoResumo[] | null>(null);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [importando, setImportando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      listarAlimentos(busca).then((r) => setCadastrados(r.cadastrados)).catch((e) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [busca]);

  function alternar(id: number) {
    setSelecionados((prev) => {
      const novo = new Set(prev);
      if (novo.has(id)) novo.delete(id); else novo.add(id);
      return novo;
    });
  }

  async function confirmar() {
    if (selecionados.size === 0) return;
    setImportando(true);
    setErro(null);
    try {
      const itens: ItemGrade[] = [];
      for (const id of selecionados) {
        const r = await resolverAlimento(id);
        itens.push(itemGradeDeResolucao(id, r));
      }
      onImportar(itens);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setImportando(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--overlay)" }} onClick={onFechar}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: "min(34rem, 92vw)", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
        <h3 style={{ margin: "0 0 0.8rem", fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>Importar do cadastro</h3>

        <div style={{ position: "relative", marginBottom: "0.7rem" }}>
          <Search size={14} style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar alimento…"
            style={{ width: "100%", padding: "0.45rem 0.6rem 0.45rem 2rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}
          />
        </div>

        <div style={{ overflowY: "auto", flex: 1, border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
          {cadastrados === null && <p style={{ padding: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>}
          {cadastrados !== null && cadastrados.length === 0 && <p style={{ padding: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum alimento cadastrado com esse termo.</p>}
          {cadastrados?.map((a) => (
            <label key={a.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)", cursor: "pointer", fontSize: "0.85rem" }}>
              <input type="checkbox" checked={selecionados.has(a.id)} onChange={() => alternar(a.id)} />
              <span style={{ flex: 1, color: "var(--text)" }}>{a.nome}</span>
              {a.sem_composicao && (
                <span title="Ainda não tem composição nutricional cadastrada — usará o template da categoria" style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem", color: "var(--amber)" }}>
                  <AlertTriangle size={12} /> sem composição
                </span>
              )}
            </label>
          ))}
        </div>

        {erro && <div className="alert-critico" style={{ marginTop: "0.6rem" }}>{erro}</div>}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.9rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{selecionados.size} selecionado(s)</span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
            <button type="button" className="btn-primary-gold" disabled={selecionados.size === 0 || importando} onClick={confirmar}>
              {importando ? "Importando…" : "Importar selecionados"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
