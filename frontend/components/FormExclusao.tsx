"use client";
import { useEffect, useState } from "react";
import { Search, Trash2, AlertTriangle, X, Check } from "lucide-react";
import { fetchTiposExclusao, buscarExclusao, impactoExclusao, confirmarExclusao } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};

type Candidato = { id: string; titulo: string; subtitulo: string };
type Tipo = { id: string; label: string };

/**
 * Aba de Exclusão: escolhe o tipo de registro, busca e seleciona o alvo, e
 * antes de excluir mostra tudo o que será impactado — só então confirma.
 */
export function FormExclusao() {
  const [tipos, setTipos] = useState<Tipo[]>([]);
  const [tipo, setTipo] = useState("");
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState<Candidato[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [alvo, setAlvo] = useState<Candidato | null>(null);
  const [impacto, setImpacto] = useState<string[] | null>(null);
  const [carregandoImpacto, setCarregandoImpacto] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  useEffect(() => { fetchTiposExclusao().then(setTipos).catch(() => {}); }, []);

  const buscar = async (t: string, q: string) => {
    if (!t) { setResultados([]); return; }
    setBuscando(true); setErro(null);
    try { setResultados(await buscarExclusao(t, q)); }
    catch (e: any) { setErro(e.message); }
    finally { setBuscando(false); }
  };

  useEffect(() => {
    if (!tipo) return;
    const h = setTimeout(() => buscar(tipo, termo), 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo, termo]);

  const escolher = async (c: Candidato) => {
    setAlvo(c); setImpacto(null); setErro(null); setMsg(null); setCarregandoImpacto(true);
    try { setImpacto((await impactoExclusao(tipo, String(c.id))).impacto); }
    catch (e: any) { setErro(e.message); setAlvo(null); }
    finally { setCarregandoImpacto(false); }
  };

  const excluir = async () => {
    if (!alvo) return;
    setExcluindo(true); setErro(null);
    try {
      await confirmarExclusao(tipo, String(alvo.id));
      setMsg(`Excluído: ${alvo.titulo}`);
      setAlvo(null); setImpacto(null);
      buscar(tipo, termo);
    } catch (e: any) { setErro(e.message); }
    finally { setExcluindo(false); }
  };

  return (
    <>
      <div className="alert-critico mb-3" style={{ alignItems: "flex-start" }}>
        <AlertTriangle size={16} style={{ marginTop: "0.1rem", flexShrink: 0 }} />
        <span>Exclusão é permanente e restrita a administradores. Escolha o tipo, encontre o registro e confira o impacto antes de confirmar.</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Tipo de lançamento</label>
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value); setTermo(""); setAlvo(null); setImpacto(null); }}>
            <option value="">Selecione…</option>
            {tipos.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
        {tipo && (
          <div>
            <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Buscar</label>
            <div style={{ position: "relative" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input style={{ ...inputStyle, paddingLeft: "2rem" }} value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="número, nome, descrição…" />
            </div>
          </div>
        )}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {msg && <p style={{ color: "var(--green-light)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{msg}</p>}

      {tipo && (
        <div className="card" style={{ padding: 0 }}>
          <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Registro</th><th></th></tr></thead>
              <tbody>
                {resultados.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>{c.titulo}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.subtitulo}</div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.75rem" }} onClick={() => escolher(c)}>
                        <Trash2 size={13} /> Excluir
                      </button>
                    </td>
                  </tr>
                ))}
                {!buscando && !resultados.length && (
                  <tr><td colSpan={2} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum registro encontrado.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {alvo && (
        <div onClick={() => { setAlvo(null); setImpacto(null); }} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "460px", maxWidth: "95vw" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0, color: "var(--red)" }}>Confirmar exclusão</div>
              <button onClick={() => { setAlvo(null); setImpacto(null); }} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>{alvo.titulo}</p>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Isto vai excluir permanentemente:</p>
            {carregandoImpacto ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Calculando impacto…</p>
            ) : (
              <ul style={{ fontSize: "0.82rem", paddingLeft: "1.1rem", marginBottom: "0.8rem" }}>
                {(impacto || []).map((i, idx) => <li key={idx} style={{ marginBottom: "0.2rem" }}>{i}</li>)}
              </ul>
            )}
            {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
            <div className="flex items-center gap-3">
              <button className="btn-primary" style={{ background: "var(--red)" }} onClick={excluir} disabled={excluindo || carregandoImpacto}>
                <Check size={14} /> {excluindo ? "Excluindo…" : "Confirmar exclusão"}
              </button>
              <button className="btn-ghost" onClick={() => { setAlvo(null); setImpacto(null); }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
