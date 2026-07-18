"use client";
// Sub-tela: News (blog de pecuária leiteira) — mesmas matérias do site
// (GET /news/), geridas por nós via Configurações > News (site, admin) ou
// aqui mesmo no app. Só administradores abrem esta tela (ver app/layout.tsx
// e app/menu/page.tsx); dentro dela, escrever/excluir/revisar exigem também
// a permissão "publicar matérias no blog" (podePublicarMaterias()), igual ao site.
import { useMemo, useState } from "react";
import { Newspaper, Link as LinkIcon, CalendarDays, Plus, X, Check, Trash2, ShieldCheck, AlertTriangle } from "lucide-react";
import { MobVoltar, MobCard, MobCampo } from "@/components/mobile/ui";
import {
  fetchNoticias, criarMateriaBlog, excluirMateriaBlog, revisarPublicacaoFinal, podePublicarMaterias,
  type NewsFeed, type NoticiaNews,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { estiloCardMateria } from "@/lib/newsVisual";

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
  const [verTudo, setVerTudo] = useState(false);
  const chave = verTudo ? "menu_news_tudo" : "menu_news_3d";
  const { dados, doCache, carregando, recarregar } = useCarregar<NewsFeed>(chave, () => fetchNoticias(verTudo));

  const [abrirForm, setAbrirForm] = useState(false);
  const [manchete, setManchete] = useState("");
  const [materia, setMateria] = useState("");
  const [fontes, setFontes] = useState<string[]>(["", ""]);
  const [salvando, setSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [revisando, setRevisando] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const materias = useMemo(() => {
    if (!dados) return [];
    const todas = dados.fontes.flatMap((f) => f.noticias);
    return [...todas].sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
  }, [dados]);

  const pendentesRevisao = materias.filter((n) => !n.revisado_final);

  const limpar = () => { setManchete(""); setMateria(""); setFontes(["", ""]); };

  const salvar = async () => {
    setSalvando(true); setErro(null); setMsg(null);
    try {
      await criarMateriaBlog({ manchete: manchete.trim(), materia: materia.trim(), fontes: fontes.map((f) => f.trim()).filter(Boolean) });
      setMsg("Matéria publicada no blog.");
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

  const revisar = async (n: NoticiaNews) => {
    setRevisando(n.id); setErro(null); setMsg(null);
    try { await revisarPublicacaoFinal(n.id); setMsg(`Revisão de "${n.manchete}" confirmada.`); await recarregar(); }
    catch (e: any) { setErro(e.message); }
    finally { setRevisando(null); }
  };

  return (
    <div>
      <MobVoltar titulo="News" onVoltar={onVoltar} />
      <AvisoCopia chave={chave} mostrar={doCache} />

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

          <button type="button" className="mob-btn-2" style={{ marginBottom: "0.9rem" }} onClick={() => setVerTudo((v) => !v)}>
            {verTudo ? "Ver só últimos dias" : "Ver tudo"}
          </button>

          {carregando && !dados ? (
            <Carregando />
          ) : materias.length === 0 ? (
            <Vazio>Nenhuma matéria publicada ainda.</Vazio>
          ) : (
            materias.map((n: NoticiaNews, i: number) => (
              <MobCard key={n.id} style={{ ...estiloCardMateria(i), marginBottom: "0.7rem" }}>
                <div className="flex items-start gap-2">
                  <Newspaper size={15} style={{ color: "#FFE9B0", flexShrink: 0, marginTop: "0.15rem" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.5rem" }}>
                      <p style={{ fontWeight: 700, fontSize: "0.94rem", color: "#FFE9B0" }}>{n.manchete}</p>
                      <button type="button" onClick={() => excluir(n)} disabled={excluindo === n.id || !podePublicar}
                        title={podePublicar ? "Excluir matéria" : "Sem permissão para excluir"}
                        style={{ background: "none", border: "none", cursor: podePublicar ? "pointer" : "not-allowed", color: "#F5B0B0", flexShrink: 0, opacity: podePublicar ? 1 : 0.4 }}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                    {(n.materia || n.resumo) && (
                      <p style={{ fontSize: "0.82rem", color: "#F5ECDD", marginTop: "0.3rem", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                        {n.materia || n.resumo}
                      </p>
                    )}
                    <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginTop: "0.45rem", fontSize: "0.7rem" }}>
                      <span style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <CalendarDays size={11} /> {formatarData(n.data_publicacao)}
                      </span>
                      {n.revisado_final ? (
                        <span style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "#C8F5D0" }}>
                          <ShieldCheck size={11} /> revisada
                        </span>
                      ) : (
                        <span style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "#FFD79A" }}>
                          <AlertTriangle size={11} /> aguardando revisão
                        </span>
                      )}
                      {(n.fontes || []).map((url, j) => (
                        <a key={j} href={url} target="_blank" rel="noopener noreferrer"
                          style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "#FFE9B0", border: "1px solid rgba(255,233,176,0.4)", borderRadius: "999px", padding: "0.1rem 0.45rem", textDecoration: "none" }}>
                          <LinkIcon size={10} /> {dominio(url)}
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              </MobCard>
            ))
          )}
        </>
      )}

      {aba === "revisao" && (
        <>
          <p style={{ color: "var(--mob-muted)", fontSize: "0.8rem", marginBottom: "0.9rem" }}>
            Toda matéria publicada — pelo robô agendado, por você ou por outra pessoa autorizada — cai aqui até alguém
            confirmar a revisão de publicação definitiva. Essa etapa é sempre humana: o robô nunca a realiza.
          </p>

          {carregando && !dados ? (
            <Carregando />
          ) : pendentesRevisao.length === 0 ? (
            <Vazio>Nenhuma matéria aguardando revisão definitiva.</Vazio>
          ) : (
            pendentesRevisao.map((n) => (
              <MobCard key={n.id} style={{ marginBottom: "0.6rem" }}>
                <p style={{ fontWeight: 700, fontSize: "0.92rem" }}>{n.manchete}</p>
                {(n.materia || n.resumo) && (
                  <p style={{ color: "var(--mob-muted)", fontSize: "0.82rem", marginTop: "0.3rem", whiteSpace: "pre-wrap" }}>
                    {n.materia || n.resumo}
                  </p>
                )}
                <p style={{ color: "var(--mob-muted)", fontSize: "0.74rem", marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
                </p>
                <button type="button" className="mob-btn" style={{ marginTop: "0.7rem" }}
                  onClick={() => revisar(n)} disabled={revisando === n.id || !podePublicar}
                  title={podePublicar ? undefined : "Você não tem permissão para publicar matérias no blog"}>
                  <ShieldCheck size={16} /> {revisando === n.id ? "Confirmando…" : "Confirmar revisão definitiva"}
                </button>
              </MobCard>
            ))
          )}
        </>
      )}
    </div>
  );
}
