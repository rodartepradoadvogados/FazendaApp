"use client";
// Sub-tela: Protocolos IATF (só leitura).
// Enquanto em andamento: lista as vacas com etapa ainda pendente (D0/D7/D9/D11).
// Ao concluir tudo (D11 com baixa), o protocolo continua aparecendo por mais
// um ciclo — mas a preocupação muda: mostra a data do próximo serviço
// (D11 + intervalo de visita reprodutiva) e as candidatas herd-wide ao
// próximo repasse (mesmo critério da Agenda) — ver tarefa #369.
import { AlertTriangle, Check } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchProtocolosIatfAtivos, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, NumAnimal } from "@/components/mobile/menu/comum";

type AnimalStatus = { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; d0_confirmado?: boolean };
type Candidata = { numero_matriz: string; sit_rep: string | null; del_dias: number | null; motivo: string };
type Protocolo = {
  lancamento_id: number; nome_protocolo: string; data_d0: string; animais: AnimalStatus[];
  concluido?: boolean; data_d11?: string; proxima_visita?: string; candidatas_proxima_visita?: Candidata[];
};

export default function ProtocolosIatf({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Protocolo[]>("menu_iatf_ativos", fetchProtocolosIatfAtivos);

  return (
    <div>
      <MobVoltar titulo="Protocolos IATF" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_iatf_ativos" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : dados.length === 0 ? (
        <Vazio>Nenhum protocolo IATF em andamento.</Vazio>
      ) : (
        dados.map((p) => (
          <MobCard key={p.lancamento_id} style={{ marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.4rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1rem" }}>{p.nome_protocolo || "Protocolo IATF"}</span>
              <span style={{ fontSize: "0.76rem", color: "var(--mob-muted)", flexShrink: 0 }}>D0 · {formatDate(p.data_d0)}</span>
            </div>

            {p.concluido ? (
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0", color: "var(--mob-verde)", fontWeight: 700, fontSize: "0.85rem" }}>
                  Concluído — inseminado em {p.data_d11 ? formatDate(p.data_d11) : "—"}
                </div>
                <div style={{ fontSize: "0.85rem", padding: "0.3rem 0", borderTop: "1px solid var(--mob-border)" }}>
                  Próximo serviço: <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>{p.proxima_visita ? formatDate(p.proxima_visita) : "—"}</span>
                </div>
                {(p.candidatas_proxima_visita || []).length > 0 && (
                  <div style={{ marginTop: "0.3rem" }}>
                    <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginBottom: "0.2rem" }}>
                      Animais que provavelmente serão inseminados nesse dia:
                    </div>
                    {(p.candidatas_proxima_visita || []).map((c) => (
                      <div key={c.numero_matriz} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", padding: "0.4rem 0", borderTop: "1px solid var(--mob-border)" }}>
                        <NumAnimal>Nº {c.numero_matriz}</NumAnimal>
                        <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{c.motivo}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              p.animais.map((a) => (
                <div key={a.numero_matriz} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", padding: "0.5rem 0", borderTop: "1px solid var(--mob-border)" }}>
                  <div>
                    <NumAnimal>Nº {a.numero_matriz}</NumAnimal>
                    {a.d0_confirmado ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.2rem", fontSize: "0.7rem", color: "var(--mob-verde)", marginTop: "0.1rem" }}>
                        <Check size={11} /> D0 confirmado
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.2rem", fontSize: "0.7rem", color: "var(--mob-ambar)", marginTop: "0.1rem" }}>
                        <AlertTriangle size={11} /> D0 não confirmado
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", textAlign: "right" }}>
                    <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>{a.etapa_atual}</span>
                    {a.data_etapa_atual ? ` · ${formatDate(a.data_etapa_atual)}` : ""}
                  </span>
                </div>
              ))
            )}
          </MobCard>
        ))
      )}
    </div>
  );
}
