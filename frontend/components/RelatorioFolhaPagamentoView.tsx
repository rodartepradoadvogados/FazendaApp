"use client";
import { useEffect, useMemo, useState } from "react";
import { Filter, Printer, Search } from "lucide-react";
import {
  fetchFolhaPagamentoUnificada, fetchPessoas, formatBRL, formatDate, type LinhaFolhaUnificada,
} from "@/lib/api";
import { Indicador, TabBar } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { Holerite } from "@/components/Holerite";
import {
  competenciaExtenso, filtrarPorSituacao, holeriteDaLinha, imprimirHolerites,
  type Holerite as DocHolerite, type SituacaoPagamento,
} from "@/lib/holerite";
import type { ColunaExport } from "@/lib/export";

const LABEL_TIPO: Record<string, string> = {
  funcionario: "Funcionário", empreita: "Empreita", contrato: "Contrato", diaria: "Diária", ferias_decimo: "Férias / 13º",
};
const VENCIDO_BG = "rgba(94, 26, 46, 0.18)";

// "A pagar" é tudo o que ainda não foi pago, vencido ou não: a pergunta aqui
// é de caixa. O atraso continua sendo dito pelo selo VENCIDO do documento e
// pelo destaque da linha na tabela — soma-se a este filtro, não o fatia.
const SITUACOES: { id: SituacaoPagamento; label: string; dica: string }[] = [
  { id: "pagos", label: "Pagos", dica: "Só os recibos cujo pagamento já saiu" },
  { id: "a_pagar", label: "A pagar", dica: "Tudo o que ainda não foi pago, vencido ou não" },
  { id: "todos", label: "Todos", dica: "Pagos e a pagar, juntos" },
];

const selStyle: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
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
 * Financeiro > Contas > Holerites e recibos.
 *
 * Esta tela e a de Ações > Fechamento da folha chamavam-se as duas "Folha de
 * Pagamento" e a segunda continha a primeira — daí a confusão. Elas passam a
 * ter trabalhos distintos: lá se FECHA o mês, aqui se CONSULTA E IMPRIME o
 * documento.
 *
 * O que mudou aqui, concretamente: a tela era a mesma tabela da outra SEM o
 * clique (`<tr>` sem onClick em 153 linhas), e o endpoint unificado calculava
 * a discriminação e a descartava antes de enviar. Clicar num nome não abria
 * nada e não havia como imprimir o holerite de uma pessoa.
 *
 * Agora: índice de documentos à esquerda, o documento inteiro já renderizado à
 * direita (zero cliques para ver um recibo), cada linha do recibo clicável até
 * a origem, e impressão individual — mais a impressão em lote da competência.
 * A tabela por lançamento continua existindo, como segunda aba: fechar o mês é
 * uma tarefa por lançamento, e nada do que a tela já fazia se perde.
 */
export default function RelatorioFolhaPagamentoView() {
  const [linhas, setLinhas] = useState<LinhaFolhaUnificada[] | null>(null);
  const [pessoas, setPessoas] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [aba, setAba] = useState<"documentos" | "lancamentos">("documentos");
  const [vencDe, setVencDe] = useState("");
  const [vencAte, setVencAte] = useState("");
  // Situação do pagamento — a categoria de filtro que o dono pediu por nome
  // (pagos · a pagar · todos). Nasce em "todos" para a tela continuar abrindo
  // com tudo à vista, como sempre abriu.
  const [situacao, setSituacao] = useState<SituacaoPagamento>("todos");
  const [pessoaId, setPessoaId] = useState("");
  const [tipo, setTipo] = useState<"" | "funcionario" | "empreita" | "contrato" | "diaria" | "ferias_decimo">("");
  const [busca, setBusca] = useState("");
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [imprimindoLote, setImprimindoLote] = useState(false);
  const [exportandoLote, setExportandoLote] = useState(false);

  useEffect(() => {
    fetchFolhaPagamentoUnificada().then(setLinhas).catch((e) => setError(e.message));
    fetchPessoas().then(setPessoas).catch(() => {});
  }, []);

  const filtradas = useMemo(() => filtrarPorSituacao((linhas || []).filter((l) =>
    (!vencDe || (l.data_vencimento || "") >= vencDe) &&
    (!vencAte || (l.data_vencimento || "") <= vencAte) &&
    (!pessoaId || String(l.pessoa_id) === pessoaId) &&
    (!tipo || l.tipo === tipo)
  ), situacao), [linhas, vencDe, vencAte, situacao, pessoaId, tipo]);

  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(filtradas);

  // Só os lançamentos que têm documento discriminado (funcionário e férias/13º).
  // Empreita, contrato e diária são pagamentos de valor único, sem composição:
  // continuam na aba por lançamento, com o recibo simples que já tinham.
  const documentos = useMemo(() => {
    const alvo = busca.trim().toLowerCase();
    return filtradas
      .map(holeriteDaLinha)
      .filter((d): d is DocHolerite => !!d)
      .filter((d) => !alvo || d.pessoaNome.toLowerCase().includes(alvo))
      .sort((a, b) => (b.competencia || "").localeCompare(a.competencia || "") || a.pessoaNome.localeCompare(b.pessoaNome));
  }, [filtradas, busca]);

  // O primeiro documento nasce selecionado: a tela nunca abre vazia. Quando o
  // filtro muda e a escolha some da lista, cai de volta no primeiro.
  const documentoAtual = useMemo(
    () => documentos.find((d) => d.chave === selecionada) || documentos[0] || null,
    [documentos, selecionada],
  );

  const somaFiltrada = filtradas.reduce((a, l) => a + l.valor, 0);
  // Líquido negativo NUNCA entra numa soma de "a vencer": uma folha estourada
  // REDUZIA o total de folha a pagar do mês — o erro se disfarçava de bom
  // número. Fica contado à parte, em valor absoluto.
  const pendentes = filtradas.filter((l) => l.status === "pendente");
  const somaPendente = pendentes.filter((l) => l.valor >= 0).reduce((a, l) => a + l.valor, 0);
  const somaPaga = filtradas.filter((l) => l.status === "pago").reduce((a, l) => a + l.valor, 0);
  const bloqueadas = filtradas.filter((l) => l.valor < 0);
  const somaBloqueada = bloqueadas.reduce((a, l) => a + Math.abs(l.valor), 0);

  const linhasExport = useMemo(() => linhasOrdenadas.map((l) => ({
    tipoLabel: LABEL_TIPO[l.tipo] || l.tipo, pessoa_nome: l.pessoa_nome, descricao: l.descricao,
    vencimentoFmt: l.data_vencimento ? formatDate(l.data_vencimento) : "—",
    valorFmt: formatBRL(l.valor),
    pagamentoFmt: l.data_pagamento ? formatDate(l.data_pagamento) : "—",
    statusLabel: l.status === "pago" ? "Pago" : (l.vencido ? "Vencido" : "A vencer"),
  })), [linhasOrdenadas]);

  // Lote: só o que pode ser emitido. Documento com desconto maior que
  // vencimento fica de fora — e o botão diz quantos ficaram.
  const emitiveis = useMemo(() => documentos.filter((d) => !d.totais.liquido_negativo), [documentos]);

  async function imprimirLote(formato: "pdf" | "excel") {
    if (!emitiveis.length) return;
    setExportandoLote(true);
    try {
      const competencias = Array.from(new Set(emitiveis.map((d) => d.competencia).filter(Boolean))).sort();
      const subtitulo = competencias.length === 1
        ? competenciaExtenso(competencias[0])
        : `${emitiveis.length} recibos — filtro atual`;
      await imprimirHolerites(emitiveis, subtitulo, `recibos_${competencias.length === 1 ? competencias[0] : "filtro"}`, formato);
    } catch {
      // erro já mostrado ao usuário dentro de lib/export.ts
    } finally {
      setExportandoLote(false);
      setImprimindoLote(false);
    }
  }

  if (error) return <div className="alert-critico mb-4"><span>Sem dados: {error}.</span></div>;
  if (!linhas) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String(filtradas.length)} l="Lançamentos" />
        <KPI v={formatBRL(somaPendente)} l="A vencer" c="var(--amber)" />
        <KPI v={formatBRL(somaPaga)} l="Pago" c="var(--green-light)" />
        {bloqueadas.length > 0 && (
          <KPI v={formatBRL(somaBloqueada)} l={`Fora da conta (${bloqueadas.length})`} c="var(--red)" />
        )}
      </div>
      {bloqueadas.length > 0 && (
        <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "-0.5rem", marginBottom: "1rem" }}>
          Não somado em “A vencer”: {bloqueadas.length === 1 ? "1 folha em que os descontos passam" : `${bloqueadas.length} folhas em que os descontos passam`} os
          vencimentos. Enquanto isso durar, o recibo não pode ser emitido.
        </p>
      )}

      {/* Categoria própria, acima das demais: é a primeira pergunta que o dono
          faz na tela ("o que já paguei / o que ainda devo"), e ela vale para
          as duas abas. Substitui o antigo select "Status", que tinha
          exatamente este predicado sob outro rótulo — dois controles com a
          mesma regra podiam se contradizer e esvaziar a tela sem explicação
          (ver `filtrarPorSituacao` em lib/holeriteRegras.ts). */}
      <div className="card mb-4">
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          <span style={{ ...labelStyle, marginRight: "0.2rem" }}>Situação do pagamento</span>
          {SITUACOES.map((s) => (
            <button
              key={s.id} type="button" className="btn-ghost"
              title={s.dica}
              onClick={() => setSituacao(s.id)}
              style={{
                fontSize: "0.76rem",
                borderColor: situacao === s.id ? "var(--dourado)" : undefined,
                color: situacao === s.id ? "var(--dourado-light)" : undefined,
                fontWeight: situacao === s.id ? 700 : undefined,
                background: situacao === s.id
                  ? "color-mix(in srgb, var(--dourado-light) 12%, transparent)" : undefined,
              }}
            >{s.label}</button>
          ))}
        </div>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <div><label style={labelStyle}>Vencimento de</label>
            <input type="date" style={selStyle} value={vencDe} onChange={(e) => setVencDe(e.target.value)} /></div>
          <div><label style={labelStyle}>Vencimento até</label>
            <input type="date" style={selStyle} value={vencAte} onChange={(e) => setVencAte(e.target.value)} /></div>
          <div><label style={labelStyle}>Pessoa</label>
            <select style={selStyle} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Todas</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
          <div><label style={labelStyle}>Tipo</label>
            <select style={selStyle} value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
              <option value="">Todos</option>
              {Object.entries(LABEL_TIPO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select></div>
        </div>
      </div>

      <TabBar
        abas={[
          { id: "documentos" as const, label: "Recibos", title: "O documento de cada pessoa, com a discriminação linha a linha" },
          { id: "lancamentos" as const, label: "Por lançamento", title: "O ledger de todos os lançamentos do período" },
        ]}
        ativa={aba}
        onChange={setAba}
      />

      {aba === "documentos" ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Índice — quem, em que mês. A escolha nunca esconde o documento. */}
          <div className="card" style={{ padding: 0, overflow: "hidden", alignSelf: "start" }}>
            <div style={{ padding: "0.75rem 0.9rem", borderBottom: "1px solid var(--border)" }}>
              <div className="flex items-center gap-2" style={{ marginBottom: "0.5rem" }}>
                <Search size={13} style={{ color: "var(--text-muted)" }} />
                <input
                  style={{ ...selStyle, padding: "0.3rem 0.5rem" }}
                  placeholder="Buscar pessoa…"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </div>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {documentos.length} {documentos.length === 1 ? "recibo" : "recibos"} — clique para abrir
              </span>
            </div>
            <div style={{ maxHeight: "32rem", overflowY: "auto" }}>
              {documentos.map((d) => {
                const ativo = documentoAtual?.chave === d.chave;
                return (
                  <div
                    key={d.chave}
                    className="row-clickable"
                    onClick={() => setSelecionada(d.chave)}
                    style={{
                      padding: "0.6rem 0.9rem", borderBottom: "1px solid var(--border)", cursor: "pointer",
                      borderLeft: `3px solid ${ativo ? "var(--dourado)" : "transparent"}`,
                      background: ativo ? "color-mix(in srgb, var(--dourado-light) 9%, transparent)" : undefined,
                    }}
                  >
                    <div className="flex items-baseline gap-2">
                      <span style={{ fontSize: "0.82rem", fontWeight: ativo ? 700 : 500 }}>{d.pessoaNome}</span>
                      <span style={{ flexGrow: 1 }} />
                      <span style={{
                        fontSize: "0.8rem", fontWeight: 600, fontVariantNumeric: "tabular-nums",
                        color: d.totais.liquido_negativo ? "var(--red)" : undefined,
                      }}>
                        {formatBRL(d.totais.liquido_negativo ? d.totais.excedente : d.totais.liquido)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2" style={{ marginTop: "0.15rem", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                        {d.especie === "holerite" ? d.competenciaLabel : d.competenciaLabel}
                        {d.status === "pago" ? ` · pago em ${formatDate(d.dataPagamento || "")}` : ""}
                      </span>
                      {d.totais.liquido_negativo && (
                        <span style={{
                          padding: "0.05rem 0.35rem", borderRadius: "var(--r-sm)", fontSize: "0.64rem", fontWeight: 700,
                          background: "color-mix(in srgb, var(--red) 12%, transparent)", color: "var(--red)",
                        }}>estourada</span>
                      )}
                    </div>
                  </div>
                );
              })}
              {!documentos.length && (
                <p style={{ padding: "0.9rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  Nenhum recibo discriminado para os filtros escolhidos. Empreita, contrato e diária são pagamentos de
                  valor único — veja em “Por lançamento”.
                </p>
              )}
            </div>
            {emitiveis.length > 0 && (
              <div style={{ padding: "0.6rem 0.9rem", borderTop: "1px solid var(--border)", background: "var(--surface-2)" }}>
                <button
                  className="btn-ghost" type="button" style={{ fontSize: "0.75rem", width: "100%", justifyContent: "center" }}
                  title="Imprimir de uma vez todos os recibos que passam pelo filtro atual"
                  onClick={() => setImprimindoLote((v) => !v)}
                >
                  <Printer size={13} /> Imprimir os {emitiveis.length} recibos
                </button>
                {imprimindoLote && (
                  <div className="flex items-center gap-1" style={{ marginTop: "0.4rem", justifyContent: "center" }}>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Formato:</span>
                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportandoLote} onClick={() => imprimirLote("pdf")}>PDF</button>
                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportandoLote} onClick={() => imprimirLote("excel")}>Excel</button>
                  </div>
                )}
                {documentos.length > emitiveis.length && (
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                    {documentos.length - emitiveis.length} fora do lote: os descontos passam os vencimentos.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* O documento — já renderizado, sem clique nenhum. */}
          <div className="md:col-span-2">
            {documentoAtual
              ? (
                <Holerite
                  documento={documentoAtual}
                  edicao
                  // O servidor remonta o documento inteiro (líquido, bases,
                  // retenções e linhas) a cada rubrica lançada: a tela relê o
                  // ledger em vez de tentar recalcular por conta — foi assim
                  // que as duas telas de folha divergiram antes.
                  onMudou={() => { fetchFolhaPagamentoUnificada().then(setLinhas).catch(() => {}); }}
                />
              )
              : (
                <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  Nenhum recibo para mostrar com os filtros atuais.
                </p>
              )}
          </div>
        </div>
      ) : (
        <>
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
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {linhasOrdenadas.map((l, i) => {
                  const doc = holeriteDaLinha(l);
                  return (
                    <tr
                      key={`${l.tipo}-${l.origem_id}-${i}`}
                      className={doc ? "row-clickable" : undefined}
                      title={doc ? `Ver o recibo de ${l.pessoa_nome}` : undefined}
                      onClick={doc ? () => { setSelecionada(doc.chave); setAba("documentos"); } : undefined}
                      style={{ background: l.vencido ? VENCIDO_BG : undefined, cursor: doc ? "pointer" : undefined }}
                    >
                      <td style={{ fontSize: "0.78rem" }}>{LABEL_TIPO[l.tipo] || l.tipo}</td>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{l.pessoa_nome}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.descricao}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.data_vencimento ? formatDate(l.data_vencimento) : "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.82rem", color: l.valor < 0 ? "var(--red)" : undefined }}>{formatBRL(l.valor)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.data_pagamento ? formatDate(l.data_pagamento) : "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>
                        {l.status === "pago" ? <span style={{ color: "var(--green-light)" }}>Pago</span>
                          : l.vencido ? <span style={{ color: "var(--red)" }}>Vencido</span>
                          : <span style={{ color: "var(--text-muted)" }}>A vencer</span>}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {doc && <Printer size={13} style={{ color: "var(--text-muted)" }} />}
                      </td>
                    </tr>
                  );
                })}
                {!linhasOrdenadas.length && (
                  <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                    {linhas.length ? "Nenhum lançamento para os filtros escolhidos." : "Nenhum lançamento de folha ainda."}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
