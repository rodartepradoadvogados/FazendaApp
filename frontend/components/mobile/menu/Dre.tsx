"use client";
// Sub-tela Financeiro: DRE Gerencial (só leitura) — igual ao site
// (financeiro/page.tsx, aba "dre"): regime de COMPETÊNCIA, agrupado por conta
// gerencial de nível 1 (o próprio /financeiro/lancamentos já traz o código
// truncado no 1º nível em "codigo_conta").
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchLancamentos, fetchOpcoesFinanceiro, fetchPlanoContas, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo, brl } from "@/components/mobile/menu/comum";
import { dentroPeriodo, type Lancamento, type Opcoes } from "@/components/mobile/menu/Financeiro";

type ContaGerencial = { codigo: string; nome: string };

export default function Dre({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ lancamentos: Lancamento[] }>("menu_fin_lancamentos", fetchLancamentos);
  const planoReq = useCarregar<ContaGerencial[]>("menu_fin_plano_contas", fetchPlanoContas);
  const opcoesReq = useCarregar<Opcoes>("menu_fin_opcoes", fetchOpcoesFinanceiro);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [centro, setCentro] = useState("");

  const regs = dados?.lancamentos || [];
  const centros = opcoesReq.dados?.centros_custo || [];
  const nomePorCodigo = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of planoReq.dados || []) m.set(c.codigo, c.nome);
    return m;
  }, [planoReq.dados]);

  const { receitas, despesas, receitaTotal, despesaTotal } = useMemo(() => {
    const filtrados = regs.filter((r) =>
      dentroPeriodo(r.data_competencia, inicio, fim) && (!centro || r.centro_custo === centro)
    );
    const porConta = new Map<string, { receita: number; despesa: number }>();
    for (const r of filtrados) {
      const acc = porConta.get(r.codigo_conta) || { receita: 0, despesa: 0 };
      if (r.tipo === "receita") acc.receita += r.valor;
      else acc.despesa += r.valor;
      porConta.set(r.codigo_conta, acc);
    }
    const linhas = Array.from(porConta.entries()).map(([codigo, v]) => ({
      codigo, nome: nomePorCodigo.get(codigo) || codigo, ...v,
    }));
    return {
      receitas: linhas.filter((l) => l.receita > 0).sort((a, b) => b.receita - a.receita),
      despesas: linhas.filter((l) => l.despesa > 0).sort((a, b) => b.despesa - a.despesa),
      receitaTotal: linhas.reduce((a, l) => a + l.receita, 0),
      despesaTotal: linhas.reduce((a, l) => a + l.despesa, 0),
    };
  }, [regs, inicio, fim, centro, nomePorCodigo]);

  const resultado = receitaTotal - despesaTotal;
  const margem = receitaTotal > 0 ? (resultado / receitaTotal) * 100 : 0;

  return (
    <div>
      <MobVoltar titulo="DRE" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_fin_lancamentos" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

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
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Receita</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 800, color: "var(--mob-verde)" }}>{brl(receitaTotal)}</div>
            </MobCard>
            <MobCard style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Despesa</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 800, color: "var(--mob-vermelho)" }}>{brl(despesaTotal)}</div>
            </MobCard>
            <MobCard style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Resultado</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 800, color: resultado >= 0 ? "var(--mob-verde)" : "var(--mob-vermelho)" }}>{brl(resultado)}</div>
            </MobCard>
            <MobCard style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", fontWeight: 700 }}>Margem</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 800 }}>{margem.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</div>
            </MobCard>
          </div>

          <div className="mob-secao">Receitas por conta</div>
          {receitas.length === 0 ? <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhuma receita no período.</p> : receitas.map((l, i) => (
            <MobCard key={l.codigo} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
              <span style={{ fontSize: "0.88rem", fontWeight: 600, flex: 1, minWidth: 0 }}>{l.nome}</span>
              <strong style={{ color: "var(--mob-verde)" }}>{brl(l.receita)}</strong>
            </MobCard>
          ))}

          <div className="mob-secao">Despesas por conta</div>
          {despesas.length === 0 ? <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhuma despesa no período.</p> : despesas.map((l, i) => (
            <MobCard key={l.codigo} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
              <span style={{ fontSize: "0.88rem", fontWeight: 600, flex: 1, minWidth: 0 }}>{l.nome}</span>
              <strong style={{ color: "var(--mob-vermelho)" }}>{brl(l.despesa)}</strong>
            </MobCard>
          ))}
        </>
      )}
    </div>
  );
}
