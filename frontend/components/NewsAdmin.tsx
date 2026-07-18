"use client";
import { useEffect, useState } from "react";
import { Newspaper, AlertTriangle, Plus, Trash2, X, Check, Link as LinkIcon, CalendarDays } from "lucide-react";
import { fetchNoticias, criarMateriaBlog, excluirMateriaBlog, type NoticiaNews } from "@/lib/api";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

// Fundo de cada matéria: a mesma foto do compost barn usada no login, com uma
// camada semitransparente na cor da paleta ativa por cima (var(--vinho) já
// reflete vinho ou verde, o que o usuário tiver escolhido) — texto claro fixo
// por cima, já que essa camada é sempre escura nos dois temas/paletas.
const cardStyle: React.CSSProperties = {
  position: "relative", padding: "1rem 1.1rem", borderRadius: "12px",
  border: "1px solid var(--vinho-light)",
  backgroundImage:
    "linear-gradient(color-mix(in srgb, var(--vinho) 76%, transparent), color-mix(in srgb, var(--vinho) 76%, transparent)), url('/images/login-fundo.webp')",
  backgroundSize: "cover", backgroundPosition: "center 55%",
};

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

export default function NewsAdmin() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [abrirForm, setAbrirForm] = useState(false);
  const [manchete, setManchete] = useState("");
  const [materia, setMateria] = useState("");
  const [fontes, setFontes] = useState<string[]>(["", "", ""]);
  const [salvando, setSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState<number | null>(null);

  const carregar = () =>
    fetchNoticias(true)
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
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
      setMsg("Matéria publicada no blog.");
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

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Newspaper size={22} style={{ color: "var(--dourado-light)" }} /> News — Blog</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Matérias do blog de pecuária leiteira que aparecem no botão "News". Só administradores veem esta tela.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {msg && <div className="card mb-4" style={{ borderLeft: "3px solid var(--green)", color: "var(--green-light)", fontSize: "0.85rem" }}>{msg}</div>}

      <div className="card mb-6">
        <button type="button" className="btn-primary" style={{ fontSize: "0.82rem", display: "flex", alignItems: "center", gap: "0.4rem" }}
          onClick={() => setAbrirForm((v) => !v)}>
          {abrirForm ? <X size={14} /> : <Plus size={14} />} {abrirForm ? "Cancelar" : "Adicionar matéria ao blog"}
        </button>

        {abrirForm && (
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

      {materias && materias.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>Nenhuma matéria publicada ainda.</p>
      )}

      {materias && materias.length > 0 && (
        <div className="flex flex-col gap-3">
          {materias.map((n) => (
            <div key={n.id} style={cardStyle}>
              <div className="flex items-start justify-between gap-2">
                <p style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--dourado-light)", marginBottom: "0.3rem" }}>{n.manchete}</p>
                <button type="button" onClick={() => excluir(n)} disabled={excluindo === n.id} title="Excluir matéria"
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#F5B0B0", flexShrink: 0 }}>
                  <Trash2 size={15} />
                </button>
              </div>
              {(n.materia || n.resumo) && (
                <p style={{ color: "#F5ECDD", fontSize: "0.83rem", lineHeight: 1.55, marginBottom: "0.5rem", whiteSpace: "pre-wrap" }}>
                  {n.materia || n.resumo}
                </p>
              )}
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap", fontSize: "0.72rem" }}>
                <span style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
                </span>
                {(n.fontes || []).map((url, i) => (
                  <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#FFE9B0", border: "1px solid rgba(255,233,176,0.4)", borderRadius: "999px", padding: "0.15rem 0.55rem", textDecoration: "none" }}>
                    <LinkIcon size={11} /> {dominio(url)}
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
