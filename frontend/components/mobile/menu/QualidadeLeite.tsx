"use client";
// Sub-tela Produção: Qualidade do leite (só leitura) — coletas do tanque ou de
// uma vaca específica (CCS, CBT, gordura, proteína...), mais recente primeiro.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchQualidadeLeite, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo } from "@/components/mobile/menu/comum";

type QualidadeRow = {
  numero_matriz: string | null; data_coleta: string; ccs: number | null; cbt: number | null;
  gordura_pct: number | null; proteina_pct: number | null; solidos_totais_pct: number | null; esd_pct: number | null;
};

function num(v?: number | null, casas = 1): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

export default function QualidadeLeite({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ registros: QualidadeRow[] }>("menu_producao_qualidade", fetchQualidadeLeite);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());

  const regs = dados?.registros || [];
  const filtrados = useMemo(
    () => regs.filter((r) => r.data_coleta >= inicio && r.data_coleta <= fim).sort((a, b) => (a.data_coleta < b.data_coleta ? 1 : -1)),
    [regs, inicio, fim]
  );

  return (
    <div>
      <MobVoltar titulo="Qualidade do leite" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_producao_qualidade" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : filtrados.length === 0 ? (
        <Vazio>Nenhuma coleta no período.</Vazio>
      ) : (
        <>
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>{filtrados.length} coleta{filtrados.length !== 1 ? "s" : ""}</p>
          {filtrados.map((r, i) => (
            <MobCard key={`${r.numero_matriz || "tanque"}-${r.data_coleta}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>{r.numero_matriz ? `Nº ${r.numero_matriz}` : "Tanque"}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{formatDate(r.data_coleta)}</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginTop: "0.35rem", fontSize: "0.82rem" }}>
                <span>CCS <strong>{num(r.ccs, 0)}</strong></span>
                <span>CBT <strong>{num(r.cbt, 0)}</strong></span>
                <span>Gordura <strong>{num(r.gordura_pct)}%</strong></span>
                <span>Proteína <strong>{num(r.proteina_pct)}%</strong></span>
              </div>
            </MobCard>
          ))}
        </>
      )}
    </div>
  );
}
