"use client";
import React, { useEffect, useState } from "react";
import { Newspaper, AlertTriangle, Plus, Pencil, Trash2, X, Check, CircleAlert, RefreshCw } from "lucide-react";
import { fetchFontesNews, criarFonteNews, atualizarFonteNews, excluirFonteNews, testarFonteNews, type FonteNews } from "@/lib/api";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

export default function NewsFontesAdmin() {
  const [fontes, setFontes] = useState<FonteNews[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const [nome, setNome] = useState("");
  const [url, setUrl] = useState("");
  const [editando, setEditando] = useState<FonteNews | null>(null);
  const [testando, setTestando] = useState<number | null>(null);
  const [resultadoTeste, setResultadoTeste] = useState<Record<number, { ok: boolean; texto: string }>>({});

  const carregar = () => fetchFontesNews().then(setFontes).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const testar = async (f: FonteNews) => {
    setTestando(f.id);
    setResultadoTeste((r) => { const { [f.id]: _omit, ...resto } = r; return resto; });
    try {
      const res = await testarFonteNews(f.id);
      setResultadoTeste((r) => ({
        ...r,
        [f.id]: res.ok
          ? { ok: true, texto: res.materias_novas > 0 ? `OK — ${res.materias_novas} matéria(s) nova(s) agora.` : "OK — buscou certo, mas nenhuma matéria nova/relevante desta vez." }
          : { ok: false, texto: res.erro || "Falhou, sem detalhe do erro." },
      }));
      carregar();
    } catch (e: any) {
      setResultadoTeste((r) => ({ ...r, [f.id]: { ok: false, texto: e.message } }));
    } finally {
      setTestando(null);
    }
  };

  const limpar = () => { setNome(""); setUrl(""); setEditando(null); };

  const salvar = async () => {
    setSalvando(true); setError(null); setMsg(null);
    try {
      if (editando) {
        await atualizarFonteNews(editando.id, { nome: nome.trim(), url: url.trim(), ativo: editando.ativo });
        setMsg(`Fonte "${nome}" atualizada.`);
      } else {
        await criarFonteNews({ nome: nome.trim(), url: url.trim(), ativo: true });
        setMsg(`Fonte "${nome}" cadastrada.`);
      }
      limpar();
      carregar();
    } catch (e: any) { setError(e.message); }
    finally { setSalvando(false); }
  };

  const editar = (f: FonteNews) => { setEditando(f); setNome(f.nome); setUrl(f.url); };

  const toggleAtivo = async (f: FonteNews) => {
    try { await atualizarFonteNews(f.id, { nome: f.nome, url: f.url, ativo: !f.ativo }); carregar(); }
    catch (e: any) { setError(e.message); }
  };

  const excluir = async (f: FonteNews) => {
    if (!confirm(`Excluir a fonte "${f.nome}" e todas as notícias já importadas dela?`)) return;
    try { await excluirFonteNews(f.id); carregar(); }
    catch (e: any) { setError(e.message); }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Newspaper size={22} style={{ color: "var(--dourado-light)" }} /> News — Fontes</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Sites que alimentam o botão "News" (blog de pecuária leiteira). Se um site parar de funcionar, o erro
          aparece na lista abaixo — corrija a URL ou substitua pelo site correto. Só administradores veem esta tela.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {msg && <div className="card mb-4" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem" }}>{msg}</div>}

      <div className="card mb-6">
        <div className="card-header mb-3 flex items-center gap-2"><Plus size={14} /> {editando ? `Editando "${editando.nome}"` : "Nova fonte"}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div>
            <label style={lbl}>Nome</label>
            <input style={inp} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: MilkPoint" />
          </div>
          <div>
            <label style={lbl}>URL (home do site ou feed RSS/Atom direto)</label>
            <input style={inp} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.exemplo.com.br/" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-primary" style={{ fontSize: "0.82rem" }} onClick={salvar} disabled={salvando || !nome.trim() || !url.trim()}>
            {editando ? "Salvar alterações" : "Cadastrar fonte"}
          </button>
          {editando && <button className="btn-ghost" style={{ fontSize: "0.82rem" }} onClick={limpar}><X size={14} /> Cancelar</button>}
        </div>
      </div>

      {!fontes && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {fontes && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="w-full" style={{ borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ background: "var(--surface-2)", textAlign: "left" }}>
                <th style={{ padding: "0.6rem 0.9rem" }}>Nome</th>
                <th style={{ padding: "0.6rem 0.9rem" }}>URL</th>
                <th style={{ padding: "0.6rem 0.9rem" }}>Status</th>
                <th style={{ padding: "0.6rem 0.9rem" }}>Ativa</th>
                <th style={{ padding: "0.6rem 0.9rem" }}></th>
              </tr>
            </thead>
            <tbody>
              {fontes.map((f) => (
                <React.Fragment key={f.id}>
                  <tr style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.6rem 0.9rem", fontWeight: 600 }}>{f.nome}</td>
                    <td style={{ padding: "0.6rem 0.9rem", color: "var(--text-muted)", maxWidth: "18rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.url}</td>
                    <td style={{ padding: "0.6rem 0.9rem" }}>
                      {f.ultimo_erro ? (
                        <span className="flex items-center gap-1" style={{ color: "var(--red)", fontSize: "0.78rem" }} title={f.ultimo_erro}>
                          <CircleAlert size={14} /> Com erro
                        </span>
                      ) : (
                        <span style={{ color: "var(--green-light)", fontSize: "0.78rem" }}>OK</span>
                      )}
                    </td>
                    <td style={{ padding: "0.6rem 0.9rem" }}>
                      <button onClick={() => toggleAtivo(f)} title={f.ativo ? "Desativar" : "Ativar"}
                        style={{ background: "none", border: "none", cursor: "pointer", color: f.ativo ? "var(--green-light)" : "var(--text-muted)" }}>
                        <Check size={16} style={{ opacity: f.ativo ? 1 : 0.3 }} />
                      </button>
                    </td>
                    <td style={{ padding: "0.6rem 0.9rem" }}>
                      <div className="flex items-center gap-2">
                        <button onClick={() => testar(f)} title="Testar agora — busca na hora, ignora a espera de 1h" disabled={testando === f.id}
                          style={{ background: "none", border: "none", cursor: testando === f.id ? "default" : "pointer", color: "var(--dourado-light)", display: "flex", alignItems: "center" }}>
                          <RefreshCw size={15} className={testando === f.id ? "animate-spin" : ""} />
                        </button>
                        <button onClick={() => editar(f)} title="Editar" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--dourado-light)" }}><Pencil size={15} /></button>
                        <button onClick={() => excluir(f)} title="Excluir" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={15} /></button>
                      </div>
                    </td>
                  </tr>
                  {resultadoTeste[f.id] && (
                    <tr>
                      <td colSpan={5} style={{ padding: "0 0.9rem 0.6rem", fontSize: "0.78rem", color: resultadoTeste[f.id].ok ? "var(--green-light)" : "var(--red)" }}>
                        Teste agora: {resultadoTeste[f.id].texto}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {fontes.length === 0 && (
                <tr><td colSpan={5} style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)" }}>Nenhuma fonte cadastrada.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {fontes && fontes.some((f) => f.ultimo_erro) && (
        <div className="alert-critico mt-4" style={{ fontSize: "0.82rem" }}>
          <AlertTriangle size={16} />
          <span>Uma ou mais fontes estão com erro de busca — os leitores do "News" veem um aviso pedindo para
          você substituir ou corrigir a URL. Passe o mouse sobre "Com erro" para ver a mensagem exata.</span>
        </div>
      )}
    </div>
  );
}
