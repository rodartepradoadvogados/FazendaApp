"use client";
// Sub-tela Produção: Secagens (só leitura) — histórico de secagens, mais
// recente primeiro. Lançar uma nova secagem continua em Lançar > Produção > Secagem.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchSecagensHistorico, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo } from "@/components/mobile/menu/comum";
import { MOTIVOS_SECAGEM } from "@/components/lancamentos/comumForms";

type SecagemRow = {
  numero: string; data: string | null; motivo: string; escore_condicao_corporal: number | null; observacao: string | null;
};

const LABEL_MOTIVO: Record<string, string> = Object.fromEntries(MOTIVOS_SECAGEM.map((m) => [m.v, m.l]));

export default function Secagens({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ secagens: SecagemRow[] }>("menu_producao_secagens", fetchSecagensHistorico);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());

  const regs = dados?.secagens || [];
  const filtrados = useMemo(
    () => regs.filter((r) => !r.data || (r.data >= inicio && r.data <= fim)).sort((a, b) => (a.data || "") < (b.data || "") ? 1 : -1),
    [regs, inicio, fim]
  );

  return (
    <div>
      <MobVoltar titulo="Secagens" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_producao_secagens" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : filtrados.length === 0 ? (
        <Vazio>Nenhuma secagem no período.</Vazio>
      ) : (
        <>
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>{filtrados.length} {filtrados.length !== 1 ? "secagens" : "secagem"}</p>
          {filtrados.map((r, i) => (
            <MobCard key={`${r.numero}-${r.data}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{r.data ? formatDate(r.data) : "—"}</span>
              </div>
              <div style={{ fontSize: "0.82rem", marginTop: "0.3rem" }}>
                {LABEL_MOTIVO[r.motivo] || r.motivo}
                {r.escore_condicao_corporal != null ? ` · ECC ${r.escore_condicao_corporal}` : ""}
              </div>
              {r.observacao && <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>{r.observacao}</div>}
            </MobCard>
          ))}
        </>
      )}
    </div>
  );
}
