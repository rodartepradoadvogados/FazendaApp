"use client";
import { useEffect, useState } from "react";
import { Search, Trash2, AlertTriangle, X, Check, Clock, ThumbsUp, ThumbsDown } from "lucide-react";
import {
  fetchTiposExclusao, buscarExclusao, impactoExclusao, confirmarExclusao,
  fetchPendentesExclusao, aprovarExclusao, rejeitarExclusao, ehAdmin, formatDate,
} from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};

type Candidato = { id: string; titulo: string; subtitulo: string };
type Tipo = { id: string; label: string };
type Pendente = { id: number; tipo: string; id_alvo: string; titulo: string | null; solicitado_por: string | null; criado_em: string };

/**
 * Aba de Exclusão: escolhe o tipo de registro, busca e seleciona o alvo, e
 * antes de excluir mostra tudo o que será impactado — só então confirma.
 * Administradores excluem na hora; os demais usuários só registram uma
 * solicitação, que fica pendente de aprovação (ver painel abaixo, admin-only).
 */
export function FormExclusao() {
  const [tipos, setTipos] = useState<Tipo[]>([]);
  const [tipo, setTipo] = useState("");
  const [termo, setTermo] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [resultados, setResultados] = useState<Candidato[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [alvo, setAlvo] = useState<Candidato | null>(null);
  const [impacto, setImpacto] = useState<string[] | null>(null);
  const [carregandoImpacto, setCarregandoImpacto] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  const [souAdmin, setSouAdmin] = useState(false);
  const [pendentes, setPendentes] = useState<Pendente[] | null>(null);
  const [decidindo, setDecidindo] = useState<number | null>(null);

  const carregarPendentes = () => {
    if (!ehAdmin()) return;
    fetchPendentesExclusao().then(setPendentes).catch(() => {});
  };
  useEffect(() => {
    setSouAdmin(ehAdmin());
    carregarPendentes();
  }, []);

  const aprovar = async (id: number) => {
    setDecidindo(id);
    try { await aprovarExclusao(id); carregarPendentes(); }
    catch (e: any) { setErro(e.message); }
    finally { setDecidindo(null); }
  };
  const rejeitar = async (id: number) => {
    setDecidindo(id);
    try { await rejeitarExclusao(id); carregarPendentes(); }
    catch (e: any) { setErro(e.message); }
    finally { setDecidindo(null); }
  };

  useEffect(() => { fetchTiposExclusao().then(setTipos).catch(() => {}); }, []);

  const TIPOS_SEM_DATA = new Set(["animal", "estoque"]);
  const temFiltroData = tipo && !TIPOS_SEM_DATA.has(tipo);

  const buscar = async (t: string, q: string, ini: string, fim: string) => {
    if (!t) { setResultados([]); return; }
    setBuscando(true); setErro(null);
    try { setResultados(await buscarExclusao(t, q, TIPOS_SEM_DATA.has(t) ? "" : ini, TIPOS_SEM_DATA.has(t) ? "" : fim)); }
    catch (e: any) { setErro(e.message); }
    finally { setBuscando(false); }
  };

  useEffect(() => {
    if (!tipo) return;
    const h = setTimeout(() => buscar(tipo, termo, dataInicio, dataFim), 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo, termo, dataInicio, dataFim]);

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
      const r = await confirmarExclusao(tipo, String(alvo.id));
      setMsg(r.status === "excluido" ? `Excluído: ${alvo.titulo}` : `Solicitação enviada: ${alvo.titulo}. Aguarda aprovação de um administrador.`);
      setAlvo(null); setImpacto(null);
      buscar(tipo, termo, dataInicio, dataFim);
    } catch (e: any) { setErro(e.message); }
    finally { setExcluindo(false); }
  };

  return (
    <>
      <div className="alert-critico mb-3" style={{ alignItems: "flex-start" }}>
        <AlertTriangle size={16} style={{ marginTop: "0.1rem", flexShrink: 0 }} />
        <span>
          {souAdmin
            ? "Exclusão é permanente. Escolha o tipo, encontre o registro e confira o impacto antes de confirmar."
            : "Escolha o tipo, encontre o registro e confira o impacto — a exclusão fica pendente de aprovação de um administrador."}
        </span>
      </div>

      {souAdmin && (
        <div className="card mb-3">
          <div className="card-header mb-2 flex items-center gap-2"><Clock size={14} /> Pendências de exclusão {pendentes ? `(${pendentes.length})` : ""}</div>
          {!pendentes?.length ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhuma solicitação pendente.</p>
          ) : (
            <div className="space-y-2">
              {pendentes.map((p) => (
                <div key={p.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", padding: "0.5rem 0.7rem", border: "1px solid var(--border)", borderRadius: "8px" }}>
                  <div>
                    <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>{p.titulo || `${p.tipo} #${p.id_alvo}`}</div>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      Solicitado por {p.solicitado_por || "—"} em {formatDate(p.criado_em.slice(0, 10))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="btn-primary" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      onClick={() => aprovar(p.id)} disabled={decidindo === p.id}>
                      <ThumbsUp size={13} /> Aprovar
                    </button>
                    <button className="btn-ghost" style={{ fontSize: "0.75rem", color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      onClick={() => rejeitar(p.id)} disabled={decidindo === p.id}>
                      <ThumbsDown size={13} /> Rejeitar
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Tipo de lançamento</label>
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value); setTermo(""); setDataInicio(""); setDataFim(""); setAlvo(null); setImpacto(null); }}>
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
        {temFiltroData && (
          <>
            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Data de</label>
              <input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Data até</label>
              <input type="date" style={inputStyle} value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
            </div>
          </>
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
              <div className="card-header" style={{ margin: 0, color: "var(--red)" }}>{souAdmin ? "Confirmar exclusão" : "Solicitar exclusão"}</div>
              <button onClick={() => { setAlvo(null); setImpacto(null); }} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>{alvo.titulo}</p>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
              {souAdmin ? "Isto vai excluir permanentemente:" : "Se aprovado por um administrador, isto vai excluir permanentemente:"}
            </p>
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
                <Check size={14} /> {excluindo ? "Enviando…" : souAdmin ? "Confirmar exclusão" : "Solicitar exclusão"}
              </button>
              <button className="btn-ghost" onClick={() => { setAlvo(null); setImpacto(null); }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
