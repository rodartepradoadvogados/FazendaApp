"use client";
import { useCallback, useEffect, useState } from "react";
import { Newspaper, Link as LinkIcon, AlertTriangle, Loader2, RefreshCw, CalendarDays } from "lucide-react";
import { fetchNoticias, type NoticiaNews } from "@/lib/api";
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

export default function NewsPage() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTudo, setVerTudo] = useState(false);

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

      <div className="flex flex-col gap-4">
        {materias && materias.map((n, i) => (
          <div key={n.id} style={{ position: "relative", padding: "1.1rem 1.2rem", borderRadius: "12px", ...estiloCardMateria(i) }}>
            <p style={{ fontWeight: 700, fontSize: "1.05rem", color: "var(--dourado-light)", marginBottom: "0.4rem" }}>
              {n.manchete}
            </p>
            {(n.materia || n.resumo) && (
              <p style={{ color: "#F5ECDD", fontSize: "0.88rem", lineHeight: 1.6, marginBottom: "0.6rem", whiteSpace: "pre-wrap" }}>
                {n.materia || n.resumo}
              </p>
            )}
            <div className="flex items-center gap-2" style={{ flexWrap: "wrap", fontSize: "0.74rem" }}>
              <span style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                <CalendarDays size={12} /> Publicado em {formatarData(n.data_publicacao)}
              </span>
              {(n.fontes || []).map((url, i) => (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                  style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "#FFE9B0", border: "1px solid rgba(255,233,176,0.4)", borderRadius: "999px", padding: "0.15rem 0.6rem", textDecoration: "none" }}>
                  <LinkIcon size={11} /> {dominio(url)}
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
