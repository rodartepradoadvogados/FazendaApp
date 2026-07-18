"use client";
// Sub-tela: News (blog de pecuária leiteira) — mesmas matérias do site
// (GET /news/), publicadas por nós via Configurações > News (site, admin).
// Só leitura no app.
import { useMemo, useState } from "react";
import { Newspaper, Link as LinkIcon, CalendarDays } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchNoticias, type NewsFeed, type NoticiaNews } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

// Mesmo tratamento de fundo do site: foto do compost barn + camada
// semitransparente na cor da paleta ativa (var(--mob-vinho) já reflete vinho
// ou verde) — texto claro fixo por cima.
const cardStyle: React.CSSProperties = {
  backgroundImage:
    "linear-gradient(color-mix(in srgb, var(--mob-vinho) 76%, transparent), color-mix(in srgb, var(--mob-vinho) 76%, transparent)), url('/images/login-fundo.webp')",
  backgroundSize: "cover", backgroundPosition: "center 55%", border: "1px solid var(--mob-vinho)",
};

export default function News({ onVoltar }: { onVoltar: () => void }) {
  const [verTudo, setVerTudo] = useState(false);
  const chave = verTudo ? "menu_news_tudo" : "menu_news_3d";
  const { dados, doCache, carregando } = useCarregar<NewsFeed>(chave, () => fetchNoticias(verTudo));

  const materias = useMemo(() => {
    if (!dados) return [];
    const todas = dados.fontes.flatMap((f) => f.noticias);
    return [...todas].sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
  }, [dados]);

  return (
    <div>
      <MobVoltar titulo="News" onVoltar={onVoltar} />
      <AvisoCopia chave={chave} mostrar={doCache} />

      <button type="button" className="mob-btn-2" style={{ marginBottom: "0.9rem" }} onClick={() => setVerTudo((v) => !v)}>
        {verTudo ? "Ver só últimos dias" : "Ver tudo"}
      </button>

      {carregando && !dados ? (
        <Carregando />
      ) : materias.length === 0 ? (
        <Vazio>Nenhuma matéria publicada ainda.</Vazio>
      ) : (
        materias.map((n: NoticiaNews) => (
          <MobCard key={n.id} style={{ ...cardStyle, marginBottom: "0.7rem" }}>
            <div className="flex items-start gap-2">
              <Newspaper size={15} style={{ color: "#FFE9B0", flexShrink: 0, marginTop: "0.15rem" }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontWeight: 700, fontSize: "0.94rem", color: "#FFE9B0" }}>{n.manchete}</p>
                {(n.materia || n.resumo) && (
                  <p style={{ fontSize: "0.82rem", color: "#F5ECDD", marginTop: "0.3rem", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                    {n.materia || n.resumo}
                  </p>
                )}
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginTop: "0.45rem", fontSize: "0.7rem" }}>
                  <span style={{ color: "rgba(255,255,255,0.75)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                    <CalendarDays size={11} /> {formatarData(n.data_publicacao)}
                  </span>
                  {(n.fontes || []).map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noopener noreferrer"
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
    </div>
  );
}
