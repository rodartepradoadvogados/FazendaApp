"use client";
// Sub-tela: Protocolos IATF em andamento (só leitura).
// Lista SOMENTE as vacas que estão DURANTE o protocolo (etapa ainda pendente):
// número, etapa atual (D0/D7/D9/D11) e a data da próxima etapa.
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchProtocolosIatfAtivos, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, NumAnimal } from "@/components/mobile/menu/comum";

type AnimalStatus = { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null };
type Protocolo = { lancamento_id: number; nome_protocolo: string; data_d0: string; animais: AnimalStatus[] };

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
            {p.animais.map((a) => (
              <div key={a.numero_matriz} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", padding: "0.5rem 0", borderTop: "1px solid var(--mob-border)" }}>
                <NumAnimal>Nº {a.numero_matriz}</NumAnimal>
                <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", textAlign: "right" }}>
                  <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>{a.etapa_atual}</span>
                  {a.data_etapa_atual ? ` · ${formatDate(a.data_etapa_atual)}` : ""}
                </span>
              </div>
            ))}
          </MobCard>
        ))
      )}
    </div>
  );
}
