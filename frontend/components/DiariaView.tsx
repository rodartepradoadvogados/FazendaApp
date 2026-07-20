"use client";
import { useEffect, useState } from "react";
import { Plus, DollarSign } from "lucide-react";
import {
  fetchPessoas, fetchDiarias, criarDiaria, registrarPagamentoDiaria, formatBRL,
  fetchParametroDiariaPadrao, salvarParametroDiariaPadrao, responderAuditoriaDiaria, ParametroDiariaPadrao, ehAdmin,
} from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { Modal } from "@/components/Modal";
import ValeAvulsoSection from "@/components/ValeAvulsoSection";
import { lbl, inputSm } from "@/components/estiloCampoAvulso";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Pagamento = { id: number; data_pagamento: string; valor: number; observacao: string | null };
type ValeAvulso = { id: number; valor: number; forma_pagamento: string; data_pagamento: string; observacao: string | null };
type AuditoriaPendente = { id: number; diaria_id: number; periodo_inicio: string; periodo_fim: string };
type Diaria = {
  id: number; pessoa_id: number; pessoa_nome: string; valor_diaria: number; data_inicio: string; status: string;
  numero_diarias: number; total_ate_hoje: number; valor_pago: number; valor_vale: number; saldo_devedor: number;
  pagamentos: Pagamento[]; vales: ValeAvulso[];
  conta_dia_a_dia: boolean; auditar_periodicamente: boolean;
  frequencia_auditoria: string | null; dia_semana_auditoria: number | null; intervalo_dias_auditoria: number | null;
  auditorias_pendentes: AuditoriaPendente[];
};

const DIAS_SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];

export default function DiariaView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Diaria[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [valorDiaria, setValorDiaria] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
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

  const [diasTrabalhadosPorAuditoria, setDiasTrabalhadosPorAuditoria] = useState<Record<number, string>>({});
  const [auditoriaErro, setAuditoriaErro] = useState<string | null>(null);

  const carregar = () => fetchDiarias().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchPessoas().then(setPessoas).catch(() => {});
    fetchParametroDiariaPadrao().then(setParametroPadrao).catch(() => {});
  }, []);

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a diarista." }); return; }
    if (!valorDiaria || parseFloat(valorDiaria) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor da diária." }); return; }
    if (!dataInicio) { setMsg({ tipo: "erro", texto: "Informe a data de início." }); return; }
    setSalvando(true);
    try {
      await criarDiaria({
        pessoa_id: Number(pessoaId), valor_diaria: parseFloat(valorDiaria), data_inicio: dataInicio, observacao: observacao || undefined,
        conta_dia_a_dia: contaDiaADia,
        auditar_periodicamente: auditarPeriodicamente,
        frequencia_auditoria: frequenciaAuditoria || null,
        dia_semana_auditoria: diaSemanaAuditoria !== "" ? Number(diaSemanaAuditoria) : null,
        intervalo_dias_auditoria: intervaloDiasAuditoria !== "" ? Number(intervaloDiasAuditoria) : null,
      });
      setMsg({ tipo: "sucesso", texto: "Diarista lançada." });
      setPessoaId(""); setValorDiaria(""); setObservacao("");
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
      await registrarPagamentoDiaria(diariaId, { data_pagamento: dataPagamento, valor: parseFloat(valorPagamento) });
      setPagandoId(null); setValorPagamento("");
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao registrar pagamento");
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Nova diarista" icon={Plus} defaultAberta={false} descricao="Valor da diária e data de início da contagem">
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
            <input type="number" step="0.01" style={inputSm} value={valorDiaria} onChange={(e) => setValorDiaria(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Data de início</label>
            <input type="date" style={inputSm} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
          </div>
        </div>
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
                <tr><th>Diarista</th><th>Período</th><th>Dias trabalhados</th><th></th></tr>
              </thead>
              <tbody>
                {itens.flatMap((d) => (d.auditorias_pendentes ?? []).map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 700 }}>{d.pessoa_nome}</td>
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
                )))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card mt-4">
        <div className="card-header mb-3">Controle de diárias</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma diarista lançada ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <th>Nome</th><th>Início</th><th>Nº diárias</th><th>Valor diária</th>
                  <th>Total até hoje</th><th>Pago</th><th>Vale</th><th>Saldo devedor</th><th></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((d) => (
                  <tr key={d.id}>
                    <td style={{ fontWeight: 700 }}>{d.pessoa_nome}</td>
                    <td>{d.data_inicio}</td>
                    <td>{d.numero_diarias}</td>
                    <td>{formatBRL(d.valor_diaria)}</td>
                    <td>{formatBRL(d.total_ate_hoje)}</td>
                    <td>{formatBRL(d.valor_pago)}</td>
                    <td>{formatBRL(d.valor_vale)}</td>
                    <td style={{ fontWeight: 700, color: d.saldo_devedor > 0 ? "var(--amber)" : "var(--green-light)" }}>{formatBRL(d.saldo_devedor)}</td>
                    <td>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                        onClick={() => { setPagandoId(d.id); setValorPagamento(d.saldo_devedor > 0 ? d.saldo_devedor.toFixed(2) : ""); setPagoErro(null); }}>
                        <DollarSign size={13} /> Pagar
                      </button>
                    </td>
                  </tr>
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
            <input type="number" step="0.01" style={inputSm} value={valorPagamento} onChange={(e) => setValorPagamento(e.target.value)} />
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
