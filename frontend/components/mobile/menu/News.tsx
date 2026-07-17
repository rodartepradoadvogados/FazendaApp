"use client";
// Sub-tela: News (blog de pecuária leiteira) — mesmo agregador do site
// (manchete + resumo + link, últimos 3 dias por fonte, com "ver tudo"),
// consumindo os mesmos endpoints (GET /news/). Só leitura; cadastro de
// fontes continua exclusivo do site (Configurações > News, admin).
import { useState } from "react";
import { Newspaper, ExternalLink, AlertTriangle } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchNoticias, type NewsFeed } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function News({ onVoltar }: { onVoltar: () => void }) {
  const [verTudo, setVerTudo] = useState(false);
  const chave = verTudo ? "menu_news_tudo" : "menu_news_3d";
  const { dados, doCache, carregando } = useCarregar<NewsFeed>(chave, () => fetchNoticias(verTudo));

  return (
    <div>
      <MobVoltar titulo="News" onVoltar={onVoltar} />
      <AvisoCopia chave={chave} mostrar={doCache} />

      <button type="button" className="mob-btn-2" style={{ marginBottom: "0.9rem" }} onClick={() => setVerTudo((v) => !v)}>
        {verTudo ? "Ver só últimos dias" : "Ver tudo"}
      </button>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados || dados.fontes.length === 0 ? (
        <Vazio>Nenhuma fonte de notícias cadastrada ainda.</Vazio>
      ) : (
        dados.fontes.map(({ fonte, noticias }) => (
          <div key={fonte.id} style={{ marginBottom: "1.2rem" }}>
            <div className="mob-secao" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Newspaper size={15} /> {fonte.nome}
            </div>

            {fonte.erro && (
              <MobCard style={{ marginBottom: "0.6rem", borderLeft: "3px solid var(--mob-vermelho)" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                  <AlertTriangle size={16} style={{ color: "var(--mob-vermelho)", flexShrink: 0, marginTop: "0.1rem" }} />
                  <span style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>
                    Esta fonte está com problema no momento. Peça para o administrador corrigir a URL em
                    Configurações &gt; News, no site.
                  </span>
                </div>
              </MobCard>
            )}

            {!fonte.erro && noticias.length === 0 && (
              <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", marginBottom: "0.6rem" }}>
                Nenhuma matéria {verTudo ? "encontrada" : `nos últimos ${dados.janela_dias} dias`}.
              </p>
            )}

            {noticias.map((n) => (
              <a key={n.id} href={n.link} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>
                <MobCard style={{ marginBottom: "0.6rem" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontWeight: 700, fontSize: "0.94rem", color: "var(--mob-dourado)" }}>{n.manchete}</p>
                      {n.resumo && (
                        <p style={{ fontSize: "0.82rem", color: "var(--mob-text)", marginTop: "0.25rem", lineHeight: 1.45 }}>
                          {n.resumo}
                        </p>
                      )}
                      <p style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.35rem" }}>
                        {n.data_publicacao ? formatarData(n.data_publicacao) : ""}
                      </p>
                    </div>
                    <ExternalLink size={15} style={{ color: "var(--mob-muted)", flexShrink: 0, marginTop: "0.15rem" }} />
                  </div>
                </MobCard>
              </a>
            ))}
          </div>
        ))
      )}
    </div>
  );
}
