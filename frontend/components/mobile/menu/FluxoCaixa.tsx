"use client";
// Sub-tela Financeiro: Fluxo de caixa (só leitura) — igual ao "Fluxo de Caixa"
// do site (financeiro/page.tsx, aba "fluxo"), só que agregado por mês e sem
// o detalhamento por conta. Regime de CAIXA: agrupa por data_pagamento.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { LinhaPills, MobPill } from "@/components/mobile/lancar/comum";
import { fetchLancamentos, fetchOpcoesFinanceiro, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo, brl } from "@/components/mobile/menu/comum";
import { dentroPeriodo, TIPOS_FILTRO, type Lancamento, type Opcoes, type TipoFiltro } from "@/components/mobile/menu/Financeiro";

export default function FluxoCaixa({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ lancamentos: Lancamento[] }>("menu_fin_lancamentos", fetchLancamentos);
  const opcoesReq = useCarregar<Opcoes>("menu_fin_opcoes", fetchOpcoesFinanceiro);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [centro, setCentro] = useState("");
  const [tipo, setTipo] = useState<TipoFiltro>("ambos");

  const regs = dados?.lancamentos || [];
  const centros = opcoesReq.dados?.centros_custo || [];

  const meses = useMemo(() => {
    const filtrados = regs.filter((r) =>
      dentroPeriodo(r.data_pagamento, inicio, fim) &&
      (!centro || r.centro_custo === centro) &&
      (tipo === "ambos" || r.tipo === tipo)
    );
    const porMes = new Map<string, { entradas: number; saidas: number }>();
    for (const r of filtrados) {
      const mes = (r.data_pagamento || "").slice(0, 7);
      const acc = porMes.get(mes) || { entradas: 0, saidas: 0 };
      if (r.tipo === "receita") acc.entradas += r.valor;
      else acc.saidas += r.valor;
      porMes.set(mes, acc);
    }
    let acumulado = 0;
    return Array.from(porMes.entries())
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([mes, v]) => {
        acumulado += v.entradas - v.saidas;
        return { mes, ...v, saldo: v.entradas - v.saidas, acumulado };
      });
  }, [regs, inicio, fim, centro, tipo]);

  const totalEntradas = meses.reduce((a, m) => a + m.entradas, 0);
  const totalSaidas = meses.reduce((a, m) => a + m.saidas, 0);

  function fmtMes(m: string): string {
    const [ano, mes] = m.split("-");
    return new Date(Number(ano), Number(mes) - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  }

  return (
    <div>
      <MobVoltar titulo="Fluxo de caixa" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_fin_lancamentos" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      <LinhaPills>
        {TIPOS_FILTRO.map((t) => (
          <MobPill key={t.chave} ativa={tipo === t.chave} onClick={() => setTipo(t.chave)}>{t.rotulo}</MobPill>
        ))}
      </LinhaPills>

      {centros.length > 0 && (
        <select className="mob-input" value={centro} onChange={(e) => setCentro(e.target.value)} style={{ marginBottom: "0.8rem" }}>
          <option value="">Todos os centros de custo</option>
          {centros.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      )}

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem", marginBottom: "0.9rem" }}>
            <MobCard style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Entradas</div>
              <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--mob-verde)" }}>{brl(totalEntradas)}</div>
            </MobCard>
            <MobCard style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Saídas</div>
              <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--mob-vermelho)" }}>{brl(totalSaidas)}</div>
            </MobCard>
          </div>

          {meses.length === 0 ? (
            <Vazio>Nenhum lançamento pago nesse período.</Vazio>
          ) : (
            meses.map((m, i) => (
              <MobCard key={m.mes} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.6rem" }}>
                <div style={{ fontWeight: 800, fontSize: "0.95rem", marginBottom: "0.5rem", textTransform: "capitalize" }}>{fmtMes(m.mes)}</div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "0.2rem" }}>
                  <span style={{ color: "var(--mob-muted)" }}>Entradas</span>
                  <strong style={{ color: "var(--mob-verde)" }}>{brl(m.entradas)}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "0.2rem" }}>
                  <span style={{ color: "var(--mob-muted)" }}>Saídas</span>
                  <strong style={{ color: "var(--mob-vermelho)" }}>{brl(m.saidas)}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.35rem", marginTop: "0.3rem" }}>
                  <span style={{ fontWeight: 700 }}>Saldo do mês</span>
                  <strong>{brl(m.saldo)}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>
                  <span>Acumulado</span>
                  <span>{brl(m.acumulado)}</span>
                </div>
              </MobCard>
            ))
          )}
        </>
      )}
    </div>
  );
}
