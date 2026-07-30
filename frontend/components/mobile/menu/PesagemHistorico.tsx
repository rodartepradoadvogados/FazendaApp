"use client";
// Sub-tela Produção: Pesagens — histórico de crescimento (GMD/GPD) por
// animal, mais recente primeiro. Lançar uma pesagem nova continua em
// Lançar > Produção > Pesagem corporal.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchRelatorioPesagemCorporal, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo } from "@/components/mobile/menu/comum";

type LinhaPesagem = {
  numero_matriz: string; grupo_primario: string | null;
  primeira_data: string; primeira_peso: number; ultima_data: string; ultima_peso: number;
  gmd_kg_dia: number | null; gpd_kg_dia: number | null; num_pesagens: number;
};

export default function PesagemHistorico({ onVoltar }: { onVoltar: () => void }) {
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const chave = `menu_producao_pesagens_${inicio}_${fim}`;
  const { dados, doCache, carregando } = useCarregar<{ linhas: LinhaPesagem[] }>(
    chave, () => fetchRelatorioPesagemCorporal({ data_inicio: inicio, data_fim: fim })
  );

  const linhas = useMemo(() => dados?.linhas ?? [], [dados]);

  return (
    <div>
      <MobVoltar titulo="Pesagens" onVoltar={onVoltar} />
      <AvisoCopia chave={chave} mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : linhas.length === 0 ? (
        <Vazio>Nenhuma pesagem no período.</Vazio>
      ) : (
        <>
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>{linhas.length} {linhas.length !== 1 ? "animais" : "animal"}</p>
          {linhas.map((l, i) => (
            <MobCard key={l.numero_matriz} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {l.numero_matriz}</span>
                <strong style={{ color: "var(--mob-verde)", fontSize: "0.95rem" }}>{l.gmd_kg_dia != null ? `${l.gmd_kg_dia} kg/dia` : "—"}</strong>
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.25rem", display: "flex", justifyContent: "space-between" }}>
                <span>{l.grupo_primario ? `Lote ${l.grupo_primario}` : "—"} · {l.num_pesagens} {l.num_pesagens !== 1 ? "pesagens" : "pesagem"}</span>
                <span>GPD {l.gpd_kg_dia ?? "—"}</span>
              </div>
              <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                {formatDate(l.primeira_data)} · {l.primeira_peso} kg → {formatDate(l.ultima_data)} · {l.ultima_peso} kg
              </div>
            </MobCard>
          ))}
        </>
      )}
    </div>
  );
}
