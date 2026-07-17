"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Paperclip, Check, ChevronDown, ChevronRight, RefreshCw, Filter, Pencil } from "lucide-react";
import {
  fetchPessoas, fetchFolhaPagamento, criarFolhaPagamento, atualizarFolhaPagamento,
  criarVale, ehAdmin, formatBRL,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { TabBar, SecaoRecolhivel } from "@/components/ui";
import { RESPONSAVEIS } from "@/lib/constants";
import EmpreitadaView from "@/components/EmpreitadaView";
import ContratoView from "@/components/ContratoView";
import DiariaView from "@/components/DiariaView";

// "2026-07" → "jul/2026" (rótulo legível do mês de competência)
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const mesCompLabel = (comp: string) => {
  const [a, m] = (comp || "").split("-");
  const idx = parseInt(m, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_ABREV[idx]}/${a}` : (comp || "");
};

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <div className="kpi-card"><p className="kpi-value" style={{ fontSize: "1.25rem", color: c }}>{v}</p><p className="kpi-label">{l}</p></div>;
}

const selStyleLote: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};
const labelStyleLote: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

/*
 * Folha de pagamento — lançamento e acompanhamento por pessoa/competência.
 * Pessoas (funcionário, veterinário, diarista etc.) vêm do cadastro em
 * Configurações > Cadastro > Pessoas; aqui só lançamos e damos baixa.
 */
type PessoaFolha = { id: number; nome: string; tipos: string[] };
type RegistroFolha = {
  id: number; pessoa_id: number; pessoa_nome: string; competencia: string;
  valor_bruto: number; descontos: number;
  percentual_inss: number; percentual_ir: number; valor_inss: number; valor_ir: number;
  valor_vale?: number;
  valor_liquido: number;
  data_pagamento: string | null; data_vencimento?: string | null; status: string; observacao: string | null;
  recorrente: boolean; dia_vencimento: number | null;
  origem_recorrencia_id: number | null; numero_lancamento_gerado: string | null;
  detalhe: { label: string; valor: number }[];
  usuario_nome?: string | null;
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

export default function FolhaPagamentoView() {
  const admin = ehAdmin();
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

  const [subaba, setSubaba] = useState<"funcionario" | "empreita" | "contrato" | "diarias">("funcionario");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // Expansão focada de um desconto (folha ou vale) numa linha específica.
  const [expandDesc, setExpandDesc] = useState<{ id: number; tipo: "folha" | "vale" } | null>(null);
  // Filtros da lista de folha.
  const [fStatus, setFStatus] = useState<"" | "pendente" | "pago">("");
  const [fPessoa, setFPessoa] = useState("");
  const [fTipoVinculo, setFTipoVinculo] = useState("");
  const [fCompDe, setFCompDe] = useState("");
  const [fCompAte, setFCompAte] = useState("");
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

  // Tipo(s) (vínculo) por pessoa, para o filtro de salário/diárias/prestador etc.
  const tipoPorPessoa = useMemo(() => { const m: Record<number, string[]> = {}; pessoas.forEach((p) => { m[p.id] = p.tipos; }); return m; }, [pessoas]);
  const tiposVinculo = useMemo(() => Array.from(new Set(pessoas.flatMap((p) => p.tipos).filter(Boolean))).sort(), [pessoas]);
  const regsFiltrados = useMemo(() => (regs || []).filter((r) =>
    (!fStatus || r.status === fStatus) &&
    (!fPessoa || String(r.pessoa_id) === fPessoa) &&
    (!fTipoVinculo || (tipoPorPessoa[r.pessoa_id] || []).includes(fTipoVinculo)) &&
    (!fCompDe || r.competencia >= fCompDe) &&
    (!fCompAte || r.competencia <= fCompAte)
  ), [regs, fStatus, fPessoa, fTipoVinculo, fCompDe, fCompAte, tipoPorPessoa]);

  const totalPendente = regsFiltrados.filter((r) => r.status === "pendente").reduce((a, r) => a + r.valor_liquido, 0);
  const totalPago = regsFiltrados.filter((r) => r.status === "pago").reduce((a, r) => a + r.valor_liquido, 0);

  return (
    <div>
      <TabBar
        abas={[
          { id: "funcionario" as const, label: "Funcionário" },
          { id: "empreita" as const, label: "Empreita" },
          { id: "contrato" as const, label: "Contrato" },
          { id: "diarias" as const, label: "Diárias" },
        ]}
        ativa={subaba}
        onChange={setSubaba}
      />

      {subaba === "empreita" && <EmpreitadaView />}
      {subaba === "contrato" && <ContratoView />}
      {subaba === "diarias" && <DiariaView />}

      {subaba === "funcionario" && (error ? <div className="alert-critico"><span>Sem dados: {error}.</span></div> : <>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
        <KPI v={String(regsFiltrados.length)} l="Lançamentos" />
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
              <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
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

      {/* 3) Filtros da lista de folha */}
      <div className="card mt-4 mb-3">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar a folha</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={labelStyleLote}>Competência — de</label>
            <input type="month" style={selStyleLote} value={fCompDe} onChange={(e) => setFCompDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Competência — até</label>
            <input type="month" style={selStyleLote} value={fCompAte} onChange={(e) => setFCompAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Status</label>
            <select style={selStyleLote} value={fStatus} onChange={(e) => setFStatus(e.target.value as any)}>
              <option value="">Todos</option><option value="pendente">Pendente</option><option value="pago">Pago</option>
            </select></div>
          <div><label style={labelStyleLote}>Funcionário</label>
            <select style={selStyleLote} value={fPessoa} onChange={(e) => setFPessoa(e.target.value)}>
              <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Vínculo (salário/diárias/contrato)</label>
            <select style={selStyleLote} value={fTipoVinculo} onChange={(e) => setFTipoVinculo(e.target.value)}>
              <option value="">Todos</option>{tiposVinculo.map((t) => <option key={t} value={t}>{t}</option>)}
            </select></div>
        </div>
      </div>

      {/* 4) Lançamentos de folha listados — clique na linha expande a discriminação completa (incluindo vales aplicados); editável enquanto não estiver paga. Os descontos (folha e vale) são clicáveis e abrem o detalhe abaixo. */}
      <div className="card mt-4">
        <div className="card-header mb-3">Lançamentos de folha</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th title="Mês de pagamento (quando paga) ou de vencimento (quando pendente)">Mês</th><th>Funcionário</th><th title="Mês de referência do salário">Competência</th>
              <th style={{ textAlign: "right" }}>Valor bruto</th>
              <th style={{ textAlign: "right" }}>Descontos de folha</th>
              <th style={{ textAlign: "right" }}>Descontos de vale</th>
              <th>Status</th><th style={{ textAlign: "right" }}>Valor pago</th>
              {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              <th></th>
            </tr></thead>
            <tbody>
              {regsFiltrados.map((r) => {
                const expandido = expandedId === r.id;
                const editando = editingId === r.id;
                const descFolha = arredonda2(r.descontos + r.valor_inss + r.valor_ir);
                const descVale = arredonda2(r.valor_vale || 0);
                const descAberto = expandDesc && expandDesc.id === r.id;
                const valeLinhas = r.detalhe.filter((d) => /vale/i.test(d.label));
                return (
                  <Fragment key={r.id}>
                    <tr className="row-clickable" title="Clique para ver a discriminação deste lançamento de folha" onClick={() => setExpandedId(expandido ? null : r.id)}>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem", whiteSpace: "nowrap" }}
                        title={r.data_pagamento ? "Mês em que a folha foi paga" : "Mês de vencimento (pagamento previsto)"}>
                        <span className="flex items-center gap-1">
                          {expandido ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          {(() => { const d = r.data_pagamento || r.data_vencimento; return d ? mesCompLabel(d.slice(0, 7)) : "—"; })()}
                        </span>
                      </td>
                      <td style={{ fontSize: "0.82rem" }}>
                        {r.pessoa_nome}
                        {(r.recorrente || r.origem_recorrencia_id) && (
                          <span title={r.recorrente ? "Modelo recorrente — gera Contas a Pagar todo mês" : "Gerado automaticamente pela recorrência"} style={{ marginLeft: "0.4rem", display: "inline-flex", verticalAlign: "middle", color: "var(--dourado-light)" }}>
                            <RefreshCw size={12} />
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{r.competencia}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(r.valor_bruto)}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", color: descFolha ? "var(--red)" : "var(--text-muted)", cursor: "pointer", textDecoration: descFolha ? "underline dotted" : undefined }}
                        title="Clique para ver o detalhe dos descontos de folha (INSS, IR, outros)"
                        onClick={(e) => { e.stopPropagation(); setExpandDesc(descAberto && expandDesc!.tipo === "folha" ? null : { id: r.id, tipo: "folha" }); }}>
                        {formatBRL(descFolha)}
                      </td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", color: descVale ? "var(--amber)" : "var(--text-muted)", cursor: "pointer", textDecoration: descVale ? "underline dotted" : undefined }}
                        title="Clique para ver as parcelas de vale descontadas nesta folha"
                        onClick={(e) => { e.stopPropagation(); setExpandDesc(descAberto && expandDesc!.tipo === "vale" ? null : { id: r.id, tipo: "vale" }); }}>
                        {formatBRL(descVale)}
                      </td>
                      <td><span style={{ fontSize: "0.72rem", fontWeight: 700, color: r.status === "pago" ? "var(--green-light)" : "var(--amber)" }}>{r.status === "pago" ? "Pago" : "Pendente"}</span></td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{r.status === "pago" ? formatBRL(r.valor_liquido) : "—"}</td>
                      {admin && <td>{r.usuario_nome ?? "—"}</td>}
                      <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                        {r.status === "pendente" && (
                          <button className="btn-ghost" title="Registrar o pagamento deste lançamento de folha" style={{ fontSize: "0.72rem" }} onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>Marcar como pago</button>
                        )}
                      </td>
                    </tr>
                    {descAberto && (
                      <tr><td colSpan={admin ? 10 : 9}>
                        <div style={{ padding: "0.5rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.3rem" }}>
                            {expandDesc!.tipo === "folha" ? "Descontos de folha" : "Descontos de vale"} — {r.pessoa_nome}, {mesCompLabel(r.competencia)}
                          </p>
                          <table style={{ width: "100%", maxWidth: 460, fontSize: "0.78rem" }}>
                            <tbody>
                              {expandDesc!.tipo === "folha" ? (
                                [
                                  { label: "Outros descontos", valor: r.descontos },
                                  { label: `INSS${r.percentual_inss ? ` (${r.percentual_inss}%)` : ""}`, valor: r.valor_inss },
                                  { label: `IR${r.percentual_ir ? ` (${r.percentual_ir}%)` : ""}`, valor: r.valor_ir },
                                ].filter((d) => d.valor).map((d, i) => (
                                  <tr key={i}>
                                    <td style={{ padding: "0.15rem 0.5rem 0.15rem 0" }}>{d.label}</td>
                                    <td style={{ textAlign: "right", color: "var(--red)" }}>− {formatBRL(d.valor)}</td>
                                  </tr>
                                ))
                              ) : (
                                valeLinhas.map((d, i) => (
                                  <tr key={i}>
                                    <td style={{ padding: "0.15rem 0.5rem 0.15rem 0" }}>{d.label}</td>
                                    <td style={{ textAlign: "right", color: "var(--amber)" }}>{formatBRL(d.valor)}</td>
                                  </tr>
                                ))
                              )}
                              {expandDesc!.tipo === "folha" && descFolha === 0 && <tr><td style={{ color: "var(--text-muted)" }}>Sem descontos de folha nesta competência.</td></tr>}
                              {expandDesc!.tipo === "vale" && !valeLinhas.length && <tr><td style={{ color: "var(--text-muted)" }}>Sem parcelas de vale nesta competência.</td></tr>}
                            </tbody>
                          </table>
                        </div>
                      </td></tr>
                    )}
                    {pagandoId === r.id && (
                      <tr><td colSpan={admin ? 10 : 9}>
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
                      <tr><td colSpan={admin ? 10 : 9}>
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
                      <tr><td colSpan={admin ? 10 : 9}>
                        <div style={{ padding: "0.75rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Pessoa</label>
                              <select style={selStyleLote} value={editPessoaId} onChange={(e) => setEditPessoaId(e.target.value)}>
                                {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
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
              {regs && !regsFiltrados.length && <tr><td colSpan={admin ? 10 : 9} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{regs.length ? "Nenhum lançamento de folha para os filtros escolhidos." : "Nenhum lançamento de folha ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      </>)}
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
            <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
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
