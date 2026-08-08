"use client";
import { useEffect, useMemo, useState } from "react";
import { Plus, Check } from "lucide-react";
import {
  fetchPessoas, fetchFerias, criarFerias, atualizarFerias,
  fetchDecimoTerceiro, criarDecimoTerceiro, atualizarDecimoTerceiro,
  fetchContasCorrentes,
  formatBRL, type RegistroFerias, type RegistroDecimoTerceiro, type ContaCorrenteCadastro,
} from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import RescisaoView from "@/components/RescisaoView";

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
function FeriasSection({ pessoas, contasCorrentes }: { pessoas: Pessoa[]; contasCorrentes: ContaCorrenteCadastro[] }) {
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
  const [contaCorrenteId, setContaCorrenteId] = useState("");

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
        conta_corrente_id: contaCorrenteId ? Number(contaCorrenteId) : undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Férias lançadas." });
      setPessoaId(""); setPeriodoInicio(""); setPeriodoFim(""); setDataInicioGozo(""); setDataFimGozo("");
      setDiasGozados("30"); setAbonoDias("0"); setObservacao(""); setCalculo(null); setContaCorrenteId("");
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
        conta_corrente_id: r.conta_corrente_id,
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

        <div className="mt-2" style={{ maxWidth: 320 }}>
          <label style={lbl}>Conta bancária (opcional)</label>
          <select style={inputSm} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
            <option value="">Não informar</option>
            {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
          </select>
        </div>

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
function DecimoTerceiroSection({ pessoas, contasCorrentes }: { pessoas: Pessoa[]; contasCorrentes: ContaCorrenteCadastro[] }) {
  const [itens, setItens] = useState<RegistroDecimoTerceiro[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [parcela, setParcela] = useState("unica");
  const [mesesTrabalhados, setMesesTrabalhados] = useState("12");
  const [observacao, setObservacao] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");

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
        conta_corrente_id: contaCorrenteId ? Number(contaCorrenteId) : undefined,
      });
      setMsg({ tipo: "sucesso", texto: "13º salário lançado." });
      setPessoaId(""); setObservacao(""); setValorCalculado(null); setContaCorrenteId("");
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
        conta_corrente_id: r.conta_corrente_id,
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

        <div className="mt-2" style={{ maxWidth: 320 }}>
          <label style={lbl}>Conta bancária (opcional)</label>
          <select style={inputSm} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
            <option value="">Não informar</option>
            {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
          </select>
        </div>

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
// Componente principal — chaveado internamente entre Férias, 13º salário e
// Rescisão.
// ---------------------------------------------------------------------------
export default function FeriasDecimoTerceiroView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [subaba, setSubaba] = useState<"ferias" | "decimo" | "rescisao">("ferias");
  // Contas correntes (id + rótulo) — para o seletor opcional "Conta bancária"
  // de Férias/13º/Rescisão, mesmo padrão do Vale de funcionário: carregado
  // uma vez aqui e repassado às 3 sub-seções.
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);

  const carregarPessoas = () => fetchPessoas().then(setPessoas).catch(() => {});
  useEffect(() => { carregarPessoas(); fetchContasCorrentes().then(setContasCorrentes).catch(() => {}); }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        <button className={subaba === "ferias" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("ferias")}>Férias</button>
        <button className={subaba === "decimo" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("decimo")}>13º salário</button>
        <button className={subaba === "rescisao" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("rescisao")}>Rescisão</button>
      </div>
      {subaba === "ferias" && <FeriasSection pessoas={pessoas} contasCorrentes={contasCorrentes} />}
      {subaba === "decimo" && <DecimoTerceiroSection pessoas={pessoas} contasCorrentes={contasCorrentes} />}
      {/* onPessoaInativada: fechar rescisão com "marcar como inativo" muda
          Pessoa.ativo no banco (confirmado em backend/tests/test_rescisao_fluxo.py),
          mas esta lista `pessoas` só era buscada 1x no mount — sem isso, o
          funcionário recém-inativado continuava aparecendo como ativo em
          qualquer dropdown desta página (Férias/13º/nova Rescisão) até um
          F5, dando a falsa impressão de que a caixinha não fez nada. */}
      {subaba === "rescisao" && <RescisaoView pessoas={pessoas} onPessoaInativada={carregarPessoas} />}
    </div>
  );
}
