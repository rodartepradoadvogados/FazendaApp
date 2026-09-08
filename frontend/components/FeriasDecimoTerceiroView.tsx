"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Check } from "lucide-react";
import {
  fetchPessoas, fetchFerias, criarFerias, atualizarFerias,
  fetchDecimoTerceiro, criarDecimoTerceiro, atualizarDecimoTerceiro,
  fetchContasCorrentes, fetchPreviaMediaVariaveis,
  formatBRL, type RegistroFerias, type RegistroDecimoTerceiro, type ContaCorrenteCadastro,
  type ComposicaoMediaVariaveis,
} from "@/lib/api";
import { MediaVerbasVariaveis } from "@/components/MediaVerbasVariaveis";
import { SecaoRecolhivel, type ModoSecaoCategoria } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

/*
 * Férias e 13º salário — controle DENTRO do app (cálculo, lançamento e
 * acompanhamento). Sem envio ao eSocial (fora de escopo — inviável sem
 * certificado digital/infraestrutura própria); aqui só organiza o que a
 * fazenda já paga hoje.
 *
 * NÃO REMONTE A RESCISÃO AQUI DENTRO. Ela já foi a 3ª sub-aba desta tela
 * (#547) porque `calcular_rescisao` reaproveita `calcular_ferias` e
 * `calcular_decimo_terceiro` no backend — conveniência de cálculo que virou
 * arquitetura de informação e, ao virar menu, inverteu a hierarquia: no
 * código a rescisão é quem CHAMA férias e 13º (o nível de cima), e no menu
 * ela aparecia como aba dentro de duas das suas próprias parcelas. A
 * rescisão abrange no mínimo 11 verbas que não são 13º nem férias (saldo de
 * salário, aviso prévio, multa de FGTS, arts. 479/480 CLT, Súmula 314,
 * estabilidades, arts. 467 e 477) e dispara obrigações acessórias próprias
 * (S-2299 do eSocial, guia de FGTS, baixa na CTPS, seguro-desemprego) — não
 * é um caso particular de férias/13º. Hoje ela é um chip irmão no seletor
 * de categoria da Folha (ver FolhaPagamentoView.tsx e RescisaoView.tsx). O
 * reaproveitamento de cálculo continua no backend e não pede nada daqui.
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
function FeriasSection({ pessoas, contasCorrentes, mostrar }: { pessoas: Pessoa[]; contasCorrentes: ContaCorrenteCadastro[]; mostrar: ModoSecaoCategoria }) {
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
  // A média das verbas variáveis do PERÍODO AQUISITIVO (CLT, art. 142) vem do
  // SERVIDOR, e não de uma segunda conta feita aqui: a média sai das rubricas
  // salariais já gravadas nas folhas, que o navegador não tem. Sem esta
  // consulta, o "valor sugerido" desta tela passaria a divergir do valor que o
  // servidor grava assim que a fazenda ligasse o parâmetro — e o dono só
  // descobriria a diferença DEPOIS de lançar.
  const [mediaPrevia, setMediaPrevia] = useState<ComposicaoMediaVariaveis | null>(null);
  const [expandido, setExpandido] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [dataPagamento, setDataPagamento] = useState(hoje());
  const [pagoErro, setPagoErro] = useState<string | null>(null);

  const ordFerias = useOrdenacao(itens ?? []);

  const carregar = () => fetchFerias().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => String(p.id) === pessoaId), [pessoas, pessoaId]);

  async function calcular() {
    setMsg(null);
    if (!pessoaSelecionada || !pessoaSelecionada.salario_base) {
      setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." });
      return;
    }
    if (!periodoInicio || !periodoFim) {
      setMsg({ tipo: "erro", texto: "Informe o período aquisitivo — é ele que define a janela da média de verbas variáveis." });
      return;
    }
    // A média entra na BASE do dia de férias, e o terço incide sobre o total
    // já somado (CLT, art. 142). Erro na consulta não pode impedir a
    // conferência: cai para média zero, que é o comportamento de quem não
    // ligou o parâmetro.
    let media: ComposicaoMediaVariaveis | null = null;
    try {
      media = await fetchPreviaMediaVariaveis({
        pessoa_id: pessoaSelecionada.id, janela: "periodo_aquisitivo",
        inicio: periodoInicio, fim: periodoFim,
      });
    } catch {
      media = null;
    }
    setMediaPrevia(media);
    const base = pessoaSelecionada.salario_base + (media?.aplicada ? media.media : 0);
    const dg = parseInt(diasGozados, 10) || 0;
    const ab = parseInt(abonoDias, 10) || 0;
    const valorDia = base / 30;
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
      setDiasGozados("30"); setAbonoDias("0"); setObservacao(""); setCalculo(null); setMediaPrevia(null); setContaCorrenteId("");
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
      {mostrar !== "listar" && (
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
            <MediaVerbasVariaveis composicao={mediaPrevia} compacto />
          </div>
        )}

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar férias"}
        </button>
      </SecaoRecolhivel>
      )}

      {mostrar !== "lancar" && (
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
                  <Fragment key={r.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{r.pessoa_nome}</td>
                      <td>{r.data_inicio_gozo} a {r.data_fim_gozo}</td>
                      <td>{r.dias_gozados}</td>
                      <td>{r.abono_pecuniario_dias || 0}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>
                        {formatBRL(r.valor_total)}
                        {/* A média aparece JUNTO do valor, e não só dentro do
                            detalhe: é ela que explica por que estas férias não
                            são simplesmente o salário-base ÷ 30 × dias. */}
                        {!!r.media_variaveis && (
                          <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 400 }}>
                            + média variáveis {formatBRL(r.media_variaveis)}
                          </div>
                        )}
                      </td>
                      <td><StatusBadge status={r.status} /></td>
                      <td>
                        {/* Só quando a média foi de fato apurada: um botão que
                            abre uma linha dizendo "desligado" é ruído para
                            quem escolheu não usar a feature. */}
                        {r.media_variaveis_detalhe?.aplicada && (
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            onClick={() => setExpandido(expandido === r.id ? null : r.id)}>
                            {expandido === r.id ? "Ocultar média" : "Ver média"}
                          </button>
                        )}
                        {r.status !== "pago" && (
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>
                            Marcar como pago
                          </button>
                        )}
                      </td>
                    </tr>
                    {expandido === r.id && (
                      <tr><td colSpan={7}>
                        <MediaVerbasVariaveis composicao={r.media_variaveis_detalhe} titulo="Férias" />
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

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
function DecimoTerceiroSection({ pessoas, contasCorrentes, mostrar }: { pessoas: Pessoa[]; contasCorrentes: ContaCorrenteCadastro[]; mostrar: ModoSecaoCategoria }) {
  const [itens, setItens] = useState<RegistroDecimoTerceiro[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [parcela, setParcela] = useState("unica");
  const [mesesTrabalhados, setMesesTrabalhados] = useState("12");
  const [observacao, setObservacao] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");

  const [valorCalculado, setValorCalculado] = useState<number | null>(null);
  // Ver o comentário equivalente na seção de Férias: a média sai das rubricas
  // salariais já gravadas nas folhas, que só o servidor conhece. Aqui a janela
  // é o ANO CIVIL, e o divisor são os MESMOS avos digitados ao lado (Decreto
  // 57.155/65, art. 2º) — dois números para a mesma contagem é como eles
  // passam a divergir.
  const [mediaPrevia, setMediaPrevia] = useState<ComposicaoMediaVariaveis | null>(null);
  const [expandido, setExpandido] = useState<number | null>(null);
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

  async function calcular() {
    setMsg(null);
    if (!pessoaSelecionada || !pessoaSelecionada.salario_base) {
      setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." });
      return;
    }
    const meses = parseInt(mesesTrabalhados, 10) || 0;
    let media: ComposicaoMediaVariaveis | null = null;
    try {
      media = await fetchPreviaMediaVariaveis({
        pessoa_id: pessoaSelecionada.id, janela: "ano_civil",
        ano: parseInt(ano, 10), meses_trabalhados: meses,
      });
    } catch {
      media = null;
    }
    setMediaPrevia(media);
    const base = pessoaSelecionada.salario_base + (media?.aplicada ? media.media : 0);
    const integral = Math.round((base / 12) * meses * 100) / 100;
    // A 1ª parcela é ADIANTAMENTO de até 50% do 13º (Lei 4.749/1965, art. 2º).
    // Esta tela sugeria o 13º cheio para as três parcelas, batendo com o
    // servidor, que também gravava cheio — era o 13º pago em dobro. O
    // servidor agora divide de verdade (e desconta o que já foi lançado no
    // ano), então o sugerido aqui é só uma estimativa da mesma regra.
    setValorCalculado(parcela === "primeira" ? Math.round(integral * 50) / 100 : integral);
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
      setPessoaId(""); setObservacao(""); setValorCalculado(null); setMediaPrevia(null); setContaCorrenteId("");
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
      {mostrar !== "listar" && (
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
            {/* Limpa o sugerido: trocar a parcela muda o valor (a 1ª é
                adiantamento de 50%), e o número velho ficava na tela. */}
            <select style={inputSm} value={parcela} onChange={(e) => { setParcela(e.target.value); setValorCalculado(null); }}>
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
              {parcela === "primeira"
                ? "Adiantamento de 50% do 13º (Lei 4.749/1965) — sem INSS/IR, que incidem só na 2ª parcela."
                : "INSS/IR (se houver) são informados na edição — o servidor recalcula o bruto ao lançar, descontando o que já foi lançado no ano."}
            </div>
            <MediaVerbasVariaveis composicao={mediaPrevia} compacto />
          </div>
        )}

        {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
        <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar 13º salário"}
        </button>
      </SecaoRecolhivel>
      )}

      {mostrar !== "lancar" && (
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
                  <Fragment key={r.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{r.pessoa_nome}</td>
                      <td>{r.ano}</td>
                      <td>{LABEL_PARCELA[r.parcela || "unica"] || r.parcela}</td>
                      <td>{r.meses_trabalhados}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>
                        {formatBRL(r.valor_liquido)}
                        {!!r.media_variaveis && (
                          <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 400 }}>
                            + média variáveis {formatBRL(r.media_variaveis)}
                          </div>
                        )}
                      </td>
                      <td><StatusBadge status={r.status} /></td>
                      <td>
                        {/* Só quando a média foi de fato apurada: um botão que
                            abre uma linha dizendo "desligado" é ruído para
                            quem escolheu não usar a feature. */}
                        {r.media_variaveis_detalhe?.aplicada && (
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            onClick={() => setExpandido(expandido === r.id ? null : r.id)}>
                            {expandido === r.id ? "Ocultar média" : "Ver média"}
                          </button>
                        )}
                        {r.status !== "pago" && (
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>
                            Marcar como pago
                          </button>
                        )}
                      </td>
                    </tr>
                    {expandido === r.id && (
                      <tr><td colSpan={7}>
                        <MediaVerbasVariaveis composicao={r.media_variaveis_detalhe} titulo="13º salário" />
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

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
// Componente principal — chaveado internamente entre Férias e 13º salário.
// (Duas sub-abas, não três: a Rescisão saiu daqui — ver o cabeçalho.)
// ---------------------------------------------------------------------------
export default function FeriasDecimoTerceiroView({ mostrar = "tudo" }: { mostrar?: ModoSecaoCategoria } = {}) {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [subaba, setSubaba] = useState<"ferias" | "decimo">("ferias");
  // Contas correntes (id + rótulo) — para o seletor opcional "Conta bancária"
  // de Férias/13º, mesmo padrão do Vale de funcionário: carregado uma vez
  // aqui e repassado às 2 sub-seções.
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);

  // Roda a cada montagem — e esta tela remonta toda vez que o chip "Férias /
  // 13º" é escolhido no seletor de categoria da Folha. É o que mantém os
  // dropdowns em dia depois de uma rescisão fechada com "marcar como
  // inativo" na tela irmã (Pessoa.ativo=False no banco, confirmado em
  // backend/tests/test_rescisao_fluxo.py), sem precisar de callback entre as
  // duas telas como era quando a rescisão morava aqui dentro.
  useEffect(() => {
    fetchPessoas().then(setPessoas).catch(() => {});
    fetchContasCorrentes().then(setContasCorrentes).catch(() => {});
  }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        <button className={subaba === "ferias" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("ferias")}>Férias</button>
        <button className={subaba === "decimo" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.8rem" }} onClick={() => setSubaba("decimo")}>13º salário</button>
      </div>
      {subaba === "ferias" && <FeriasSection pessoas={pessoas} contasCorrentes={contasCorrentes} mostrar={mostrar} />}
      {subaba === "decimo" && <DecimoTerceiroSection pessoas={pessoas} contasCorrentes={contasCorrentes} mostrar={mostrar} />}
    </div>
  );
}
