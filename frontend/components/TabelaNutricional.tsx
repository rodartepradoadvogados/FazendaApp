"use client";
// Tabela nutricional dos alimentos (referência do veterinário) — abre num modal
// suspenso, com uma calculadora ao lado que aceita o teclado numérico do
// computador. Botão reutilizável: <TabelaNutricionalBotao />.
import { useEffect, useMemo, useState } from "react";
import { X, Table2, Search } from "lucide-react";
import { fetchTabelaNutricional } from "@/lib/api";

type Dados = { alimentos: string[]; linhas: string[][] };

// ── Calculadora simples (aceita teclado numérico físico) ──
function Calculadora() {
  const [expr, setExpr] = useState("");
  const [res, setRes] = useState<string | null>(null);

  function press(ch: string) {
    setRes(null);
    if (ch === "C") { setExpr(""); return; }
    if (ch === "←") { setExpr((e) => e.slice(0, -1)); return; }
    if (ch === "=") { calcular(); return; }
    setExpr((e) => e + ch);
  }
  function calcular() {
    try {
      const limpo = expr.replace(/,/g, ".").replace(/[^0-9+\-*/.() ]/g, "");
      if (!limpo.trim()) return;
      // Avaliação restrita a uma expressão aritmética já filtrada.
      // eslint-disable-next-line no-new-func
      const v = Function(`"use strict"; return (${limpo})`)();
      setRes(typeof v === "number" && isFinite(v) ? String(Math.round(v * 10000) / 10000) : "erro");
    } catch { setRes("erro"); }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key;
      if (/[0-9]/.test(k) || ["+", "-", "*", "/", ".", "(", ")"].includes(k)) { press(k); e.preventDefault(); }
      else if (k === "," ) { press("."); e.preventDefault(); }
      else if (k === "Enter" || k === "=") { press("="); e.preventDefault(); }
      else if (k === "Backspace") { press("←"); e.preventDefault(); }
      else if (k === "Escape") { /* fecha o modal — tratado fora */ }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expr]);

  const btn: React.CSSProperties = { padding: "0.7rem 0", fontSize: "1.05rem", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", cursor: "pointer", fontWeight: 600 };
  const teclas = ["7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "0", ".", "=", "+"];

  return (
    <div style={{ width: 220, flexShrink: 0 }}>
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Calculadora (use o teclado numérico)</div>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem", minHeight: "3.2rem", marginBottom: "0.5rem", textAlign: "right" }}>
        <div style={{ fontSize: "0.9rem", color: "var(--text-muted)", wordBreak: "break-all" }}>{expr || "0"}</div>
        {res != null && <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--dourado-light)" }}>= {res}</div>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem" }}>
        <button style={{ ...btn, gridColumn: "span 2", color: "var(--red)" }} onClick={() => press("C")}>C</button>
        <button style={btn} onClick={() => press("←")}>←</button>
        <button style={btn} onClick={() => press("(")}>(</button>
        {teclas.map((t) => (
          <button key={t} style={t === "=" ? { ...btn, background: "var(--dourado)", color: "#1a1205", fontWeight: 800 } : btn} onClick={() => press(t)}>{t}</button>
        ))}
        <button style={{ ...btn, gridColumn: "span 4" }} onClick={() => press(")")}>)</button>
      </div>
    </div>
  );
}

export function TabelaNutricionalBotao({ estilo }: { estilo?: React.CSSProperties }) {
  const [aberto, setAberto] = useState(false);
  const [dados, setDados] = useState<Dados | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    if (aberto && !dados) fetchTabelaNutricional().then(setDados).catch(() => setDados({ alimentos: [], linhas: [] }));
  }, [aberto, dados]);

  useEffect(() => {
    if (!aberto) return;
    function onEsc(e: KeyboardEvent) { if (e.key === "Escape") setAberto(false); }
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [aberto]);

  const linhasFiltradas = useMemo(() => {
    if (!dados) return [];
    const q = busca.trim().toLowerCase();
    return q ? dados.linhas.filter((l) => (l[0] || "").toLowerCase().includes(q)) : dados.linhas;
  }, [dados, busca]);

  return (
    <>
      <button className="btn-ghost" style={{ fontSize: "0.8rem", display: "inline-flex", alignItems: "center", gap: "0.4rem", ...estilo }} onClick={() => setAberto(true)}>
        <Table2 size={15} /> Tabela nutricional
      </button>

      {aberto && (
        <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: "1100px", width: "100%", maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div className="card-header flex items-center justify-between" style={{ marginBottom: "0.6rem" }}>
              <span className="flex items-center gap-2"><Table2 size={16} /> Tabela nutricional dos alimentos</span>
              <button className="btn-ghost" onClick={() => setAberto(false)}><X size={16} /></button>
            </div>
            <div className="flex gap-4" style={{ minHeight: 0, flex: 1 }}>
              <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                <div style={{ position: "relative", marginBottom: "0.5rem", maxWidth: 320 }}>
                  <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar nutriente…"
                    style={{ width: "100%", padding: "0.4rem 0.5rem 0.4rem 1.8rem", borderRadius: 6, fontSize: "0.82rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
                </div>
                <div style={{ overflow: "auto", flex: 1 }}>
                  {!dados ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
                    <table className="fazenda-table" style={{ fontSize: "0.76rem" }}>
                      <thead><tr>
                        <th style={{ position: "sticky", top: 0, background: "var(--surface-2)" }}>Nutriente</th>
                        {dados.alimentos.map((a) => <th key={a} style={{ position: "sticky", top: 0, background: "var(--surface-2)" }}>{a}</th>)}
                      </tr></thead>
                      <tbody>
                        {linhasFiltradas.map((l, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 700 }}>{l[0]}</td>
                            {l.slice(1).map((c, j) => <td key={j}>{c || "—"}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
              <Calculadora />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
