"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, DollarSign, Pencil, Check, X, Trash2, Receipt } from "lucide-react";
import {
  fetchPessoas, fetchDiarias, criarDiaria, atualizarDiaria, registrarPagamentoDiaria, formatBRL,
  fetchParametroDiariaPadrao, salvarParametroDiariaPadrao, responderAuditoriaDiaria, ParametroDiariaPadrao, ehAdmin,
  confirmarExclusao, fetchContasCorrentes, type ContaCorrenteCadastro,
} from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { Modal } from "@/components/Modal";
import ValeAvulsoSection from "@/components/ValeAvulsoSection";
import { lbl, inputSm } from "@/components/estiloCampoAvulso";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Pagamento = { id: number; data_pagamento: string; valor: number; observacao: string | null };
type ValeAvulso = { id: number; valor: number; forma_pagamento: string; data_pagamento: string; observacao: string | null };
type AuditoriaPendente = { id: number; diaria_id: number; periodo_inicio: string; periodo_fim: string };
type Diaria = {
  id: number; pessoa_id: number; pessoa_nome: string; valor_diaria: number; data_inicio: string; data_fim: string | null; status: string;
  numero_diarias: number; total_ate_hoje: number; valor_pago: number; valor_vale: number; saldo_devedor: number;
  pagamentos: Pagamento[]; vales: ValeAvulso[];
  conta_dia_a_dia: boolean; auditar_periodicamente: boolean;
  frequencia_auditoria: string | null; dia_semana_auditoria: number | null; intervalo_dias_auditoria: number | null;
  auditorias_pendentes: AuditoriaPendente[];
};

const DIAS_SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];

function fmtDataBR(iso: string | null): string {
  if (!iso) return "—";
  return iso.split("-").reverse().join("/");
}

export default function DiariaView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Diaria[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [valorDiaria, setValorDiaria] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
  const [dataFim, setDataFim] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [contaDiaADia, setContaDiaADia] = useState(true);
  const [auditarPeriodicamente, setAuditarPeriodicamente] = useState<boolean | null>(null);
  const [frequenciaAuditoria, setFrequenciaAuditoria] = useState<string>("");
  const [diaSemanaAuditoria, setDiaSemanaAuditoria] = useState<string>("");
  const [intervaloDiasAuditoria, setIntervaloDiasAuditoria] = useState<string>("");

  const [parametroPadrao, setParametroPadrao] = useState<ParametroDiariaPadrao | null>(null);
  const [salvandoParametro, setSalvandoParametro] = useState(false);
  const [msgParametro, setMsgParametro] = useState<string | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [valorPagamento, setValorPagamento] = useState("");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [pagoErro, setPagoErro] = useState<string | null>(null);
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);
  const [pagamentoContaCorrenteId, setPagamentoContaCorrenteId] = useState("");

  const [diasTrabalhadosPorAuditoria, setDiasTrabalhadosPorAuditoria] = useState<Record<number, string>>({});
  const [auditoriaErro, setAuditoriaErro] = useState<string | null>(null);

  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [editDataInicio, setEditDataInicio] = useState("");
  const [editDataFim, setEditDataFim] = useState("");
  const [editAjuste, setEditAjuste] = useState("");
  const [editSalvando, setEditSalvando] = useState(false);
  const [editErro, setEditErro] = useState<string | null>(null);

  // G3/G14 — pagamentos lançados (com botão de excluir) e exclusão da
  // diária, ambos via motor genérico de exclusões (mesmo padrão de
  // app/sanidade/page.tsx): admin exclui na hora, operador só solicita.
  const [pagamentosAbertoId, setPagamentosAbertoId] = useState<number | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);
  const [ocupadoExclusao, setOcupadoExclusao] = useState<number | null>(null);

  // Estimativa de nº de diárias/valor quando início e fim são informados no
  // lançamento — se o fim é futuro, mostra também a quantidade até hoje.
  const estimativa = useMemo(() => {
    const valor = parseFloat(valorDiaria) || 0;
    if (!dataInicio || !dataFim || !valor) return null;
    const ini = new Date(`${dataInicio}T00:00:00`);
    const fim = new Date(`${dataFim}T00:00:00`);
    if (fim < ini) return null;
    const totalDias = Math.round((fim.getTime() - ini.getTime()) / 86400000) + 1;
    const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    const futura = fim > hoje;
    const diasAteHoje = futura ? Math.max(Math.round((Math.min(hoje.getTime(), fim.getTime()) - ini.getTime()) / 86400000) + 1, 0) : totalDias;
    return { totalDias, totalValor: totalDias * valor, futura, diasAteHoje, valorAteHoje: diasAteHoje * valor };
  }, [dataInicio, dataFim, valorDiaria]);

  const carregar = () => fetchDiarias().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchPessoas().then(setPessoas).catch(() => {});
    fetchParametroDiariaPadrao().then(setParametroPadrao).catch(() => {});
    fetchContasCorrentes().then(setContasCorrentes).catch(() => {});
  }, []);

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a diarista." }); return; }
    if (!valorDiaria || parseFloat(valorDiaria) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor da diária." }); return; }
    if (!dataInicio) { setMsg({ tipo: "erro", texto: "Informe a data de início." }); return; }
    setSalvando(true);
    try {
      await criarDiaria({
        pessoa_id: Number(pessoaId), valor_diaria: parseFloat(valorDiaria), data_inicio: dataInicio, data_fim: dataFim || null, observacao: observacao || undefined,
        conta_dia_a_dia: contaDiaADia,
        auditar_periodicamente: auditarPeriodicamente,
        frequencia_auditoria: frequenciaAuditoria || null,
        dia_semana_auditoria: diaSemanaAuditoria !== "" ? Number(diaSemanaAuditoria) : null,
        intervalo_dias_auditoria: intervaloDiasAuditoria !== "" ? Number(intervaloDiasAuditoria) : null,
      });
      setMsg({ tipo: "sucesso", texto: "Diarista lançada." });
      setPessoaId(""); setValorDiaria(""); setDataFim(""); setObservacao("");
      setContaDiaADia(true); setAuditarPeriodicamente(null); setFrequenciaAuditoria(""); setDiaSemanaAuditoria(""); setIntervaloDiasAuditoria("");
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar diária" });
    } finally {
      setSalvando(false);
    }
  }

  async function salvarParametro() {
    if (!parametroPadrao) return;
    setMsgParametro(null);
    setSalvandoParametro(true);
    try {
      await salvarParametroDiariaPadrao(parametroPadrao);
      setMsgParametro("Parâmetro padrão salvo.");
    } catch (e: any) {
      setMsgParametro(e.message || "Erro ao salvar parâmetro padrão");
    } finally {
      setSalvandoParametro(false);
    }
  }

  async function responderAuditoria(auditoriaId: number) {
    setAuditoriaErro(null);
    const valor = diasTrabalhadosPorAuditoria[auditoriaId];
    if (valor === undefined || valor === "") { setAuditoriaErro("Informe a quantidade de dias trabalhados."); return; }
    try {
      await responderAuditoriaDiaria(auditoriaId, Number(valor));
      setDiasTrabalhadosPorAuditoria((prev) => { const novo = { ...prev }; delete novo[auditoriaId]; return novo; });
      carregar();
    } catch (e: any) {
      setAuditoriaErro(e.message || "Erro ao responder auditoria");
    }
  }

  async function registrarPagamento(diariaId: number) {
    setPagoErro(null);
    if (!valorPagamento || parseFloat(valorPagamento) <= 0) { setPagoErro("Informe o valor do pagamento."); return; }
    try {
      await registrarPagamentoDiaria(diariaId, {
        data_pagamento: dataPagamento, valor: parseFloat(valorPagamento),
        conta_corrente_id: pagamentoContaCorrenteId ? Number(pagamentoContaCorrenteId) : undefined,
      });
      setPagandoId(null); setValorPagamento(""); setPagamentoContaCorrenteId("");
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao registrar pagamento");
    }
  }

  function abrirEdicao(d: Diaria) {
    setEditandoId(d.id);
    setEditDataInicio(d.data_inicio);
    setEditDataFim(d.data_fim || "");
    setEditAjuste("");
    setEditErro(null);
  }

  async function salvarEdicao(diariaId: number) {
    setEditErro(null);
    if (!editDataInicio) { setEditErro("Informe a data de início."); return; }
    setEditSalvando(true);
    try {
      await atualizarDiaria(diariaId, {
        data_inicio: editDataInicio,
        data_fim: editDataFim || null,
        ajuste_numero_diarias: editAjuste !== "" ? Number(editAjuste) : null,
      });
      setEditandoId(null);
      carregar();
    } catch (e: any) {
      setEditErro(e.message || "Erro ao editar diária");
    } finally {
      setEditSalvando(false);
    }
  }

  // G3 — exclui um pagamento já lançado (o saldo devedor sobe de volta
  // sozinho, sem nada a reverter manualmente: ver rules/exclusao_tipos/
  // pessoal.py::_alvos_diaria_pagamento).
  async function excluirPagamento(pagamentoId: number, pessoaNome: string, valor: number) {
    const admin = ehAdmin();
    const msg = admin
      ? `Excluir o pagamento de ${formatBRL(valor)} de ${pessoaNome}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão do pagamento de ${formatBRL(valor)} de ${pessoaNome}? Um administrador precisa aprovar antes de ser excluído de fato.`;
    if (!window.confirm(msg)) return;
    setErroExclusao(null);
    setOcupadoExclusao(pagamentoId);
    try {
      const r = await confirmarExclusao("diaria_pagamento", String(pagamentoId));
      if (r.status !== "excluido") {
        setErroExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir pagamento");
    } finally {
      setOcupadoExclusao(null);
    }
  }

  // G14 — exclui a diária inteira (o backend bloqueia com 400 se houver
  // pagamento registrado ou vale avulso com saída de caixa — a mensagem de
  // erro já aponta para os botões acima/de vale).
  async function excluirDiaria(d: Diaria) {
    const admin = ehAdmin();
    const msg = admin
      ? `Excluir a diária de ${d.pessoa_nome}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da diária de ${d.pessoa_nome}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setErroExclusao(null);
    setOcupadoExclusao(d.id);
    try {
      const r = await confirmarExclusao("diaria", String(d.id));
      if (r.status !== "excluido") {
        setErroExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir diária");
    } finally {
      setOcupadoExclusao(null);
    }
  }

  const auditoriasPendentes = useMemo(
    () => (itens ?? []).flatMap((d) => (d.auditorias_pendentes ?? []).map((a) => ({ ...a, pessoa_nome: d.pessoa_nome }))),
    [itens],
  );
  const ordAuditorias = useOrdenacao(auditoriasPendentes);
  const ordDiarias = useOrdenacao(itens ?? []);

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Novo diarista" icon={Plus} defaultAberta={false} descricao="Valor da diária e data de início da contagem">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Diarista</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Valor da diária (R$)</label>
            <CampoMoeda style={inputSm} value={Number(valorDiaria) || 0} onChange={(v) => setValorDiaria(v ? String(v) : "")} />
          </div>
          <div>
            <label style={lbl}>Data de início</label>
            <input type="date" style={inputSm} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Data de fim (opcional)</label>
            <input type="date" style={inputSm} value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
          </div>
        </div>
        {estimativa && (
          <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", marginBottom: "0.75rem" }}>
            {estimativa.futura ? (
              <>Estimativa: <strong>{estimativa.totalDias}</strong> diária(s) no período (<strong>{formatBRL(estimativa.totalValor)}</strong>) — até hoje, <strong>{estimativa.diasAteHoje}</strong> diária(s) (<strong>{formatBRL(estimativa.valorAteHoje)}</strong>).</>
            ) : (
              <>Estimativa: <strong>{estimativa.totalDias}</strong> diária(s) no período, totalizando <strong>{formatBRL(estimativa.totalValor)}</strong>.</>
            )}
          </div>
        )}
        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        <div className="mt-3" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.6rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: "pointer" }}>
            <input type="checkbox" checked={contaDiaADia} onChange={(e) => setContaDiaADia(e.target.checked)} />
            Calcular as diárias dia a dia (comportamento padrão)
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: "pointer", marginTop: "0.4rem" }}>
            <input type="checkbox" checked={auditarPeriodicamente ?? parametroPadrao?.auditar_periodicamente ?? false}
              onChange={(e) => setAuditarPeriodicamente(e.target.checked)} />
            Auditar periodicamente a quantidade de diárias realizadas
            {parametroPadrao && auditarPeriodicamente === null && <span style={{ color: "var(--text-muted)" }}> (padrão da fazenda)</span>}
          </label>
          {(auditarPeriodicamente ?? parametroPadrao?.auditar_periodicamente ?? false) && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2">
              <div>
                <label style={lbl}>Frequência da auditoria</label>
                <select style={inputSm} value={frequenciaAuditoria || parametroPadrao?.frequencia_auditoria || "semanal"} onChange={(e) => setFrequenciaAuditoria(e.target.value)}>
                  <option value="semanal">Semanal</option>
                  <option value="intervalo_dias">A cada X dias</option>
                  <option value="mensal">Mensal</option>
                </select>
              </div>
              {(frequenciaAuditoria || parametroPadrao?.frequencia_auditoria) === "semanal" && (
                <div>
                  <label style={lbl}>Dia da semana</label>
                  <select style={inputSm} value={diaSemanaAuditoria || String(parametroPadrao?.dia_semana_auditoria ?? 1)} onChange={(e) => setDiaSemanaAuditoria(e.target.value)}>
                    {DIAS_SEMANA.map((d, i) => <option key={i} value={i}>{d}</option>)}
                  </select>
                </div>
              )}
              {(frequenciaAuditoria || parametroPadrao?.frequencia_auditoria) === "intervalo_dias" && (
                <div>
                  <label style={lbl}>Intervalo (dias)</label>
                  <input type="number" min={1} style={inputSm} value={intervaloDiasAuditoria || String(parametroPadrao?.intervalo_dias_auditoria ?? 7)} onChange={(e) => setIntervaloDiasAuditoria(e.target.value)} />
                </div>
              )}
            </div>
          )}
        </div>

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar diarista"}
        </button>
      </SecaoRecolhivel>

      {ehAdmin() && (
      <SecaoRecolhivel titulo="Parâmetro padrão de auditoria de diárias" icon={Plus} defaultAberta={false} descricao="Configura o padrão usado quando uma nova diarista não define auditoria própria — respondido semanalmente/mensalmente na Agenda">
        {!parametroPadrao && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>}
        {parametroPadrao && (
          <div>
            <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: "pointer" }}>
              <input type="checkbox" checked={parametroPadrao.auditar_periodicamente}
                onChange={(e) => setParametroPadrao({ ...parametroPadrao, auditar_periodicamente: e.target.checked })} />
              Perguntar, por padrão, a quantidade de diárias realizadas no período
            </label>
            {parametroPadrao.auditar_periodicamente && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2">
                <div>
                  <label style={lbl}>Frequência</label>
                  <select style={inputSm} value={parametroPadrao.frequencia_auditoria} onChange={(e) => setParametroPadrao({ ...parametroPadrao, frequencia_auditoria: e.target.value })}>
                    <option value="semanal">Semanal</option>
                    <option value="intervalo_dias">A cada X dias</option>
                    <option value="mensal">Mensal</option>
                  </select>
                </div>
                {parametroPadrao.frequencia_auditoria === "semanal" && (
                  <div>
                    <label style={lbl}>Dia da semana</label>
                    <select style={inputSm} value={parametroPadrao.dia_semana_auditoria} onChange={(e) => setParametroPadrao({ ...parametroPadrao, dia_semana_auditoria: Number(e.target.value) })}>
                      {DIAS_SEMANA.map((d, i) => <option key={i} value={i}>{d}</option>)}
                    </select>
                  </div>
                )}
                {parametroPadrao.frequencia_auditoria === "intervalo_dias" && (
                  <div>
                    <label style={lbl}>Intervalo (dias)</label>
                    <input type="number" min={1} style={inputSm} value={parametroPadrao.intervalo_dias_auditoria} onChange={(e) => setParametroPadrao({ ...parametroPadrao, intervalo_dias_auditoria: Number(e.target.value) })} />
                  </div>
                )}
              </div>
            )}
            {msgParametro && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msgParametro}</p>}
            <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvarParametro} disabled={salvandoParametro}>
              {salvandoParametro ? "Salvando…" : "Salvar parâmetro padrão"}
            </button>
          </div>
        )}
      </SecaoRecolhivel>
      )}

      <SecaoRecolhivel titulo="Vale de diária" icon={Plus} defaultAberta={false} descricao="Adiantamento abatido do saldo devedor acumulado">
        <ValeAvulsoSection
          origemTipo="diaria"
          origens={(itens ?? []).filter((d) => d.status !== "encerrado").map((d) => ({ id: d.id, label: d.pessoa_nome }))}
          onLancado={carregar}
        />
      </SecaoRecolhivel>

      {itens && itens.some((d) => d.auditorias_pendentes?.length) && (
        <div className="card mt-4" style={{ borderLeft: "3px solid var(--amber)" }}>
          <div className="card-header mb-3">Auditorias de diária pendentes</div>
          {auditoriaErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{auditoriaErro}</p>}
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Diarista" campo="pessoa_nome" coluna={ordAuditorias.coluna} dir={ordAuditorias.dir} ordenar={ordAuditorias.ordenar} />
                  <ThOrdenavel label="Período" campo="periodo_inicio" coluna={ordAuditorias.coluna} dir={ordAuditorias.dir} ordenar={ordAuditorias.ordenar} />
                  <th>Dias trabalhados</th><th></th>
                </tr>
              </thead>
              <tbody>
                {ordAuditorias.linhasOrdenadas.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 700 }}>{a.pessoa_nome}</td>
                    <td>{a.periodo_inicio} a {a.periodo_fim}</td>
                    <td>
                      <input type="number" min={0} style={{ ...inputSm, width: "5rem" }}
                        value={diasTrabalhadosPorAuditoria[a.id] ?? ""}
                        onChange={(e) => setDiasTrabalhadosPorAuditoria((prev) => ({ ...prev, [a.id]: e.target.value }))} />
                    </td>
                    <td>
                      <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={() => responderAuditoria(a.id)}>
                        Confirmar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card mt-4">
        <div className="card-header mb-3">Controle de diárias</div>
        {erroExclusao && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erroExclusao}</p>}
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma diarista lançada ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Nome" campo="pessoa_nome" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Início" campo="data_inicio" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Fim" campo="data_fim" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Nº diárias" campo="numero_diarias" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Valor diária" campo="valor_diaria" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Total até hoje" campo="total_ate_hoje" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Pago" campo="valor_pago" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Vale" campo="valor_vale" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <ThOrdenavel label="Saldo devedor" campo="saldo_devedor" coluna={ordDiarias.coluna} dir={ordDiarias.dir} ordenar={ordDiarias.ordenar} />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ordDiarias.linhasOrdenadas.map((d) => (
                  <Fragment key={d.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{d.pessoa_nome}</td>
                    <td>{fmtDataBR(d.data_inicio)}</td>
                    <td>{fmtDataBR(d.data_fim)}</td>
                    <td>{d.numero_diarias}</td>
                    <td>{formatBRL(d.valor_diaria)}</td>
                    <td>{formatBRL(d.total_ate_hoje)}</td>
                    <td>{formatBRL(d.valor_pago)}</td>
                    <td>{formatBRL(d.valor_vale)}</td>
                    <td style={{ fontWeight: 700, color: d.saldo_devedor > 0 ? "var(--amber)" : "var(--green-light)" }}>{formatBRL(d.saldo_devedor)}</td>
                    <td>
                      <span className="flex items-center gap-2">
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} title="Editar data de início, data de fim ou corrigir o número de diárias"
                          onClick={() => (editandoId === d.id ? setEditandoId(null) : abrirEdicao(d))}>
                          <Pencil size={13} />
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                          onClick={() => { setPagandoId(d.id); setValorPagamento(d.saldo_devedor > 0 ? d.saldo_devedor.toFixed(2) : ""); setPagamentoContaCorrenteId(""); setPagoErro(null); }}>
                          <DollarSign size={13} /> Pagar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} title="Ver pagamentos lançados"
                          onClick={() => setPagamentosAbertoId(pagamentosAbertoId === d.id ? null : d.id)}>
                          <Receipt size={13} /> {d.pagamentos?.length ?? 0}
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} title="Excluir diária"
                          disabled={ocupadoExclusao === d.id} onClick={() => excluirDiaria(d)}>
                          <Trash2 size={13} />
                        </button>
                      </span>
                    </td>
                  </tr>
                  {pagamentosAbertoId === d.id && (
                    <tr>
                      <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                        <div style={{ fontSize: "0.75rem", fontWeight: 700, marginBottom: "0.4rem" }}>Pagamentos lançados</div>
                        {!d.pagamentos?.length && <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Nenhum pagamento lançado ainda.</p>}
                        {d.pagamentos?.length > 0 && (
                          <table className="fazenda-table" style={{ fontSize: "0.78rem" }}>
                            <thead>
                              <tr><th>Data</th><th>Valor</th><th>Observação</th><th></th></tr>
                            </thead>
                            <tbody>
                              {d.pagamentos.map((p) => (
                                <tr key={p.id}>
                                  <td>{fmtDataBR(p.data_pagamento)}</td>
                                  <td>{formatBRL(p.valor)}</td>
                                  <td>{p.observacao || "—"}</td>
                                  <td>
                                    <button className="btn-ghost" style={{ fontSize: "0.7rem", color: "var(--red)" }} title="Excluir pagamento"
                                      disabled={ocupadoExclusao === p.id}
                                      onClick={() => excluirPagamento(p.id, d.pessoa_nome, p.valor)}>
                                      <Trash2 size={12} />
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                  {editandoId === d.id && (
                    <tr>
                      <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
                          <div><label style={lbl}>Data de início</label>
                            <input type="date" style={inputSm} value={editDataInicio} onChange={(e) => setEditDataInicio(e.target.value)} /></div>
                          <div><label style={lbl}>Data de fim (opcional)</label>
                            <input type="date" style={inputSm} value={editDataFim} onChange={(e) => setEditDataFim(e.target.value)} /></div>
                          <div><label style={lbl}>Corrigir nº de diárias (opcional)</label>
                            <input type="number" min={0} style={inputSm} placeholder={String(d.numero_diarias)} value={editAjuste} onChange={(e) => setEditAjuste(e.target.value)} /></div>
                        </div>
                        {editErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{editErro}</p>}
                        <div className="flex items-center gap-2">
                          <button className="btn-primary" style={{ fontSize: "0.78rem" }} disabled={editSalvando} onClick={() => salvarEdicao(d.id)}>
                            <Check size={13} /> {editSalvando ? "Salvando…" : "Salvar"}
                          </button>
                          <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setEditandoId(null)}>
                            <X size={13} /> Cancelar
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {pagandoId !== null && (
        <Modal title="Registrar pagamento de diária" onClose={() => setPagandoId(null)} width="380px">
          <div>
            <label style={lbl}>Data do pagamento</label>
            <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
          </div>
          <div style={{ marginTop: "0.6rem" }}>
            <label style={lbl}>Valor (R$)</label>
            <CampoMoeda style={inputSm} value={Number(valorPagamento) || 0} onChange={(v) => setValorPagamento(v ? String(v) : "")} />
          </div>
          <div style={{ marginTop: "0.6rem" }}>
            <label style={lbl}>Conta bancária (opcional)</label>
            <select style={inputSm} value={pagamentoContaCorrenteId} onChange={(e) => setPagamentoContaCorrenteId(e.target.value)}>
              <option value="">Não informar</option>
              {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
            </select>
          </div>
          {pagoErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{pagoErro}</p>}
          <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "1rem" }} onClick={() => registrarPagamento(pagandoId)}>
            Confirmar pagamento
          </button>
        </Modal>
      )}
    </div>
  );
}
