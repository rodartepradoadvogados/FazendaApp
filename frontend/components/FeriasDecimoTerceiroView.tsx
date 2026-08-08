"use client";
import { useEffect, useMemo, useState } from "react";
import { Plus, Check } from "lucide-react";
import {
  fetchPessoas, fetchFerias, criarFerias, atualizarFerias,
  fetchDecimoTerceiro, criarDecimoTerceiro, atualizarDecimoTerceiro,
  simularRescisao, criarRescisao, fetchRescisoes,
  formatBRL, type RegistroFerias, type RegistroDecimoTerceiro,
  type TipoRescisao, type CalculoRescisao, type RegistroRescisao,
} from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

/*
 * Férias e 13º salário — controle DENTRO do app (cálculo, lançamento e
 * acompanhamento). Sem envio ao eSocial (fora de escopo — inviável sem
 * certificado digital/infraestrutura própria); aqui só organiza o que a
 * fazenda já paga hoje.
 */
type Pessoa = { id: number; nome: string; tipos: string[]; salario_base?: number | null; data_admissao?: string | null };

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
};
const hoje = () => new Date().toISOString().slice(0, 10);

function StatusBadge({ status }: { status: string }) {
  return (
    <span style={{ fontSize: "0.72rem", fontWeight: 700, color: status === "pago" ? "var(--green-light)" : "var(--amber)" }}>
      {status === "pago" ? "Pago" : "Pendente"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Sub-seção: Férias
// ---------------------------------------------------------------------------
function FeriasSection({ pessoas }: { pessoas: Pessoa[] }) {
  const [itens, setItens] = useState<RegistroFerias[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [periodoInicio, setPeriodoInicio] = useState("");
  const [periodoFim, setPeriodoFim] = useState("");
  const [diasDireito, setDiasDireito] = useState("30");
  const [diasGozados, setDiasGozados] = useState("30");
  const [dataInicioGozo, setDataInicioGozo] = useState("");
  const [dataFimGozo, setDataFimGozo] = useState("");
  const [abonoDias, setAbonoDias] = useState("0");
  const [observacao, setObservacao] = useState("");

  const [calculo, setCalculo] = useState<{ valor_ferias: number; valor_terco_constitucional: number; valor_abono: number; valor_total: number } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [dataPagamento, setDataPagamento] = useState(hoje());
  const [pagoErro, setPagoErro] = useState<string | null>(null);

  const ordFerias = useOrdenacao(itens ?? []);

  const carregar = () => fetchFerias().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => String(p.id) === pessoaId), [pessoas, pessoaId]);

  function calcular() {
    setMsg(null);
    if (!pessoaSelecionada || !pessoaSelecionada.salario_base) {
      setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." });
      return;
    }
    const salario = pessoaSelecionada.salario_base;
    const dg = parseInt(diasGozados, 10) || 0;
    const ab = parseInt(abonoDias, 10) || 0;
    const valorDia = salario / 30;
    const valorFerias = Math.round(valorDia * dg * 100) / 100;
    const valorTerco = Math.round(valorFerias * (1 / 3) * 100) / 100;
    const valorAbono = ab > 0 ? Math.round(valorDia * ab * (1 + 1 / 3) * 100) / 100 : 0;
    setCalculo({
      valor_ferias: valorFerias, valor_terco_constitucional: valorTerco,
      valor_abono: valorAbono, valor_total: Math.round((valorFerias + valorTerco + valorAbono) * 100) / 100,
    });
  }

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o funcionário." }); return; }
    if (!periodoInicio || !periodoFim) { setMsg({ tipo: "erro", texto: "Informe o período aquisitivo." }); return; }
    if (!dataInicioGozo || !dataFimGozo) { setMsg({ tipo: "erro", texto: "Informe o período de gozo." }); return; }
    setSalvando(true);
    try {
      await criarFerias({
        pessoa_id: Number(pessoaId), periodo_aquisitivo_inicio: periodoInicio, periodo_aquisitivo_fim: periodoFim,
        dias_direito: parseInt(diasDireito, 10) || 30, dias_gozados: parseInt(diasGozados, 10) || 0,
        data_inicio_gozo: dataInicioGozo, data_fim_gozo: dataFimGozo,
        abono_pecuniario_dias: parseInt(abonoDias, 10) || 0, observacao: observacao || undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Férias lançadas." });
      setPessoaId(""); setPeriodoInicio(""); setPeriodoFim(""); setDataInicioGozo(""); setDataFimGozo("");
      setDiasGozados("30"); setAbonoDias("0"); setObservacao(""); setCalculo(null);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar férias" });
    } finally {
      setSalvando(false);
    }
  }

  async function marcarPago(r: RegistroFerias) {
    setPagoErro(null);
    try {
      await atualizarFerias(r.id, {
        pessoa_id: r.pessoa_id, periodo_aquisitivo_inicio: r.periodo_aquisitivo_inicio, periodo_aquisitivo_fim: r.periodo_aquisitivo_fim,
        dias_direito: r.dias_direito, dias_gozados: r.dias_gozados,
        data_inicio_gozo: r.data_inicio_gozo, data_fim_gozo: r.data_fim_gozo,
        abono_pecuniario_dias: r.abono_pecuniario_dias, observacao: r.observacao || undefined,
        status: "pago", data_pagamento: dataPagamento, centro_custo: r.centro_custo,
      });
      setPagandoId(null);
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao marcar como pago");
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Nova férias" icon={Plus} defaultAberta={false} descricao="Período aquisitivo, dias a gozar e abono pecuniário opcional">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Funcionário</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => { setPessoaId(e.target.value); setCalculo(null); }}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Período aquisitivo — início</label>
            <input type="date" style={inputSm} value={periodoInicio} onChange={(e) => setPeriodoInicio(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Período aquisitivo — fim</label>
            <input type="date" style={inputSm} value={periodoFim} onChange={(e) => setPeriodoFim(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Dias de direito</label>
            <input type="number" style={inputSm} value={diasDireito} onChange={(e) => { setDiasDireito(e.target.value); setCalculo(null); }} />
          </div>
          <div>
            <label style={lbl}>Dias a gozar</label>
            <input type="number" style={inputSm} value={diasGozados} onChange={(e) => { setDiasGozados(e.target.value); setCalculo(null); }} />
          </div>
          <div>
            <label style={lbl}>Abono pecuniário (dias vendidos)</label>
            <input type="number" style={inputSm} value={abonoDias} onChange={(e) => { setAbonoDias(e.target.value); setCalculo(null); }} />
          </div>
          <div>
            <label style={lbl}>Início do gozo</label>
            <input type="date" style={inputSm} value={dataInicioGozo} onChange={(e) => setDataInicioGozo(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Fim do gozo</label>
            <input type="date" style={inputSm} value={dataFimGozo} onChange={(e) => setDataFimGozo(e.target.value)} />
          </div>
        </div>
        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        <div className="flex items-center gap-2" style={{ marginTop: "0.6rem" }}>
          <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={calcular}>Calcular valor sugerido</button>
        </div>
        {calculo && (
          <div className="card mt-2" style={{ padding: "0.6rem 0.8rem", fontSize: "0.8rem" }}>
            <div>Férias: <strong>{formatBRL(calculo.valor_ferias)}</strong></div>
            <div>1/3 constitucional: <strong>{formatBRL(calculo.valor_terco_constitucional)}</strong></div>
            {calculo.valor_abono > 0 && <div>Abono pecuniário: <strong>{formatBRL(calculo.valor_abono)}</strong></div>}
            <div style={{ marginTop: "0.3rem" }}>Total: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(calculo.valor_total)}</strong></div>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.2rem" }}>
              Valor sugerido só para conferência — o valor final é recalculado pelo servidor ao lançar.
            </div>
          </div>
        )}

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar férias"}
        </button>
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">Férias lançadas</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma férias lançada ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Funcionário" campo="pessoa_nome" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} />
                  <ThOrdenavel label="Gozo" campo="data_inicio_gozo" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} />
                  <ThOrdenavel label="Dias" campo="dias_gozados" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} />
                  <ThOrdenavel label="Abono" campo="abono_pecuniario_dias" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} />
                  <ThOrdenavel label="Valor total" campo="valor_total" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} alinhar="right" />
                  <ThOrdenavel label="Status" campo="status" coluna={ordFerias.coluna} dir={ordFerias.dir} ordenar={ordFerias.ordenar} />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ordFerias.linhasOrdenadas.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.pessoa_nome}</td>
                    <td>{r.data_inicio_gozo} a {r.data_fim_gozo}</td>
                    <td>{r.dias_gozados}</td>
                    <td>{r.abono_pecuniario_dias || 0}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{formatBRL(r.valor_total)}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>
                      {r.status !== "pago" && (
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                          onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>
                          Marcar como pago
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {pagandoId !== null && (
        <Modal title="Registrar pagamento de férias" onClose={() => setPagandoId(null)} width="380px">
          <div>
            <label style={lbl}>Data do pagamento</label>
            <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
          </div>
          {pagoErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{pagoErro}</p>}
          <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "1rem" }}
            onClick={() => { const r = (itens || []).find((x) => x.id === pagandoId); if (r) marcarPago(r); }}>
            <Check size={13} /> Confirmar pagamento
          </button>
        </Modal>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-seção: 13º salário
// ---------------------------------------------------------------------------
function DecimoTerceiroSection({ pessoas }: { pessoas: Pessoa[] }) {
  const [itens, setItens] = useState<RegistroDecimoTerceiro[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [parcela, setParcela] = useState("unica");
  const [mesesTrabalhados, setMesesTrabalhados] = useState("12");
  const [observacao, setObservacao] = useState("");

  const [valorCalculado, setValorCalculado] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [dataPagamento, setDataPagamento] = useState(hoje());
  const [pagoErro, setPagoErro] = useState<string | null>(null);

  const ordDecimo = useOrdenacao(itens ?? []);

  const carregar = () => fetchDecimoTerceiro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => String(p.id) === pessoaId), [pessoas, pessoaId]);

  // Sugere meses trabalhados a partir da data de admissão (só quando o ano
  // lançado é o ano de admissão) — mesmo espírito de `_proporcional_admissao`
  // da Folha, mas sempre editável.
  useEffect(() => {
    if (!pessoaSelecionada?.data_admissao) return;
    const admissao = new Date(pessoaSelecionada.data_admissao);
    if (admissao.getFullYear() === Number(ano)) {
      setMesesTrabalhados(String(12 - admissao.getMonth()));
    } else {
      setMesesTrabalhados("12");
    }
    setValorCalculado(null);
  }, [pessoaSelecionada, ano]);

  function calcular() {
    setMsg(null);
    if (!pessoaSelecionada || !pessoaSelecionada.salario_base) {
      setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." });
      return;
    }
    const meses = parseInt(mesesTrabalhados, 10) || 0;
    setValorCalculado(Math.round((pessoaSelecionada.salario_base / 12) * meses * 100) / 100);
  }

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o funcionário." }); return; }
    const meses = parseInt(mesesTrabalhados, 10) || 0;
    if (meses < 1 || meses > 12) { setMsg({ tipo: "erro", texto: "Meses trabalhados deve estar entre 1 e 12." }); return; }
    setSalvando(true);
    try {
      await criarDecimoTerceiro({
        pessoa_id: Number(pessoaId), ano: parseInt(ano, 10), parcela, meses_trabalhados: meses,
        observacao: observacao || undefined,
      });
      setMsg({ tipo: "sucesso", texto: "13º salário lançado." });
      setPessoaId(""); setObservacao(""); setValorCalculado(null);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar 13º salário" });
    } finally {
      setSalvando(false);
    }
  }

  async function marcarPago(r: RegistroDecimoTerceiro) {
    setPagoErro(null);
    try {
      await atualizarDecimoTerceiro(r.id, {
        pessoa_id: r.pessoa_id, ano: r.ano, parcela: r.parcela, meses_trabalhados: r.meses_trabalhados,
        valor_inss: r.valor_inss, valor_ir: r.valor_ir, observacao: r.observacao || undefined,
        status: "pago", data_pagamento: dataPagamento, centro_custo: r.centro_custo,
      });
      setPagandoId(null);
      carregar();
    } catch (e: any) {
      setPagoErro(e.message || "Erro ao marcar como pago");
    }
  }

  const LABEL_PARCELA: Record<string, string> = { unica: "Única", primeira: "1ª parcela", segunda: "2ª parcela" };

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Novo 13º salário" icon={Plus} defaultAberta={false} descricao="Proporcional aos meses trabalhados no ano">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Funcionário</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => { setPessoaId(e.target.value); setValorCalculado(null); }}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Ano</label>
            <input type="number" style={inputSm} value={ano} onChange={(e) => setAno(e.target.value)} />
          </div>
          <div>
            <label style={lbl}>Parcela</label>
            <select style={inputSm} value={parcela} onChange={(e) => setParcela(e.target.value)}>
              <option value="unica">Única</option>
              <option value="primeira">1ª parcela</option>
              <option value="segunda">2ª parcela</option>
            </select>
          </div>
          <div>
            <label style={lbl}>Meses trabalhados</label>
            <input type="number" min={1} max={12} style={inputSm} value={mesesTrabalhados}
              onChange={(e) => { setMesesTrabalhados(e.target.value); setValorCalculado(null); }} />
          </div>
        </div>
        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        <div className="flex items-center gap-2" style={{ marginTop: "0.6rem" }}>
          <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={calcular}>Calcular valor sugerido</button>
        </div>
        {valorCalculado !== null && (
          <div className="card mt-2" style={{ padding: "0.6rem 0.8rem", fontSize: "0.8rem" }}>
            Valor bruto sugerido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorCalculado)}</strong>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.2rem" }}>
              INSS/IR (se houver) são informados na edição — o servidor recalcula o bruto ao lançar.
            </div>
          </div>
        )}

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar 13º salário"}
        </button>
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">13º salário lançado</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum 13º salário lançado ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Funcionário" campo="pessoa_nome" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} />
                  <ThOrdenavel label="Ano" campo="ano" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} />
                  <ThOrdenavel label="Parcela" campo="parcela" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} />
                  <ThOrdenavel label="Meses" campo="meses_trabalhados" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} />
                  <ThOrdenavel label="Valor líquido" campo="valor_liquido" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} alinhar="right" />
                  <ThOrdenavel label="Status" campo="status" coluna={ordDecimo.coluna} dir={ordDecimo.dir} ordenar={ordDecimo.ordenar} />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {ordDecimo.linhasOrdenadas.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.pessoa_nome}</td>
                    <td>{r.ano}</td>
                    <td>{LABEL_PARCELA[r.parcela || "unica"] || r.parcela}</td>
                    <td>{r.meses_trabalhados}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{formatBRL(r.valor_liquido)}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>
                      {r.status !== "pago" && (
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                          onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>
                          Marcar como pago
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {pagandoId !== null && (
        <Modal title="Registrar pagamento de 13º salário" onClose={() => setPagandoId(null)} width="380px">
          <div>
            <label style={lbl}>Data do pagamento</label>
            <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
          </div>
          {pagoErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{pagoErro}</p>}
          <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "1rem" }}
            onClick={() => { const r = (itens || []).find((x) => x.id === pagandoId); if (r) marcarPago(r); }}>
            <Check size={13} /> Confirmar pagamento
          </button>
        </Modal>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-seção: Rescisão contratual (CLT) — saldo de salário, aviso prévio,
// férias vencidas/proporcionais, 13º proporcional e multa de FGTS (ESTIMADA
// — o sistema não guarda o extrato real de depósitos de FGTS). Diferente de
// férias/13º, não há tabela de acompanhamento dedicada: o cálculo só vira
// lançamento em Contas a Pagar (dar baixa depois na aba Contas a pagar).
// ---------------------------------------------------------------------------
const LABEL_TIPO_RESCISAO: Record<TipoRescisao, string> = {
  sem_justa_causa: "Dispensa sem justa causa",
  pedido_demissao: "Pedido de demissão",
  justa_causa: "Dispensa por justa causa",
  acordo_mutuo: "Acordo mútuo (distrato)",
};

function RescisaoSection({ pessoas }: { pessoas: Pessoa[] }) {
  const [itens, setItens] = useState<RegistroRescisao[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [tipoRescisao, setTipoRescisao] = useState<TipoRescisao>("sem_justa_causa");
  const [dataDesligamento, setDataDesligamento] = useState(hoje());
  const [diasFeriasVencidas, setDiasFeriasVencidas] = useState("0");
  const [avisoPrevioTrabalhado, setAvisoPrevioTrabalhado] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [statusLancamento, setStatusLancamento] = useState("pendente");
  const [dataPagamento, setDataPagamento] = useState(hoje());

  const [calculo, setCalculo] = useState<CalculoRescisao | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const carregar = () => fetchRescisoes().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => String(p.id) === pessoaId), [pessoas, pessoaId]);

  function montarDados() {
    return {
      pessoa_id: Number(pessoaId), tipo_rescisao: tipoRescisao, data_desligamento: dataDesligamento,
      dias_ferias_vencidas: parseInt(diasFeriasVencidas, 10) || 0, aviso_previo_trabalhado: avisoPrevioTrabalhado,
      observacao: observacao || undefined,
    };
  }

  async function calcular() {
    setMsg(null); setCalculo(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o funcionário." }); return; }
    if (!pessoaSelecionada?.salario_base) { setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." }); return; }
    if (!pessoaSelecionada?.data_admissao) { setMsg({ tipo: "erro", texto: "Funcionário sem data de admissão cadastrada." }); return; }
    setCalculando(true);
    try {
      const resultado = await simularRescisao(montarDados());
      setCalculo(resultado);
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao calcular rescisão" });
    } finally {
      setCalculando(false);
    }
  }

  async function salvar() {
    setMsg(null);
    if (!calculo) { setMsg({ tipo: "erro", texto: "Calcule antes de lançar." }); return; }
    setSalvando(true);
    try {
      await criarRescisao({
        ...montarDados(), status: statusLancamento,
        data_pagamento: statusLancamento === "pago" ? dataPagamento : undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Rescisão lançada em Contas a Pagar." });
      setPessoaId(""); setDiasFeriasVencidas("0"); setAvisoPrevioTrabalhado(false);
      setObservacao(""); setCalculo(null); setStatusLancamento("pendente");
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar rescisão" });
    } finally {
      setSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      <SecaoRecolhivel titulo="Calcular rescisão" icon={Plus} defaultAberta={false}
        descricao="Saldo de salário, aviso prévio, férias vencidas/proporcionais, 13º proporcional e multa de FGTS (estimada)">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label style={lbl}>Funcionário</label>
            <select style={inputSm} value={pessoaId} onChange={(e) => { setPessoaId(e.target.value); setCalculo(null); }}>
              <option value="">Selecione…</option>
              {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Modalidade</label>
            <select style={inputSm} value={tipoRescisao}
              onChange={(e) => { setTipoRescisao(e.target.value as TipoRescisao); setCalculo(null); }}>
              {Object.entries(LABEL_TIPO_RESCISAO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Data de desligamento</label>
            <input type="date" style={inputSm} value={dataDesligamento}
              onChange={(e) => { setDataDesligamento(e.target.value); setCalculo(null); }} />
          </div>
          <div>
            <label style={lbl}>Dias de férias vencidas</label>
            <input type="number" min={0} max={30} style={inputSm} value={diasFeriasVencidas}
              onChange={(e) => { setDiasFeriasVencidas(e.target.value); setCalculo(null); }} />
          </div>
          {(tipoRescisao === "sem_justa_causa" || tipoRescisao === "acordo_mutuo") && (
            <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: "0.3rem" }}>
              <label style={{ ...lbl, marginBottom: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <input type="checkbox" checked={avisoPrevioTrabalhado}
                  onChange={(e) => { setAvisoPrevioTrabalhado(e.target.checked); setCalculo(null); }} />
                Aviso prévio já foi trabalhado
              </label>
            </div>
          )}
        </div>
        <div><label style={lbl}>Observação</label>
          <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

        <div className="flex items-center gap-2" style={{ marginTop: "0.6rem" }}>
          <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={calcular} disabled={calculando}>
            {calculando ? "Calculando…" : "Calcular verbas rescisórias"}
          </button>
        </div>

        {calculo && (
          <div className="card mt-2" style={{ padding: "0.6rem 0.8rem", fontSize: "0.8rem" }}>
            <div>Saldo de salário ({calculo.saldo_salario.dias_trabalhados_mes} dias): <strong>{formatBRL(calculo.saldo_salario.valor)}</strong></div>
            {calculo.aviso_previo.devido && (
              <div>Aviso prévio indenizado ({calculo.aviso_previo.dias_indenizados} de {calculo.aviso_previo.dias} dias): <strong>{formatBRL(calculo.aviso_previo.valor)}</strong></div>
            )}
            {calculo.ferias_vencidas.valor_total > 0 && (
              <div>Férias vencidas + 1/3: <strong>{formatBRL(calculo.ferias_vencidas.valor_total)}</strong></div>
            )}
            {calculo.ferias_proporcionais.valor_total > 0 && (
              <div>Férias proporcionais + 1/3 ({calculo.ferias_proporcionais.meses} meses): <strong>{formatBRL(calculo.ferias_proporcionais.valor_total)}</strong></div>
            )}
            {calculo.decimo_terceiro_proporcional.valor > 0 && (
              <div>13º proporcional ({calculo.decimo_terceiro_proporcional.meses} meses): <strong>{formatBRL(calculo.decimo_terceiro_proporcional.valor)}</strong></div>
            )}
            {calculo.fgts.multa > 0 && (
              <div>Multa de {Math.round(calculo.fgts.percentual_multa * 100)}% do FGTS: <strong>{formatBRL(calculo.fgts.multa)}</strong></div>
            )}
            <div style={{ marginTop: "0.3rem" }}>Total: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(calculo.valor_total)}</strong></div>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem" }}>
              A multa do FGTS é uma ESTIMATIVA ({Math.round(calculo.fgts.percentual_mensal_estimado * 100)}% do salário/mês × {calculo.fgts.meses_considerados} meses de casa) —
              o sistema não guarda o extrato real de depósitos. Confira com o extrato oficial do FGTS antes de pagar.
              Sem envio ao eSocial/TRCT — só o cálculo interno e o lançamento financeiro.
            </div>

            <div className="grid grid-cols-2 gap-3 mt-3">
              <div>
                <label style={lbl}>Status do lançamento</label>
                <select style={inputSm} value={statusLancamento} onChange={(e) => setStatusLancamento(e.target.value)}>
                  <option value="pendente">Pendente</option>
                  <option value="pago">Já pago</option>
                </select>
              </div>
              {statusLancamento === "pago" && (
                <div>
                  <label style={lbl}>Data do pagamento</label>
                  <input type="date" style={inputSm} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} />
                </div>
              )}
            </div>
          </div>
        )}

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando || !calculo}>
          {salvando ? "Salvando…" : "Lançar rescisão em Contas a Pagar"}
        </button>
      </SecaoRecolhivel>

      <div className="card mt-4">
        <div className="card-header mb-3">Rescisões lançadas</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma rescisão lançada ainda.</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr><th>Descrição</th><th>Competência</th><th>Valor total</th><th>Status</th></tr>
              </thead>
              <tbody>
                {itens.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.descricao}</td>
                    <td>{r.data_competencia}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{formatBRL(r.valor_total)}</td>
                    <td><StatusBadge status={r.valor_pago != null ? "pago" : "pendente"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem" }}>
              Para dar baixa em pagamento pendente, use a aba Contas a pagar.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal — chaveado internamente entre Férias, 13º salário e
// Rescisão.
// ---------------------------------------------------------------------------
export default function FeriasDecimoTerceiroView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [subaba, setSubaba] = useState<"ferias" | "decimo" | "rescisao">("ferias");

  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        <button className={subaba === "ferias" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("ferias")}>Férias</button>
        <button className={subaba === "decimo" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("decimo")}>13º salário</button>
        <button className={subaba === "rescisao" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("rescisao")}>Rescisão</button>
      </div>
      {subaba === "ferias" && <FeriasSection pessoas={pessoas} />}
      {subaba === "decimo" && <DecimoTerceiroSection pessoas={pessoas} />}
      {subaba === "rescisao" && <RescisaoSection pessoas={pessoas} />}
    </div>
  );
}
