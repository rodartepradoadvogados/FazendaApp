"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import {
  BarChart3, Filter, Wallet, BookOpen, FileText, Clock, CheckCircle2, Circle, Receipt, X, Check, Building2, Layers, Search, Users, Plus,
  RefreshCw, Paperclip, Pencil, ChevronDown, ChevronRight,
} from "lucide-react";
import {
  fetchLancamentos, marcarPagoFinanceiro, criarBaixaLote, fetchOpcoesFinanceiro, fetchPlanoContas, fetchPatrimonio,
  fetchPessoas, fetchFolhaPagamento, criarFolhaPagamento, atualizarFolhaPagamento, fetchRmca, formatBRL, formatDate,
  criarVale,
} from "@/lib/api";
import {
  ComposedChart, Bar, Line, LineChart, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell, CartesianGrid,
} from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { Modal } from "@/components/Modal";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { TabBar, SecaoRecolhivel } from "@/components/ui";
import { RESPONSAVEIS } from "@/lib/constants";

const COLUNAS_LANCAMENTOS = [
  { header: "Nº lanç.", key: "numero_lancamento" }, { header: "Data", key: "data" },
  { header: "Descrição", key: "descricao" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
  { header: "Centro custo", key: "centro_custo" }, { header: "Documento", key: "documento" },
  { header: "Valor", key: "valor" }, { header: "Pago", key: "valor_pago" }, { header: "Conta bancária", key: "conta_bancaria" },
];
const COLUNAS_LIVRO = [
  { header: "Data", key: "dataFmt" }, { header: "Descrição", key: "descricao" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
  { header: "Entrada", key: "entrada" }, { header: "Saída", key: "saida" }, { header: "Saldo", key: "saldo" },
];

type Lanc = {
  id: number; numero_lancamento: string | null;
  tipo: string; valor: number; valor_pago: number | null; desconto_acrescimo: number | null;
  centro_custo: string; codigo_conta: string; conta_completa: string;
  descricao: string; fornecedor: string; responsavel: string | null;
  tipo_documento: string | null; numero_documento: string | null; numero_documento_pagamento: string | null;
  conta_bancaria: string | null; forma_pagamento: string | null; data_vencimento_cartao: string | null; entregue: boolean | null;
  parcela_num: number | null; parcela_total: number | null;
  data_competencia: string | null; data_pagamento: string | null; data_vencimento: string | null; data_emissao: string | null;
  mes_competencia: string | null; mes_caixa: string | null;
  itens?: { produto: string }[];
};

type Rel = "fluxo" | "dre" | "livro" | "a_pagar" | "a_receber" | "pagas" | "recebidas" | "extrato" | "patrimonio" | "lote" | "pagamento" | "recebimento" | "folha" | "rmca";
const RELATORIOS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "fluxo", label: "Fluxo de Caixa", icon: Wallet, desc: "Entradas × saídas por regime de caixa" },
  { id: "dre", label: "DRE Gerencial", icon: FileText, desc: "Resultado por competência" },
  { id: "livro", label: "Livro Caixa", icon: BookOpen, desc: "Lançamentos com saldo acumulado" },
];
const INDICADORES: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "rmca", label: "RMCA", icon: BarChart3, desc: "Receita do leite menos custo de alimentação — gerencial e físico lado a lado" },
];
const CONTAS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "a_pagar", label: "Contas a pagar", icon: Clock, desc: "Despesas em aberto (sem data de pagamento)" },
  { id: "a_receber", label: "Contas a receber", icon: Clock, desc: "Receitas em aberto (sem data de recebimento)" },
  { id: "pagas", label: "Contas pagas", icon: CheckCircle2, desc: "Despesas já quitadas" },
  { id: "recebidas", label: "Contas recebidas", icon: CheckCircle2, desc: "Receitas já recebidas" },
  { id: "extrato", label: "Extrato completo", icon: Receipt, desc: "Todos os lançamentos, com ou sem baixa" },
];
const CONTAS_IDS = new Set(CONTAS.map((c) => c.id));
const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;
const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };
const fmtMes = (m: string) => m?.slice(2) ?? "";

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <div className="kpi-card"><p className="kpi-value" style={{ fontSize: "1.25rem", color: c }}>{v}</p><p className="kpi-label">{l}</p></div>;
}

export default function FinanceiroPage() {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rel, setRel] = useState<Rel>("a_pagar");
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [centro, setCentro] = useState("");
  const [contaBanco, setContaBanco] = useState("");
  const [exp, setExp] = useState<Set<string>>(new Set());
  const toggleExp = (k: string) => setExp((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const [contasBancarias, setContasBancarias] = useState<string[]>([]);
  // Nota a tratar (pré-selecionada) quando se chega às sub-abas de
  // Pagamento/Recebimento vindo da lista de Contas a pagar/receber ou da Agenda.
  const [notaAlvoRef, setNotaAlvoRef] = useState<string | null>(null);
  const [planoContas, setPlanoContas] = useState<{ codigo: string; nome: string; nivel: number }[]>([]);
  const [visaoFluxo, setVisaoFluxo] = useState<"mensal" | "diario">("mensal");

  const recarregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    recarregar();
    fetchOpcoesFinanceiro().then((d) => setContasBancarias(d.contas_bancarias || [])).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
  }, []);

  // Vindo da Agenda (link "Ir para Financeiro" de uma conta a pagar/receber
  // vencendo) — abre a sub-aba de Pagamento/Recebimento certa e já pré-seleciona
  // a nota informada, em vez de dar baixa direto na lista.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const ir = qs.get("ir");
    if (ir === "a_pagar") setRel("pagamento");
    else if (ir === "a_receber") setRel("recebimento");
    else if (ir && ["pagas", "recebidas", "extrato"].includes(ir)) setRel(ir as Rel);
    const ref = qs.get("ref");
    if (ref) setNotaAlvoRef(ref);
  }, []);

  // Nome real de cada código do plano de contas — usado para dar nome à
  // hierarquia no DRE e no detalhamento por conta do Fluxo de Caixa, em vez
  // de mostrar só o código ou a descrição solta de cada lançamento.
  const nomePorCodigo = useMemo(() => new Map(planoContas.map((p) => [p.codigo, p.nome])), [planoContas]);

  useEffect(() => {
    if (regs && !inicio) {
      const ds = regs.flatMap((r) => [r.data_pagamento, r.data_competencia, r.data_vencimento]).filter(Boolean).sort() as string[];
      // Início = data mais antiga real dos lançamentos, mas o fim sempre parte de
      // hoje — nunca da maior data encontrada (um lançamento com data futura/errada
      // não deve puxar o filtro inteiro para o futuro).
      if (ds.length) setInicio(ds[0]);
      setFim(new Date().toISOString().slice(0, 10));
    }
  }, [regs, inicio]);

  const centros = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo))).sort(), [regs]);

  // Base de cada sub-aba de contas: em aberto (sem data de pagamento) ou já quitadas.
  const contasBase = useMemo(() => {
    if (!regs) return [];
    switch (rel) {
      case "a_pagar": return regs.filter((r) => r.tipo === "despesa" && !r.data_pagamento);
      case "a_receber": return regs.filter((r) => r.tipo === "receita" && !r.data_pagamento);
      case "pagas": return regs.filter((r) => r.tipo === "despesa" && r.data_pagamento);
      case "recebidas": return regs.filter((r) => r.tipo === "receita" && r.data_pagamento);
      case "extrato": return regs;
      default: return regs;
    }
  }, [regs, rel]);

  // Data relevante por aba: DRE = competência; a pagar/receber = vencimento; pagas/recebidas = pagamento; fluxo/livro = pagamento.
  const campoData = (r: Lanc) => {
    if (rel === "dre") return r.data_competencia;
    if (rel === "a_pagar" || rel === "a_receber") return r.data_vencimento || r.data_competencia;
    if (rel === "pagas" || rel === "recebidas") return r.data_pagamento;
    if (rel === "extrato") return r.data_pagamento || r.data_vencimento || r.data_competencia;
    return r.data_pagamento;
  };
  const campoMes = (r: Lanc) => (rel === "dre" ? r.mes_competencia : r.mes_caixa);

  const filtrados = useMemo(() => {
    if (CONTAS_IDS.has(rel)) {
      // Sem período definido, mostra tudo — contas em aberto não devem sumir por falta de filtro.
      return contasBase.filter((r) => {
        const d = campoData(r);
        const dentroPeriodo = !inicio || !fim || !d || (d >= inicio && d <= fim);
        return dentroPeriodo && (!centro || r.centro_custo === centro) && (!contaBanco || r.conta_bancaria === contaBanco);
      });
    }
    if (!regs || !inicio || !fim) return [];
    return regs.filter((r) => {
      const d = campoData(r);
      return d && d >= inicio && d <= fim && (!centro || r.centro_custo === centro);
    });
  }, [regs, contasBase, rel, inicio, fim, centro, contaBanco]);

  const receitas = filtrados.filter((r) => r.tipo === "receita").reduce((a, r) => a + r.valor, 0);
  const despesas = filtrados.filter((r) => r.tipo === "despesa").reduce((a, r) => a + r.valor, 0);
  const resultado = receitas - despesas;

  // Fluxo de caixa mensal (com saldo acumulado)
  const fluxoMensal = useMemo(() => {
    const by = new Map<string, { mes: string; entradas: number; saidas: number }>();
    filtrados.forEach((r) => {
      const m = campoMes(r); if (!m) return;
      const e = by.get(m) ?? { mes: m, entradas: 0, saidas: 0 };
      if (r.tipo === "receita") e.entradas += r.valor; else e.saidas += r.valor;
      by.set(m, e);
    });
    let acc = 0;
    return Array.from(by.values()).sort((a, b) => a.mes.localeCompare(b.mes)).map((x) => {
      acc += x.entradas - x.saidas;
      return { ...x, saldo: x.entradas - x.saidas, acumulado: Math.round(acc) };
    });
  }, [filtrados, rel]);

  // Fluxo de caixa diário (mesma lógica do mensal, por data em vez de mês) —
  // acompanhamento dia a dia, igual ao extrato bancário.
  const fluxoDiario = useMemo(() => {
    const by = new Map<string, { dia: string; entradas: number; saidas: number }>();
    filtrados.forEach((r) => {
      const d = campoData(r); if (!d) return;
      const e = by.get(d) ?? { dia: d, entradas: 0, saidas: 0 };
      if (r.tipo === "receita") e.entradas += r.valor; else e.saidas += r.valor;
      by.set(d, e);
    });
    let acc = 0;
    return Array.from(by.values()).sort((a, b) => a.dia.localeCompare(b.dia)).map((x) => {
      acc += x.entradas - x.saidas;
      return { ...x, saldo: x.entradas - x.saidas, acumulado: Math.round(acc) };
    });
  }, [filtrados, rel]);

  // Propaga o valor de um lançamento por TODOS os níveis do código (ex.:
  // "2.01.01.01" também soma em "2.01.01", "2.01" e "2") — é assim que uma
  // conta de grupo (sem lançamento direto) mostra o total dos filhos.
  const propagarPorHierarquia = (codigoFolha: string): string[] => {
    const partes = codigoFolha.split(".");
    return partes.map((_, i) => partes.slice(0, i + 1).join("."));
  };

  // DRE por conta gerencial — hierárquico, usando o NOME real do plano de
  // contas (Configurações > Importar dados). Lançamentos sem conta classificada
  // continuam aparecendo à parte, por descrição (comportamento antigo).
  const dreContas = useMemo(() => {
    const by = new Map<string, { conta: string; nome: string; codigo: string; nivel: number; receitas: number; despesas: number }>();
    filtrados.forEach((r) => {
      const codigoFolha = r.conta_completa || r.codigo_conta || "";
      if (!codigoFolha) {
        const k = r.descricao || "(sem conta)";
        const e = by.get(k) ?? { conta: k, nome: k, codigo: "", nivel: 0, receitas: 0, despesas: 0 };
        if (r.tipo === "receita") e.receitas += r.valor; else e.despesas += r.valor;
        by.set(k, e);
        return;
      }
      const niveis = propagarPorHierarquia(codigoFolha);
      niveis.forEach((codigo, i) => {
        const nomeConhecido = nomePorCodigo.get(codigo);
        const ehFolha = i === niveis.length - 1;
        if (!nomeConhecido && !ehFolha) return; // nível intermediário sem nome cadastrado — não gera linha "só número"
        const nome = nomeConhecido || (r.descricao || codigo);
        const e = by.get(codigo) ?? { conta: codigo, nome, codigo, nivel: i + 1, receitas: 0, despesas: 0 };
        if (r.tipo === "receita") e.receitas += r.valor; else e.despesas += r.valor;
        by.set(codigo, e);
      });
    });
    return Array.from(by.values()).map((x) => ({ ...x, saldo: x.receitas - x.despesas })).sort((a, b) => a.conta.localeCompare(b.conta));
  }, [filtrados, nomePorCodigo]);

  // Meses presentes no período filtrado (para as colunas do detalhamento).
  const mesesFluxo = useMemo(() => Array.from(new Set(filtrados.map(campoMes).filter(Boolean))).sort() as string[], [filtrados, rel]);

  // Detalhamento por conta do Fluxo de Caixa — mesma hierarquia do DRE, mas
  // com uma coluna por mês (igual ao "Fluxo mensal detalhado" de referência).
  const detalhePorContaMensal = useMemo(() => {
    const by = new Map<string, { codigo: string; nome: string; nivel: number; porMes: Record<string, number>; total: number }>();
    filtrados.forEach((r) => {
      const codigoFolha = r.conta_completa || r.codigo_conta || "";
      const mes = campoMes(r);
      if (!codigoFolha || !mes) return;
      const niveis = propagarPorHierarquia(codigoFolha);
      niveis.forEach((codigo, i) => {
        const nomeConhecido = nomePorCodigo.get(codigo);
        const ehFolha = i === niveis.length - 1;
        if (!nomeConhecido && !ehFolha) return; // nível intermediário sem nome cadastrado — não gera linha "só número"
        const nome = nomeConhecido || (r.descricao || codigo);
        const e = by.get(codigo) ?? { codigo, nome, nivel: i + 1, porMes: {}, total: 0 };
        e.porMes[mes] = Math.round(((e.porMes[mes] || 0) + r.valor) * 100) / 100;
        e.total = Math.round((e.total + r.valor) * 100) / 100;
        by.set(codigo, e);
      });
    });
    return Array.from(by.values()).sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [filtrados, nomePorCodigo, rel]);

  // Livro caixa (cronológico com saldo acumulado)
  const livro = useMemo(() => {
    let acc = 0;
    return [...filtrados].filter((r) => r.data_pagamento).sort((a, b) => (a.data_pagamento! < b.data_pagamento! ? -1 : 1)).map((r) => {
      const entrada = r.tipo === "receita" ? r.valor : 0;
      const saida = r.tipo === "despesa" ? r.valor : 0;
      acc += entrada - saida;
      return { data: r.data_pagamento, descricao: r.descricao, fornecedor: r.fornecedor, entrada, saida, saldo: Math.round(acc) };
    });
  }, [filtrados]);

  const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><BarChart3 size={22} style={{ color: "var(--dourado)" }} /> Financeiro</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Escolha o relatório, o período e o centro de custo — indicadores, consolidado e gráfico.</p>
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o CONTA_GERENCIAL</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && regs.length === 0 && !error && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <BarChart3 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-muted)" }}>Nenhum lançamento financeiro no banco.</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
            Suba o <strong>CONTA_GERENCIAL.csv</strong> na tela de <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload</a>.
            Se você já subiu e sumiu, o banco de produção não está persistindo — confira o Postgres no Railway.
          </p>
        </div>
      )}

      {regs && regs.length > 0 && <>
        {/* Seletor de contas */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Contas</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
          {CONTAS.map((r) => {
            const ativo = rel === r.id; const Icon = r.icon;
            const n = regs ? (
              r.id === "a_pagar" ? regs.filter((x) => x.tipo === "despesa" && !x.data_pagamento).length :
              r.id === "a_receber" ? regs.filter((x) => x.tipo === "receita" && !x.data_pagamento).length :
              r.id === "pagas" ? regs.filter((x) => x.tipo === "despesa" && x.data_pagamento).length :
              r.id === "recebidas" ? regs.filter((x) => x.tipo === "receita" && x.data_pagamento).length :
              regs.length
            ) : 0;
            return (
              <button key={r.id} onClick={() => setRel(r.id)} className="card" style={{ textAlign: "left", cursor: "pointer", border: ativo ? "1px solid var(--dourado)" : "1px solid var(--border)", background: ativo ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
                <div className="flex items-center gap-2" style={{ color: ativo ? "var(--dourado-light)" : "var(--text)" }}><Icon size={16} /><span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{r.label}</span></div>
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{n} lançamento{n === 1 ? "" : "s"}</p>
              </button>
            );
          })}
        </div>

        {/* Seletor de relatório */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Relatórios</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          {RELATORIOS.map((r) => {
            const ativo = rel === r.id; const Icon = r.icon;
            return (
              <button key={r.id} onClick={() => setRel(r.id)} className="card" style={{ textAlign: "left", cursor: "pointer", border: ativo ? "1px solid var(--dourado)" : "1px solid var(--border)", background: ativo ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
                <div className="flex items-center gap-2" style={{ color: ativo ? "var(--dourado-light)" : "var(--text)" }}><Icon size={18} /><span style={{ fontWeight: 700 }}>{r.label}</span></div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{r.desc}</p>
              </button>
            );
          })}
        </div>

        {/* Indicadores */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Indicadores</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          {INDICADORES.map((r) => {
            const ativo = rel === r.id; const Icon = r.icon;
            return (
              <button key={r.id} onClick={() => setRel(r.id)} className="card" style={{ textAlign: "left", cursor: "pointer", border: ativo ? "1px solid var(--dourado)" : "1px solid var(--border)", background: ativo ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
                <div className="flex items-center gap-2" style={{ color: ativo ? "var(--dourado-light)" : "var(--text)" }}><Icon size={18} /><span style={{ fontWeight: 700 }}>{r.label}</span></div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{r.desc}</p>
              </button>
            );
          })}
        </div>

        {/* Patrimônio e ações em lote */}
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Patrimônio e ações</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <button onClick={() => setRel("patrimonio")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "patrimonio" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "patrimonio" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "patrimonio" ? "var(--dourado-light)" : "var(--text)" }}><Building2 size={18} /><span style={{ fontWeight: 700 }}>Patrimônio</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Máquinas, veículos, implementos e terras</p>
          </button>
          <button onClick={() => setRel("pagamento")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "pagamento" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "pagamento" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "pagamento" ? "var(--dourado-light)" : "var(--text)" }}><Wallet size={18} /><span style={{ fontWeight: 700 }}>Pagamento</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Escolha uma despesa em aberto e trate a baixa: data, conta corrente, forma e comprovante</p>
          </button>
          <button onClick={() => setRel("recebimento")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "recebimento" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "recebimento" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "recebimento" ? "var(--dourado-light)" : "var(--text)" }}><Wallet size={18} /><span style={{ fontWeight: 700 }}>Recebimento</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Escolha uma receita em aberto e trate a baixa: data, conta corrente, forma e comprovante</p>
          </button>
          <button onClick={() => setRel("lote")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "lote" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "lote" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "lote" ? "var(--dourado-light)" : "var(--text)" }}><Layers size={18} /><span style={{ fontWeight: 700 }}>Pagamento/recebimento em lote</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Filtre notas em aberto e dê baixa em várias de uma vez, com um comprovante único</p>
          </button>
          <button onClick={() => setRel("folha")} className="card" style={{ textAlign: "left", cursor: "pointer", border: rel === "folha" ? "1px solid var(--dourado)" : "1px solid var(--border)", background: rel === "folha" ? "rgba(94,26,46,0.35)" : "var(--surface)" }}>
            <div className="flex items-center gap-2" style={{ color: rel === "folha" ? "var(--dourado-light)" : "var(--text)" }}><Users size={18} /><span style={{ fontWeight: 700 }}>Folha de pagamento</span></div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Lance e acompanhe os pagamentos por pessoa e por mês de competência</p>
          </button>
        </div>

        {rel === "patrimonio" ? <PatrimonioView />
          : rel === "pagamento" ? <PagamentoIndividualView key="despesa" tipo="despesa" contasBancarias={contasBancarias} notaAlvoRef={notaAlvoRef} onNotaTratada={() => setNotaAlvoRef(null)} onFeito={recarregar} />
          : rel === "recebimento" ? <PagamentoIndividualView key="receita" tipo="receita" contasBancarias={contasBancarias} notaAlvoRef={notaAlvoRef} onNotaTratada={() => setNotaAlvoRef(null)} onFeito={recarregar} />
          : rel === "lote" ? <PagamentoLoteView contasBancarias={contasBancarias} onFeito={recarregar} /> : rel === "folha" ? <FolhaPagamentoView /> : rel === "rmca" ? <RmcaView /> : <>
        {/* Filtros */}
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="flex flex-wrap gap-3 items-end">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Início</label><input type="date" style={inputStyle} value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Fim</label><input type="date" style={inputStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Centro de custo</label>
              <select style={inputStyle} value={centro} onChange={(e) => setCentro(e.target.value)}><option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}</select></div>
            {CONTAS_IDS.has(rel) && (
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Conta bancária</label>
                <select style={inputStyle} value={contaBanco} onChange={(e) => setContaBanco(e.target.value)}><option value="">Todas</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}</select></div>
            )}
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingBottom: "0.4rem" }}>
              {!CONTAS_IDS.has(rel) && <>Regime: <strong style={{ color: "var(--dourado-light)" }}>{rel === "dre" ? "competência" : "caixa"}</strong> · </>}
              {filtrados.length} lançamento{filtrados.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {CONTAS_IDS.has(rel) ? (
          <TabelaContas rel={rel} itens={filtrados} onTratar={(l) => { setRel(l.tipo === "receita" ? "recebimento" : "pagamento"); setNotaAlvoRef(l.numero_lancamento || l.numero_documento || null); }} />
        ) : <>
        {/* Indicadores consolidados */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {rel === "fluxo" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo do período" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={fluxoMensal.length ? formatBRL(fluxoMensal[fluxoMensal.length - 1].acumulado) : "—"} l="Saldo acumulado" c="var(--dourado-light)" />
          </>}
          {rel === "dre" && <>
            <KPI v={formatBRL(receitas)} l="Receita" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Despesa" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Resultado" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={receitas > 0 ? `${Math.round((1000 * resultado) / receitas) / 10}%` : "—"} l="Margem" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
          </>}
          {rel === "livro" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo final" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={String(livro.length)} l="Lançamentos" />
          </>}
        </div>

        {/* Diário/Mensal — só se aplica ao Fluxo de Caixa */}
        {rel === "fluxo" && (
          <TabBar
            abas={[
              { id: "mensal", label: "Mensal", title: "Fluxo agrupado por mês de caixa" },
              { id: "diario", label: "Diário", title: "Fluxo dia a dia, como o extrato bancário" },
            ] as const}
            ativa={visaoFluxo}
            onChange={setVisaoFluxo}
          />
        )}

        {/* Gráfico do consolidado */}
        <div className="card mb-4">
          <div className="card-header mb-3">{rel === "fluxo" ? `Fluxo de Caixa ${visaoFluxo === "diario" ? "diário" : "mensal"} (entradas × saídas × acumulado)` : rel === "dre" ? "Receita × Despesa × Resultado" : "Saldo Acumulado"}</div>
          {rel === "fluxo" && visaoFluxo === "mensal" && (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={fluxoMensal}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="mes" tickFormatter={fmtMes} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="entradas" name="Entradas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="var(--red)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {rel === "fluxo" && visaoFluxo === "diario" && (<>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={fluxoDiario.filter((_, i) => i % Math.ceil(fluxoDiario.length / 200 || 1) === 0)}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="dia" tickFormatter={(d) => (d ? d.slice(5) : "")} tick={{ fill: "var(--text-muted)", fontSize: 9 }} minTickGap={30} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(d: any) => formatDate(d as string)} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="entradas" name="Entradas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="var(--red)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
            {Math.ceil(fluxoDiario.length / 200 || 1) > 1 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem", textAlign: "center" }}>
                Exibindo 1 a cada {Math.ceil(fluxoDiario.length / 200 || 1)} pontos para legibilidade.
              </p>
            )}
          </>)}
          {rel === "dre" && (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={[{ n: "Receita", v: receitas, f: "var(--green-light)" }, { n: "Despesa", v: despesas, f: "var(--red)" }, { n: "Resultado", v: Math.abs(resultado), f: resultado >= 0 ? "var(--dourado)" : "var(--amber)" }]}>
                <XAxis dataKey="n" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="v" barSize={70}>{[0, 1, 2].map((i) => <Cell key={i} fill={["var(--green-light)", "var(--red)", resultado >= 0 ? "var(--dourado)" : "var(--amber)"][i]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {rel === "livro" && (<>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={livro.filter((_, i) => i % Math.ceil(livro.length / 150 || 1) === 0)}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="data" tickFormatter={(d) => (d ? d.slice(5) : "")} tick={{ fill: "var(--text-muted)", fontSize: 9 }} minTickGap={30} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(d: any) => formatDate(d as string)} contentStyle={tip} />
                <Line type="monotone" dataKey="saldo" name="Saldo acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            {Math.ceil(livro.length / 150 || 1) > 1 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem", textAlign: "center" }}>
                Exibindo 1 a cada {Math.ceil(livro.length / 150 || 1)} pontos para legibilidade.
              </p>
            )}
          </>)}
        </div>

        {/* Detalhamento do relatório */}
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.4rem" }}>
            <span>
              {rel === "fluxo" ? `Fluxo ${visaoFluxo === "diario" ? "Diário" : "Mensal"}` : rel === "dre" ? "Detalhamento por Conta Gerencial" : "Lançamentos"}
              {rel !== "livro" && <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}> (clique numa linha para ver os lançamentos)</span>}
            </span>
            {rel === "livro" && (
              <ExportarBotoes titulo="Livro Caixa" nomeArquivoBase="livro_caixa" colunas={COLUNAS_LIVRO}
                linhas={livro.map((l) => ({ ...l, dataFmt: formatDate(l.data || "") }))} />
            )}
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: rel === "livro" ? "460px" : "460px" }}>
            {rel === "fluxo" && visaoFluxo === "mensal" && (
              <table className="fazenda-table">
                <thead><tr><th></th><th>Mês</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Acumulado</th></tr></thead>
                <tbody>{fluxoMensal.map((m) => {
                  const aberto = exp.has("fluxo:" + m.mes);
                  const itens = aberto ? filtrados.filter((r) => campoMes(r) === m.mes).sort((a, b) => ((a.data_pagamento || "") < (b.data_pagamento || "") ? -1 : 1)) : [];
                  return (
                    <Fragment key={m.mes}>
                      <tr onClick={() => toggleExp("fluxo:" + m.mes)} title="Clique para ver os lançamentos deste mês" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600 }}>{m.mes}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={m.mes + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{formatDate(r.data_pagamento || "")} · {r.descricao}</td>
                          <td colSpan={2} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.fornecedor}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            )}
            {rel === "fluxo" && visaoFluxo === "diario" && (
              <table className="fazenda-table">
                <thead><tr><th></th><th>Data</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo diário</th><th style={{ textAlign: "right" }}>Saldo acumulado</th></tr></thead>
                <tbody>{fluxoDiario.map((m) => {
                  const aberto = exp.has("fluxodia:" + m.dia);
                  const itens = aberto ? filtrados.filter((r) => campoData(r) === m.dia) : [];
                  return (
                    <Fragment key={m.dia}>
                      <tr onClick={() => toggleExp("fluxodia:" + m.dia)} title="Clique para ver os lançamentos deste dia" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{formatDate(m.dia)}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={m.dia + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{r.descricao}</td>
                          <td colSpan={2} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.fornecedor}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            )}
            {rel === "dre" && (<>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Resultado por <strong>conta gerencial</strong> do seu plano de contas (por competência), com a
                hierarquia completa — uma conta de grupo soma o total das contas abaixo dela. Clique numa conta{" "}
                <span style={{ color: "var(--text-muted)" }}>▾</span> para ver os lançamentos.
              </p>
              <table className="fazenda-table">
                <thead><tr><th></th><th>Conta gerencial</th><th style={{ textAlign: "right" }}>Receitas</th><th style={{ textAlign: "right" }}>Despesas</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{dreContas.map((c) => {
                  const aberto = exp.has("dre:" + c.conta);
                  const itens = aberto ? filtrados.filter((r) => {
                    const codigo = r.conta_completa || r.codigo_conta || "";
                    if (!c.codigo) return (r.descricao || "(sem conta)") === c.conta;
                    return codigo === c.codigo || codigo.startsWith(c.codigo + ".");
                  }).sort((a, b) => b.valor - a.valor) : [];
                  return (
                    <Fragment key={c.conta}>
                      <tr onClick={() => toggleExp("dre:" + c.conta)} title="Clique para ver os lançamentos desta conta" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: c.nivel <= 1 ? 700 : 600, paddingLeft: `${Math.max(0, c.nivel - 1) * 1.1}rem` }}>
                          {c.nome}{c.codigo && c.codigo !== c.nome ? <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.4rem" }}>{c.codigo}</span> : null}
                        </td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{c.receitas ? formatBRL(c.receitas) : "—"}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{c.despesas ? formatBRL(c.despesas) : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: c.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(c.saldo)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={c.conta + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{formatDate(r.data_pagamento || r.data_competencia || "")} <span style={{ color: "var(--text-muted)" }}>· {r.fornecedor || "—"}</span></td>
                          <td colSpan={2} style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            </>)}
            {rel === "livro" && (
              <table className="fazenda-table">
                <thead><tr><th>Data</th><th>Descrição</th><th>Fornecedor/Cliente</th><th style={{ textAlign: "right" }}>Entrada</th><th style={{ textAlign: "right" }}>Saída</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{livro.slice(0, 500).map((l, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{formatDate(l.data || "")}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.descricao}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{l.fornecedor}</td>
                    <td style={{ textAlign: "right", color: "var(--green-light)" }}>{l.entrada ? formatBRL(l.entrada) : ""}</td>
                    <td style={{ textAlign: "right", color: "var(--red)" }}>{l.saida ? formatBRL(l.saida) : ""}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: l.saldo >= 0 ? "var(--dourado-light)" : "var(--amber)" }}>{formatBRL(l.saldo)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            {rel === "livro" && livro.length > 500 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 500 de {livro.length} — refine o período.</p>}
          </div>
        </div>

        {/* Detalhamento por conta gerencial, mês a mês — só no Fluxo de Caixa */}
        {rel === "fluxo" && mesesFluxo.length > 0 && (
          <SecaoRecolhivel
            titulo="Detalhamento por conta gerencial (mês a mês)"
            defaultAberta={false}
            descricao="Uma coluna por mês, com a hierarquia completa do plano de contas"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{detalhePorContaMensal.length} conta(s)</span>}
          >
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Mesma hierarquia do plano de contas — uma conta de grupo soma o total das contas abaixo dela.
            </p>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <th>Conta</th><th style={{ textAlign: "right" }}>Total</th>
                    {mesesFluxo.map((m) => <th key={m} style={{ textAlign: "right" }}>{fmtMes(m)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {detalhePorContaMensal.map((c) => (
                    <tr key={c.codigo}>
                      <td style={{ fontWeight: c.nivel <= 1 ? 700 : 500, fontSize: "0.82rem", paddingLeft: `${Math.max(0, c.nivel - 1) * 1.1}rem`, whiteSpace: "nowrap" }}>
                        {c.nome}<span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.7rem", marginLeft: "0.4rem" }}>{c.codigo}</span>
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(c.total)}</td>
                      {mesesFluxo.map((m) => (
                        <td key={m} style={{ textAlign: "right", fontSize: "0.78rem", color: (c.porMes[m] || 0) === 0 ? "var(--text-muted)" : undefined }}>
                          {c.porMes[m] ? formatBRL(c.porMes[m]) : "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {!detalhePorContaMensal.length && (
                    <tr><td colSpan={2 + mesesFluxo.length} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento com conta gerencial classificada neste período.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>
        )}
        </>}
        </>}
      </>}
    </div>
  );
}

const selStyleLote: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyleLote: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

/**
 * Pagamento/recebimento em lote — filtra notas (despesa ou receita, aberta
 * ou já baixada) por nota/documento, fornecedor, produto e datas; o usuário
 * seleciona quais notas EM ABERTO quer baixar de uma vez, com um único
 * pagamento (data, conta corrente, forma de pagamento, comprovante).
 */
function PagamentoLoteView({ contasBancarias, onFeito }: { contasBancarias: string[]; onFeito?: () => void }) {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opcoes, setOpcoes] = useState<{ fornecedores: string[]; produtos: string[] }>({ fornecedores: [], produtos: [] });

  const [tipoFiltro, setTipoFiltro] = useState<"todos" | "despesa" | "receita">("todos");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [produto, setProduto] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [emissaoDe, setEmissaoDe] = useState("");
  const [emissaoAte, setEmissaoAte] = useState("");
  const [vencimentoDe, setVencimentoDe] = useState("");
  const [vencimentoAte, setVencimentoAte] = useState("");

  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [contaBancaria, setContaBancaria] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [dataVencimentoCartao, setDataVencimentoCartao] = useState("");
  const [numeroComprovante, setNumeroComprovante] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const [anexarAberto, setAnexarAberto] = useState(false);

  const carregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchOpcoesFinanceiro().then((d) => setOpcoes({ fornecedores: d.fornecedores || [], produtos: d.produtos || [] })).catch(() => {});
  }, []);

  const centrosCusto = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo).filter(Boolean))).sort(), [regs]);

  // Só notas em aberto entram na visualização — esta tela é para dar baixa,
  // não para consultar histórico (isso já existe em Contas pagas/recebidas).
  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      !r.data_pagamento &&
      (tipoFiltro === "todos" || r.tipo === tipoFiltro) &&
      (!numeroDocumento || (r.numero_documento || "").toLowerCase().includes(numeroDocumento.toLowerCase()) || (r.numero_lancamento || "").toLowerCase().includes(numeroDocumento.toLowerCase())) &&
      (!fornecedor || r.fornecedor === fornecedor) &&
      (!produto || (r.itens || []).some((it) => it.produto === produto)) &&
      (!centroCusto || r.centro_custo === centroCusto) &&
      (!emissaoDe || (r.data_emissao || "") >= emissaoDe) && (!emissaoAte || (r.data_emissao || "") <= emissaoAte) &&
      (!vencimentoDe || (r.data_vencimento || "") >= vencimentoDe) && (!vencimentoAte || (r.data_vencimento || "") <= vencimentoAte)
    );
  }, [regs, tipoFiltro, numeroDocumento, fornecedor, produto, centroCusto, emissaoDe, emissaoAte, vencimentoDe, vencimentoAte]);

  const toggle = (id: number) => setSelecionados((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleTodos = () => setSelecionados((p) =>
    p.size === filtrados.length && filtrados.length ? new Set() : new Set(filtrados.map((r) => r.id))
  );
  const totalSelecionado = useMemo(() => filtrados.filter((r) => selecionados.has(r.id)).reduce((a, r) => a + r.valor, 0), [filtrados, selecionados]);
  const totalFiltrado = useMemo(() => filtrados.reduce((a, r) => a + r.valor, 0), [filtrados]);

  async function darBaixaEmLote() {
    setMsg(null);
    if (!selecionados.size) { setMsg({ tipo: "erro", texto: "Selecione ao menos uma nota em aberto." }); return; }
    if (formaPagamento === "credito" && !dataVencimentoCartao) { setMsg({ tipo: "erro", texto: "Informe a data de vencimento do cartão." }); return; }
    setSalvando(true);
    try {
      const r = await criarBaixaLote({
        lancamento_ids: Array.from(selecionados), data_pagamento: dataPagamento,
        conta_bancaria: contaBancaria || undefined, forma_pagamento: formaPagamento || undefined,
        data_vencimento_cartao: formaPagamento === "credito" ? dataVencimentoCartao : undefined,
        numero_documento_pagamento: numeroComprovante || undefined,
      });
      setMsg({ tipo: "sucesso", texto: `${r.baixados} lançamento(s) baixado(s) com sucesso.` });
      setSelecionados(new Set()); setNumeroComprovante("");
      carregar();
      onFeito?.();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao dar baixa em lote" });
    } finally {
      setSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;
  if (!regs) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Filtros</span>
          <button className="btn-ghost" title="Criar um novo lançamento anexando nota fiscal ou recibo (leitura automática)" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Anexar nota fiscal ou recibo
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Tipo</label>
            <select style={selStyleLote} title="Filtrar por tipo de nota: a pagar, a receber ou ambas" value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value as any)}>
              <option value="todos">Despesas e receitas</option><option value="despesa">Só despesas (a pagar)</option><option value="receita">Só receitas (a receber)</option>
            </select></div>
          <div><label style={labelStyleLote}>Nota fiscal / nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" />
            </div></div>
          <div><label style={labelStyleLote}>Fornecedor / cliente</label>
            <select style={selStyleLote} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Todos</option>{opcoes.fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Produto</label>
            <select style={selStyleLote} value={produto} onChange={(e) => setProduto(e.target.value)}>
              <option value="">Todos</option>{opcoes.produtos.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Emissão — de</label><input type="date" style={selStyleLote} value={emissaoDe} onChange={(e) => setEmissaoDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Emissão — até</label><input type="date" style={selStyleLote} value={emissaoAte} onChange={(e) => setEmissaoAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — de</label><input type="date" style={selStyleLote} value={vencimentoDe} onChange={(e) => setVencimentoDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — até</label><input type="date" style={selStyleLote} value={vencimentoAte} onChange={(e) => setVencimentoAte(e.target.value)} /></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>
              {centrosCusto.map((c) => (<option key={c} value={c}>{c}</option>))}
            </select></div>
        </div>
      </div>

      {anexarAberto && (
        <Modal title="Novo lançamento — leitura automática" onClose={() => setAnexarAberto(false)} width="1000px">
          <FormFinanceiro tipo={tipoFiltro === "receita" ? "receita" : "despesa"} responsaveis={RESPONSAVEIS} onSalvo={() => { setAnexarAberto(false); carregar(); }} />
        </Modal>
      )}

      <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden", marginBottom: "1rem" }}>
        <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
          <span style={{ fontSize: "0.85rem" }}>
            {filtrados.length} nota(s) em aberto no filtro — total {formatBRL(totalFiltrado)}
            {selecionados.size > 0 && <> · {selecionados.size} selecionada(s) — {formatBRL(totalSelecionado)}</>}
          </span>
          <button className="btn-ghost" title="Selecionar ou limpar todas as notas do filtro" style={{ fontSize: "0.72rem" }} onClick={toggleTodos} disabled={!filtrados.length}>
            {selecionados.size === filtrados.length && filtrados.length ? "Limpar seleção" : `Selecionar todas (${filtrados.length})`}
          </button>
        </div>
        <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead><tr><th></th><th>Nota / lançamento</th><th>Emissão</th><th>Vencimento</th><th>Situação</th><th>Produtos</th><th style={{ textAlign: "right" }}>Valor</th></tr></thead>
            <tbody>
              {filtrados.map((r) => {
                const produtos = (r.itens || []).map((it) => it.produto).filter(Boolean).join(", ");
                return (
                  <tr key={r.id} className="row-clickable" title="Clique para selecionar esta nota" onClick={() => toggle(r.id)}>
                    <td><input type="checkbox" checked={selecionados.has(r.id)} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} /></td>
                    <td style={{ fontSize: "0.78rem" }}>
                      <strong>{r.numero_documento || r.numero_lancamento || "—"}</strong>
                      {r.numero_documento && r.numero_lancamento && <span style={{ color: "var(--text-muted)" }}> · {r.numero_lancamento}</span>}
                      <br /><span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{r.fornecedor || "—"} · {r.descricao}</span>
                    </td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_emissao ? formatDate(r.data_emissao) : "—"}</td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</td>
                    <td>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--amber)" }}>
                        {r.tipo === "receita" ? "A receber" : "A pagar"}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{produtos || "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                  </tr>
                );
              })}
              {!filtrados.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma nota em aberto no filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {selecionados.size > 0 && (
        <div className="card">
          <div className="card-header mb-3">Pagamento único para {selecionados.size} lançamento(s) — {formatBRL(totalSelecionado)}</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div><label style={labelStyleLote}>Data do pagamento</label>
              <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Conta corrente</label>
              <select style={selStyleLote} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                <option value="">Selecione…</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
              </select></div>
            <div><label style={labelStyleLote}>Forma</label>
              <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                <option value="">Selecione…</option>{Object.entries(LABEL_FORMA_PAGAMENTO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            {formaPagamento === "credito" ? (
              <div><label style={labelStyleLote}>Vencimento do cartão</label>
                <input type="date" style={selStyleLote} value={dataVencimentoCartao} onChange={(e) => setDataVencimentoCartao(e.target.value)} /></div>
            ) : (
              <div><label style={labelStyleLote}>Nº do comprovante de pagamento</label>
                <input style={selStyleLote} value={numeroComprovante} onChange={(e) => setNumeroComprovante(e.target.value)} /></div>
            )}
          </div>
          {formaPagamento === "credito" && (
            <div className="mb-3" style={{ maxWidth: "280px" }}>
              <label style={labelStyleLote}>Nº do comprovante de pagamento</label>
              <input style={selStyleLote} value={numeroComprovante} onChange={(e) => setNumeroComprovante(e.target.value)} />
            </div>
          )}
          {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
          <button className="btn-primary" title="Baixar todas as notas selecionadas com este pagamento único" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={darBaixaEmLote} disabled={salvando}>
            <Check size={14} /> {salvando ? "Salvando…" : `Dar baixa em ${selecionados.size} lançamento(s)`}
          </button>
        </div>
      )}
    </div>
  );
}

type ItemPatrimonio = {
  id: number; tipo: string | null; nome: string; numero: string | null;
  atividade_cultura: string | null; placa: string | null; data_imobilizacao: string | null;
  metodo_depreciacao: string | null; vida_util: string | null; valor_residual: number | null;
  quantidade: number | null; unidade: string | null; valor_total: number | null; data_baixa: string | null;
};

function PatrimonioView() {
  const [dados, setDados] = useState<{ itens: ItemPatrimonio[]; total: number; valor_total: number } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchPatrimonio().then(setDados).catch((e) => setErro(e.message)); }, []);

  if (erro) return <div className="alert-critico"><span>Sem dados: {erro}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o LISTA_DE_PATRIMONIO.csv</a>.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  if (!dados.itens.length) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <Building2 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
        <p style={{ color: "var(--text-muted)" }}>Nenhum item de patrimônio no banco.</p>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Suba o <strong>LISTA_DE_PATRIMONIO.csv</strong> na tela de <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Upload</a>.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KPI v={String(dados.total)} l="Itens" />
        <KPI v={formatBRL(dados.valor_total)} l="Valor total (ativo)" c="var(--dourado-light)" />
        <KPI v={String(dados.itens.filter((i) => i.data_baixa).length)} l="Com baixa" c="var(--text-muted)" />
      </div>
      <div className="card">
        <div className="card-header mb-3">Bens</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Tipo</th><th>Nome</th><th>Nº</th><th>Placa</th><th>Imobilização</th>
                <th>Depreciação</th><th>Vida útil</th><th style={{ textAlign: "right" }}>Vlr. residual</th>
                <th style={{ textAlign: "right" }}>Qtd.</th><th style={{ textAlign: "right" }}>Vlr. total</th><th>Baixa</th>
              </tr>
            </thead>
            <tbody>
              {dados.itens.map((i) => (
                <tr key={i.id} style={i.data_baixa ? { opacity: 0.55 } : undefined}>
                  <td style={{ fontSize: "0.78rem" }}>{i.tipo || "—"}</td>
                  <td style={{ fontWeight: 600, fontSize: "0.83rem" }}>{i.nome}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.numero || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.placa || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.data_imobilizacao ? formatDate(i.data_imobilizacao) : "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.metodo_depreciacao || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.vida_util || "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.valor_residual != null ? formatBRL(i.valor_residual) : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, fontSize: "0.83rem" }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                  <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{i.data_baixa ? formatDate(i.data_baixa) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function TabelaContas({ rel, itens, onTratar }: { rel: Rel; itens: Lanc[]; onTratar: (l: Lanc) => void }) {
  const emAberto = rel === "a_pagar" || rel === "a_receber";
  const total = itens.reduce((a, r) => a + r.valor, 0);
  const totalPago = itens.reduce((a, r) => a + (r.valor_pago ?? 0), 0);
  const totalDesconto = itens.reduce((a, r) => a + (r.desconto_acrescimo ?? 0), 0);
  const hoje = new Date().toISOString().slice(0, 10);

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String(itens.length)} l="Lançamentos" />
        <KPI v={formatBRL(total)} l={emAberto ? "Valor em aberto" : "Valor total"} c={rel === "a_pagar" || rel === "pagas" ? "var(--red)" : rel === "extrato" ? undefined : "var(--green-light)"} />
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalPago)} l="Valor pago/recebido" c="var(--dourado-light)" />}
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalDesconto)} l="Desconto/acréscimo" c={totalDesconto <= 0 ? "var(--green-light)" : "var(--amber)"} />}
      </div>
      <div className="card">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Lançamentos</span>
          <ExportarBotoes titulo={CONTAS.find((c) => c.id === rel)?.label || "Lançamentos"} nomeArquivoBase={`financeiro_${rel}`}
            colunas={COLUNAS_LANCAMENTOS}
            linhas={itens.map((r) => ({ ...r, data: formatDate((emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento)) || ""), documento: `${r.tipo_documento ? `${r.tipo_documento} ` : ""}${r.numero_documento || ""}` }))} />
        </div>
        <div className="overflow-x-auto" style={{ maxHeight: "520px" }}>
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Nº lanç.</th><th>{emAberto ? "Vencimento" : "Data"}</th><th>Descrição</th><th>Fornecedor/Cliente</th>
                <th>Centro custo</th><th>Documento</th><th style={{ textAlign: "right" }}>Valor</th>
                {!emAberto && <th style={{ textAlign: "right" }}>Pago</th>}
                {!emAberto && <th>Conta bancária</th>}
                {emAberto && <th></th>}
              </tr>
            </thead>
            <tbody>
              {itens.map((r) => {
                const vencido = emAberto && r.data_vencimento && r.data_vencimento < hoje;
                return (
                  <tr key={r.id}>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.numero_lancamento}{r.parcela_total && r.parcela_total > 1 ? ` (${r.parcela_num}/${r.parcela_total})` : ""}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem", color: vencido ? "var(--red)" : undefined, fontWeight: vencido ? 700 : undefined }}>
                      {formatDate((emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento)) || "")}{vencido ? " ⚠" : ""}
                    </td>
                    <td style={{ fontSize: "0.78rem" }}>{r.descricao || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                    <td style={{ fontSize: "0.75rem" }}>{r.centro_custo}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.tipo_documento ? `${r.tipo_documento} ` : ""}{r.numero_documento || ""}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    {!emAberto && <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.valor_pago != null ? formatBRL(r.valor_pago) : "—"}</td>}
                    {!emAberto && <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{r.conta_bancaria || "—"}</td>}
                    {emAberto && <td><button className="btn-ghost" title="Tratar a baixa desta nota (data, conta, forma e comprovante)" style={{ fontSize: "0.72rem" }} onClick={() => onTratar(r)}>Tratar</button></td>}
                  </tr>
                );
              })}
              {!itens.length && <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum lançamento nesta aba.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

const LABEL_FORMA_PAGAMENTO: Record<string, string> = { pix: "Pix", transferencia: "Transferência", boleto: "Boleto", credito: "Crédito", debito: "Débito" };

/**
 * Pagamento (despesa) ou Recebimento (receita) individual — escolhe UMA nota
 * em aberto (fornecedor/cliente e produto por lista, nunca texto livre) e
 * trata a baixa dela: data, conta corrente, forma de pagamento (com débito)
 * e número do comprovante. Substitui a antiga baixa direto na lista de
 * Contas a pagar/receber — "Tratar" leva para cá em vez de abrir um modal.
 */
function PagamentoIndividualView({ tipo, contasBancarias, notaAlvoRef, onNotaTratada, onFeito }: {
  tipo: "despesa" | "receita"; contasBancarias: string[]; notaAlvoRef: string | null;
  onNotaTratada?: () => void; onFeito?: () => void;
}) {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opcoes, setOpcoes] = useState<{ fornecedores: string[]; produtos: string[] }>({ fornecedores: [], produtos: [] });

  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [produto, setProduto] = useState("");
  const [centroCusto, setCentroCusto] = useState("");

  const [notaId, setNotaId] = useState<number | null>(null);
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [dataVencimentoCartao, setDataVencimentoCartao] = useState("");
  const [numeroDocPagamento, setNumeroDocPagamento] = useState("");
  const [confirmando, setConfirmando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const [anexarAberto, setAnexarAberto] = useState(false);

  const carregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchOpcoesFinanceiro().then((d) => setOpcoes({ fornecedores: d.fornecedores || [], produtos: d.produtos || [] })).catch(() => {});
  }, []);

  const abertas = useMemo(() => (regs ?? []).filter((r) => r.tipo === tipo && !r.data_pagamento), [regs, tipo]);
  const centrosCusto = useMemo(() => Array.from(new Set(abertas.map((r) => r.centro_custo).filter(Boolean))).sort(), [abertas]);

  const filtradas = useMemo(() => abertas.filter((r) =>
    (!numeroDocumento || (r.numero_documento || "").toLowerCase().includes(numeroDocumento.toLowerCase()) || (r.numero_lancamento || "").toLowerCase().includes(numeroDocumento.toLowerCase())) &&
    (!fornecedor || r.fornecedor === fornecedor) &&
    (!produto || (r.itens || []).some((it) => it.produto === produto)) &&
    (!centroCusto || r.centro_custo === centroCusto)
  ), [abertas, numeroDocumento, fornecedor, produto, centroCusto]);
  const totalFiltrado = useMemo(() => filtradas.reduce((a, r) => a + r.valor, 0), [filtradas]);

  function selecionar(nota: Lanc) {
    setNotaId(nota.id);
    setValorPago(String(nota.valor));
    setDataPagamento(new Date().toISOString().slice(0, 10));
    setContaBancaria(""); setFormaPagamento(""); setDataVencimentoCartao(""); setNumeroDocPagamento("");
    setConfirmando(false); setMsg(null);
  }

  // Chega da lista de Contas a pagar/receber ou da Agenda com uma nota específica já em mente.
  useEffect(() => {
    if (!notaAlvoRef || !regs) return;
    const alvo = abertas.find((r) => (r.numero_lancamento || r.numero_documento) === notaAlvoRef);
    if (alvo) selecionar(alvo);
    onNotaTratada?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaAlvoRef, regs]);

  const notaSelecionada = useMemo(() => abertas.find((r) => r.id === notaId) || null, [abertas, notaId]);
  const diferenca = notaSelecionada ? Math.round((Number(valorPago) - notaSelecionada.valor) * 100) / 100 : 0;

  async function confirmar() {
    if (!notaSelecionada) return;
    if (diferenca !== 0 && !confirmando) { setConfirmando(true); return; }
    if (formaPagamento === "credito" && !dataVencimentoCartao) { setMsg({ tipo: "erro", texto: "Informe a data de vencimento do cartão." }); return; }
    setSalvando(true); setMsg(null);
    try {
      await marcarPagoFinanceiro(notaSelecionada.id, {
        data_pagamento: dataPagamento, valor_pago: Number(valorPago) || 0,
        conta_bancaria: contaBancaria || undefined, numero_documento_pagamento: numeroDocPagamento || undefined,
        forma_pagamento: formaPagamento || undefined, data_vencimento_cartao: formaPagamento === "credito" ? dataVencimentoCartao : undefined,
      });
      setMsg({ tipo: "sucesso", texto: `${tipo === "receita" ? "Recebimento" : "Pagamento"} registrado com sucesso.` });
      setNotaId(null);
      carregar();
      onFeito?.();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao tratar a nota" });
    } finally {
      setSalvando(false); setConfirmando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;
  if (!regs) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Filtrar notas em aberto</span>
          <button className="btn-ghost" title="Criar um novo lançamento anexando nota fiscal ou recibo (leitura automática)" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Anexar nota fiscal ou recibo
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={labelStyleLote}>Nota fiscal / nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" />
            </div></div>
          <div><label style={labelStyleLote}>{tipo === "receita" ? "Cliente" : "Fornecedor"}</label>
            <select style={selStyleLote} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Todos</option>{opcoes.fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Produto</label>
            <select style={selStyleLote} value={produto} onChange={(e) => setProduto(e.target.value)}>
              <option value="">Todos</option>{opcoes.produtos.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>{centrosCusto.map((c) => <option key={c} value={c}>{c}</option>)}
            </select></div>
        </div>
      </div>

      {anexarAberto && (
        <Modal title={`Novo lançamento — leitura automática (${tipo === "receita" ? "recebimento" : "pagamento"})`} onClose={() => setAnexarAberto(false)} width="1000px">
          <FormFinanceiro tipo={tipo} responsaveis={RESPONSAVEIS} onSalvo={() => { setAnexarAberto(false); carregar(); }} />
        </Modal>
      )}

      <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden", marginBottom: "1rem" }}>
        <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem" }}>
          <span style={{ fontSize: "0.85rem" }}>{filtradas.length} nota(s) em aberto no filtro — total {formatBRL(totalFiltrado)}</span>
        </div>
        <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead><tr><th>Nota / lançamento</th><th>Vencimento</th><th>{tipo === "receita" ? "Cliente" : "Fornecedor"}</th><th>Produtos</th><th style={{ textAlign: "right" }}>Valor</th><th></th></tr></thead>
            <tbody>
              {filtradas.map((r) => {
                const produtos = (r.itens || []).map((it) => it.produto).filter(Boolean).join(", ");
                const ativa = r.id === notaId;
                return (
                  <tr key={r.id} className="row-clickable" title="Clique para selecionar esta nota" style={{ background: ativa ? "rgba(94,26,46,0.35)" : undefined }} onClick={() => selecionar(r)}>
                    <td style={{ fontSize: "0.78rem" }}>
                      <strong>{r.numero_documento || r.numero_lancamento || "—"}</strong>
                      {r.numero_documento && r.numero_lancamento && <span style={{ color: "var(--text-muted)" }}> · {r.numero_lancamento}</span>}
                      <br /><span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{r.descricao}</span>
                    </td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{produtos || "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    <td>{ativa ? <CheckCircle2 size={14} style={{ color: "var(--dourado-light)" }} /> : <Circle size={14} style={{ color: "var(--text-muted)", opacity: 0.4 }} />}</td>
                  </tr>
                );
              })}
              {!filtradas.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma nota em aberto no filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {notaSelecionada && (
        <div className="card">
          <div className="card-header mb-3">
            Tratar {tipo === "receita" ? "recebimento" : "pagamento"} — {notaSelecionada.descricao} · {formatBRL(notaSelecionada.valor)}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><label style={labelStyleLote}>Data de {tipo === "receita" ? "recebimento" : "pagamento"}</label>
              <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Valor {tipo === "receita" ? "recebido" : "pago"} (R$)</label>
              <input type="number" inputMode="decimal" style={selStyleLote} value={valorPago} onChange={(e) => setValorPago(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Conta corrente</label>
              <select style={selStyleLote} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                <option value="">Selecione…</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
              </select></div>
            <div><label style={labelStyleLote}>Forma</label>
              <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                <option value="">Selecione…</option>{Object.entries(LABEL_FORMA_PAGAMENTO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            {formaPagamento === "credito" ? (
              <div><label style={labelStyleLote}>Vencimento do cartão</label>
                <input type="date" style={selStyleLote} value={dataVencimentoCartao} onChange={(e) => setDataVencimentoCartao(e.target.value)} /></div>
            ) : (
              <div><label style={labelStyleLote}>Nº do comprovante</label>
                <input style={selStyleLote} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
            )}
            {formaPagamento === "credito" && (
              <div><label style={labelStyleLote}>Nº do comprovante</label>
                <input style={selStyleLote} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
            )}
          </div>
          {diferenca !== 0 && (
            <p style={{ fontSize: "0.78rem", marginTop: "0.6rem", color: diferenca < 0 ? "var(--green-light)" : "var(--amber)" }}>
              {diferenca < 0 ? `Desconto de ${formatBRL(Math.abs(diferenca))}` : `Acréscimo de ${formatBRL(diferenca)}`} em relação ao valor do lançamento.
            </p>
          )}
          {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginTop: "0.6rem" }}>{msg.texto}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary" title="Registrar a baixa desta nota" onClick={confirmar} disabled={salvando}>
              <Check size={14} /> {confirmando ? "Confirmar mesmo com diferença" : salvando ? "Salvando…" : "Confirmar baixa"}
            </button>
            <button className="btn-ghost" title="Cancelar e voltar à seleção de nota" onClick={() => setNotaId(null)}>Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}

/*
 * Folha de pagamento — lançamento e acompanhamento por pessoa/competência.
 * Pessoas (funcionário, veterinário, diarista etc.) vêm do cadastro em
 * Configurações > Cadastro > Pessoas; aqui só lançamos e damos baixa.
 */
type PessoaFolha = { id: number; nome: string; tipo: string };
type RegistroFolha = {
  id: number; pessoa_id: number; pessoa_nome: string; competencia: string;
  valor_bruto: number; descontos: number;
  percentual_inss: number; percentual_ir: number; valor_inss: number; valor_ir: number;
  valor_liquido: number;
  data_pagamento: string | null; status: string; observacao: string | null;
  recorrente: boolean; dia_vencimento: number | null;
  origem_recorrencia_id: number | null; numero_lancamento_gerado: string | null;
  detalhe: { label: string; valor: number }[];
};

function arredonda2(n: number) {
  return Math.round(n * 100) / 100;
}

/** Par percentual/valor de retenção (INSS ou IR) — o valor é recalculado
 * automaticamente a partir do percentual, mas fica editável: digitar
 * diretamente no valor "trava" o campo contra o recálculo automático até
 * o percentual ser alterado de novo. */
function CampoRetencao({
  label, percentual, valor, onChangePercentual, onChangeValor,
}: {
  label: string; percentual: string; valor: string;
  onChangePercentual: (v: string) => void; onChangeValor: (v: string) => void;
}) {
  return (
    <>
      <div><label style={labelStyleLote}>{label} (%)</label>
        <input type="number" inputMode="decimal" style={selStyleLote} value={percentual} onChange={(e) => onChangePercentual(e.target.value)} /></div>
      <div><label style={labelStyleLote}>{label} (R$)</label>
        <input type="number" inputMode="decimal" style={selStyleLote} value={valor} onChange={(e) => onChangeValor(e.target.value)} /></div>
    </>
  );
}

function FolhaPagamentoView() {
  const [pessoas, setPessoas] = useState<PessoaFolha[]>([]);
  const [regs, setRegs] = useState<RegistroFolha[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [valorBruto, setValorBruto] = useState("");
  const [descontos, setDescontos] = useState("");
  const [percentualInss, setPercentualInss] = useState("");
  const [valorInss, setValorInss] = useState("");
  const [inssManual, setInssManual] = useState(false);
  const [percentualIr, setPercentualIr] = useState("");
  const [valorIr, setValorIr] = useState("");
  const [irManual, setIrManual] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [recorrente, setRecorrente] = useState(false);
  const [diaVencimento, setDiaVencimento] = useState("5");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [pagoErro, setPagoErro] = useState<string | null>(null);
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [anexarAberto, setAnexarAberto] = useState(false);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPessoaId, setEditPessoaId] = useState("");
  const [editCompetencia, setEditCompetencia] = useState("");
  const [editValorBruto, setEditValorBruto] = useState("");
  const [editDescontos, setEditDescontos] = useState("");
  const [editPercentualInss, setEditPercentualInss] = useState("");
  const [editValorInss, setEditValorInss] = useState("");
  const [editInssManual, setEditInssManual] = useState(true);
  const [editPercentualIr, setEditPercentualIr] = useState("");
  const [editValorIr, setEditValorIr] = useState("");
  const [editIrManual, setEditIrManual] = useState(true);
  const [editObservacao, setEditObservacao] = useState("");
  const [editRecorrente, setEditRecorrente] = useState(false);
  const [editDiaVencimento, setEditDiaVencimento] = useState("5");
  const [editSalvando, setEditSalvando] = useState(false);
  const [editMsg, setEditMsg] = useState<string | null>(null);

  const carregar = () => fetchFolhaPagamento().then(setRegs).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  useEffect(() => {
    if (inssManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualInss) || 0) / 100);
    setValorInss(novo ? String(novo) : "");
  }, [valorBruto, percentualInss, inssManual]);
  useEffect(() => {
    if (irManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualIr) || 0) / 100);
    setValorIr(novo ? String(novo) : "");
  }, [valorBruto, percentualIr, irManual]);
  useEffect(() => {
    if (editInssManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualInss) || 0) / 100);
    setEditValorInss(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualInss, editInssManual]);
  useEffect(() => {
    if (editIrManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualIr) || 0) / 100);
    setEditValorIr(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualIr, editIrManual]);

  const valorLiquido = useMemo(
    () => (parseFloat(valorBruto) || 0) - (parseFloat(descontos) || 0) - (parseFloat(valorInss) || 0) - (parseFloat(valorIr) || 0),
    [valorBruto, descontos, valorInss, valorIr]
  );
  const editValorLiquido = useMemo(
    () => (parseFloat(editValorBruto) || 0) - (parseFloat(editDescontos) || 0) - (parseFloat(editValorInss) || 0) - (parseFloat(editValorIr) || 0),
    [editValorBruto, editDescontos, editValorInss, editValorIr]
  );

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!competencia) { setMsg({ tipo: "erro", texto: "Informe o mês de competência." }); return; }
    if (!valorBruto || parseFloat(valorBruto) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor bruto." }); return; }
    if (recorrente && (!diaVencimento || Number(diaVencimento) < 1 || Number(diaVencimento) > 28)) {
      setMsg({ tipo: "erro", texto: "Informe o dia de vencimento (1 a 28) para lançamentos recorrentes." }); return;
    }
    setSalvando(true);
    try {
      await criarFolhaPagamento({
        pessoa_id: Number(pessoaId), competencia, valor_bruto: parseFloat(valorBruto),
        descontos: parseFloat(descontos) || 0,
        percentual_inss: parseFloat(percentualInss) || 0, percentual_ir: parseFloat(percentualIr) || 0,
        valor_inss: parseFloat(valorInss) || 0, valor_ir: parseFloat(valorIr) || 0,
        observacao: observacao || undefined,
        recorrente, dia_vencimento: recorrente ? Number(diaVencimento) : null,
      });
      setMsg({
        tipo: "sucesso",
        texto: recorrente
          ? "Lançamento de folha criado — as próximas competências serão geradas automaticamente em Contas a Pagar."
          : "Lançamento de folha criado.",
      });
      setPessoaId(""); setValorBruto(""); setDescontos(""); setObservacao(""); setRecorrente(false); setDiaVencimento("5");
      setPercentualInss(""); setValorInss(""); setInssManual(false);
      setPercentualIr(""); setValorIr(""); setIrManual(false);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar folha" });
    } finally {
      setSalvando(false);
    }
  }

  async function marcarPago(r: RegistroFolha) {
    setPagoErro(null);
    try {
      await atualizarFolhaPagamento(r.id, {
        pessoa_id: r.pessoa_id, competencia: r.competencia, valor_bruto: r.valor_bruto,
        descontos: r.descontos, percentual_inss: r.percentual_inss, percentual_ir: r.percentual_ir,
        valor_inss: r.valor_inss, valor_ir: r.valor_ir,
        data_pagamento: dataPagamento, status: "pago", observacao: r.observacao || undefined,
        recorrente: r.recorrente, dia_vencimento: r.dia_vencimento,
      });
      setPagandoId(null);
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao marcar como pago");
    }
  }

  function iniciarEdicao(r: RegistroFolha) {
    setEditingId(r.id);
    setExpandedId(r.id);
    setEditPessoaId(String(r.pessoa_id));
    setEditCompetencia(r.competencia);
    setEditValorBruto(String(r.valor_bruto));
    setEditDescontos(String(r.descontos));
    setEditPercentualInss(r.percentual_inss ? String(r.percentual_inss) : "");
    setEditValorInss(r.valor_inss ? String(r.valor_inss) : "");
    setEditInssManual(true);
    setEditPercentualIr(r.percentual_ir ? String(r.percentual_ir) : "");
    setEditValorIr(r.valor_ir ? String(r.valor_ir) : "");
    setEditIrManual(true);
    setEditObservacao(r.observacao || "");
    setEditRecorrente(r.recorrente);
    setEditDiaVencimento(r.dia_vencimento ? String(r.dia_vencimento) : "5");
    setEditMsg(null);
  }

  async function salvarEdicao(r: RegistroFolha) {
    setEditMsg(null);
    if (!editPessoaId || !editCompetencia || !editValorBruto || parseFloat(editValorBruto) <= 0) {
      setEditMsg("Preencha pessoa, competência e valor bruto.");
      return;
    }
    setEditSalvando(true);
    try {
      await atualizarFolhaPagamento(r.id, {
        pessoa_id: Number(editPessoaId), competencia: editCompetencia, valor_bruto: parseFloat(editValorBruto) || 0,
        descontos: parseFloat(editDescontos) || 0,
        percentual_inss: parseFloat(editPercentualInss) || 0, percentual_ir: parseFloat(editPercentualIr) || 0,
        valor_inss: parseFloat(editValorInss) || 0, valor_ir: parseFloat(editValorIr) || 0,
        observacao: editObservacao || undefined,
        recorrente: editRecorrente, dia_vencimento: editRecorrente ? Number(editDiaVencimento) : null,
        status: r.status, data_pagamento: r.data_pagamento || undefined,
      });
      setEditingId(null);
      carregar();
    } catch (e: any) {
      setEditMsg(e.message || "Erro ao atualizar lançamento de folha");
    } finally {
      setEditSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  const totalPendente = (regs || []).filter((r) => r.status === "pendente").reduce((a, r) => a + r.valor_liquido, 0);
  const totalPago = (regs || []).filter((r) => r.status === "pago").reduce((a, r) => a + r.valor_liquido, 0);

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KPI v={String((regs || []).length)} l="Lançamentos" />
        <KPI v={formatBRL(totalPendente)} l="Pendente" c="var(--amber)" />
        <KPI v={formatBRL(totalPago)} l="Pago" c="var(--green-light)" />
      </div>

      {anexarAberto && (
        <Modal title="Anexar comprovante — leitura automática (despesa)" onClose={() => setAnexarAberto(false)} width="1000px">
          <FormFinanceiro tipo="despesa" responsaveis={RESPONSAVEIS} onSalvo={() => { setAnexarAberto(false); carregar(); }} />
        </Modal>
      )}

      {/* 1) Novo lançamento de folha */}
      <SecaoRecolhivel titulo="Novo lançamento de folha" icon={Plus} defaultAberta={false} descricao="Lance a folha de uma pessoa em uma competência">
        <div className="mb-3" style={{ textAlign: "right" }}>
          <button className="btn-ghost" title="Anexar recibo ou comprovante e preencher por leitura automática" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Anexar recibo/comprovante
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipo})</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Competência (mês)</label>
            <input type="month" style={selStyleLote} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Valor bruto (R$)</label>
            <input type="number" inputMode="decimal" style={selStyleLote} value={valorBruto} onChange={(e) => setValorBruto(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Outros descontos (R$)</label>
            <input type="number" inputMode="decimal" style={selStyleLote} value={descontos} onChange={(e) => setDescontos(e.target.value)} /></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <CampoRetencao
            label="INSS" percentual={percentualInss} valor={valorInss}
            onChangePercentual={(v) => { setPercentualInss(v); setInssManual(false); }}
            onChangeValor={(v) => { setValorInss(v); setInssManual(true); }}
          />
          <CampoRetencao
            label="IR" percentual={percentualIr} valor={valorIr}
            onChangePercentual={(v) => { setPercentualIr(v); setIrManual(false); }}
            onChangeValor={(v) => { setValorIr(v); setIrManual(true); }}
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div><label style={labelStyleLote}>Observação</label>
            <input style={selStyleLote} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
          <div className="flex items-end"><span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Valor líquido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</strong></span></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
          <div className="flex items-center gap-2" style={{ paddingBottom: "0.4rem" }}>
            <input id="folha-recorrente" type="checkbox" checked={recorrente} onChange={(e) => setRecorrente(e.target.checked)} />
            <label htmlFor="folha-recorrente" style={{ fontSize: "0.8rem" }}>Recorrente (lançar em Contas a Pagar todo mês)</label>
          </div>
          {recorrente && (
            <div><label style={labelStyleLote}>Dia de vencimento (1–28)</label>
              <input type="number" min={1} max={28} style={selStyleLote} value={diaVencimento} onChange={(e) => setDiaVencimento(e.target.value)} /></div>
          )}
        </div>
        {recorrente && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
            A partir do próximo mês, o sistema gera automaticamente o lançamento de folha e a conta a pagar correspondente — não é preciso relançar manualmente.
          </p>
        )}
        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
        <button className="btn-primary" title="Salvar o lançamento de folha" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Lançar"}
        </button>
      </SecaoRecolhivel>

      {/* 2) Vale de funcionário */}
      <SecaoRecolhivel titulo="Vale de funcionário" icon={Plus} defaultAberta={false} descricao="Adiantamento pago à parte, descontado da folha">
        <ValeFuncionarioSection pessoas={pessoas} onLancado={carregar} />
      </SecaoRecolhivel>

      {/* 3) Lançamentos de folha listados — clique na linha expande a discriminação completa (incluindo vales aplicados); editável enquanto não estiver paga */}
      <div className="card mt-4">
        <div className="card-header mb-3">Lançamentos de folha</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Pessoa</th><th>Competência</th><th style={{ textAlign: "right" }}>Bruto</th><th style={{ textAlign: "right" }}>Descontos</th><th style={{ textAlign: "right" }}>Líquido</th><th>Status</th><th>Pagamento</th><th></th></tr></thead>
            <tbody>
              {(regs || []).map((r) => {
                const expandido = expandedId === r.id;
                const editando = editingId === r.id;
                return (
                  <Fragment key={r.id}>
                    <tr className="row-clickable" title="Clique para ver a discriminação deste lançamento de folha" onClick={() => setExpandedId(expandido ? null : r.id)}>
                      <td style={{ fontWeight: 600, fontSize: "0.83rem" }}>
                        <span className="flex items-center gap-1">
                          {expandido ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          {r.pessoa_nome}
                        </span>
                        {(r.recorrente || r.origem_recorrencia_id) && (
                          <span title={r.recorrente ? "Modelo recorrente — gera Contas a Pagar todo mês" : "Gerado automaticamente pela recorrência"} style={{ marginLeft: "0.4rem", display: "inline-flex", verticalAlign: "middle", color: "var(--dourado-light)" }}>
                            <RefreshCw size={12} />
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: "0.78rem" }}>{r.competencia}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(r.valor_bruto)}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(arredonda2(r.descontos + r.valor_inss + r.valor_ir))}</td>
                      <td style={{ textAlign: "right", fontWeight: 600, fontSize: "0.83rem" }}>{formatBRL(r.valor_liquido)}</td>
                      <td><span style={{ fontSize: "0.72rem", fontWeight: 700, color: r.status === "pago" ? "var(--green-light)" : "var(--amber)" }}>{r.status === "pago" ? "Pago" : "Pendente"}</span></td>
                      <td style={{ fontSize: "0.75rem" }}>{r.data_pagamento ? formatDate(r.data_pagamento) : "—"}</td>
                      <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                        {r.status === "pendente" && (
                          <button className="btn-ghost" title="Registrar o pagamento deste lançamento de folha" style={{ fontSize: "0.72rem" }} onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>Marcar como pago</button>
                        )}
                      </td>
                    </tr>
                    {pagandoId === r.id && (
                      <tr><td colSpan={8}>
                        <div className="flex items-end gap-2" style={{ padding: "0.5rem 0", flexWrap: "wrap" }} onClick={(e) => e.stopPropagation()}>
                          <div><label style={labelStyleLote}>Data do pagamento</label>
                            <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
                          <button className="btn-primary" title="Confirmar pagamento" style={{ fontSize: "0.78rem" }} onClick={() => marcarPago(r)}><Check size={13} /> Confirmar</button>
                          <button className="btn-ghost" title="Cancelar" style={{ fontSize: "0.78rem" }} onClick={() => { setPagoErro(null); setPagandoId(null); }}>Cancelar</button>
                          {pagoErro && <span style={{ color: "var(--red)", fontSize: "0.78rem", alignSelf: "center" }}>{pagoErro}</span>}
                        </div>
                      </td></tr>
                    )}
                    {expandido && !editando && (
                      <tr><td colSpan={8}>
                        <div style={{ padding: "0.6rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <table style={{ width: "100%", maxWidth: 420, fontSize: "0.78rem" }}>
                            <tbody>
                              {r.detalhe.map((d, i) => (
                                <tr key={i}>
                                  <td style={{ padding: "0.15rem 0.5rem 0.15rem 0", fontWeight: d.label === "Valor líquido" ? 700 : 400 }}>{d.label}</td>
                                  <td style={{ textAlign: "right", fontWeight: d.label === "Valor líquido" ? 700 : 400, color: d.valor < 0 ? "var(--red)" : undefined }}>{formatBRL(d.valor)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {r.observacao && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Obs.: {r.observacao}</p>}
                          {r.status !== "pago" ? (
                            <button className="btn-ghost mt-2" title="Editar este lançamento de folha (enquanto não estiver pago)" style={{ fontSize: "0.75rem" }} onClick={() => iniciarEdicao(r)}>
                              <Pencil size={12} /> Editar lançamento
                            </button>
                          ) : (
                            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Lançamento já pago — não pode mais ser editado.</p>
                          )}
                        </div>
                      </td></tr>
                    )}
                    {editando && (
                      <tr><td colSpan={8}>
                        <div style={{ padding: "0.75rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Pessoa</label>
                              <select style={selStyleLote} value={editPessoaId} onChange={(e) => setEditPessoaId(e.target.value)}>
                                {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipo})</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Competência (mês)</label>
                              <input type="month" style={selStyleLote} value={editCompetencia} onChange={(e) => setEditCompetencia(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Valor bruto (R$)</label>
                              <input type="number" inputMode="decimal" style={selStyleLote} value={editValorBruto} onChange={(e) => setEditValorBruto(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Outros descontos (R$)</label>
                              <input type="number" inputMode="decimal" style={selStyleLote} value={editDescontos} onChange={(e) => setEditDescontos(e.target.value)} /></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <CampoRetencao
                              label="INSS" percentual={editPercentualInss} valor={editValorInss}
                              onChangePercentual={(v) => { setEditPercentualInss(v); setEditInssManual(false); }}
                              onChangeValor={(v) => { setEditValorInss(v); setEditInssManual(true); }}
                            />
                            <CampoRetencao
                              label="IR" percentual={editPercentualIr} valor={editValorIr}
                              onChangePercentual={(v) => { setEditPercentualIr(v); setEditIrManual(false); }}
                              onChangeValor={(v) => { setEditValorIr(v); setEditIrManual(true); }}
                            />
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editObservacao} onChange={(e) => setEditObservacao(e.target.value)} /></div>
                            <div className="flex items-end"><span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Valor líquido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(editValorLiquido)}</strong></span></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
                            <div className="flex items-center gap-2" style={{ paddingBottom: "0.4rem" }}>
                              <input id="folha-edit-recorrente" type="checkbox" checked={editRecorrente} onChange={(e) => setEditRecorrente(e.target.checked)} />
                              <label htmlFor="folha-edit-recorrente" style={{ fontSize: "0.8rem" }}>Recorrente</label>
                            </div>
                            {editRecorrente && (
                              <div><label style={labelStyleLote}>Dia de vencimento (1–28)</label>
                                <input type="number" min={1} max={28} style={selStyleLote} value={editDiaVencimento} onChange={(e) => setEditDiaVencimento(e.target.value)} /></div>
                            )}
                          </div>
                          {editMsg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{editMsg}</p>}
                          <div className="flex items-center gap-2">
                            <button className="btn-primary" title="Salvar as alterações deste lançamento" style={{ fontSize: "0.78rem" }} onClick={() => salvarEdicao(r)} disabled={editSalvando}>
                              <Check size={13} /> {editSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" title="Cancelar a edição" style={{ fontSize: "0.78rem" }} onClick={() => setEditingId(null)}>Cancelar</button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
              {regs && !regs.length && <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento de folha ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const FORMAS_VALE = [
  { value: "dinheiro", label: "Dinheiro" }, { value: "pix", label: "Pix" },
  { value: "transferencia", label: "Transferência" }, { value: "desconto_integral_folha", label: "Desconto integral na próxima folha" },
];

/**
 * Vale de funcionário — só o formulário de lançamento. A lista de parcelas
 * geradas não aparece mais aqui: ela vira a expansão da folha listada (na
 * competência em que a parcela é aplicada), por decisão explícita do
 * usuário — ver `_detalhe_folha` no backend.
 */
function ValeFuncionarioSection({ pessoas, onLancado }: { pessoas: PessoaFolha[]; onLancado: () => void }) {
  const [pessoaId, setPessoaId] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("dinheiro");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState("1");
  const [competenciaInicio, setCompetenciaInicio] = useState(() => new Date().toISOString().slice(0, 7));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  async function lancar(confirmar = false) {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!valorTotal || parseFloat(valorTotal) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor do vale." }); return; }
    if (!parcelas || Number(parcelas) < 1) { setMsg({ tipo: "erro", texto: "Informe ao menos 1 parcela." }); return; }
    setSalvando(true);
    try {
      await criarVale({
        pessoa_id: Number(pessoaId), valor_total: parseFloat(valorTotal), forma_pagamento: formaPagamento,
        data_pagamento: dataPagamento, parcelas: Number(parcelas), competencia_inicio: competenciaInicio,
        observacao: observacao || undefined, confirmar,
      });
      setMsg({ tipo: "sucesso", texto: "Vale lançado — o desconto aparecerá na expansão da folha de cada competência afetada." });
      setPessoaId(""); setValorTotal(""); setParcelas("1"); setObservacao("");
      onLancado();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (R$ ${c.total.toFixed(2)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja lançar mesmo assim?`)) {
          await lancar(true);
          setSalvando(false);
          return;
        }
      } else {
        setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar vale" });
      }
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Adiantamento pago à parte, descontado da folha em uma ou mais competências. Se a soma dos descontos de vale
        de uma competência ultrapassar 40% do salário base da pessoa, o sistema pede confirmação antes de lançar.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyleLote}>Pessoa</label>
          <select style={selStyleLote} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
            <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipo})</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Valor total (R$)</label>
          <input type="number" inputMode="decimal" style={selStyleLote} value={valorTotal} onChange={(e) => setValorTotal(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Forma de pagamento</label>
          <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
            {FORMAS_VALE.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Data do pagamento</label>
          <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyleLote}>Parcelas do desconto</label>
          <input type="number" min={1} style={selStyleLote} value={parcelas} onChange={(e) => setParcelas(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Competência inicial do desconto</label>
          <input type="month" style={selStyleLote} value={competenciaInicio} onChange={(e) => setCompetenciaInicio(e.target.value)} /></div>
        <div style={{ gridColumn: "span 2" }}><label style={labelStyleLote}>Observação</label>
          <input style={selStyleLote} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      </div>
      {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
      <button className="btn-primary" title="Lançar o vale" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={() => lancar(false)} disabled={salvando}>
        <Check size={14} /> {salvando ? "Salvando…" : "Lançar vale"}
      </button>
    </div>
  );
}

/*
 * RMCA (Receita Menos Custo com Alimentação) — duas versões lado a lado, por
 * decisão explícita do usuário: "gerencial" (contas do plano de contas
 * marcadas em Configurações > Parâmetros financeiros) e "físico" (consumo
 * real registrado pela Alimentação × valor unitário do Estoque).
 */
type ItemFisicoRmca = { ingrediente: string; quantidade: number; valor_unitario: number; custo: number };
type RmcaResp = {
  periodo: { inicio: string; fim: string };
  configurado: boolean;
  contas_receita: string[];
  contas_custo: string[];
  gerencial: { receita_leite: number; custo_alimentacao: number; rmca: number };
  fisico: { receita_leite: number; custo_alimentacao: number; rmca: number; itens: ItemFisicoRmca[] };
};

function primeiroDiaDoMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
}

/* ───────────────────────── Roteiro do RMCA (modal em tela, mesmo padrão do manual de colostro/sangue) ───────────────────────── */
const ROTEIRO_RMCA = [
  { t: "1. O que é o RMCA", d: "Receita Menos Custo com Alimentação: quanto sobra da receita do leite depois de descontar o gasto com ração/alimentação no mesmo período. Duas versões lado a lado — gerencial e físico — para conferência cruzada." },
  { t: "2. Versão gerencial — marque as contas", d: "Vá em Configurações → Parâmetros financeiros → Conta gerencial. Marque a(s) conta(s) de receita que representam a venda do leite (ex.: \"Leite indústria\") e a(s) conta(s) de despesa que representam alimentação (ex.: \"Ração\", \"Silagem\", \"Sal mineral\"). O RMCA gerencial soma os lançamentos financeiros dessas contas no período." },
  { t: "3. Versão física — indique os produtos", d: "Vá em Configurações → Cadastro → Itens de estoque. Na coluna RMCA, marque quais produtos são ração/alimento e devem entrar no custo físico. Desmarque produtos que não são alimentação (medicamentos, materiais etc.), mesmo que também tenham baixa de \"Saída de ajuste\"." },
  { t: "4. Como o custo físico é calculado", d: "Para cada produto marcado, o sistema soma a quantidade baixada como \"Saída de ajuste\" pela Alimentação no período e multiplica pelo valor unitário cadastrado no Estoque. O card \"RMCA físico\" mostra o detalhamento produto a produto." },
  { t: "5. Por que duas versões", d: "A gerencial reflete o que foi de fato lançado no financeiro (pode incluir sobras de estoque, compras antecipadas). A física reflete o consumo real no período, ainda que o pagamento tenha sido em outro mês. Comparar as duas ajuda a identificar diferenças de timing." },
];

function RoteiroRmcaModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "560px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Roteiro — Como indicar os produtos do RMCA</div>
          <button onClick={onClose} title="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {ROTEIRO_RMCA.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--dourado-light)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RmcaView() {
  const [dataInicio, setDataInicio] = useState(() => primeiroDiaDoMes());
  const [dataFim, setDataFim] = useState(() => new Date().toISOString().slice(0, 10));
  const [dados, setDados] = useState<RmcaResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [roteiroAberto, setRoteiroAberto] = useState(false);

  useEffect(() => { fetchRmca(dataInicio, dataFim).then(setDados).catch((e) => setErro(e.message)); }, [dataInicio, dataFim]);

  return (
    <div>
      {roteiroAberto && <RoteiroRmcaModal onClose={() => setRoteiroAberto(false)} />}

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Período</span>
          <button className="btn-ghost" title="Abrir o passo a passo de configuração do RMCA" style={{ fontSize: "0.75rem" }} onClick={() => setRoteiroAberto(true)}>
            <BookOpen size={13} /> Roteiro — como indicar os produtos do RMCA
          </button>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Início</label><input type="date" style={selStyleLote} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Fim</label><input type="date" style={selStyleLote} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {!dados.configurado && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Nenhuma conta gerencial está marcada como receita do leite ou custo de alimentação — a versão gerencial fica zerada até a configuração ser feita.
                Marque em <strong>Configurações → Parâmetros financeiros → Conta gerencial</strong>.
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-header mb-3">RMCA gerencial</div>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                A partir dos lançamentos financeiros, pelas contas marcadas como receita do leite / custo de alimentação.
              </p>
              <div className="grid grid-cols-1 gap-3 mb-3">
                <KPI v={formatBRL(dados.gerencial.receita_leite)} l="Receita do leite" c="var(--green-light)" />
                <KPI v={formatBRL(dados.gerencial.custo_alimentacao)} l="Custo de alimentação" c="var(--red)" />
                <KPI v={formatBRL(dados.gerencial.rmca)} l="RMCA" c={dados.gerencial.rmca >= 0 ? "var(--green-light)" : "var(--amber)"} />
              </div>
              {dados.contas_receita.length > 0 && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Receita: {dados.contas_receita.join(", ")}</p>}
              {dados.contas_custo.length > 0 && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Custo: {dados.contas_custo.join(", ")}</p>}
            </div>
            <div className="card">
              <div className="card-header mb-3">RMCA físico</div>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Mesma receita do leite, mas custo a partir do consumo real registrado pela Alimentação × valor unitário do Estoque.
              </p>
              <div className="grid grid-cols-1 gap-3 mb-3">
                <KPI v={formatBRL(dados.fisico.receita_leite)} l="Receita do leite" c="var(--green-light)" />
                <KPI v={formatBRL(dados.fisico.custo_alimentacao)} l="Custo de alimentação (físico)" c="var(--red)" />
                <KPI v={formatBRL(dados.fisico.rmca)} l="RMCA" c={dados.fisico.rmca >= 0 ? "var(--green-light)" : "var(--amber)"} />
              </div>
              {dados.fisico.itens.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Consumo</th><th style={{ textAlign: "right" }}>Vlr. unit.</th><th style={{ textAlign: "right" }}>Custo</th></tr></thead>
                    <tbody>
                      {dados.fisico.itens.map((it) => (
                        <tr key={it.ingrediente}>
                          <td style={{ fontSize: "0.78rem" }}>{it.ingrediente}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{it.quantidade}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(it.valor_unitario)}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(it.custo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {!dados.fisico.itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem consumo registrado pela Alimentação no período.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
