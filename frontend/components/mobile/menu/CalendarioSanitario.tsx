"use client";
// Sub-tela: Calendário Sanitário — versão enxuta do card Calendário do site
// (Sanidade > Preventiva > Calendário sanitário): projeta as próximas
// vacinas/exames dos próximos 90 dias e agrupa as que caem perto no tempo,
// sugerindo "vale chamar o veterinário" quando o total de animais do
// agrupamento bate o mínimo configurado em Configurações > Parâmetros.
// Sem visão por mês (lista é o formato natural do celular).
//
// Aba "Já aplicado" (nova, 10/09/2026): antes esta tela só mostrava o
// futuro — "não mostra o que eu lancei" era o relato — agora reaproveita
// PreventivoHistoricoLista (mesma lista de Histórico > Preventivo).
//
// "Ver quem está na janela" (novo): para eventos agendados POR EVENTO DE VIDA
// (gatilho — ex.: novilha apta, pré-parto), mostra AQUI MESMO (mesmo padrão de
// "drill" de Indicadores.tsx) a lista de quem está na janela deste evento —
// só depois oferece ir para Lançar > Sanidade > Preventiva > Aplicação, já no
// modo "Na janela" e com o evento escolhido, pronto para selecionar quem
// recebe e agendar. Antes o botão pulava direto pra tela de Lançamentos sem
// mostrar ninguém primeiro — a lista existia lá, mas só aparecia depois de
// rolar por Evento/Data/Medicamento, então parecia que "não abria lista".
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MobVoltar, MobCard, MobAviso } from "@/components/mobile/ui";
import { fetchCalendarioVisao, fetchEventosSanitarios, fetchRelatorioEventosVida, formatDate, type JanelaCalendario, type JanelaCalendarioEvento } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { MobPill, LinhaPills } from "@/components/mobile/lancar/comum";
import { PreventivoHistoricoLista } from "@/components/mobile/menu/HistoricoPreventivo";

const ROTULO_STATUS: Record<string, string> = {
  aberto: "Aguardando decisão", agendado: "Agendado", concluido: "Concluído", cancelado: "Cancelado",
};

type Visao = { janelas: JanelaCalendario[]; min_animais_agrupamento: number; janela_agrupamento_dias: number };

export default function CalendarioSanitario({ onVoltar }: { onVoltar: () => void }) {
  const router = useRouter();
  const { dados, doCache, carregando } = useCarregar<Visao>("menu_calendario_sanitario_visao", () => fetchCalendarioVisao());
  const janelas = dados?.janelas || [];
  const [aba, setAba] = useState<"proximos" | "aplicado">("proximos");

  // Eventos elegíveis para "Ver quem está na janela" — só os agendados por
  // evento de vida (gatilho), mesmo critério do relatório que alimenta a
  // tela (GET /sanidade/calendario/relatorio-eventos-vida exige isso).
  const [elegiveis, setElegiveis] = useState<Set<number>>(new Set());
  useEffect(() => {
    fetchEventosSanitarios()
      .then((d: any[]) => setElegiveis(new Set(d.filter((e) => e.tipo_agendamento === "evento" && e.gatilho).map((e) => e.id))))
      .catch(() => {});
  }, []);

  // Drill "Ver quem está na janela" — abre a lista aqui, por dentro da
  // própria sub-tela (ver JanelaAnimais abaixo), em vez de navegar direto.
  const [janelaAberta, setJanelaAberta] = useState<{ id: number; nome: string } | null>(null);
  if (janelaAberta) {
    return (
      <JanelaAnimais
        eventoId={janelaAberta.id}
        eventoNome={janelaAberta.nome}
        onVoltar={() => setJanelaAberta(null)}
        onLancar={() => router.push(`/app/lancar?ir=sanidade_janela&evento_sanitario_id=${janelaAberta.id}`)}
      />
    );
  }

  return (
    <div>
      <MobVoltar titulo="Calendário Sanitário" onVoltar={onVoltar} />

      <LinhaPills>
        <MobPill ativa={aba === "proximos"} onClick={() => setAba("proximos")}>Próximos</MobPill>
        <MobPill ativa={aba === "aplicado"} onClick={() => setAba("aplicado")}>Já aplicado</MobPill>
      </LinhaPills>

      {aba === "aplicado" ? (
        <PreventivoHistoricoLista />
      ) : (
        <>
          <AvisoCopia chave="menu_calendario_sanitario_visao" mostrar={doCache} />

          {dados && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "-0.3rem 0 0.8rem" }}>
              Agrupadas quando caem perto no tempo — mínimo de {dados.min_animais_agrupamento} animais numa janela de {dados.janela_agrupamento_dias} dias.
            </p>
          )}

          {carregando && !dados ? (
            <Carregando />
          ) : !dados ? (
            <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
          ) : janelas.length === 0 ? (
            <Vazio>Nenhum evento sanitário nos próximos 90 dias.</Vazio>
          ) : (
            janelas.map((j) => (
              <MobCard key={j.data_inicio + j.data_fim} style={{ marginBottom: "0.6rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.35rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "0.95rem", color: "var(--mob-azul)" }}>
                    {formatDate(j.data_inicio)}{j.data_fim !== j.data_inicio ? ` – ${formatDate(j.data_fim)}` : ""}
                  </span>
                  <span
                    style={{
                      fontSize: "0.68rem", fontWeight: 700, padding: "0.2rem 0.5rem", borderRadius: 6, whiteSpace: "nowrap",
                      color: j.sugerir_veterinario ? "var(--mob-verde)" : "var(--mob-muted)",
                      background: j.sugerir_veterinario ? "color-mix(in srgb, var(--mob-verde) 12%, transparent)" : "transparent",
                      border: j.sugerir_veterinario ? "none" : "1px solid var(--mob-border)",
                    }}
                  >
                    {j.animais_total} animal(is){j.tem_estimativa ? " (estimado)" : ""}{j.sugerir_veterinario ? " · vale chamar o veterinário" : ""}
                  </span>
                </div>
                {j.eventos.map((o) => (
                  <LinhaEvento
                    key={`${o.calendario_sanitario_id}-${o.data}`}
                    evento={o}
                    router={router}
                    elegivelJanela={elegiveis.has(o.evento_sanitario_id)}
                    onVerJanela={() => setJanelaAberta({ id: o.evento_sanitario_id, nome: o.evento_sanitario_nome })}
                  />
                ))}
              </MobCard>
            ))
          )}
        </>
      )}
    </div>
  );
}

function LinhaEvento({ evento: o, router, elegivelJanela, onVerJanela }: {
  evento: JanelaCalendarioEvento; router: ReturnType<typeof useRouter>; elegivelJanela: boolean; onVerJanela: () => void;
}) {
  return (
    <div style={{ padding: "0.45rem 0", borderTop: "1px solid var(--mob-border)" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem" }}>
        <span style={{ fontWeight: 700, fontSize: "0.86rem" }}>{o.evento_sanitario_nome}</span>
        <span style={{ fontSize: "0.74rem", color: "var(--mob-muted)", flexShrink: 0 }}>{formatDate(o.data)}</span>
      </div>
      <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
        {o.categoria_alvo || "Todos os animais"}
        {" · "}
        {o.animais == null ? "sem estimativa" : <>{o.estimativa ? "~" : ""}{o.animais} animal(is){o.estimativa ? " (última aplicação)" : ""}</>}
      </div>
      {(o.usa_cronograma && o.cronograma) || o.servico_financeiro || elegivelJanela ? (
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.35rem", flexWrap: "wrap" }}>
          {o.usa_cronograma && o.cronograma && (
            <span style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--mob-azul)", background: "color-mix(in srgb, var(--mob-azul) 10%, transparent)", borderRadius: 6, padding: "0.15rem 0.45rem" }}>
              Cronograma: {ROTULO_STATUS[o.cronograma.status] || o.cronograma.status}
            </span>
          )}
          {elegivelJanela && (
            <button
              type="button"
              onClick={onVerJanela}
              style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--mob-dourado-2)", background: "none", border: "none", padding: 0 }}
            >
              Ver quem está na janela →
            </button>
          )}
          {o.servico_financeiro && (
            <button
              type="button"
              onClick={() => router.push(`/app/lancar?servico=${encodeURIComponent(o.servico_financeiro!)}#financeiro`)}
              style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--mob-verde)", background: "none", border: "none", padding: 0 }}
            >
              $ Lançar financeiro
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}

// ── "Ver quem está na janela" — lista de quem está na janela deste evento,
// ANTES de ir para o lançamento (mesmo padrão de "drill" de Indicadores.tsx:
// mostra a lista aqui dentro; só o botão do fim navega, e já leva o evento
// escolhido — ver deep-link `ir=sanidade_janela` em FormSanidade.tsx).
function JanelaAnimais({ eventoId, eventoNome, onVoltar, onLancar }: {
  eventoId: number; eventoNome: string; onVoltar: () => void; onLancar: () => void;
}) {
  const [dados, setDados] = useState<{ animais: { numero_matriz: string; nome: string | null; situacao_janela?: string; dias_para_fechar_janela?: number | null }[] } | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setCarregando(true); setErro(null);
    fetchRelatorioEventosVida({ eventoSanitarioId: eventoId })
      .then((r: any) => { if (vivo) setDados(r); })
      .catch((e) => { if (vivo) setErro(e instanceof Error ? e.message : "Erro ao carregar a janela."); })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [eventoId]);

  const lista = dados?.animais || [];

  return (
    <div>
      <MobVoltar titulo={eventoNome} onVoltar={onVoltar} />
      {carregando ? (
        <Carregando />
      ) : erro ? (
        <MobAviso tipo="erro">{erro}</MobAviso>
      ) : !lista.length ? (
        <Vazio>Nenhum animal na janela agora.</Vazio>
      ) : (
        <>
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>
            {lista.length} animal(is) na janela
          </p>
          {lista.map((a) => (
            <div key={a.numero_matriz} className="mob-card" style={{ padding: "0.75rem 0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1.05rem", minWidth: "3rem" }}>{a.numero_matriz}</span>
              <span style={{ flex: 1, minWidth: 0, fontSize: "0.82rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {a.nome || "—"}
              </span>
              {a.situacao_janela === "na_janela" && a.dias_para_fechar_janela != null && (
                <span style={{ fontSize: "0.7rem", fontWeight: 700, color: "var(--mob-dourado-2)", flexShrink: 0 }}>
                  fecha em {a.dias_para_fechar_janela}d
                </span>
              )}
            </div>
          ))}
          <button type="button" className="mob-btn" style={{ marginTop: "0.8rem" }} onClick={onLancar}>
            Lançar aplicação para estes animais →
          </button>
        </>
      )}
    </div>
  );
}
