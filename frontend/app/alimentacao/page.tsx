"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, Wheat, ChevronDown, ChevronRight, ListOrdered, PieChart, CalendarClock, Package, FileSpreadsheet, FileText, NotebookPen } from "lucide-react";
import { fetchAlimentacao, fetchNecessidadeMensal, fetchEstadoBaixaAlimentacao } from "@/lib/api";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { MultiFiltro, TelaSkeleton } from "@/components/ui";
import { exportarMultiExcel, exportarFichaPDF, type SecaoFicha } from "@/lib/export";
// A dieta em si (CadastrarNovaDieta) mudou de casa para cá — pedido original:
// "tirar alimentação [de Lançamentos] e colocar dentro de Insumos e Sanidade
// - Alimentação, mas com o nome de Lançar nova dieta". Continua o mesmo
// componente único (histórico de dietas, registrar real, comparativo), só
// muda quem o monta — ver components/lancamentos/FormAlimentacaoDieta.tsx.
const FormAlimentacaoDieta = dynamic(() => import("@/components/lancamentos/FormAlimentacaoDieta").then((m) => m.FormAlimentacaoDieta), { ssr: false });

const TRATOS = 2; // 2 tratos por dia
const fmt = (v: number) => Number(v.toFixed(2)).toLocaleString("pt-BR");
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

function StatusBaixa() {
  const [estado, setEstado] = useState<{ ultima_data_deducao: string | null } | null>(null);
  useEffect(() => { fetchEstadoBaixaAlimentacao().then(setEstado).catch(() => {}); }, []);
  if (!estado) return null;
  return (
    <div className="card mb-4 flex items-center gap-2" style={{ background: "rgba(94,26,46,0.18)" }}>
      <Package size={15} style={{ color: "var(--dourado-light)" }} />
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
        Baixa automática de estoque: última atualização em <strong style={{ color: "var(--text)" }}>{fmtDia(estado.ultima_data_deducao)}</strong>.
        O sistema desconta o consumo acumulado do estoque sozinho, conforme os dias que passaram desde a última vez — sem precisar de botão.
      </p>
    </div>
  );
}

function ConsumoDiario({ a, error }: { a: any; error: string | null }) {
  const total: any[] = a?.consumo_total ?? [];
  const porLote: any[] = a?.por_lote ?? [];
  const [lotesSel, setLotesSel] = useState<string[]>([]);

  const lotesOpcoes = useMemo(() => Array.from(new Set(porLote.map((l) => String(l.lote)))), [porLote]);

  const totalFiltrado = useMemo(() => {
    if (!lotesSel.length) return total;
    const selecionados = porLote.filter((l) => lotesSel.includes(String(l.lote)));
    const acc = new Map<string, { ingrediente: string; unidade: string; consumo_dia: number }>();
    for (const l of selecionados) {
      for (const i of l.itens ?? []) {
        const atual = acc.get(i.ingrediente);
        if (atual) atual.consumo_dia += i.consumo_dia;
        else acc.set(i.ingrediente, { ingrediente: i.ingrediente, unidade: i.unidade, consumo_dia: i.consumo_dia });
      }
    }
    return Array.from(acc.values());
  }, [lotesSel, porLote, total]);

  const maxTotal = totalFiltrado.reduce((m, x) => Math.max(m, x.consumo_dia), 0) || 1;
  return (
    <div className="card">
      <div className="card-header mb-3">Consumo Diário do Rebanho (por ingrediente)</div>
      <div style={{ maxWidth: "16rem", marginBottom: "0.9rem" }}>
        <MultiFiltro label="Lote" opcoes={lotesOpcoes} selecionados={lotesSel} onChange={setLotesSel} />
      </div>
      <table className="fazenda-table">
        <thead><tr><th>Ingrediente</th><th></th><th style={{ textAlign: "right" }}>Por dia</th><th style={{ textAlign: "right" }}>Por trato</th></tr></thead>
        <tbody>
          {totalFiltrado.map((x) => (
            <tr key={x.ingrediente}>
              <td style={{ fontWeight: 600, fontSize: "0.85rem", minWidth: "9rem" }}>{x.ingrediente}</td>
              <td style={{ width: "40%" }}>
                <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", height: "14px", overflow: "hidden" }}><div style={{ width: `${(x.consumo_dia / maxTotal) * 100}%`, height: "100%", background: "var(--dourado)", minWidth: "2px" }} /></div>
              </td>
              <td style={{ textAlign: "right", fontWeight: 700 }}>{fmt(x.consumo_dia)} {x.unidade}</td>
              <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{fmt(x.consumo_dia / TRATOS)} {x.unidade}</td>
            </tr>
          ))}
          {!totalFiltrado.length && !error && <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>Sem dieta carregada.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function PlanoPorLote({ a }: { a: any }) {
  const porLote: any[] = a?.por_lote ?? [];
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const toggle = (l: number) => setAbertos((p) => { const n = new Set(p); n.has(l) ? n.delete(l) : n.add(l); return n; });

  // Seleção de lote(s) pra exportação — vazio = todos (mesmo padrão do
  // filtro de Consumo Diário acima).
  const [lotesExport, setLotesExport] = useState<string[]>([]);
  const lotesOpcoes = useMemo(() => porLote.map((l) => String(l.lote)), [porLote]);
  const [exportando, setExportando] = useState(false);

  function secoesParaExportar(): SecaoFicha[] {
    const alvo = lotesExport.length ? porLote.filter((l) => lotesExport.includes(String(l.lote))) : porLote;
    return alvo.map((l) => ({
      titulo: `Lote ${l.lote} — ${l.categoria} (${l.efetivo} cab.)`,
      colunas: [
        { header: "Ingrediente", key: "ingrediente" },
        { header: "Por cabeça", key: "por_cabeca" },
        { header: "Lote/dia", key: "lote_dia" },
        { header: "Lote/trato", key: "lote_trato" },
      ],
      linhas: (l.itens || []).map((i: any) => ({
        ingrediente: i.ingrediente,
        por_cabeca: `${fmt(i.por_cabeca)} ${i.unidade}`,
        lote_dia: `${fmt(i.consumo_dia)} ${i.unidade}`,
        lote_trato: `${fmt(i.consumo_dia / TRATOS)} ${i.unidade}`,
      })),
    }));
  }

  async function exportar(formato: "pdf" | "excel") {
    setExportando(true);
    try {
      const secoes = secoesParaExportar();
      const subtitulo = lotesExport.length ? `Lote(s): ${lotesExport.join(", ")}` : "Todos os lotes";
      if (formato === "pdf") await exportarFichaPDF("Plano por Lote", subtitulo, secoes, "plano_por_lote");
      else await exportarMultiExcel("Plano por Lote", secoes, "plano_por_lote");
    } catch {
      // erro já mostrado ao usuário dentro de exportarFichaPDF/exportarMultiExcel (lib/export.ts)
    } finally {
      setExportando(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.6rem" }}>
        <span>Plano por Lote <span style={{ fontWeight: 400, fontSize: "0.72rem", color: "var(--text-muted)" }}>(clique para expandir)</span></span>
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          <div style={{ minWidth: "12rem" }}>
            <MultiFiltro label="Lote(s) a exportar" opcoes={lotesOpcoes} selecionados={lotesExport} onChange={setLotesExport} />
          </div>
          <button type="button" className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.78rem" }}
            disabled={exportando || !porLote.length} onClick={() => exportar("excel")}>
            <FileSpreadsheet size={14} /> Excel
          </button>
          <button type="button" className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.78rem" }}
            disabled={exportando || !porLote.length} onClick={() => exportar("pdf")}>
            <FileText size={14} /> PDF
          </button>
        </div>
      </div>
      <div className="space-y-2">
        {porLote.map((l) => {
          const aberto = abertos.has(l.lote);
          return (
            <div key={l.lote} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
              <button onClick={() => toggle(l.lote)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.6rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <span style={{ fontWeight: 700, minWidth: "1.5rem" }}>{l.lote}</span>
                <span style={{ flex: 1 }}>{l.categoria}</span>
                <span style={{ fontSize: "0.8rem", color: l.efetivo === 0 ? "var(--text-muted)" : "var(--dourado-light)" }}>{l.efetivo} cab.</span>
              </button>
              {aberto && (
                <div style={{ overflowX: "auto" }}>
                  <table className="fazenda-table" style={{ margin: 0, minWidth: 440 }}>
                    <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Por cabeça</th><th style={{ textAlign: "right" }}>Lote/dia</th><th style={{ textAlign: "right" }}>Lote/trato</th></tr></thead>
                    <tbody>
                      {l.itens.map((i: any) => (
                        <tr key={i.ingrediente}>
                          <td style={{ fontSize: "0.82rem", whiteSpace: "nowrap" }}>{i.ingrediente}</td>
                          <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{fmt(i.por_cabeca)} {i.unidade}</td>
                          <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{fmt(i.consumo_dia)} {i.unidade}</td>
                          <td style={{ textAlign: "right", color: "var(--text-muted)", whiteSpace: "nowrap" }}>{fmt(i.consumo_dia / TRATOS)} {i.unidade}</td>
                        </tr>
                      ))}
                      {!l.itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem dieta para este lote.</td></tr>}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NecessidadeMensal() {
  const [dados, setDados] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchNecessidadeMensal().then(setDados).catch((e) => setError(e.message)); }, []);

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!dados) return <TelaSkeleton />;

  const itens: any[] = dados.itens ?? [];
  return (
    <div className="card">
      <div className="card-header mb-3">Necessidade mensal (30 dias)</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Projeção simples: consumo diário × 30. Itens de estoque cadastrados com unidade "saca 30kg"/"saca 60kg" (ou com o cadastro
        de embalagem preenchido em Configurações {"›"} Cadastro {"›"} Estoque {"›"} Itens de Estoque) aparecem convertidos em sacos (arredondado para cima).
      </p>
      <table className="fazenda-table">
        <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Necessidade (30d)</th><th style={{ textAlign: "right" }}>Sacos (30d)</th><th>Vínculo com estoque</th></tr></thead>
        <tbody>
          {itens.map((i) => (
            <tr key={i.ingrediente}>
              <td style={{ fontWeight: 600, fontSize: "0.85rem" }}>{i.ingrediente}</td>
              <td style={{ textAlign: "right", fontWeight: 700 }}>{fmt(i.necessidade_mes)} {i.unidade}</td>
              <td style={{ textAlign: "right" }}>{i.sacos_mes ?? "—"}</td>
              <td style={{ fontSize: "0.76rem", color: i.item_estoque_vinculado ? "var(--green-light)" : "var(--amber)" }}>
                {i.item_estoque_vinculado
                  ? (i.ensacado ? `Ensacado (${i.kg_por_saco} kg/saco)` : "Vinculado (a granel)")
                  : i.alimento_sem_vinculo
                    ? "Alimento cadastrado, mas sem produto de estoque vinculado — cadastre o vínculo em Configurações › Cadastro › Alimentação › Alimentos"
                    : "Sem item de estoque nem alimento cadastrado com esse nome"}
              </td>
            </tr>
          ))}
          {!itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>Sem dieta carregada.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// Item D1 da sessão 3: "Lançar nova dieta" entra ANTES de "Consumo Diário" —
// é o cadastro/plano da dieta em si (o lançamento do CONSUMO do dia a dia
// ficou em Lançamentos > Alimentação, ver components/lancamentos/ConsumoAlimento.tsx).
const ABAS = [
  ["nova_dieta", "Lançar nova dieta", NotebookPen],
  ["consumo", "Consumo Diário", ListOrdered],
  ["lote", "Plano por Lote", PieChart],
  ["mensal", "Necessidade mensal", CalendarClock],
] as const;

export default function AlimentacaoPage() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("nova_dieta");
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchAlimentacao().then(setA).catch((e) => setError(e.message)); }, []);

  // Link "Ir para Dieta" da Agenda manda ?lote=NN — abre direto na aba de
  // dieta, que é quem sabe ler esse parâmetro (abre a seção de encerrar do
  // lote). Continua funcionando de graça se algum dia apontar pra cá também.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("lote")) setAba("nova_dieta");
  }, []);

  const subNavTree: SubNavNode[] = useMemo(() => ABAS.map(([id, label, Icon]) => ({ id, label, icon: Icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: (id: string) => setAba(id as (typeof ABAS)[number][0]) }), [subNavTree, aba]));

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Wheat size={22} style={{ color: "var(--dourado-light)" }} /> Alimentação</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Dieta por lote cruzada com o efetivo — consumo por cabeça, por lote/dia e por lote/trato ({TRATOS} tratos/dia).</p>
      </div>

      {/* Erro de fetchAlimentacao só diz respeito às 2 abas que dependem dela
          (consumo/lote). A aba de dieta usa fetchDietas e a de necessidade
          mensal usa fetchNecessidadeMensal, cada uma com erro próprio. */}
      {error && (aba === "consumo" || aba === "lote") && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados de alimentação</a>.</span></div>}

      <StatusBaixa />

      {aba === "nova_dieta" && <FormAlimentacaoDieta />}

      {!a && !error && aba !== "nova_dieta" && <TelaSkeleton kpis={0} />}
      {a && aba === "consumo" && <ConsumoDiario a={a} error={error} />}
      {a && aba === "lote" && <PlanoPorLote a={a} />}
      {aba === "mensal" && <NecessidadeMensal />}
    </div>
  );
}
