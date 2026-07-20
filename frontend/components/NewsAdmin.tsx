"use client";
import { useEffect, useState } from "react";
import { Newspaper, AlertTriangle, Plus, Trash2, X, Check, Link as LinkIcon, CalendarDays, ShieldCheck, ClipboardCheck, Pencil, Ban } from "lucide-react";
import { fetchTodasMaterias, criarMateriaBlog, atualizarMateriaBlog, excluirMateriaBlog, revisarPublicacaoFinal, podePublicarMaterias, type NoticiaNews } from "@/lib/api";
import { imagemMateria } from "@/lib/newsVisual";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatarDataHora(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

const TABS = [
  { key: "publicadas", label: "Matérias publicadas", icon: Newspaper },
  { key: "revisao", label: "Revisão de publicação definitiva", icon: ClipboardCheck },
] as const;

export default function NewsAdmin() {
  const [aba, setAba] = useState<(typeof TABS)[number]["key"]>("publicadas");
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [abrirForm, setAbrirForm] = useState(false);
  const [manchete, setManchete] = useState("");
  const [materia, setMateria] = useState("");
  const [fontes, setFontes] = useState<string[]>(["", "", ""]);
  const [salvando, setSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [revisando, setRevisando] = useState<number | null>(null);

  // Edição inline de uma matéria (botão "Editar matéria" na Revisão de publicação definitiva).
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [editManchete, setEditManchete] = useState("");
  const [editCorpo, setEditCorpo] = useState("");
  const [editFontes, setEditFontes] = useState<string[]>([""]);
  const [editSalvando, setEditSalvando] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const podePublicar = podePublicarMaterias();

  const carregar = () =>
    fetchTodasMaterias()
      .then((todas) => {
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
        setMaterias(todas);
      })
      .catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const limpar = () => { setManchete(""); setMateria(""); setFontes(["", "", ""]); };

  const salvar = async () => {
    setSalvando(true); setError(null); setMsg(null);
    try {
      await criarMateriaBlog({ manchete: manchete.trim(), materia: materia.trim(), fontes: fontes.map((f) => f.trim()).filter(Boolean) });
      setMsg("Matéria publicada no blog — aguardando revisão de publicação definitiva.");
      limpar();
      setAbrirForm(false);
      carregar();
    } catch (e: any) { setError(e.message); }
    finally { setSalvando(false); }
  };

  const excluir = async (n: NoticiaNews) => {
    if (!confirm(`Excluir a matéria "${n.manchete}"?`)) return;
    setExcluindo(n.id);
    try { await excluirMateriaBlog(n.id); carregar(); }
    catch (e: any) { setError(e.message); }
    finally { setExcluindo(null); }
  };

  const rejeitar = async (n: NoticiaNews) => {
    if (!confirm(`Rejeitar (excluir) a matéria "${n.manchete}"? Ela não será publicada.`)) return;
    setExcluindo(n.id); setError(null); setMsg(null);
    try { await excluirMateriaBlog(n.id); setMsg(`Matéria "${n.manchete}" rejeitada.`); carregar(); }
    catch (e: any) { setError(e.message); }
    finally { setExcluindo(null); }
  };

  const revisar = async (n: NoticiaNews) => {
    setRevisando(n.id); setError(null); setMsg(null);
    try { await revisarPublicacaoFinal(n.id); setMsg(`Revisão de "${n.manchete}" confirmada — agora publicada.`); carregar(); }
    catch (e: any) { setError(e.message); }
    finally { setRevisando(null); }
  };

  const iniciarEdicao = (n: NoticiaNews) => {
    setEditandoId(n.id);
    setEditManchete(n.manchete);
    setEditCorpo(n.materia || n.resumo || "");
    setEditFontes(n.fontes && n.fontes.length ? n.fontes : [""]);
    setEditError(null);
  };

  const salvarEdicao = async (n: NoticiaNews) => {
    setEditError(null);
    if (!editManchete.trim()) { setEditError("A manchete é obrigatória."); return; }
    setEditSalvando(true);
    try {
      await atualizarMateriaBlog(n.id, {
        manchete: editManchete.trim(),
        materia: n.materia != null ? editCorpo.trim() : undefined,
        resumo: n.materia == null ? editCorpo.trim() : undefined,
        fontes: editFontes.map((f) => f.trim()).filter(Boolean),
      });
      setEditandoId(null);
      setMsg(`Matéria "${editManchete.trim()}" atualizada.`);
      carregar();
    } catch (e: any) { setEditError(e.message); }
    finally { setEditSalvando(false); }
  };

  const materiasPublicadas = (materias || []).filter((n) => n.revisado_final);
  const pendentesRevisao = (materias || []).filter((n) => !n.revisado_final);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Newspaper size={22} style={{ color: "var(--dourado-light)" }} /> News — Blog</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Matérias do blog de pecuária leiteira que aparecem no botão "News". Só administradores veem esta tela.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-4" style={{ borderBottom: "1px solid var(--border)" }}>
        {TABS.map((t) => {
          const Icon = t.icon;
          const ativa = aba === t.key;
          return (
            <button key={t.key} type="button" onClick={() => setAba(t.key)}
              style={{
                display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.55rem 0.9rem", fontSize: "0.82rem",
                fontWeight: ativa ? 700 : 500, background: "none", border: "none", cursor: "pointer",
                color: ativa ? "var(--dourado-light)" : "var(--text-muted)",
                borderBottom: ativa ? "2px solid var(--dourado-light)" : "2px solid transparent",
              }}>
              <Icon size={14} /> {t.label}
              {t.key === "revisao" && pendentesRevisao.length > 0 && (
                <span style={{
                  background: "var(--red)", color: "#fff", borderRadius: "999px", fontSize: "0.68rem",
                  padding: "0.05rem 0.4rem", fontWeight: 700,
                }}>{pendentesRevisao.length}</span>
              )}
            </button>
          );
        })}
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {msg && <div className="card mb-4" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem" }}>{msg}</div>}

      {aba === "publicadas" && (
        <>
          <div className="card mb-6">
            <button type="button" className="btn-primary" style={{ fontSize: "0.82rem", display: "flex", alignItems: "center", gap: "0.4rem" }}
              onClick={() => setAbrirForm((v) => !v)} disabled={!podePublicar}
              title={podePublicar ? undefined : "Você não tem permissão para publicar matérias no blog"}>
              {abrirForm ? <X size={14} /> : <Plus size={14} />} {abrirForm ? "Cancelar" : "Adicionar matéria ao blog"}
            </button>
            {!podePublicar && (
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                Você não tem a permissão "publicar matérias no blog" — peça a um administrador para liberá-la em Usuários.
              </p>
            )}

            {abrirForm && podePublicar && (
              <div className="mt-4" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div>
                  <label style={lbl}>Manchete</label>
                  <input style={inp} value={manchete} onChange={(e) => setManchete(e.target.value)} placeholder="Título da matéria" />
                </div>
                <div>
                  <label style={lbl}>Matéria</label>
                  <textarea style={{ ...inp, minHeight: "9rem", resize: "vertical", fontFamily: "inherit" }} value={materia}
                    onChange={(e) => setMateria(e.target.value)} placeholder="Texto completo da matéria…" />
                </div>
                <div>
                  <label style={lbl}>Fontes (URL) — opcional</label>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {fontes.map((f, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <input style={inp} value={f} onChange={(e) => setFontes((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                          placeholder={`https://... (fonte ${i + 1})`} />
                        {fontes.length > 1 && (
                          <button type="button" className="btn-ghost" title="Remover este campo"
                            onClick={() => setFontes((prev) => prev.filter((_, j) => j !== i))}>
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <button type="button" className="btn-ghost mt-2" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                    onClick={() => setFontes((prev) => [...prev, ""])}>
                    <Plus size={13} /> Adicionar fonte
                  </button>
                </div>
                <div>
                  <button type="button" className="btn-primary" style={{ fontSize: "0.82rem", display: "flex", alignItems: "center", gap: "0.4rem" }}
                    onClick={salvar} disabled={salvando || !manchete.trim() || !materia.trim()}>
                    <Check size={14} /> {salvando ? "Publicando…" : "Publicar matéria"}
                  </button>
                </div>
              </div>
            )}
          </div>

          {!materias && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

          {materias && materiasPublicadas.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>Nenhuma matéria publicada ainda.</p>
          )}

          {materiasPublicadas.length > 0 && (
            <div className="flex flex-col gap-3">
              {materiasPublicadas.map((n, i) => (
                <div key={n.id} className="rounded-xl overflow-hidden flex" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
                  <div className="relative" style={{ width: "140px", flexShrink: 0 }}>
                    <img src={imagemMateria(n, i)} alt="" className="w-full h-full object-cover" style={{ minHeight: "100%" }} />
                    {n.categoria && (
                      <span className="absolute top-2 left-2" style={{
                        fontSize: "0.6rem", fontWeight: 700, padding: "0.18rem 0.5rem", borderRadius: "999px",
                        textTransform: "uppercase", letterSpacing: "0.03em", background: "var(--pill-active-bg, var(--vinho))",
                        color: "var(--pill-active-fg, #fff)",
                      }}>
                        {n.categoria}
                      </span>
                    )}
                  </div>
                  <div style={{ padding: "1rem 1.1rem", flex: 1, minWidth: 0 }}>
                    <div className="flex items-start justify-between gap-2">
                      <p style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--dourado-light)", marginBottom: "0.3rem" }}>{n.manchete}</p>
                      <button type="button" onClick={() => excluir(n)} disabled={excluindo === n.id || !podePublicar} title={podePublicar ? "Excluir matéria" : "Sem permissão para excluir"}
                        style={{ background: "none", border: "none", cursor: podePublicar ? "pointer" : "not-allowed", color: "var(--red)", flexShrink: 0, opacity: podePublicar ? 1 : 0.4 }}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                    {(n.materia || n.resumo) && (
                      <p className="line-clamp-3" style={{ color: "var(--text-muted)", fontSize: "0.83rem", lineHeight: 1.55, marginBottom: "0.5rem", whiteSpace: "pre-wrap" }}>
                        {n.materia || n.resumo}
                      </p>
                    )}
                    <div className="flex items-center gap-2" style={{ flexWrap: "wrap", fontSize: "0.72rem" }}>
                      <span style={{ color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
                      </span>
                      <span style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "var(--green-light)" }} title={n.revisado_final_por ? `Por ${n.revisado_final_por} em ${formatarDataHora(n.revisado_final_em)}` : undefined}>
                        <ShieldCheck size={12} /> Revisão definitiva confirmada
                      </span>
                      {(n.fontes || []).map((url, i) => (
                        <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                          style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: "999px", padding: "0.15rem 0.55rem", textDecoration: "none" }}>
                          <LinkIcon size={11} /> {dominio(url)}
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {aba === "revisao" && (
        <>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
            Toda matéria publicada — pelo robô agendado, por você ou por outra pessoa autorizada — cai aqui até alguém
            confirmar a revisão de publicação definitiva; só depois disso ela aparece em "Matérias publicadas" e na
            página pública. Confira as fontes/hiperlinks antes de confirmar. Essa etapa é sempre humana: o robô nunca a realiza.
          </p>

          {!materias && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

          {materias && pendentesRevisao.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>Nenhuma matéria aguardando revisão definitiva.</p>
          )}

          {pendentesRevisao.length > 0 && (
            <div className="flex flex-col gap-3">
              {pendentesRevisao.map((n) => {
                const editando = editandoId === n.id;
                return (
                  <div key={n.id} className="card" style={{ borderLeft: "3px solid var(--dourado-light)" }}>
                    {editando ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                        <div>
                          <label style={lbl}>Manchete</label>
                          <input style={inp} value={editManchete} onChange={(e) => setEditManchete(e.target.value)} />
                        </div>
                        <div>
                          <label style={lbl}>Matéria</label>
                          <textarea style={{ ...inp, minHeight: "7rem", resize: "vertical", fontFamily: "inherit" }} value={editCorpo}
                            onChange={(e) => setEditCorpo(e.target.value)} />
                        </div>
                        <div>
                          <label style={lbl}>Fontes (URL) — hiperlinks de referência</label>
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                            {editFontes.map((f, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <input style={inp} value={f} onChange={(e) => setEditFontes((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                                  placeholder={`https://... (fonte ${i + 1})`} />
                                {editFontes.length > 1 && (
                                  <button type="button" className="btn-ghost" title="Remover este campo"
                                    onClick={() => setEditFontes((prev) => prev.filter((_, j) => j !== i))}>
                                    <X size={14} />
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                          <button type="button" className="btn-ghost mt-2" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                            onClick={() => setEditFontes((prev) => [...prev, ""])}>
                            <Plus size={13} /> Adicionar fonte
                          </button>
                        </div>
                        {editError && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{editError}</p>}
                        <div className="flex items-center gap-2">
                          <button type="button" className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                            onClick={() => salvarEdicao(n)} disabled={editSalvando}>
                            <Check size={14} /> {editSalvando ? "Salvando…" : "Salvar edição"}
                          </button>
                          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setEditandoId(null)}>Cancelar</button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div>
                          <p style={{ fontWeight: 700, fontSize: "0.9rem" }}>{n.manchete}</p>
                          {(n.materia || n.resumo) && (
                            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "0.25rem", whiteSpace: "pre-wrap" }}>
                              {n.materia || n.resumo}
                            </p>
                          )}
                          <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginTop: "0.4rem" }}>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                              <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
                            </span>
                            {(n.fontes || []).map((url, i) => (
                              <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                                style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "var(--dourado-light)", border: "1px solid var(--border)", borderRadius: "999px", padding: "0.15rem 0.55rem", fontSize: "0.72rem", textDecoration: "none" }}>
                                <LinkIcon size={11} /> {dominio(url)}
                              </a>
                            ))}
                            {!(n.fontes || []).length && (
                              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", fontStyle: "italic" }}>Sem fontes/hiperlinks de referência informados.</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap" style={{ flexShrink: 0 }}>
                          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                            onClick={() => iniciarEdicao(n)} disabled={!podePublicar}
                            title={podePublicar ? "Editar matéria" : "Sem permissão para editar"}>
                            <Pencil size={13} /> Editar matéria
                          </button>
                          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }}
                            onClick={() => rejeitar(n)} disabled={excluindo === n.id || !podePublicar}
                            title={podePublicar ? "Rejeitar (excluir) matéria" : "Sem permissão para rejeitar"}>
                            <Ban size={13} /> {excluindo === n.id ? "Rejeitando…" : "Rejeitar"}
                          </button>
                          <button type="button" className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                            onClick={() => revisar(n)} disabled={revisando === n.id || !podePublicar}
                            title={podePublicar ? undefined : "Você não tem permissão para publicar matérias no blog"}>
                            <ShieldCheck size={14} /> {revisando === n.id ? "Confirmando…" : "Confirmar revisão definitiva"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
