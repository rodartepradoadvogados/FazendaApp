"use client";
// Sub-tela: News (blog de pecuária leiteira) — mesmas matérias do site
// (GET /news/), geridas por nós via Configurações > News (site, admin) ou
// aqui mesmo no app. Só administradores abrem esta tela (ver app/layout.tsx
// e app/menu/page.tsx); dentro dela, escrever/excluir/revisar exigem também
// a permissão "publicar matérias no blog" (podePublicarMaterias()), igual ao site.
import { useMemo, useState } from "react";
import { Newspaper, Link as LinkIcon, CalendarDays, Plus, X, Check, Trash2, ShieldCheck, AlertTriangle, Pencil, Ban } from "lucide-react";
import { MobVoltar, MobCard, MobCampo } from "@/components/mobile/ui";
import {
  fetchTodasMaterias, criarMateriaBlog, atualizarMateriaBlog, excluirMateriaBlog, revisarPublicacaoFinal, podePublicarMaterias,
  type NoticiaNews,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { imagemMateria } from "@/lib/newsVisual";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

const inp: React.CSSProperties = {
  width: "100%", background: "var(--mob-surface-2)", color: "var(--mob-text)",
  border: "1px solid var(--mob-border)", borderRadius: 10, padding: "0.55rem 0.7rem", fontSize: "0.9rem",
};

const ABAS = [
  { key: "publicadas", label: "Matérias" },
  { key: "revisao", label: "Revisão final" },
] as const;

export default function News({ onVoltar }: { onVoltar: () => void }) {
  const podePublicar = podePublicarMaterias();
  const [aba, setAba] = useState<(typeof ABAS)[number]["key"]>("publicadas");
  const { dados, doCache, carregando, recarregar } = useCarregar<NoticiaNews[]>("menu_news_todas", () => fetchTodasMaterias());

  const [abrirForm, setAbrirForm] = useState(false);
  const [manchete, setManchete] = useState("");
  const [materia, setMateria] = useState("");
  const [fontes, setFontes] = useState<string[]>(["", ""]);
  const [salvando, setSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [revisando, setRevisando] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // Edição inline de uma matéria (botão "Editar" na Revisão final).
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [editManchete, setEditManchete] = useState("");
  const [editCorpo, setEditCorpo] = useState("");
  const [editFontes, setEditFontes] = useState<string[]>([""]);
  const [editSalvando, setEditSalvando] = useState(false);
  const [editErro, setEditErro] = useState<string | null>(null);

  const materias = useMemo(() => {
    if (!dados) return [];
    return [...dados].sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
  }, [dados]);

  const materiasPublicadas = materias.filter((n) => n.revisado_final);
  const pendentesRevisao = materias.filter((n) => !n.revisado_final);

  const limpar = () => { setManchete(""); setMateria(""); setFontes(["", ""]); };

  const salvar = async () => {
    setSalvando(true); setErro(null); setMsg(null);
    try {
      await criarMateriaBlog({ manchete: manchete.trim(), materia: materia.trim(), fontes: fontes.map((f) => f.trim()).filter(Boolean) });
      setMsg("Matéria publicada no blog — aguardando revisão de publicação definitiva.");
      limpar();
      setAbrirForm(false);
      await recarregar();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  const excluir = async (n: NoticiaNews) => {
    if (!window.confirm(`Excluir a matéria "${n.manchete}"? Não dá para desfazer.`)) return;
    setExcluindo(n.id); setErro(null);
    try { await excluirMateriaBlog(n.id); await recarregar(); }
    catch (e: any) { setErro(e.message); }
    finally { setExcluindo(null); }
  };

  const rejeitar = async (n: NoticiaNews) => {
    if (!window.confirm(`Rejeitar (excluir) a matéria "${n.manchete}"? Ela não será publicada.`)) return;
    setExcluindo(n.id); setErro(null); setMsg(null);
    try { await excluirMateriaBlog(n.id); setMsg(`Matéria "${n.manchete}" rejeitada.`); await recarregar(); }
    catch (e: any) { setErro(e.message); }
    finally { setExcluindo(null); }
  };

  const revisar = async (n: NoticiaNews) => {
    setRevisando(n.id); setErro(null); setMsg(null);
    try { await revisarPublicacaoFinal(n.id); setMsg(`Revisão de "${n.manchete}" confirmada — agora publicada.`); await recarregar(); }
    catch (e: any) { setErro(e.message); }
    finally { setRevisando(null); }
  };

  const iniciarEdicao = (n: NoticiaNews) => {
    setEditandoId(n.id);
    setEditManchete(n.manchete);
    setEditCorpo(n.materia || n.resumo || "");
    setEditFontes(n.fontes && n.fontes.length ? n.fontes : [""]);
    setEditErro(null);
  };

  const salvarEdicao = async (n: NoticiaNews) => {
    setEditErro(null);
    if (!editManchete.trim()) { setEditErro("A manchete é obrigatória."); return; }
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
      await recarregar();
    } catch (e: any) { setEditErro(e.message); }
    finally { setEditSalvando(false); }
  };

  return (
    <div>
      <MobVoltar titulo="News" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_news_todas" mostrar={doCache} />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.9rem" }}>
        {ABAS.map((t) => (
          <button key={t.key} type="button" className={`mob-pill${aba === t.key ? " ativa" : ""}`} style={{ flex: 1, position: "relative" }}
            onClick={() => setAba(t.key)}>
            {t.label}
            {t.key === "revisao" && pendentesRevisao.length > 0 && (
              <span style={{ marginLeft: "0.4rem", background: "var(--mob-vermelho)", color: "#fff", borderRadius: 999, fontSize: "0.68rem", padding: "0.05rem 0.4rem", fontWeight: 700 }}>
                {pendentesRevisao.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {erro && (
        <p style={{ color: "var(--mob-vermelho)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <AlertTriangle size={14} /> {erro}
        </p>
      )}
      {msg && (
        <p style={{ color: "var(--mob-verde)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600 }}>{msg}</p>
      )}

      {aba === "publicadas" && (
        <>
          <button type="button" className="mob-btn-2" style={{ marginBottom: "0.9rem" }}
            onClick={() => setAbrirForm((v) => !v)} disabled={!podePublicar}
            title={podePublicar ? undefined : "Você não tem permissão para publicar matérias no blog"}>
            {abrirForm ? <X size={16} /> : <Plus size={16} />} {abrirForm ? "Cancelar" : "Adicionar matéria"}
          </button>
          {!podePublicar && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.9rem" }}>
              Você não tem a permissão "publicar matérias no blog" — peça a um administrador para liberá-la em Usuários.
            </p>
          )}

          {abrirForm && podePublicar && (
            <MobCard style={{ marginBottom: "0.9rem" }}>
              <MobCampo label="Manchete">
                <input style={inp} value={manchete} onChange={(e) => setManchete(e.target.value)} placeholder="Título da matéria" />
              </MobCampo>
              <MobCampo label="Matéria">
                <textarea style={{ ...inp, minHeight: "8rem", resize: "vertical", fontFamily: "inherit" }} value={materia}
                  onChange={(e) => setMateria(e.target.value)} placeholder="Texto completo da matéria…" />
              </MobCampo>
              <MobCampo label="Fontes (URL) — opcional">
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {fontes.map((f, i) => (
                    <div key={i} style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                      <input style={inp} value={f} onChange={(e) => setFontes((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                        placeholder={`https://... (fonte ${i + 1})`} />
                      {fontes.length > 1 && (
                        <button type="button" onClick={() => setFontes((prev) => prev.filter((_, j) => j !== i))}
                          style={{ background: "none", border: "none", color: "var(--mob-muted)", cursor: "pointer", flexShrink: 0 }}>
                          <X size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button type="button" onClick={() => setFontes((prev) => [...prev, ""])}
                  style={{ marginTop: "0.4rem", background: "none", border: "none", color: "var(--mob-dourado-2)", fontSize: "0.82rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer" }}>
                  <Plus size={14} /> Adicionar fonte
                </button>
              </MobCampo>
              <button type="button" className="mob-btn" onClick={salvar} disabled={salvando || !manchete.trim() || !materia.trim()}>
                <Check size={16} /> {salvando ? "Publicando…" : "Publicar matéria"}
              </button>
            </MobCard>
          )}

          {carregando && !dados ? (
            <Carregando />
          ) : materiasPublicadas.length === 0 ? (
            <Vazio>Nenhuma matéria publicada ainda.</Vazio>
          ) : (
            materiasPublicadas.map((n: NoticiaNews, i: number) => (
              <div key={n.id} className="mob-card" style={{ overflow: "hidden", marginBottom: "0.7rem" }}>
                <div className="relative">
                  <img src={imagemMateria(n, i)} alt="" style={{ width: "100%", height: "120px", objectFit: "cover", display: "block" }} />
                  {n.categoria && (
                    <span className="absolute top-2 left-2" style={{
                      fontSize: "0.62rem", fontWeight: 700, padding: "0.2rem 0.55rem", borderRadius: "999px",
                      textTransform: "uppercase", letterSpacing: "0.03em",
                      background: "var(--mob-vinho)", color: "#fff",
                    }}>
                      {n.categoria}
                    </span>
                  )}
                </div>
                <div style={{ padding: "0.95rem 1rem" }}>
                  <div className="flex items-start gap-2">
                    <Newspaper size={15} style={{ color: "var(--mob-dourado-2)", flexShrink: 0, marginTop: "0.15rem" }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.5rem" }}>
                        <p style={{ fontWeight: 700, fontSize: "0.94rem", color: "var(--mob-dourado-2)" }}>{n.manchete}</p>
                        <button type="button" onClick={() => excluir(n)} disabled={excluindo === n.id || !podePublicar}
                          title={podePublicar ? "Excluir matéria" : "Sem permissão para excluir"}
                          style={{ background: "none", border: "none", cursor: podePublicar ? "pointer" : "not-allowed", color: "var(--mob-vermelho)", flexShrink: 0, opacity: podePublicar ? 1 : 0.4 }}>
                          <Trash2 size={15} />
                        </button>
                      </div>
                      {(n.materia || n.resumo) && (
                        <p className="line-clamp-3" style={{ fontSize: "0.82rem", color: "var(--mob-text)", marginTop: "0.3rem", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                          {n.materia || n.resumo}
                        </p>
                      )}
                      <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginTop: "0.45rem", fontSize: "0.7rem" }}>
                        <span style={{ color: "var(--mob-muted)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                          <CalendarDays size={11} /> {formatarData(n.data_publicacao)}
                        </span>
                        <span style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--mob-verde)" }}>
                          <ShieldCheck size={11} /> revisada
                        </span>
                        {(n.fontes || []).map((url, j) => (
                          <a key={j} href={url} target="_blank" rel="noopener noreferrer"
                            style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--mob-muted)", border: "1px solid var(--mob-border)", borderRadius: "999px", padding: "0.1rem 0.45rem", textDecoration: "none" }}>
                            <LinkIcon size={10} /> {dominio(url)}
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </>
      )}

      {aba === "revisao" && (
        <>
          <p style={{ color: "var(--mob-muted)", fontSize: "0.8rem", marginBottom: "0.9rem" }}>
            Toda matéria publicada — pelo robô agendado, por você ou por outra pessoa autorizada — cai aqui até alguém
            confirmar a revisão de publicação definitiva; só depois disso ela aparece em "Matérias" e na página
            pública. Confira as fontes/hiperlinks antes de confirmar. Essa etapa é sempre humana: o robô nunca a realiza.
          </p>

          {carregando && !dados ? (
            <Carregando />
          ) : pendentesRevisao.length === 0 ? (
            <Vazio>Nenhuma matéria aguardando revisão definitiva.</Vazio>
          ) : (
            pendentesRevisao.map((n) => {
              const editando = editandoId === n.id;
              return (
                <MobCard key={n.id} style={{ marginBottom: "0.6rem" }}>
                  {editando ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                      <MobCampo label="Manchete">
                        <input style={inp} value={editManchete} onChange={(e) => setEditManchete(e.target.value)} />
                      </MobCampo>
                      <MobCampo label="Matéria">
                        <textarea style={{ ...inp, minHeight: "7rem", resize: "vertical", fontFamily: "inherit" }} value={editCorpo}
                          onChange={(e) => setEditCorpo(e.target.value)} />
                      </MobCampo>
                      <MobCampo label="Fontes (URL) — hiperlinks de referência">
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                          {editFontes.map((f, i) => (
                            <div key={i} style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                              <input style={inp} value={f} onChange={(e) => setEditFontes((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                                placeholder={`https://... (fonte ${i + 1})`} />
                              {editFontes.length > 1 && (
                                <button type="button" onClick={() => setEditFontes((prev) => prev.filter((_, j) => j !== i))}
                                  style={{ background: "none", border: "none", color: "var(--mob-muted)", cursor: "pointer", flexShrink: 0 }}>
                                  <X size={16} />
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                        <button type="button" onClick={() => setEditFontes((prev) => [...prev, ""])}
                          style={{ marginTop: "0.4rem", background: "none", border: "none", color: "var(--mob-dourado-2)", fontSize: "0.82rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer" }}>
                          <Plus size={14} /> Adicionar fonte
                        </button>
                      </MobCampo>
                      {editErro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.8rem" }}>{editErro}</p>}
                      <div className="flex items-center gap-2">
                        <button type="button" className="mob-btn" onClick={() => salvarEdicao(n)} disabled={editSalvando}>
                          <Check size={16} /> {editSalvando ? "Salvando…" : "Salvar edição"}
                        </button>
                        <button type="button" className="mob-btn-2" onClick={() => setEditandoId(null)}>Cancelar</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p style={{ fontWeight: 700, fontSize: "0.92rem" }}>{n.manchete}</p>
                      {(n.materia || n.resumo) && (
                        <p style={{ color: "var(--mob-muted)", fontSize: "0.82rem", marginTop: "0.3rem", whiteSpace: "pre-wrap" }}>
                          {n.materia || n.resumo}
                        </p>
                      )}
                      <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginTop: "0.4rem" }}>
                        <span style={{ color: "var(--mob-muted)", fontSize: "0.74rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                          <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
                        </span>
                        {(n.fontes || []).map((url, j) => (
                          <a key={j} href={url} target="_blank" rel="noopener noreferrer"
                            style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--mob-dourado-2)", border: "1px solid var(--mob-border)", borderRadius: "999px", padding: "0.1rem 0.45rem", fontSize: "0.72rem", textDecoration: "none" }}>
                            <LinkIcon size={10} /> {dominio(url)}
                          </a>
                        ))}
                        {!(n.fontes || []).length && (
                          <span style={{ color: "var(--mob-muted)", fontSize: "0.72rem", fontStyle: "italic" }}>Sem fontes/hiperlinks informados.</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap" style={{ marginTop: "0.7rem" }}>
                        <button type="button" className="mob-btn-2" onClick={() => iniciarEdicao(n)} disabled={!podePublicar}
                          title={podePublicar ? "Editar matéria" : "Sem permissão para editar"}>
                          <Pencil size={15} /> Editar
                        </button>
                        <button type="button" className="mob-btn-2" style={{ color: "var(--mob-vermelho)" }}
                          onClick={() => rejeitar(n)} disabled={excluindo === n.id || !podePublicar}
                          title={podePublicar ? "Rejeitar (excluir) matéria" : "Sem permissão para rejeitar"}>
                          <Ban size={15} /> {excluindo === n.id ? "Rejeitando…" : "Rejeitar"}
                        </button>
                        <button type="button" className="mob-btn"
                          onClick={() => revisar(n)} disabled={revisando === n.id || !podePublicar}
                          title={podePublicar ? undefined : "Você não tem permissão para publicar matérias no blog"}>
                          <ShieldCheck size={16} /> {revisando === n.id ? "Confirmando…" : "Confirmar revisão definitiva"}
                        </button>
                      </div>
                    </>
                  )}
                </MobCard>
              );
            })
          )}
        </>
      )}
    </div>
  );
}
