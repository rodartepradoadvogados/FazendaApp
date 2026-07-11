"use client";
// Sub-tela: Calendário Sanitário (só leitura).
// Lista os próximos eventos sanitários agendados (vacinas, protocolos) dos
// próximos 90 dias, em ordem de data — data, evento, alvo e produto.
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchCalendarioSanitario, formatDate, today } from "@/lib/api";
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

  // O backend já filtra pela próxima ocorrência dentro do período; reforçamos os
  // futuros (>= hoje) e a ordem por data.
  const eventos = (dados || [])
    .filter((r) => r.proxima_ocorrencia >= hoje)
    .sort((a, b) => (a.proxima_ocorrencia < b.proxima_ocorrencia ? -1 : 1));

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
            </MobCard>
          );
        })
      )}
    </div>
  );
}
