"use client";
// Sub-tela Financeiro: Extrato completo (só leitura) — igual à sub-aba
// "Extrato" do site (financeiro/page.tsx, TabelaContas): todos os lançamentos
// (pagos e em aberto, receitas e despesas) no período de vencimento, com
// filtros de tipo, centro de custo e status de pagamento.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { LinhaPills, MobPill } from "@/components/mobile/lancar/comum";
import { fetchLancamentos, fetchOpcoesFinanceiro, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo, brl } from "@/components/mobile/menu/comum";
import { dentroPeriodo, TIPOS_FILTRO, type Lancamento, type Opcoes, type TipoFiltro } from "@/components/mobile/menu/Financeiro";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";

const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "data_vencimento", rotulo: "Vencimento" },
  { chave: "valor", rotulo: "Valor" },
  { chave: "descricao", rotulo: "Descrição" },
  { chave: "centro_custo", rotulo: "Centro de custo" },
];

const STATUS_PAGAMENTO = [
  { chave: "todos", rotulo: "Todos" },
  { chave: "pagas", rotulo: "Pagas" },
  { chave: "abertas", rotulo: "Em aberto" },
] as const;
type StatusPagamento = (typeof STATUS_PAGAMENTO)[number]["chave"];

export default function ExtratoCompleto({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ lancamentos: Lancamento[] }>("menu_fin_lancamentos", fetchLancamentos);
  const opcoesReq = useCarregar<Opcoes>("menu_fin_opcoes", fetchOpcoesFinanceiro);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [centro, setCentro] = useState("");
  const [tipo, setTipo] = useState<TipoFiltro>("ambos");
  const [status, setStatus] = useState<StatusPagamento>("todos");

  const regs = dados?.lancamentos || [];
  const centros = opcoesReq.dados?.centros_custo || [];

  const filtrados = useMemo(() => {
    return regs
      .filter((r) => dentroPeriodo(r.data_vencimento || r.data_competencia, inicio, fim))
      .filter((r) => !centro || r.centro_custo === centro)
      .filter((r) => tipo === "ambos" || r.tipo === tipo)
      .filter((r) => status === "todos" || (status === "pagas" ? !!r.data_pagamento : !r.data_pagamento))
      .sort((a, b) => (a.data_vencimento || "") < (b.data_vencimento || "") ? 1 : -1);
  }, [regs, inicio, fim, centro, tipo, status]);
  // useOrdenacao assume o controle só depois que o usuário escolhe um campo em
  // SeletorOrdenacao; até lá, `filtrados` já vem em ordem (vencimento desc).
  const ord = useOrdenacao(filtrados);

  const total = filtrados.reduce((a, r) => a + (r.tipo === "receita" ? r.valor : -r.valor), 0);

  return (
    <div>
      <MobVoltar titulo="Extrato completo" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_fin_lancamentos" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      <LinhaPills>
        {TIPOS_FILTRO.map((t) => (
          <MobPill key={t.chave} ativa={tipo === t.chave} onClick={() => setTipo(t.chave)}>{t.rotulo}</MobPill>
        ))}
      </LinhaPills>
      <LinhaPills>
        {STATUS_PAGAMENTO.map((s) => (
          <MobPill key={s.chave} ativa={status === s.chave} onClick={() => setStatus(s.chave)}>{s.rotulo}</MobPill>
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
          <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />

          <MobCard style={{ marginBottom: "0.8rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>{filtrados.length} lançamento{filtrados.length !== 1 ? "s" : ""}</span>
            <strong style={{ fontSize: "1.05rem", color: total >= 0 ? "var(--mob-verde)" : "var(--mob-vermelho)" }}>{brl(total)}</strong>
          </MobCard>

          {ord.linhasOrdenadas.length === 0 ? (
            <Vazio>Nenhum lançamento encontrado nesse filtro.</Vazio>
          ) : (
            ord.linhasOrdenadas.map((r, i) => (
              <MobCard key={r.id} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.92rem", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.descricao || r.fornecedor || "—"}
                  </span>
                  <strong style={{ color: r.tipo === "receita" ? "var(--mob-verde)" : "var(--mob-vermelho)", whiteSpace: "nowrap" }}>{brl(r.valor)}</strong>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.25rem" }}>
                  {r.fornecedor ? `${r.fornecedor} · ` : ""}{r.centro_custo}
                </div>
                <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem", display: "flex", justifyContent: "space-between" }}>
                  <span>Venc. {r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</span>
                  <span style={{ fontWeight: 700, color: r.data_pagamento ? "var(--mob-verde)" : "var(--mob-ambar)" }}>
                    {r.data_pagamento ? `Pago em ${formatDate(r.data_pagamento)}` : "Em aberto"}
                  </span>
                </div>
              </MobCard>
            ))
          )}
        </>
      )}
    </div>
  );
}
