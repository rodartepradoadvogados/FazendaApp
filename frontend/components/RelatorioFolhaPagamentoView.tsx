"use client";
import { useEffect, useMemo, useState } from "react";
import { Filter } from "lucide-react";
import { fetchFolhaPagamentoUnificada, fetchPessoas, formatBRL, formatDate, type LinhaFolhaUnificada } from "@/lib/api";
import { Indicador } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const LABEL_TIPO: Record<string, string> = { funcionario: "Funcionário", empreita: "Empreita", contrato: "Contrato", diaria: "Diária" };
const VENCIDO_BG = "rgba(94, 26, 46, 0.18)";

const selStyle: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <Indicador categoria="financeiro" valor={v} rotulo={l} cor={c || "var(--dourado-light)"} />;
}

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Tipo", key: "tipoLabel" }, { header: "Pessoa", key: "pessoa_nome" }, { header: "Descrição", key: "descricao" },
  { header: "Vencimento", key: "vencimentoFmt" }, { header: "Valor", key: "valorFmt" },
  { header: "Pagamento", key: "pagamentoFmt" }, { header: "Status", key: "statusLabel" },
];

/*
 * Relatório da folha de pagamento — Financeiro > Contas > Folha de Pagamento.
 * Visão somente leitura da mesma folha unificada (funcionário, empreita,
 * contrato, diária) lançada em Financeiro > Ações > Folha de pagamento,
 * com filtro de pagos/a vencer e exportação Excel/PDF.
 */
export default function RelatorioFolhaPagamentoView() {
  const [linhas, setLinhas] = useState<LinhaFolhaUnificada[] | null>(null);
  const [pessoas, setPessoas] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [vencDe, setVencDe] = useState("");
  const [vencAte, setVencAte] = useState("");
  const [status, setStatus] = useState<"" | "pendente" | "pago">("");
  const [pessoaId, setPessoaId] = useState("");
  const [tipo, setTipo] = useState<"" | "funcionario" | "empreita" | "contrato" | "diaria">("");

  useEffect(() => {
    fetchFolhaPagamentoUnificada().then(setLinhas).catch((e) => setError(e.message));
    fetchPessoas().then(setPessoas).catch(() => {});
  }, []);

  const filtradas = useMemo(() => (linhas || []).filter((l) =>
    (!vencDe || (l.data_vencimento || "") >= vencDe) &&
    (!vencAte || (l.data_vencimento || "") <= vencAte) &&
    (!status || l.status === status) &&
    (!pessoaId || String(l.pessoa_id) === pessoaId) &&
    (!tipo || l.tipo === tipo)
  ), [linhas, vencDe, vencAte, status, pessoaId, tipo]);

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtradas);

  const somaFiltrada = filtradas.reduce((a, l) => a + l.valor, 0);
  const somaPendente = filtradas.filter((l) => l.status === "pendente").reduce((a, l) => a + l.valor, 0);
  const somaPaga = filtradas.filter((l) => l.status === "pago").reduce((a, l) => a + l.valor, 0);

  const linhasExport = useMemo(() => linhasOrdenadas.map((l) => ({
    tipoLabel: LABEL_TIPO[l.tipo] || l.tipo, pessoa_nome: l.pessoa_nome, descricao: l.descricao,
    vencimentoFmt: l.data_vencimento ? formatDate(l.data_vencimento) : "—",
    valorFmt: formatBRL(l.valor),
    pagamentoFmt: l.data_pagamento ? formatDate(l.data_pagamento) : "—",
    statusLabel: l.status === "pago" ? "Pago" : (l.vencido ? "Vencido" : "A vencer"),
  })), [linhasOrdenadas]);

  if (error) return <div className="alert-critico mb-4"><span>Sem dados: {error}.</span></div>;
  if (!linhas) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KPI v={String(filtradas.length)} l="Lançamentos" />
        <KPI v={formatBRL(somaPendente)} l="A vencer" c="var(--red)" />
        <KPI v={formatBRL(somaPaga)} l="Pago" c="var(--green-light)" />
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar a folha de pagamento</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
          <div><label style={labelStyle}>Vencimento de</label>
            <input type="date" style={selStyle} value={vencDe} onChange={(e) => setVencDe(e.target.value)} /></div>
          <div><label style={labelStyle}>Vencimento até</label>
            <input type="date" style={selStyle} value={vencAte} onChange={(e) => setVencAte(e.target.value)} /></div>
          <div><label style={labelStyle}>Status</label>
            <select style={selStyle} value={status} onChange={(e) => setStatus(e.target.value as any)}>
              <option value="">Todos</option><option value="pendente">A vencer</option><option value="pago">Pago</option>
            </select></div>
          <div><label style={labelStyle}>Pessoa</label>
            <select style={selStyle} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Todas</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
          <div><label style={labelStyle}>Tipo</label>
            <select style={selStyle} value={tipo} onChange={(e) => setTipo(e.target.value as any)}>
              <option value="">Todos</option>
              {Object.entries(LABEL_TIPO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select></div>
        </div>
      </div>

      <div className="flex items-center justify-between mb-3">
        <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Total filtrado: <strong style={{ color: "var(--text)" }}>{formatBRL(somaFiltrada)}</strong></span>
        <ExportarBotoes titulo="Folha de Pagamento" nomeArquivoBase="financeiro_folha_pagamento" colunas={COLUNAS_EXPORT} linhas={linhasExport} />
      </div>

      <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead>
            <tr>
              <ThOrdenavel label="Tipo" campo="tipo" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={coluna} dir={dir} ordenar={ordenar} />
              <th>Descrição</th>
              <ThOrdenavel label="Vencimento" campo="data_vencimento" coluna={coluna} dir={dir} ordenar={ordenar} />
              <ThOrdenavel label="Valor" campo="valor" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
              <th>Pagamento</th>
              <ThOrdenavel label="Status" campo="status" coluna={coluna} dir={dir} ordenar={ordenar} />
            </tr>
          </thead>
          <tbody>
            {linhasOrdenadas.map((l, i) => (
              <tr key={`${l.tipo}-${l.origem_id}-${i}`} style={{ background: l.vencido ? VENCIDO_BG : undefined }}>
                <td style={{ fontSize: "0.78rem" }}>{LABEL_TIPO[l.tipo] || l.tipo}</td>
                <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{l.pessoa_nome}</td>
                <td style={{ fontSize: "0.78rem" }}>{l.descricao}</td>
                <td style={{ fontSize: "0.78rem" }}>{l.data_vencimento ? formatDate(l.data_vencimento) : "—"}</td>
                <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{formatBRL(l.valor)}</td>
                <td style={{ fontSize: "0.78rem" }}>{l.data_pagamento ? formatDate(l.data_pagamento) : "—"}</td>
                <td style={{ fontSize: "0.78rem" }}>
                  {l.status === "pago" ? <span style={{ color: "var(--green-light)" }}>Pago</span>
                    : l.vencido ? <span style={{ color: "var(--red)" }}>Vencido</span>
                    : <span style={{ color: "var(--text-muted)" }}>A vencer</span>}
                </td>
              </tr>
            ))}
            {!linhasOrdenadas.length && (
              <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                {linhas.length ? "Nenhum lançamento para os filtros escolhidos." : "Nenhum lançamento de folha ainda."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
