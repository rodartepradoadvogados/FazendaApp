"use client";
// Sub-tela: Protocolos (só leitura) — os 4 tipos juntos, em andamento e
// concluídos, com filtro por tipo. É o espelho no app da Central de
// Protocolos do site, consumindo os MESMOS endpoints
// (/central-protocolos/acompanhamento e /historico).
//
// Aqui não se lança nada: lançar é em Lançar > Protocolos. Mesma divisão do
// resto do app (o Menu é sempre consulta).
import { useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import {
  fetchCentralProtocolosAcompanhamento, fetchCentralProtocolosHistorico, formatDate,
  type LinhaCentralProtocolos,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

const LABEL_TIPO: Record<string, string> = { produtivo: "Produtivo", reprodutivo: "Reprodutivo", sanitario: "Sanitário" };
const COR_TIPO: Record<string, string> = {
  produtivo: "var(--mob-azul)", reprodutivo: "var(--mob-roxo)", sanitario: "var(--mob-verde)",
};

type Aba = "andamento" | "concluidos";

export default function Protocolos({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<Aba>("andamento");
  const [tipo, setTipo] = useState<string>("");

  const ativos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_andamento", () => fetchCentralProtocolosAcompanhamento(),
  );
  const concluidos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_concluidos", () => fetchCentralProtocolosHistorico(),
  );

  const atual = aba === "andamento" ? ativos : concluidos;
  const linhas = (atual.dados || []).filter((l) => !tipo || l.tipo === tipo);

  return (
    <div>
      <MobVoltar titulo="Protocolos" onVoltar={onVoltar} />
      <AvisoCopia chave={aba === "andamento" ? "menu_protocolos_andamento" : "menu_protocolos_concluidos"} mostrar={atual.doCache} />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.7rem" }}>
        {([["andamento", "Em andamento"], ["concluidos", "Concluídos"]] as [Aba, string][]).map(([id, label]) => (
          <button key={id} type="button" className={`mob-pill${aba === id ? " ativa" : ""}`} onClick={() => setAba(id)}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.9rem" }}>
        {([["", "Todos"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"], ["sanitario", "Sanitário"]] as [string, string][]).map(([id, label]) => (
          <button key={id || "todos"} type="button" className={`mob-pill${tipo === id ? " ativa" : ""}`} onClick={() => setTipo(id)}>
            {label}
          </button>
        ))}
      </div>

      {atual.carregando && !atual.dados ? (
        <Carregando />
      ) : !atual.dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : linhas.length === 0 ? (
        <Vazio>
          {aba === "andamento" ? "Nenhum protocolo em andamento" : "Nenhum protocolo concluído"}
          {tipo ? ` do tipo ${LABEL_TIPO[tipo]}.` : "."}
        </Vazio>
      ) : (
        linhas.map((l) => (
          <MobCard key={`${l.origem}-${l.origem_id}`} style={{ marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <span style={{ fontWeight: 800, fontSize: "0.92rem", lineHeight: 1.3 }}>{l.nome}</span>
              <span style={{
                fontSize: "0.68rem", fontWeight: 800, flexShrink: 0, padding: "0.12rem 0.5rem", borderRadius: 999,
                color: COR_TIPO[l.tipo] || "var(--mob-muted)",
                border: `1px solid ${COR_TIPO[l.tipo] || "var(--mob-border)"}`,
              }}>{LABEL_TIPO[l.tipo] || l.tipo}</span>
            </div>
            <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
              {formatDate(l.data_inicio)} a {formatDate(l.data_fim)}
              {l.animais ? ` · ${l.animais} animal(is)` : ""}
            </div>
            <div style={{ fontSize: "0.85rem", marginTop: "0.3rem" }}>
              <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>
                {l.etapas_realizadas}/{l.etapas_total} etapas
              </span>
              {aba === "andamento" && l.etapas_faltam > 0 && (
                <span style={{ color: "var(--mob-muted)" }}> · faltam {l.etapas_faltam}</span>
              )}
              {l.status === "cancelado" && <span style={{ color: "var(--mob-vermelho)" }}> · cancelado</span>}
            </div>
          </MobCard>
        ))
      )}
    </div>
  );
}
