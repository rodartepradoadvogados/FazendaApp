"use client";
// Sub-tela: Calendário Sanitário (só leitura) — versão enxuta do card
// Calendário do site (Sanidade > Preventiva > Calendário sanitário): projeta
// as próximas vacinas/exames dos próximos 90 dias e agrupa as que caem perto
// no tempo, sugerindo "vale chamar o veterinário" quando o total de animais
// do agrupamento bate o mínimo configurado em Configurações > Parâmetros.
// Sem visão por mês (lista é o formato natural do celular) e sem lista de
// animais por janela (fica no site por ora) — o acompanhamento em si
// (incluir/excluir animal, decidir veterinário, aplicar) continua todo pela
// Agenda; aqui é só a visão de conjunto, com atalho para lançar financeiro.
import { useRouter } from "next/navigation";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchCalendarioVisao, formatDate, type JanelaCalendario, type JanelaCalendarioEvento } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

const ROTULO_STATUS: Record<string, string> = {
  aberto: "Aguardando decisão", agendado: "Agendado", concluido: "Concluído", cancelado: "Cancelado",
};

type Visao = { janelas: JanelaCalendario[]; min_animais_agrupamento: number; janela_agrupamento_dias: number };

export default function CalendarioSanitario({ onVoltar }: { onVoltar: () => void }) {
  const router = useRouter();
  const { dados, doCache, carregando } = useCarregar<Visao>("menu_calendario_sanitario_visao", () => fetchCalendarioVisao());
  const janelas = dados?.janelas || [];

  return (
    <div>
      <MobVoltar titulo="Calendário Sanitário" onVoltar={onVoltar} />
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
                  background: j.sugerir_veterinario ? "rgba(4,120,87,0.12)" : "transparent",
                  border: j.sugerir_veterinario ? "none" : "1px solid var(--mob-border)",
                }}
              >
                {j.animais_total} animal(is){j.tem_estimativa ? " (estimado)" : ""}{j.sugerir_veterinario ? " · vale chamar o veterinário" : ""}
              </span>
            </div>
            {j.eventos.map((o) => <LinhaEvento key={`${o.calendario_sanitario_id}-${o.data}`} evento={o} router={router} />)}
          </MobCard>
        ))
      )}
    </div>
  );
}

function LinhaEvento({ evento: o, router }: { evento: JanelaCalendarioEvento; router: ReturnType<typeof useRouter> }) {
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
      {(o.usa_cronograma && o.cronograma) || o.servico_financeiro ? (
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.35rem", flexWrap: "wrap" }}>
          {o.usa_cronograma && o.cronograma && (
            <span style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--mob-azul)", background: "rgba(37,99,235,0.1)", borderRadius: 6, padding: "0.15rem 0.45rem" }}>
              Cronograma: {ROTULO_STATUS[o.cronograma.status] || o.cronograma.status}
            </span>
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
