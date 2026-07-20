"use client";
import { useCallback, useEffect, useState } from "react";
import { Newspaper, Link as LinkIcon, AlertTriangle, Loader2, RefreshCw, CalendarDays, ArrowRight } from "lucide-react";
import { fetchNoticias, type NoticiaNews } from "@/lib/api";
import { fundoMateria } from "@/lib/newsVisual";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

// Ilustração de uma matéria: foto do banco (#news-redesign) quando a matéria
// tem `imagem`; senão cai no fundo temático rotativo já usado no resto do
// site (mesma foto por índice, sempre a mesma combinação).
function imagemMateria(n: NoticiaNews, index: number): string {
  return n.imagem || fundoMateria(index);
}

export default function NewsPage() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTudo, setVerTudo] = useState(false);
  const [expandida, setExpandida] = useState<number | null>(null);

  const carregar = useCallback((tudo: boolean) => {
    setCarregando(true);
    setErro(null);
    fetchNoticias(tudo)
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
        setMaterias(todas);
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => { carregar(verTudo); }, [carregar, verTudo]);

  const destaque = materias && materias.length ? materias[0] : null;
  const restantes = materias && materias.length > 1 ? materias.slice(1) : [];

  return (
    <div className="p-6 animate-in">
      <div className="mb-6 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Newspaper size={22} style={{ color: "var(--dourado)" }} /> News — Nosso blog de Pecuária Leiteira
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Matérias escritas por nós sobre leite, produtor de leite, pecuária leiteira, ordenha, Compost Barn e Free Stall.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
            onClick={() => carregar(verTudo)} disabled={carregando}>
            {carregando ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <RefreshCw size={14} />}
            Atualizar
          </button>
          <button className={verTudo ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.78rem" }}
            onClick={() => setVerTudo((v) => !v)}>
            {verTudo ? "Ver só últimos dias" : "Ver tudo"}
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={16} /> <span>Não foi possível carregar as notícias: {erro}.</span></div>}
      {carregando && !materias && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {materias && materias.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>Nenhuma matéria publicada ainda.</p>
      )}

      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {destaque && (
          <article
            className="rounded-2xl overflow-hidden flex flex-col md:flex-row"
            style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
          >
            <div className="md:w-3/5 relative" style={{ minHeight: "260px" }}>
              <img src={imagemMateria(destaque, 0)} alt="" className="w-full h-full object-cover" style={{ minHeight: "260px", maxHeight: "420px" }} />
              {destaque.categoria && (
                <span className="absolute top-4 left-4" style={{
                  fontSize: "0.68rem", fontWeight: 700, padding: "0.3rem 0.75rem", borderRadius: "999px",
                  textTransform: "uppercase", letterSpacing: "0.03em", background: "var(--pill-active-bg, var(--vinho))",
                  color: "var(--pill-active-fg, #fff)", backdropFilter: "blur(4px)",
                }}>
                  {destaque.categoria}
                </span>
              )}
            </div>
            <div className="md:w-2/5 p-6 md:p-8 flex flex-col justify-center">
              <div className="flex items-center gap-2 mb-3" style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                <CalendarDays size={12} /> Publicado em {formatarData(destaque.data_publicacao)}
              </div>
              <h2 className="text-2xl font-bold mb-3" style={{ color: "var(--dourado-light)", lineHeight: 1.25 }}>
                {destaque.manchete}
              </h2>
              {(destaque.materia || destaque.resumo) && (
                <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: "1rem" }}
                  className={expandida === destaque.id ? "" : "line-clamp-3"}>
                  {destaque.materia || destaque.resumo}
                </p>
              )}
              {(destaque.materia || destaque.resumo) && (destaque.materia || destaque.resumo)!.length > 220 && (
                <button className="self-start mb-3" style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.35rem" }}
                  onClick={() => setExpandida(expandida === destaque.id ? null : destaque.id)}>
                  {expandida === destaque.id ? "Mostrar menos" : "Ler artigo completo"} <ArrowRight size={14} />
                </button>
              )}
              {!!(destaque.fontes || []).length && (
                <div className="flex flex-wrap gap-2 mt-auto">
                  {(destaque.fontes || []).map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={{
                      display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem",
                      color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: "999px",
                      padding: "0.15rem 0.6rem", textDecoration: "none",
                    }}>
                      <LinkIcon size={10} /> {dominio(url)}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </article>
        )}

        {!!restantes.length && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {restantes.map((n, i) => (
              <article key={n.id} className="rounded-xl overflow-hidden flex flex-col"
                style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
                <div className="relative" style={{ height: "160px" }}>
                  <img src={imagemMateria(n, i + 1)} alt="" className="w-full h-full object-cover" />
                  {n.categoria && (
                    <span className="absolute top-3 left-3" style={{
                      fontSize: "0.62rem", fontWeight: 700, padding: "0.22rem 0.6rem", borderRadius: "999px",
                      textTransform: "uppercase", letterSpacing: "0.03em", background: "var(--pill-active-bg, var(--vinho))",
                      color: "var(--pill-active-fg, #fff)",
                    }}>
                      {n.categoria}
                    </span>
                  )}
                </div>
                <div className="p-4 flex flex-col flex-1">
                  <h3 className="font-bold mb-2" style={{ fontSize: "1rem", color: "var(--dourado-light)", lineHeight: 1.35 }}>
                    {n.manchete}
                  </h3>
                  {(n.materia || n.resumo) && (
                    <p className="line-clamp-3 flex-1" style={{ color: "var(--text-muted)", fontSize: "0.82rem", lineHeight: 1.55, marginBottom: "0.75rem" }}>
                      {n.materia || n.resumo}
                    </p>
                  )}
                  <div className="pt-3 flex items-center justify-between" style={{ borderTop: "1px solid var(--border)", fontSize: "0.7rem", color: "var(--text-muted)" }}>
                    <span className="flex items-center gap-1"><CalendarDays size={11} /> {formatarData(n.data_publicacao)}</span>
                    {!!(n.fontes || []).length && (
                      <a href={n.fontes![0]} target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--text-muted)", textDecoration: "none" }}>
                        <LinkIcon size={10} /> {dominio(n.fontes![0])}
                      </a>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
