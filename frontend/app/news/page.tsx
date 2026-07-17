"use client";
import { useCallback, useEffect, useState } from "react";
import { Newspaper, ExternalLink, AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { fetchNoticias, type NewsFeed } from "@/lib/api";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function NewsPage() {
  const [dados, setDados] = useState<NewsFeed | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTudo, setVerTudo] = useState(false);

  const carregar = useCallback((tudo: boolean) => {
    setCarregando(true);
    setErro(null);
    fetchNoticias(tudo)
      .then(setDados)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => { carregar(verTudo); }, [carregar, verTudo]);

  return (
    <div style={{ position: "relative", minHeight: "100%" }}>
      {/* Mesmo fundo da tela de login (vaca no Compost Barn, CWD Milk), em
          transparência — fica atrás do conteúdo, sem atrapalhar a leitura. */}
      <div aria-hidden="true" style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden", pointerEvents: "none" }}>
        <img
          src="/images/login-fundo.webp"
          alt=""
          style={{
            position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 60%",
            opacity: 0.1, filter: "grayscale(1) contrast(1.08) brightness(0.95)", mixBlendMode: "luminosity",
          }}
        />
      </div>

      <div className="p-6 animate-in" style={{ position: "relative", zIndex: 1 }}>
        <div className="mb-6 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Newspaper size={22} style={{ color: "var(--dourado)" }} /> News — Pecuária Leiteira
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Manchetes, resumos e links das principais fontes de jornalismo do setor — leite, produtor de leite,
              pecuária leiteira, ordenha, Compost Barn e Free Stall. Mostra só os últimos {dados?.janela_dias ?? 3} dias por site.
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
        {carregando && !dados && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

        {dados && dados.fontes.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>Nenhuma fonte de notícias cadastrada ainda.</p>
        )}

        {dados && dados.fontes.map(({ fonte, noticias }) => (
          <section key={fonte.id} className="card mb-6">
            <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <a href={fonte.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "1.05rem", color: "var(--text)", textDecoration: "none" }}>
                {fonte.nome} <ExternalLink size={14} style={{ color: "var(--text-muted)" }} />
              </a>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{noticias.length} matéria(s)</span>
            </div>

            {fonte.erro && (
              <div className="alert-critico mb-3" style={{ fontSize: "0.8rem" }}>
                <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                <span>
                  Esta fonte está com problema no momento ({fonte.erro}). Peça para o administrador substituir ou
                  corrigir a URL em Configurações &gt; News.
                </span>
              </div>
            )}

            {!fonte.erro && noticias.length === 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Nenhuma matéria sobre pecuária leiteira {verTudo ? "encontrada" : `nos últimos ${dados.janela_dias} dias`}.
              </p>
            )}

            <div className="flex flex-col gap-3">
              {noticias.map((n) => (
                <a key={n.id} href={n.link} target="_blank" rel="noopener noreferrer"
                  style={{
                    display: "block", padding: "0.75rem 0.9rem", borderRadius: "10px",
                    background: "var(--surface-2)", border: "1px solid var(--border)", textDecoration: "none",
                  }}>
                  <p style={{ fontWeight: 700, fontSize: "0.92rem", color: "var(--dourado-light)", marginBottom: "0.2rem" }}>
                    {n.manchete}
                  </p>
                  {n.resumo && <p style={{ color: "var(--text)", fontSize: "0.82rem", lineHeight: 1.5, marginBottom: "0.35rem" }}>{n.resumo}</p>}
                  <p style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
                    {fonte.nome}{n.data_publicacao ? ` · ${formatarData(n.data_publicacao)}` : ""} · Ler no site original
                  </p>
                </a>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
