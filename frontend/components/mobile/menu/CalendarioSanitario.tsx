"use client";
// Sub-tela: Calendário Sanitário (só leitura).
// Lista os próximos eventos sanitários agendados (vacinas, protocolos) dos
// próximos 90 dias, em ordem de data — data, evento, alvo e produto. Regras
// com "usa_cronograma" ganham um resumo do cronograma em aberto/mais recente
// (status, veterinário/própria, contagem de animais) — o acompanhamento em
// si (incluir/excluir animal, decidir veterinário, aplicar) continua todo
// pela Agenda; aqui é só a visão de conjunto.
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchCalendarioSanitario, fetchCronogramasSanitarios, formatDate, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type Regra = {
  id: number;
  evento_sanitario_nome: string;
  categoria_alvo?: string | null;
  produto?: string | null;
  principio_ativo_nome?: string | null;
  doenca_nome?: string | null;
  dosagem?: string | null;
  observacao?: string | null;
  proxima_ocorrencia: string;
  usa_cronograma?: boolean;
};

type Cronograma = {
  id: number;
  calendario_sanitario_id: number;
  data_evento: string;
  status: string;
  modo_execucao: string | null;
  veterinario_nome: string | null;
  animais_contagem: { sugerido: number; incluido: number; excluido: number; aplicado: number };
};

const ROTULO_STATUS: Record<string, string> = {
  aberto: "Aguardando decisão", agendado: "Agendado", concluido: "Concluído", cancelado: "Cancelado",
};

function maisDias(iso: string, dias: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return d.toISOString().split("T")[0];
}

export default function CalendarioSanitario({ onVoltar }: { onVoltar: () => void }) {
  const hoje = today();
  const { dados, doCache, carregando } = useCarregar<Regra[]>("menu_calendario_sanitario", () =>
    fetchCalendarioSanitario({ dataInicio: hoje, dataFim: maisDias(hoje, 90) })
  );
  const { dados: cronogramas } = useCarregar<Cronograma[]>("menu_cronogramas_sanitarios", () =>
    fetchCronogramasSanitarios()
  );

  // O backend já filtra pela próxima ocorrência dentro do período; reforçamos os
  // futuros (>= hoje) e a ordem por data.
  const eventos = (dados || [])
    .filter((r) => r.proxima_ocorrencia >= hoje)
    .sort((a, b) => (a.proxima_ocorrencia < b.proxima_ocorrencia ? -1 : 1));

  // fetchCronogramasSanitarios já devolve em ordem de data_evento decrescente;
  // o primeiro que achamos por regra é o mais recente (aberto/agendado ou,
  // na falta desse, o último concluído/cancelado).
  const cronogramaPorRegra = new Map<number, Cronograma>();
  for (const c of cronogramas || []) {
    if (!cronogramaPorRegra.has(c.calendario_sanitario_id)) cronogramaPorRegra.set(c.calendario_sanitario_id, c);
  }

  return (
    <div>
      <MobVoltar titulo="Calendário Sanitário" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_calendario_sanitario" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : eventos.length === 0 ? (
        <Vazio>Nenhum evento sanitário nos próximos 90 dias.</Vazio>
      ) : (
        eventos.map((r) => {
          const produto = r.produto || r.principio_ativo_nome;
          const cron = r.usa_cronograma ? cronogramaPorRegra.get(r.id) : undefined;
          return (
            <MobCard key={r.id} style={{ marginBottom: "0.6rem" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1rem", color: "var(--mob-azul)", flexShrink: 0 }}>
                  {formatDate(r.proxima_ocorrencia)}
                </span>
                <span style={{ fontWeight: 700, fontSize: "0.98rem", flex: 1, minWidth: 0 }}>{r.evento_sanitario_nome}</span>
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.25rem" }}>
                Alvo: {r.categoria_alvo || "Todos os animais"}
              </div>
              {(produto || r.dosagem) && (
                <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                  {produto}{produto && r.dosagem ? " · " : ""}{r.dosagem || ""}
                </div>
              )}
              {r.doenca_nome && (
                <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>Doença: {r.doenca_nome}</div>
              )}
              {cron && (
                <div
                  style={{
                    marginTop: "0.45rem", paddingTop: "0.45rem", borderTop: "1px dashed var(--mob-border)",
                    fontSize: "0.8rem", color: "var(--mob-text)",
                  }}
                >
                  <strong>Cronograma:</strong> {ROTULO_STATUS[cron.status] || cron.status}
                  {" · "}
                  {cron.modo_execucao === "veterinario"
                    ? cron.veterinario_nome || "Veterinário"
                    : cron.modo_execucao === "propria"
                    ? "Equipe própria"
                    : "sem execução definida"}
                  <br />
                  <span style={{ color: "var(--mob-muted)" }}>
                    {cron.animais_contagem.incluido} incluído(s) · {cron.animais_contagem.aplicado} aplicado(s)
                    {cron.animais_contagem.sugerido > 0 ? ` · ${cron.animais_contagem.sugerido} aguardando decisão` : ""}
                  </span>
                </div>
              )}
            </MobCard>
          );
        })
      )}
    </div>
  );
}
