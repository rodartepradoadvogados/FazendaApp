"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Pencil, Trash2, Printer, X } from "lucide-react";
import {
  simularRescisao, fetchRescisoesFuncionario, criarSimulacaoRescisao, atualizarSimulacaoRescisao,
  excluirSimulacaoRescisao, fecharRescisao, formatBRL, fetchContasCorrentes, fetchPessoas,
  type TipoRescisao, type CalculoRescisao, type RegistroRescisaoFuncionario,
  type RescisaoSimulacaoDados, type FormaLancamentoRescisao, type ContaCorrenteCadastro,
  type SaldoValeEmAberto, type MediasVariaveisComposicao,
} from "@/lib/api";
import { MediaVerbasVariaveis } from "@/components/MediaVerbasVariaveis";
import { ReciboModal } from "@/components/ReciboModal";
import { exportarFichaPDF, exportarMultiExcel, type SecaoFicha, type LancamentoRecibo } from "@/lib/export";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { type ModoSecaoCategoria } from "@/components/ui";

/*
 * Rescisão contratual (CLT) — saldo de salário, aviso prévio, férias
 * vencidas/proporcionais, 13º proporcional e multa de FGTS (ESTIMADA — o
 * sistema não guarda o extrato real de depósitos de FGTS). Fluxo em 4
 * etapas: (1) simular (calcula só como sugestão, não grava nada), (2) editar
 * as verbas e descontos e salvar como rascunho ("simulacao"), (3) fechar —
 * gera o lançamento em Contas a Pagar, (4) acompanhar — tabela sempre
 * visível com as rescisões simuladas/fechadas, incluindo o histórico legado
 * pré-migração (somente leitura). Sem envio ao eSocial (fora de escopo —
 * inviável sem certificado digital/infraestrutura própria).
 *
 * ONDE ESTA TELA MORA — e por que NÃO volta para dentro de Férias/13º:
 * até #547 esta tela era a 3ª sub-aba de `FeriasDecimoTerceiroView`. O
 * motivo era de CÁLCULO, não de navegação: `calcular_rescisao` reaproveita
 * `calcular_ferias` e `calcular_decimo_terceiro` (backend/fazenda/rules/
 * folha_rh.py). Só que essa conveniência, ao virar menu, INVERTEU a
 * hierarquia: no código a rescisão é o CONSUMIDOR (o nível de cima, que
 * chama os dois), e no menu ela aparecia como terceira aba dentro de duas
 * das suas próprias parcelas. Juridicamente a inversão é ainda mais clara —
 * a rescisão abrange no mínimo 11 verbas que não são 13º nem férias (saldo
 * de salário, aviso prévio, multa de 40%/20% do FGTS, arts. 479/480 CLT,
 * Súmula 314 do TST, estabilidades, multas dos arts. 467 e 477) e dispara
 * 10 obrigações acessórias; sem o evento S-2299 do eSocial não há guia de
 * FGTS, baixa na CTPS nem seguro-desemprego.
 * O reaproveitamento de cálculo vive no BACKEND e continua valendo onde
 * quer que a tela fique — não há dívida técnica pedindo o contrário. Por
 * isso a Rescisão é hoje um chip PRÓPRIO do seletor de categoria da Folha
 * (ver FolhaPagamentoView.tsx), irmão de Funcionário/Empreita/Contrato/
 * Diária/Férias-13º, e este componente é autossuficiente: busca as próprias
 * pessoas, sem depender de um pai que já tivesse a lista carregada.
 */
type Pessoa = { id: number; nome: string; tipos: string[]; salario_base?: number | null; data_admissao?: string | null };

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
};
const hoje = () => new Date().toISOString().slice(0, 10);

const LABEL_TIPO_RESCISAO: Record<TipoRescisao, string> = {
  sem_justa_causa: "Dispensa sem justa causa",
  pedido_demissao: "Pedido de demissão",
  justa_causa: "Dispensa por justa causa",
  acordo_mutuo: "Acordo mútuo (distrato)",
};

function StatusBadgeRescisao({ status }: { status: string }) {
  return (
    <span style={{ fontSize: "0.72rem", fontWeight: 700, color: status === "fechada" ? "var(--green-light)" : "var(--amber)" }}>
      {status === "fechada" ? "Fechada" : "Simulação"}
    </span>
  );
}

// Contexto (dias/meses/percentuais) usado para legendar os campos editáveis
// — vem do cálculo recém-feito (etapa "simular") OU dos próprios campos do
// registro já persistido (ao reabrir uma simulação existente pela tabela).
type ContextoVerbas = {
  diasSaldoSalario?: number; diasAvisoPrevio?: number; diasAvisoPrevioIndenizados?: number; avisoDevido?: boolean;
  mesesFeriasProporcionais?: number; mesesDecimoTerceiro?: number; percentualMultaFgts?: number;
};

function paraNumeroOuNulo(v: string): number | null {
  if (v.trim() === "") return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}
function paraNumero(v: string): number {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
}

export default function RescisaoView({ mostrar = "tudo" }: { mostrar?: ModoSecaoCategoria } = {}) {
  // A lista de pessoas é DESTA tela desde que a rescisão virou chip próprio:
  // antes ela descia como prop de `FeriasDecimoTerceiroView` (que a buscava
  // 1x no mount) e por isso precisava do callback `onPessoaInativada` para
  // não ficar desatualizada depois de um fechamento com "marcar como
  // inativo". Agora o refresh acontece aqui mesmo, em `carregarPessoas()`.
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<RegistroRescisaoFuncionario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const [etapa, setEtapa] = useState<"simular" | "editar" | "fechar">("simular");
  const [rascunhoId, setRascunhoId] = useState<number | null>(null);

  // Etapa 1 — dados de identificação da rescisão (mesmos campos de sempre).
  const [pessoaId, setPessoaId] = useState("");
  const [tipoRescisao, setTipoRescisao] = useState<TipoRescisao>("sem_justa_causa");
  const [dataDesligamento, setDataDesligamento] = useState(hoje());
  const [diasFeriasVencidas, setDiasFeriasVencidas] = useState("0");
  const [avisoPrevioTrabalhado, setAvisoPrevioTrabalhado] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [centroCusto, setCentroCusto] = useState<string | undefined>(undefined);

  const [calculando, setCalculando] = useState(false);
  const [contexto, setContexto] = useState<ContextoVerbas | null>(null);
  // As TRÊS composições de média de verbas variáveis habituais, vindas da
  // simulação. São três porque cada verba segue a regra da SUA natureza: o 13º
  // proporcional usa o ANO CIVIL (Decreto 57.155/65, art. 2º), as férias
  // vencidas e proporcionais usam o PERÍODO AQUISITIVO (CLT, art. 142) e o
  // aviso prévio indenizado usa os ÚLTIMOS 12 MESES. Mostrar uma média só
  // esconderia que as outras duas são outro número.
  const [medias, setMedias] = useState<MediasVariaveisComposicao | null>(null);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  // Etapa 2 — as 6 verbas + 3 descontos, todas editáveis.
  const [valorSaldoSalario, setValorSaldoSalario] = useState("");
  const [valorAvisoPrevio, setValorAvisoPrevio] = useState("");
  const [valorFeriasVencidas, setValorFeriasVencidas] = useState("");
  const [valorFeriasProporcionais, setValorFeriasProporcionais] = useState("");
  const [valorDecimoTerceiroProporcional, setValorDecimoTerceiroProporcional] = useState("");
  const [valorMultaFgts, setValorMultaFgts] = useState("");
  const [valorInss, setValorInss] = useState("0");
  const [valorIr, setValorIr] = useState("0");
  const [valorValeEmAberto, setValorValeEmAberto] = useState("0");
  /* O saldo de vale REAL da pessoa, vindo do servidor — o número que a tela
   * não tinha. "Vale em aberto" era digitado à mão e nascia em zero: uma
   * rescisão real foi fechada com R$ 0,00 nesse campo e deixou R$ 6.485,00 de
   * vale de pé, em competências que nunca mais teriam folha para descontar.
   * Aqui ele é PRÉ-PREENCHIDO com o saldo e continua editável (o dono pode
   * ter acertado parte por fora) — mas o fechamento recusa enquanto sobrar
   * saldo não endereçado, porque rescisão fechada não reabre. */
  const [saldoVale, setSaldoVale] = useState<SaldoValeEmAberto | null>(null);
  const [salvando, setSalvando] = useState(false);

  // Etapa 3 — fechamento.
  const [formaLancamento, setFormaLancamento] = useState<FormaLancamentoRescisao>("unico");
  const [statusPagamentoFechar, setStatusPagamentoFechar] = useState<"pendente" | "pago">("pendente");
  const [dataPagamentoFechar, setDataPagamentoFechar] = useState(hoje());
  const [inativarPessoa, setInativarPessoa] = useState(true);
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [fechando, setFechando] = useState(false);
  const [fecharMsg, setFecharMsg] = useState<string | null>(null);

  // Ações da tabela (etapa 4 — acompanhar).
  const [excluindoId, setExcluindoId] = useState<number | null>(null);
  const [excluirErro, setExcluirErro] = useState<string | null>(null);
  const [imprimindoId, setImprimindoId] = useState<number | null>(null);
  const [exportando, setExportando] = useState(false);
  const [reciboLinha, setReciboLinha] = useState<LancamentoRecibo | null>(null);

  const carregar = () => fetchRescisoesFuncionario().then(setItens).catch((e) => setError(e.message));
  // Mesma busca (sem filtro de `ativo`) que `FeriasDecimoTerceiroView` fazia
  // e repassava por prop — o dropdown de "nova rescisão" continua listando
  // exatamente as mesmas pessoas de antes.
  const carregarPessoas = () => fetchPessoas().then(setPessoas).catch(() => {});
  useEffect(() => {
    carregar();
    carregarPessoas();
    fetchContasCorrentes().then(setContasCorrentes).catch(() => {});
  }, []);

  const ordRescisoes = useOrdenacao(itens ?? []);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => String(p.id) === pessoaId), [pessoas, pessoaId]);

  function resetVerbas() {
    setValorSaldoSalario(""); setValorAvisoPrevio(""); setValorFeriasVencidas("");
    setValorFeriasProporcionais(""); setValorDecimoTerceiroProporcional(""); setValorMultaFgts("");
    setValorInss("0"); setValorIr("0"); setValorValeEmAberto("0");
    setSaldoVale(null);
    setContexto(null);
  }

  function resetTudo() {
    setEtapa("simular"); setRascunhoId(null);
    setPessoaId(""); setTipoRescisao("sem_justa_causa"); setDataDesligamento(hoje());
    setDiasFeriasVencidas("0"); setAvisoPrevioTrabalhado(false); setObservacao(""); setCentroCusto(undefined);
    setMsg(null); setFecharMsg(null);
    setFormaLancamento("unico"); setStatusPagamentoFechar("pendente"); setDataPagamentoFechar(hoje()); setInativarPessoa(true);
    setContaCorrenteId("");
    resetVerbas();
  }

  async function calcular() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o funcionário." }); return; }
    if (!pessoaSelecionada?.salario_base) { setMsg({ tipo: "erro", texto: "Selecione um funcionário com salário base cadastrado." }); return; }
    if (!pessoaSelecionada?.data_admissao) { setMsg({ tipo: "erro", texto: "Funcionário sem data de admissão cadastrada." }); return; }
    setCalculando(true);
    try {
      const resultado: CalculoRescisao = await simularRescisao({
        pessoa_id: Number(pessoaId), tipo_rescisao: tipoRescisao, data_desligamento: dataDesligamento,
        dias_ferias_vencidas: parseInt(diasFeriasVencidas, 10) || 0, aviso_previo_trabalhado: avisoPrevioTrabalhado,
        observacao: observacao || undefined,
      });
      setContexto({
        diasSaldoSalario: resultado.saldo_salario.dias_trabalhados_mes,
        diasAvisoPrevio: resultado.aviso_previo.dias, diasAvisoPrevioIndenizados: resultado.aviso_previo.dias_indenizados,
        avisoDevido: resultado.aviso_previo.devido,
        mesesFeriasProporcionais: resultado.ferias_proporcionais.meses, mesesDecimoTerceiro: resultado.decimo_terceiro_proporcional.meses,
        percentualMultaFgts: Math.round(resultado.fgts.percentual_multa * 100),
      });
      setMedias(resultado.medias_variaveis_composicao ?? null);
      setValorSaldoSalario(String(resultado.saldo_salario.valor));
      setValorAvisoPrevio(String(resultado.aviso_previo.valor));
      setValorFeriasVencidas(String(resultado.ferias_vencidas.valor_total));
      setValorFeriasProporcionais(String(resultado.ferias_proporcionais.valor_total));
      setValorDecimoTerceiroProporcional(String(resultado.decimo_terceiro_proporcional.valor));
      setValorMultaFgts(String(resultado.fgts.multa));
      setValorInss("0"); setValorIr("0");
      // Pré-preenchido com o saldo real (e não mais com zero fixo) — editável.
      setSaldoVale(resultado.vale_em_aberto ?? null);
      setValorValeEmAberto(String(resultado.vale_em_aberto?.total ?? 0));
      setRascunhoId(null);
      setEtapa("editar");
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao calcular rescisão" });
    } finally {
      setCalculando(false);
    }
  }

  const netTotal = useMemo(() => {
    const verbas = paraNumero(valorSaldoSalario) + paraNumero(valorAvisoPrevio) + paraNumero(valorFeriasVencidas)
      + paraNumero(valorFeriasProporcionais) + paraNumero(valorDecimoTerceiroProporcional) + paraNumero(valorMultaFgts);
    const descontos = paraNumero(valorInss) + paraNumero(valorIr) + paraNumero(valorValeEmAberto);
    return Math.round((verbas - descontos) * 100) / 100;
  }, [valorSaldoSalario, valorAvisoPrevio, valorFeriasVencidas, valorFeriasProporcionais, valorDecimoTerceiroProporcional, valorMultaFgts, valorInss, valorIr, valorValeEmAberto]);

  function montarDadosSimulacao(): RescisaoSimulacaoDados {
    return {
      pessoa_id: Number(pessoaId), tipo_rescisao: tipoRescisao, data_desligamento: dataDesligamento,
      dias_ferias_vencidas: parseInt(diasFeriasVencidas, 10) || 0, aviso_previo_trabalhado: avisoPrevioTrabalhado,
      observacao: observacao || undefined, centro_custo: centroCusto,
      valor_saldo_salario: paraNumeroOuNulo(valorSaldoSalario), valor_aviso_previo: paraNumeroOuNulo(valorAvisoPrevio),
      valor_ferias_vencidas: paraNumeroOuNulo(valorFeriasVencidas), valor_ferias_proporcionais: paraNumeroOuNulo(valorFeriasProporcionais),
      valor_decimo_terceiro_proporcional: paraNumeroOuNulo(valorDecimoTerceiroProporcional), valor_multa_fgts: paraNumeroOuNulo(valorMultaFgts),
      valor_inss: paraNumero(valorInss), valor_ir: paraNumero(valorIr), valor_vale_em_aberto: paraNumero(valorValeEmAberto),
    };
  }

  async function salvarSimulacao() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione o funcionário." }); return; }
    if (netTotal < 0) { setMsg({ tipo: "erro", texto: "O valor líquido não pode ser negativo." }); return; }
    setSalvando(true);
    try {
      const r = rascunhoId == null
        ? await criarSimulacaoRescisao(montarDadosSimulacao())
        : await atualizarSimulacaoRescisao(rascunhoId, montarDadosSimulacao());
      setRascunhoId(r.id);
      if (r.vale_em_aberto !== undefined) setSaldoVale(r.vale_em_aberto);
      setMsg({ tipo: "sucesso", texto: "Simulação salva." });
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao salvar simulação de rescisão" });
    } finally {
      setSalvando(false);
    }
  }

  function editarRascunho(r: RegistroRescisaoFuncionario) {
    setRascunhoId(r.id);
    setPessoaId(r.pessoa_id != null ? String(r.pessoa_id) : "");
    setTipoRescisao(r.tipo_rescisao || "sem_justa_causa");
    setDataDesligamento(r.data_desligamento);
    setDiasFeriasVencidas(String(r.dias_ferias_vencidas ?? 0));
    setAvisoPrevioTrabalhado(!!r.aviso_previo_trabalhado);
    setObservacao(r.observacao || "");
    setCentroCusto(r.centro_custo || undefined);
    setValorSaldoSalario(String(r.valor_saldo_salario));
    setValorAvisoPrevio(String(r.valor_aviso_previo));
    setValorFeriasVencidas(String(r.valor_ferias_vencidas));
    setValorFeriasProporcionais(String(r.valor_ferias_proporcionais));
    setValorDecimoTerceiroProporcional(String(r.valor_decimo_terceiro_proporcional));
    setValorMultaFgts(String(r.valor_multa_fgts));
    setValorInss(String(r.valor_inss ?? 0));
    setValorIr(String(r.valor_ir ?? 0));
    setValorValeEmAberto(String(r.valor_vale_em_aberto ?? 0));
    setSaldoVale(r.vale_em_aberto ?? null);
    setContexto({
      diasSaldoSalario: r.dias_saldo_salario, diasAvisoPrevio: r.dias_aviso_previo,
      diasAvisoPrevioIndenizados: r.dias_aviso_previo_indenizados, avisoDevido: r.valor_aviso_previo > 0,
      mesesFeriasProporcionais: r.meses_ferias_proporcionais, mesesDecimoTerceiro: r.meses_decimo_terceiro,
      percentualMultaFgts: r.percentual_multa_fgts,
    });
    setMsg(null);
    setEtapa("editar");
  }

  function irParaFechar(r?: RegistroRescisaoFuncionario) {
    if (r) editarRascunho(r);
    setFormaLancamento("unico"); setStatusPagamentoFechar("pendente"); setDataPagamentoFechar(hoje()); setInativarPessoa(true);
    setContaCorrenteId("");
    setFecharMsg(null);
    setEtapa("fechar");
  }

  async function fechar() {
    if (rascunhoId == null) return;
    setFecharMsg(null);
    setFechando(true);
    try {
      const marcouInativo = inativarPessoa;
      await fecharRescisao(rascunhoId, {
        forma_lancamento: formaLancamento, status_pagamento: statusPagamentoFechar,
        data_pagamento: statusPagamentoFechar === "pago" ? dataPagamentoFechar : null,
        inativar_pessoa: inativarPessoa,
        conta_corrente_id: contaCorrenteId ? Number(contaCorrenteId) : undefined,
      });
      resetTudo();
      carregar();
      // Sem isto, a lista `pessoas` (buscada 1x no mount) continua mostrando
      // o funcionário como ativo no dropdown de nova rescisão até um F5 —
      // mesmo com o backend já tendo gravado ativo=False (confirmado em
      // backend/tests/test_rescisao_fluxo.py). Os dropdowns de Férias/13º
      // não precisam mais de aviso: aquela tela é irmã desta no seletor de
      // categoria e remonta (refazendo o fetch) ao ser escolhida.
      if (marcouInativo) carregarPessoas();
    } catch (e: any) {
      setFecharMsg(e.message || "Erro ao fechar rescisão");
    } finally {
      setFechando(false);
    }
  }

  async function excluir(r: RegistroRescisaoFuncionario) {
    if (!window.confirm(`Excluir a simulação de rescisão de ${r.pessoa_nome}?`)) return;
    setExcluirErro(null);
    setExcluindoId(r.id);
    try {
      await excluirSimulacaoRescisao(r.id);
      if (rascunhoId === r.id) resetTudo();
      if (expandedId === r.id) setExpandedId(null);
      carregar();
    } catch (e: any) {
      setExcluirErro(e.message || "Erro ao excluir simulação de rescisão");
    } finally {
      setExcluindoId(null);
    }
  }

  function abrirReciboUnico(r: RegistroRescisaoFuncionario) {
    setReciboLinha({
      numero_lancamento: r.numero_lancamento_gerado,
      tipo: "despesa",
      fornecedor: r.pessoa_nome,
      descricao: `Rescisão — ${r.tipo_rescisao ? LABEL_TIPO_RESCISAO[r.tipo_rescisao] : "—"} — ${r.pessoa_nome}`,
      valor: r.valor_total,
      valor_pago: r.status === "fechada" && r.data_pagamento ? r.valor_total : undefined,
      data_vencimento: r.data_pagamento || undefined,
      data_pagamento: r.data_pagamento,
      tipo_documento: "Rescisão",
    });
  }

  function abrirReciboLegado(r: RegistroRescisaoFuncionario) {
    setReciboLinha({
      numero_lancamento: r.numero_lancamento_gerado,
      tipo: "despesa",
      fornecedor: r.pessoa_nome,
      descricao: r.descricao || "Rescisão",
      valor: r.valor_total,
      data_pagamento: r.data_pagamento,
      tipo_documento: "Rescisão",
    });
  }

  async function gerarReciboDetalhado(r: RegistroRescisaoFuncionario, formato: "pdf" | "excel") {
    setExportando(true);
    try {
      const secoes: SecaoFicha[] = [{
        titulo: r.pessoa_nome,
        colunas: [{ header: "Item", key: "item" }, { header: "Valor", key: "valor" }],
        linhas: r.detalhe.map((d) => ({ item: d.label, valor: formatBRL(d.valor) })),
      }];
      const base = `rescisao_${r.pessoa_nome.replace(/\s+/g, "_")}_${r.data_desligamento}`;
      if (formato === "pdf") await exportarFichaPDF("Rescisão contratual", r.pessoa_nome, secoes, base);
      else await exportarMultiExcel("Rescisão contratual", secoes, base);
    } catch {
      // erro já mostrado ao usuário dentro de exportarFichaPDF/exportarMultiExcel (lib/export.ts)
    } finally {
      setExportando(false);
      setImprimindoId(null);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;

  return (
    <div>
      {mostrar !== "listar" && (
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <div className="card-header">
            {etapa === "simular" && "1. Simular rescisão"}
            {etapa === "editar" && "2. Conferir e editar verbas"}
            {etapa === "fechar" && "3. Fechar rescisão"}
          </div>
          {(etapa !== "simular" || rascunhoId != null) && (
            <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={resetTudo}>
              <X size={13} /> Nova simulação
            </button>
          )}
        </div>

        {etapa === "simular" && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
              <div>
                <label style={lbl}>Funcionário</label>
                <select style={inputSm} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
                  <option value="">Selecione…</option>
                  {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>Modalidade</label>
                <select style={inputSm} value={tipoRescisao} onChange={(e) => setTipoRescisao(e.target.value as TipoRescisao)}>
                  {Object.entries(LABEL_TIPO_RESCISAO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>Data de desligamento</label>
                <input type="date" style={inputSm} value={dataDesligamento} onChange={(e) => setDataDesligamento(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>Dias de férias vencidas</label>
                <input type="number" min={0} max={30} style={inputSm} value={diasFeriasVencidas} onChange={(e) => setDiasFeriasVencidas(e.target.value)} />
              </div>
              {(tipoRescisao === "sem_justa_causa" || tipoRescisao === "acordo_mutuo") && (
                <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: "0.3rem" }}>
                  <label style={{ ...lbl, marginBottom: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <input type="checkbox" checked={avisoPrevioTrabalhado} onChange={(e) => setAvisoPrevioTrabalhado(e.target.checked)} />
                    Aviso prévio já foi trabalhado
                  </label>
                </div>
              )}
            </div>
            <div><label style={lbl}>Observação</label>
              <textarea style={{ ...inputSm, minHeight: "2.4rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

            {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
            <button className="btn-primary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }} onClick={calcular} disabled={calculando}>
              {calculando ? "Calculando…" : "Calcular verbas rescisórias"}
            </button>
          </div>
        )}

        {etapa === "editar" && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
              <div>
                <label style={lbl}>Saldo de salário{contexto?.diasSaldoSalario != null ? ` (${contexto.diasSaldoSalario} dia(s))` : ""}</label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorSaldoSalario} onChange={(e) => setValorSaldoSalario(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>
                  Aviso prévio indenizado
                  {contexto?.diasAvisoPrevioIndenizados != null && contexto?.diasAvisoPrevio != null
                    ? ` (${contexto.diasAvisoPrevioIndenizados} de ${contexto.diasAvisoPrevio} dia(s))` : ""}
                </label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorAvisoPrevio} onChange={(e) => setValorAvisoPrevio(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>Férias vencidas + 1/3</label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorFeriasVencidas} onChange={(e) => setValorFeriasVencidas(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>Férias proporcionais + 1/3{contexto?.mesesFeriasProporcionais != null ? ` (${contexto.mesesFeriasProporcionais} mês(es))` : ""}</label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorFeriasProporcionais} onChange={(e) => setValorFeriasProporcionais(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>13º proporcional{contexto?.mesesDecimoTerceiro != null ? ` (${contexto.mesesDecimoTerceiro} mês(es))` : ""}</label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorDecimoTerceiroProporcional} onChange={(e) => setValorDecimoTerceiroProporcional(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>Multa do FGTS{contexto?.percentualMultaFgts != null ? ` (${contexto.percentualMultaFgts}% estimado)` : " (estimada)"}</label>
                <input type="number" step="0.01" min="0" style={inputSm} value={valorMultaFgts} onChange={(e) => setValorMultaFgts(e.target.value)} />
              </div>
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginBottom: "0.8rem" }}>
              A multa do FGTS é uma ESTIMATIVA — o sistema não guarda o extrato real de depósitos. Confira com o extrato oficial do FGTS antes de pagar.
              A média de verbas variáveis NÃO entra nela, justamente por ser estimativa; entra no 13º, nas férias e no aviso prévio indenizado.
              Sem envio ao eSocial/TRCT — só o cálculo interno e o lançamento financeiro.
            </div>

            {/* Só aparece quando a fazenda LIGOU as médias. Desligado, três
                linhas dizendo "não apurada" seriam ruído puro para quem
                escolheu deixar isso com a contabilidade externa. */}
            {medias?.decimo_terceiro?.aplicada && (
              <div style={{ marginBottom: "0.8rem" }}>
                <MediaVerbasVariaveis composicao={medias.decimo_terceiro} titulo="13º proporcional" compacto />
                <MediaVerbasVariaveis composicao={medias.ferias} titulo="Férias (vencidas e proporcionais)" compacto />
                <MediaVerbasVariaveis composicao={medias.aviso_previo} titulo="Aviso prévio indenizado" compacto />
              </div>
            )}

            <div className="card" style={{ padding: "0.6rem 0.8rem", background: "var(--surface-2)", marginBottom: "0.8rem" }}>
              <div className="card-header mb-2" style={{ fontSize: "0.8rem" }}>Descontos</div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div>
                  <label style={lbl}>INSS</label>
                  <input type="number" step="0.01" min="0" style={inputSm} value={valorInss} onChange={(e) => setValorInss(e.target.value)} />
                </div>
                <div>
                  <label style={lbl}>IRRF</label>
                  <input type="number" step="0.01" min="0" style={inputSm} value={valorIr} onChange={(e) => setValorIr(e.target.value)} />
                </div>
                <div>
                  <label style={lbl}>
                    Vale em aberto
                    {saldoVale ? ` (saldo cobrável: ${formatBRL(saldoVale.total)})` : ""}
                  </label>
                  <input type="number" step="0.01" min="0" style={inputSm} value={valorValeEmAberto} onChange={(e) => setValorValeEmAberto(e.target.value)} />
                </div>
              </div>
              {saldoVale && saldoVale.total > 0 && (
                <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.5rem" }}>
                  Parcelas de vale ainda a descontar: {saldoVale.competencias.map((c) => `${c.competencia} (${formatBRL(c.valor)})`).join(", ")}.
                  {" "}O que for descontado aqui BAIXA essas parcelas no fechamento. O que sobrar impede o
                  fechamento — depois de fechada a rescisão não há mais folha para descontar e ela não reabre:
                  resolva a sobra em Folha de Pagamento &gt; vale &gt; Ações (abater, desconsiderar o mês ou
                  cancelar o vale, que faz a fazenda assumir).
                </div>
              )}
            </div>

            <div className="card" style={{ padding: "0.6rem 0.8rem" }}>
              Valor líquido: <strong style={{ color: netTotal < 0 ? "var(--red)" : "var(--dourado-light)" }}>{formatBRL(netTotal)}</strong>
            </div>

            {msg && <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{msg.texto}</p>}
            <div className="flex items-center gap-2 mt-3" style={{ flexWrap: "wrap" }}>
              <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={() => setEtapa("simular")}>Voltar</button>
              <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={salvarSimulacao} disabled={salvando}>
                {salvando ? "Salvando…" : "Salvar simulação"}
              </button>
              {rascunhoId != null && (
                <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={() => irParaFechar()}>
                  Ir para fechamento
                </button>
              )}
            </div>
          </div>
        )}

        {etapa === "fechar" && (
          <div>
            <p style={{ fontSize: "0.82rem", marginBottom: "0.8rem" }}>
              Fechando a rescisão de <strong>{pessoaSelecionada?.nome || "—"}</strong> — valor líquido <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(netTotal)}</strong>.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              <div className="card" style={{ padding: "0.6rem 0.8rem", cursor: "pointer", border: formaLancamento === "unico" ? "1px solid var(--dourado)" : "1px solid var(--border)" }}
                onClick={() => setFormaLancamento("unico")}>
                <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
                  <input type="radio" checked={formaLancamento === "unico"} onChange={() => setFormaLancamento("unico")} style={{ marginTop: "0.2rem" }} />
                  <span>
                    <strong style={{ fontSize: "0.82rem" }}>Lançamento único</strong>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>1 conta a pagar com o valor líquido total</div>
                  </span>
                </label>
              </div>
              <div className="card" style={{ padding: "0.6rem 0.8rem", cursor: "pointer", border: formaLancamento === "detalhado" ? "1px solid var(--dourado)" : "1px solid var(--border)" }}
                onClick={() => setFormaLancamento("detalhado")}>
                <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
                  <input type="radio" checked={formaLancamento === "detalhado"} onChange={() => setFormaLancamento("detalhado")} style={{ marginTop: "0.2rem" }} />
                  <span>
                    <strong style={{ fontSize: "0.82rem" }}>Lançamento detalhado</strong>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>uma conta a pagar por verba, agrupadas sob o mesmo número de lançamento</div>
                  </span>
                </label>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label style={lbl}>Status do pagamento</label>
                <select style={inputSm} value={statusPagamentoFechar} onChange={(e) => setStatusPagamentoFechar(e.target.value as "pendente" | "pago")}>
                  <option value="pendente">Pendente</option>
                  <option value="pago">Já pago</option>
                </select>
              </div>
              {statusPagamentoFechar === "pago" && (
                <div>
                  <label style={lbl}>Data do pagamento</label>
                  <input type="date" style={inputSm} value={dataPagamentoFechar} onChange={(e) => setDataPagamentoFechar(e.target.value)} />
                </div>
              )}
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "-0.4rem", marginBottom: "0.8rem" }}>
              {statusPagamentoFechar === "pendente"
                ? "Pendente: entra em Financeiro › Contas › Contas a pagar. Só aparece em Contas pagas depois de dar baixa no pagamento."
                : "Já pago: entra direto em Financeiro › Contas › Contas pagas, com a data de pagamento informada."}
            </div>

            <div className="mb-3" style={{ maxWidth: 320 }}>
              <label style={lbl}>Conta bancária (opcional)</label>
              <select style={inputSm} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
                <option value="">Não informar</option>
                {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
              </select>
            </div>

            <label style={{ ...lbl, display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.8rem" }}>
              <input type="checkbox" checked={inativarPessoa} onChange={(e) => setInativarPessoa(e.target.checked)} />
              Marcar {pessoaSelecionada?.nome || "o funcionário"} como inativo no cadastro
            </label>

            {fecharMsg && <p style={{ color: "var(--red)", fontSize: "0.8rem", margin: "0.5rem 0" }}>{fecharMsg}</p>}
            <div className="flex items-center gap-2">
              <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={() => setEtapa("editar")}>Voltar</button>
              <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={fechar} disabled={fechando}>
                {fechando ? "Fechando…" : "Fechar rescisão"}
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {mostrar !== "lancar" && (
      <div className="card">
        <div className="card-header mb-3">Rescisões</div>
        {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
        {itens && !itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma rescisão simulada ou lançada ainda.</p>}
        {excluirErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{excluirErro}</p>}
        {itens && itens.length > 0 && (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Funcionário" campo="pessoa_nome" coluna={ordRescisoes.coluna} dir={ordRescisoes.dir} ordenar={ordRescisoes.ordenar} />
                  <ThOrdenavel label="Modalidade" campo="tipo_rescisao" coluna={ordRescisoes.coluna} dir={ordRescisoes.dir} ordenar={ordRescisoes.ordenar} />
                  <ThOrdenavel label="Desligamento" campo="data_desligamento" coluna={ordRescisoes.coluna} dir={ordRescisoes.dir} ordenar={ordRescisoes.ordenar} />
                  <ThOrdenavel label="Valor líquido" campo="valor_total" coluna={ordRescisoes.coluna} dir={ordRescisoes.dir} ordenar={ordRescisoes.ordenar} alinhar="right" />
                  <ThOrdenavel label="Status" campo="status" coluna={ordRescisoes.coluna} dir={ordRescisoes.dir} ordenar={ordRescisoes.ordenar} />
                  <th>Lançamento</th><th></th>
                </tr>
              </thead>
              <tbody>
                {ordRescisoes.linhasOrdenadas.map((r) => {
                  const expandido = expandedId === r.id;
                  return (
                    <Fragment key={r.id}>
                      <tr className="row-clickable" title="Clique para ver a discriminação das verbas" onClick={() => setExpandedId(expandido ? null : r.id)}>
                        <td style={{ fontWeight: 700 }}>
                          <span className="flex items-center gap-1">
                            {expandido ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            {r.pessoa_nome}
                          </span>
                        </td>
                        <td>{r.tipo_rescisao ? LABEL_TIPO_RESCISAO[r.tipo_rescisao] : "—"}</td>
                        <td>{r.data_desligamento ? r.data_desligamento.split("-").reverse().join("/") : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 600 }}>{formatBRL(r.valor_total)}</td>
                        <td><StatusBadgeRescisao status={r.status} /></td>
                        <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                          {r.forma_lancamento === "unico" ? "Único" : r.forma_lancamento === "detalhado" ? "Detalhado" : "—"}
                        </td>
                        <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                          <span className="flex items-center gap-2" style={{ justifyContent: "flex-end" }}>
                            {r.status === "simulacao" && (
                              <>
                                <button className="btn-ghost" title="Editar simulação" style={{ fontSize: "0.72rem" }} onClick={() => editarRascunho(r)}>
                                  <Pencil size={13} />
                                </button>
                                <button className="btn-ghost" title="Fechar rescisão" style={{ fontSize: "0.72rem" }} onClick={() => irParaFechar(r)}>
                                  Fechar
                                </button>
                                <button className="btn-ghost" title="Excluir simulação" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                                  disabled={excluindoId === r.id} onClick={() => excluir(r)}>
                                  <Trash2 size={13} />
                                </button>
                              </>
                            )}
                            {r.status === "fechada" && !r.legado && r.forma_lancamento === "unico" && (
                              <button className="btn-ghost" title="Recibo" style={{ fontSize: "0.72rem" }} onClick={() => abrirReciboUnico(r)}>
                                <Printer size={13} /> Recibo
                              </button>
                            )}
                            {r.status === "fechada" && !r.legado && r.forma_lancamento === "detalhado" && (
                              <span style={{ position: "relative" }}>
                                <button className="btn-ghost" title="Recibo detalhado" style={{ fontSize: "0.72rem" }}
                                  onClick={() => setImprimindoId(imprimindoId === r.id ? null : r.id)}>
                                  <Printer size={13} /> Recibo
                                </button>
                                {imprimindoId === r.id && (
                                  <span className="flex items-center gap-1" style={{ position: "absolute", top: "100%", right: 0, zIndex: 5, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem", whiteSpace: "nowrap" }}>
                                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportando} onClick={() => gerarReciboDetalhado(r, "pdf")}>PDF</button>
                                    <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportando} onClick={() => gerarReciboDetalhado(r, "excel")}>Excel</button>
                                  </span>
                                )}
                              </span>
                            )}
                            {r.legado && (
                              <button className="btn-ghost" title="Recibo" style={{ fontSize: "0.72rem" }} onClick={() => abrirReciboLegado(r)}>
                                <Printer size={13} /> Recibo
                              </button>
                            )}
                          </span>
                        </td>
                      </tr>
                      {expandido && (
                        <tr><td colSpan={7}>
                          <div style={{ padding: "0.6rem 0" }} onClick={(e) => e.stopPropagation()}>
                            {r.legado ? (
                              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                Rescisão lançada antes do controle de simulações — sem discriminação por verba.
                              </p>
                            ) : (
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
                            )}
                            {r.medias_variaveis_composicao?.decimo_terceiro?.aplicada && (
                              <div style={{ marginTop: "0.5rem", maxWidth: 620 }}>
                                <MediaVerbasVariaveis composicao={r.medias_variaveis_composicao.decimo_terceiro} titulo="13º proporcional" compacto />
                                <MediaVerbasVariaveis composicao={r.medias_variaveis_composicao.ferias} titulo="Férias (vencidas e proporcionais)" compacto />
                                <MediaVerbasVariaveis composicao={r.medias_variaveis_composicao.aviso_previo} titulo="Aviso prévio indenizado" compacto />
                              </div>
                            )}
                            {r.observacao && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Obs.: {r.observacao}</p>}
                          </div>
                        </td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            <div style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem" }}>
              Para dar baixa em pagamento pendente, use a aba Contas a pagar.
            </div>
          </div>
        )}
      </div>
      )}

      {reciboLinha && <ReciboModal lanc={reciboLinha} onClose={() => setReciboLinha(null)} />}
    </div>
  );
}
