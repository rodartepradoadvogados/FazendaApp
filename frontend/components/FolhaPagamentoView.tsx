"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Paperclip, Check, ChevronDown, ChevronRight, RefreshCw, Filter, Pencil, Trash2, Printer } from "lucide-react";
import {
  fetchPessoas, fetchFolhaPagamento, criarFolhaPagamento, atualizarFolhaPagamento, excluirFolhaPagamento,
  fetchFolhaPagamentoUnificada, excluirParcelaEmpreitada, excluirParcelaContrato, type LinhaFolhaUnificada,
  atualizarParcelaEmpreitada, atualizarParcelaContrato,
  fetchVales, criarVale, atualizarVale, atualizarParcelaVale, excluirVale, ehAdmin, formatBRL,
  fetchValesAvulsos, atualizarValeAvulso, excluirValeAvulso,
  fetchPreviewGuiasFgtsDctf, gerarGuiasFgtsDctf, type PreviewGuiasFgtsDctf,
  fetchContasCorrentes, type ContaCorrenteCadastro,
} from "@/lib/api";
import { ModalDivergenciaVale, ModalResultadoDivergenciaVale, ModalConfirmarDivergenciaTotal } from "@/components/ModalDivergenciaVale";
import { Modal } from "@/components/Modal";
import { ReciboModal } from "@/components/ReciboModal";
import { exportarFichaPDF, exportarMultiExcel, type SecaoFicha, type LancamentoRecibo } from "@/lib/export";
import { ModalDivididoDocumento } from "@/components/ModalDivididoDocumento";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { AvisoSalvo } from "@/components/AvisoSalvo";
import { TabBar, SecaoRecolhivel, Indicador } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { RESPONSAVEIS } from "@/lib/constants";
import EmpreitadaView from "@/components/EmpreitadaView";
import ContratoView from "@/components/ContratoView";
import DiariaView from "@/components/DiariaView";
import FeriasDecimoTerceiroView from "@/components/FeriasDecimoTerceiroView";

const LABEL_TIPO: Record<string, string> = { funcionario: "Funcionário", empreita: "Empreita", contrato: "Contrato", diaria: "Diária" };
// Fundo vinho translúcido para destacar lançamentos vencidos e não pagos.
const VENCIDO_BG = "rgba(94, 26, 46, 0.18)";

// "2026-07" → "jul/2026" (rótulo legível do mês de competência)
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const mesCompLabel = (comp: string) => {
  const [a, m] = (comp || "").split("-");
  const idx = parseInt(m, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_ABREV[idx]}/${a}` : (comp || "");
};

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <Indicador categoria="financeiro" valor={v} rotulo={l} cor={c || "var(--dourado-light)"} />;
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
  // FGTS/DCTF — opcionais, só para projeção (ver painel "Gerar guias de FGTS/DCTF").
  percentual_fgts?: number | null; valor_fgts?: number | null;
  percentual_dctf?: number | null; valor_dctf?: number | null;
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
  // FGTS/DCTF — opcionais; em branco, não entram na projeção da guia mensal.
  const [percentualFgts, setPercentualFgts] = useState("");
  const [valorFgts, setValorFgts] = useState("");
  const [fgtsManual, setFgtsManual] = useState(false);
  const [percentualDctf, setPercentualDctf] = useState("");
  const [valorDctf, setValorDctf] = useState("");
  const [dctfManual, setDctfManual] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [recorrente, setRecorrente] = useState(false);
  const [diaVencimento, setDiaVencimento] = useState("5");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [pagoErro, setPagoErro] = useState<string | null>(null);
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [anexarAberto, setAnexarAberto] = useState(false);
  const [arquivoPreview, setArquivoPreview] = useState<File | null>(null);

  const [subaba, setSubaba] = useState<"funcionario" | "empreita" | "contrato" | "diarias" | "ferias_decimo">("funcionario");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // Expansão focada de um desconto (folha ou vale) numa linha específica.
  const [expandDesc, setExpandDesc] = useState<{ id: number; tipo: "folha" | "vale" } | null>(null);
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
  const [editPercentualFgts, setEditPercentualFgts] = useState("");
  const [editValorFgts, setEditValorFgts] = useState("");
  const [editFgtsManual, setEditFgtsManual] = useState(true);
  const [editPercentualDctf, setEditPercentualDctf] = useState("");
  const [editValorDctf, setEditValorDctf] = useState("");
  const [editDctfManual, setEditDctfManual] = useState(true);
  const [editObservacao, setEditObservacao] = useState("");
  const [editRecorrente, setEditRecorrente] = useState(false);
  const [editDiaVencimento, setEditDiaVencimento] = useState("5");
  const [editSalvando, setEditSalvando] = useState(false);
  const [editMsg, setEditMsg] = useState<string | null>(null);
  const [editValorVale, setEditValorVale] = useState(0);
  const [editValorLiquidoOriginal, setEditValorLiquidoOriginal] = useState(0);
  const [confirmarDivergenciaFolha, setConfirmarDivergenciaFolha] = useState<RegistroFolha | null>(null);

  // Folha de pagamento unificada — funcionário + empreita + contrato + diária.
  const [unificada, setUnificada] = useState<LinhaFolhaUnificada[] | null>(null);
  const [erroUnificada, setErroUnificada] = useState<string | null>(null);
  const [fUniVencDe, setFUniVencDe] = useState("");
  const [fUniVencAte, setFUniVencAte] = useState("");
  const [fUniStatus, setFUniStatus] = useState<"" | "pendente" | "pago">("");
  const [fUniPessoa, setFUniPessoa] = useState("");
  const [fUniTipo, setFUniTipo] = useState<"" | "funcionario" | "empreita" | "contrato" | "diaria">("");
  const [excluindoChave, setExcluindoChave] = useState<string | null>(null);
  const [excluirErro, setExcluirErro] = useState<string | null>(null);

  // Contas correntes (id + rótulo) — para o campo "Conta bancária" dos vales,
  // que precisa gravar o id (o backend agora espera conta_corrente_id, não
  // mais o rótulo em texto usado no Financeiro).
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);

  // Relatório de vales e descontos (vale de funcionário).
  const [vales, setVales] = useState<any[] | null>(null);
  const [fValeDe, setFValeDe] = useState("");
  const [fValeAte, setFValeAte] = useState("");
  const [fValePessoa, setFValePessoa] = useState("");
  const [expandedValeId, setExpandedValeId] = useState<number | null>(null);
  const [editingValeId, setEditingValeId] = useState<number | null>(null);
  const [editValePessoaId, setEditValePessoaId] = useState("");
  const [editValeValorTotal, setEditValeValorTotal] = useState("");
  const [editValeFormaPagamento, setEditValeFormaPagamento] = useState("dinheiro");
  const [editValeDataPagamento, setEditValeDataPagamento] = useState("");
  const [editValeParcelas, setEditValeParcelas] = useState("1");
  const [editValeCompetenciaInicio, setEditValeCompetenciaInicio] = useState("");
  const [editValeObservacao, setEditValeObservacao] = useState("");
  const [editValeNumeroDocumento, setEditValeNumeroDocumento] = useState("");
  const [editValeContaCorrenteId, setEditValeContaCorrenteId] = useState("");
  const [editValeSalvando, setEditValeSalvando] = useState(false);
  const [editValeMsg, setEditValeMsg] = useState<string | null>(null);
  const [excluindoValeId, setExcluindoValeId] = useState<number | null>(null);
  const [excluirValeErro, setExcluirValeErro] = useState<string | null>(null);

  // Edição de UMA parcela de vale (dentro da linha expandida) — separado da
  // edição do vale inteiro (editingValeId acima). ModalDivergenciaVale entra
  // em cena quando o valor digitado diverge do calculado.
  const [editandoParcela, setEditandoParcela] = useState<{ valeId: number; parcelaId: number } | null>(null);
  const [editParcelaValor, setEditParcelaValor] = useState("");
  const [parcelaSalvando, setParcelaSalvando] = useState(false);
  const [parcelaErro, setParcelaErro] = useState<string | null>(null);
  const [divergenciaParcela, setDivergenciaParcela] = useState<{
    vale: any; parcela: any; valorCalculado: number; valorInformado: number;
  } | null>(null);
  const [resultadoDivergencia, setResultadoDivergencia] = useState<{ valorPago: number; valorDesconto: number } | null>(null);
  // Redistribuição livre: total (parcela editada + posteriores) diferente do
  // valor pago no vale — confirma ANTES de salvar (diferente de
  // resultadoDivergencia, que só avisa depois de já ter gravado).
  const [divergenciaTotalParcela, setDivergenciaTotalParcela] = useState<{
    vale: any; parcela: any; valoresItens: Record<number, number>; valorVale: number; valorLancado: number;
  } | null>(null);

  // Vale avulso (Empreitada/Contrato/Diária) — mesma seção de relatório, tabela própria.
  const [valesAvulsos, setValesAvulsos] = useState<any[] | null>(null);
  const [expandedValeAvulsoId, setExpandedValeAvulsoId] = useState<number | null>(null);
  const [editingValeAvulsoId, setEditingValeAvulsoId] = useState<number | null>(null);
  const [editValeAvulsoValor, setEditValeAvulsoValor] = useState("");
  const [editValeAvulsoFormaPagamento, setEditValeAvulsoFormaPagamento] = useState("dinheiro");
  const [editValeAvulsoDataPagamento, setEditValeAvulsoDataPagamento] = useState("");
  const [editValeAvulsoContaCorrenteId, setEditValeAvulsoContaCorrenteId] = useState("");
  const [editValeAvulsoObservacao, setEditValeAvulsoObservacao] = useState("");
  const [editValeAvulsoSalvando, setEditValeAvulsoSalvando] = useState(false);
  const [editValeAvulsoMsg, setEditValeAvulsoMsg] = useState<string | null>(null);
  const [excluindoValeAvulsoId, setExcluindoValeAvulsoId] = useState<number | null>(null);
  const [excluirValeAvulsoErro, setExcluirValeAvulsoErro] = useState<string | null>(null);
  const [divergenciaValeAvulso, setDivergenciaValeAvulso] = useState<{
    v: any; valorCalculado: number; valorInformado: number;
  } | null>(null);

  const carregar = () => fetchFolhaPagamento().then(setRegs).catch((e) => setError(e.message));
  const carregarUnificada = () => fetchFolhaPagamentoUnificada().then(setUnificada).catch((e) => setErroUnificada(e.message));
  const carregarVales = () => fetchVales().then(setVales).catch(() => {});
  const carregarValesAvulsos = () => fetchValesAvulsos().then(setValesAvulsos).catch(() => {});
  useEffect(() => {
    carregar(); carregarUnificada(); carregarVales(); carregarValesAvulsos();
    fetchPessoas().then(setPessoas).catch(() => {});
    fetchContasCorrentes().then(setContasCorrentes).catch(() => {});
  }, []);

  // Rótulo da conta bancária de um vale, a partir do conta_corrente_id salvo
  // — "—" tanto para vale sem conta (desconto integral/próximo pagamento)
  // quanto para uma conta que não foi encontrada na lista carregada.
  const rotuloContaVale = (contaCorrenteId: number | null | undefined) =>
    contasCorrentes.find((c) => c.id === contaCorrenteId)?.rotulo || "—";

  async function excluirLinha(linha: LinhaFolhaUnificada) {
    const chave = `${linha.tipo}-${linha.origem_subtipo}-${linha.origem_id}`;
    setExcluirErro(null);
    setExcluindoChave(chave);
    try {
      if (linha.tipo === "funcionario") await excluirFolhaPagamento(linha.origem_id);
      else if (linha.tipo === "empreita" && linha.origem_subtipo === "parcela") await excluirParcelaEmpreitada(linha.origem_id);
      else if (linha.tipo === "contrato" && linha.origem_subtipo === "parcela") await excluirParcelaContrato(linha.origem_id);
      else return;
      carregar(); carregarUnificada();
    } catch (e: any) {
      setExcluirErro(e.message || "Erro ao excluir lançamento");
    } finally {
      setExcluindoChave(null);
    }
  }

  // Editar parcela de Empreita/Contrato diretamente na Folha de pagamento
  // unificada — mesma UX de "Editar lançamento" já usada para funcionário.
  const [editingLinhaChave, setEditingLinhaChave] = useState<string | null>(null);
  const [editLinhaData, setEditLinhaData] = useState("");
  const [editLinhaValor, setEditLinhaValor] = useState("");
  const [editLinhaMsg, setEditLinhaMsg] = useState<string | null>(null);
  const [salvandoLinha, setSalvandoLinha] = useState(false);

  function podeEditarLinha(l: LinhaFolhaUnificada) {
    return l.status !== "pago" && l.origem_subtipo === "parcela" && (l.tipo === "empreita" || l.tipo === "contrato");
  }

  function iniciarEdicaoLinha(l: LinhaFolhaUnificada) {
    setEditingLinhaChave(`${l.tipo}-${l.origem_subtipo}-${l.origem_id}`);
    setEditLinhaData(l.data_vencimento || "");
    setEditLinhaValor(String(l.valor));
    setEditLinhaMsg(null);
  }

  async function salvarEdicaoLinha(l: LinhaFolhaUnificada) {
    setEditLinhaMsg(null);
    if (!editLinhaValor || parseFloat(editLinhaValor) <= 0) { setEditLinhaMsg("Informe o valor."); return; }
    setSalvandoLinha(true);
    try {
      const dados = { data_vencimento: editLinhaData, valor: parseFloat(editLinhaValor) };
      if (l.tipo === "empreita") await atualizarParcelaEmpreitada(l.origem_id, dados);
      else await atualizarParcelaContrato(l.origem_id, dados);
      setEditingLinhaChave(null);
      carregarUnificada();
    } catch (e: any) {
      setEditLinhaMsg(e.message || "Erro ao editar lançamento.");
    } finally {
      setSalvandoLinha(false);
    }
  }

  const unificadaFiltrada = useMemo(() => (unificada || []).filter((l) =>
    (!fUniVencDe || (l.data_vencimento || "") >= fUniVencDe) &&
    (!fUniVencAte || (l.data_vencimento || "") <= fUniVencAte) &&
    (!fUniStatus || l.status === fUniStatus) &&
    (!fUniPessoa || String(l.pessoa_id) === fUniPessoa) &&
    (!fUniTipo || l.tipo === fUniTipo)
  ), [unificada, fUniVencDe, fUniVencAte, fUniStatus, fUniPessoa, fUniTipo]);
  const { linhasOrdenadas: unificadaOrdenada, coluna: uniColuna, dir: uniDir, ordenar: uniOrdenar } = useOrdenacao(unificadaFiltrada);
  const somaUnificadaFiltrada = unificadaFiltrada.reduce((a, l) => a + l.valor, 0);
  const somaUniPendente = unificadaFiltrada.filter((l) => l.status === "pendente").reduce((a, l) => a + l.valor, 0);
  const somaUniPago = unificadaFiltrada.filter((l) => l.status === "pago").reduce((a, l) => a + l.valor, 0);

  const valesFiltrados = useMemo(() => (vales || []).filter((v: any) =>
    (!fValeDe || v.data_pagamento >= fValeDe) &&
    (!fValeAte || v.data_pagamento <= fValeAte) &&
    (!fValePessoa || String(v.pessoa_id) === fValePessoa)
  ).map((v: any) => {
    const parcelas: any[] = v.parcelas_detalhe || [];
    const valorParcela = parcelas.length ? parcelas[0].valor : (v.parcelas ? v.valor_total / v.parcelas : v.valor_total);
    const aplicadas = parcelas.filter((p) => p.aplicada).length;
    const valorPago = parcelas.filter((p) => p.aplicada).reduce((a, p) => a + p.valor, 0);
    return {
      ...v, valor_parcela: valorParcela, valor_pago: valorPago,
      status_desconto: aplicadas === 0 ? "Pendente" : (aplicadas === parcelas.length ? "Concluído" : `${aplicadas}/${parcelas.length} aplicadas`),
    };
  }), [vales, fValeDe, fValeAte, fValePessoa]);
  const { linhasOrdenadas: valesOrdenados, coluna: valeColuna, dir: valeDir, ordenar: valeOrdenar } = useOrdenacao(valesFiltrados);

  function iniciarEdicaoVale(v: any) {
    setEditingValeId(v.id);
    setExpandedValeId(v.id);
    setEditValePessoaId(String(v.pessoa_id));
    setEditValeValorTotal(String(v.valor_total));
    setEditValeFormaPagamento(v.forma_pagamento);
    setEditValeDataPagamento(v.data_pagamento);
    setEditValeParcelas(String(v.parcelas));
    setEditValeCompetenciaInicio(v.competencia_inicio);
    setEditValeObservacao(v.observacao || "");
    setEditValeNumeroDocumento(v.numero_documento_pagamento || "");
    setEditValeContaCorrenteId(v.conta_corrente_id ? String(v.conta_corrente_id) : "");
    setEditValeMsg(null);
  }

  async function salvarEdicaoVale(valeId: number, confirmar = false) {
    setEditValeMsg(null);
    if (!editValePessoaId) { setEditValeMsg("Selecione a pessoa."); return; }
    if (!editValeValorTotal || parseFloat(editValeValorTotal) <= 0) { setEditValeMsg("Informe o valor do vale."); return; }
    if (!editValeParcelas || Number(editValeParcelas) < 1) { setEditValeMsg("Informe ao menos 1 parcela."); return; }
    if (contaObrigatoriaVale(editValeFormaPagamento) && !editValeContaCorrenteId) {
      setEditValeMsg("Selecione a conta bancária de onde sai o vale."); return;
    }
    setEditValeSalvando(true);
    try {
      await atualizarVale(valeId, {
        pessoa_id: Number(editValePessoaId), valor_total: parseFloat(editValeValorTotal), forma_pagamento: editValeFormaPagamento,
        data_pagamento: editValeDataPagamento, parcelas: Number(editValeParcelas), competencia_inicio: editValeCompetenciaInicio,
        observacao: editValeObservacao || undefined, numero_documento_pagamento: editValeNumeroDocumento || undefined,
        conta_corrente_id: contaObrigatoriaVale(editValeFormaPagamento) && editValeContaCorrenteId ? Number(editValeContaCorrenteId) : undefined,
        confirmar,
      });
      setEditingValeId(null);
      setExpandedValeId(null);
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (R$ ${c.total.toFixed(2)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja salvar mesmo assim?`)) {
          await salvarEdicaoVale(valeId, true);
          return;
        }
      } else {
        setEditValeMsg(e.message || "Erro ao editar vale");
      }
    } finally {
      setEditValeSalvando(false);
    }
  }

  function abrirEdicaoParcela(vale: any, parcela: any) {
    setEditandoParcela({ valeId: vale.id, parcelaId: parcela.id });
    setEditParcelaValor(String(parcela.valor));
    setParcelaErro(null);
  }

  async function salvarParcela(
    vale: any, parcela: any, acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre",
    valoresItens?: Record<number, number>, confirmarDivergenciaTotal?: boolean,
  ) {
    const valor = parseFloat(editParcelaValor);
    if (isNaN(valor) || valor < 0) { setParcelaErro("Informe um valor válido."); return; }
    setParcelaSalvando(true);
    setParcelaErro(null);
    try {
      const resultado = await atualizarParcelaVale(vale.id, parcela.id, {
        valor, acao, valores_parcelas: valoresItens, confirmar: !!acao,
        confirmar_divergencia_total: !!confirmarDivergenciaTotal,
      });
      setEditandoParcela(null);
      setDivergenciaParcela(null);
      setDivergenciaTotalParcela(null);
      if (resultado.diverge_valor_pago) {
        setResultadoDivergencia({ valorPago: vale.valor_total, valorDesconto: resultado.soma_parcelas_atual });
      }
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      // Duas divergências distintas, cada uma com seu próprio popup:
      // 1) valor_vale/valor_lancado — total final (redistribuir_livre) ≠ valor pago no vale.
      // 2) valor_calculado/valor_informado — o valor desta parcela ≠ o que estava calculado.
      if (e.status === 409 && e.detail?.valor_vale !== undefined) {
        setDivergenciaTotalParcela({
          vale, parcela, valoresItens: valoresItens || {}, valorVale: e.detail.valor_vale, valorLancado: e.detail.valor_lancado,
        });
      } else if (e.status === 409 && e.detail?.diferenca !== undefined) {
        setDivergenciaParcela({
          vale, parcela, valorCalculado: e.detail.valor_calculado, valorInformado: e.detail.valor_informado,
        });
      } else {
        setParcelaErro(e.message || "Erro ao editar parcela");
      }
    } finally {
      setParcelaSalvando(false);
    }
  }

  async function excluirValeHandler(v: any) {
    if (!window.confirm("Excluir este vale? Os descontos já refletidos em folhas ainda não pagas serão revertidos.")) return;
    setExcluirValeErro(null);
    setExcluindoValeId(v.id);
    try {
      await excluirVale(v.id);
      if (expandedValeId === v.id) setExpandedValeId(null);
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      setExcluirValeErro(e.message || "Erro ao excluir vale");
    } finally {
      setExcluindoValeId(null);
    }
  }

  const valesAvulsosFiltrados = useMemo(() => (valesAvulsos || []).filter((v: any) =>
    (!fValeDe || v.data_pagamento >= fValeDe) &&
    (!fValeAte || v.data_pagamento <= fValeAte) &&
    (!fValePessoa || String(v.pessoa_id) === fValePessoa)
  ), [valesAvulsos, fValeDe, fValeAte, fValePessoa]);
  const { linhasOrdenadas: valesAvulsosOrdenados, coluna: valeAvulsoColuna, dir: valeAvulsoDir, ordenar: valeAvulsoOrdenar } = useOrdenacao(valesAvulsosFiltrados);

  function iniciarEdicaoValeAvulso(v: any) {
    setEditingValeAvulsoId(v.id);
    setExpandedValeAvulsoId(v.id);
    setEditValeAvulsoValor(String(v.valor));
    setEditValeAvulsoFormaPagamento(v.forma_pagamento);
    setEditValeAvulsoDataPagamento(v.data_pagamento);
    setEditValeAvulsoContaCorrenteId(v.conta_corrente_id ? String(v.conta_corrente_id) : "");
    setEditValeAvulsoObservacao(v.observacao || "");
    setEditValeAvulsoMsg(null);
  }

  async function salvarEdicaoValeAvulso(
    v: any, acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre", valoresItens?: Record<number, number>,
  ) {
    setEditValeAvulsoMsg(null);
    if (!editValeAvulsoValor || parseFloat(editValeAvulsoValor) <= 0) { setEditValeAvulsoMsg("Informe o valor do vale."); return; }
    if (contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && !editValeAvulsoContaCorrenteId) {
      setEditValeAvulsoMsg("Selecione a conta bancária de onde sai o vale."); return;
    }
    setEditValeAvulsoSalvando(true);
    try {
      await atualizarValeAvulso(v.id, {
        origem_tipo: v.origem_tipo, origem_id: v.origem_id, valor: parseFloat(editValeAvulsoValor),
        forma_pagamento: editValeAvulsoFormaPagamento, data_pagamento: editValeAvulsoDataPagamento,
        conta_corrente_id: contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && editValeAvulsoContaCorrenteId
          ? Number(editValeAvulsoContaCorrenteId) : undefined,
        observacao: editValeAvulsoObservacao || undefined, acao, valores_itens: valoresItens, confirmar: !!acao,
      });
      setEditingValeAvulsoId(null);
      setExpandedValeAvulsoId(null);
      setDivergenciaValeAvulso(null);
      carregarValesAvulsos(); carregarUnificada();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.diferenca !== undefined) {
        setDivergenciaValeAvulso({ v, valorCalculado: e.detail.valor_calculado, valorInformado: e.detail.valor_informado });
      } else {
        setEditValeAvulsoMsg(e.message || "Erro ao editar vale");
      }
    } finally {
      setEditValeAvulsoSalvando(false);
    }
  }

  async function excluirValeAvulsoHandler(v: any) {
    if (!window.confirm("Excluir este vale? O valor abatido da(s) parcela(s)/etapa(s) pendente(s) será revertido.")) return;
    setExcluirValeAvulsoErro(null);
    setExcluindoValeAvulsoId(v.id);
    try {
      await excluirValeAvulso(v.id);
      if (expandedValeAvulsoId === v.id) setExpandedValeAvulsoId(null);
      carregarValesAvulsos(); carregarUnificada();
    } catch (e: any) {
      setExcluirValeAvulsoErro(e.message || "Erro ao excluir vale");
    } finally {
      setExcluindoValeAvulsoId(null);
    }
  }

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
  // FGTS/DCTF — mesmo recálculo automático (percentual × bruto) do INSS/IR,
  // mas em branco por padrão: sem percentual nem edição manual, o campo
  // fica vazio e não é enviado (backend recebe None e ignora na projeção).
  useEffect(() => {
    if (fgtsManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualFgts) || 0) / 100);
    setValorFgts(novo ? String(novo) : "");
  }, [valorBruto, percentualFgts, fgtsManual]);
  useEffect(() => {
    if (dctfManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualDctf) || 0) / 100);
    setValorDctf(novo ? String(novo) : "");
  }, [valorBruto, percentualDctf, dctfManual]);
  useEffect(() => {
    if (editFgtsManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualFgts) || 0) / 100);
    setEditValorFgts(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualFgts, editFgtsManual]);
  useEffect(() => {
    if (editDctfManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualDctf) || 0) / 100);
    setEditValorDctf(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualDctf, editDctfManual]);

  const valorLiquido = useMemo(
    () => (parseFloat(valorBruto) || 0) - (parseFloat(descontos) || 0) - (parseFloat(valorInss) || 0) - (parseFloat(valorIr) || 0),
    [valorBruto, descontos, valorInss, valorIr]
  );
  const editValorLiquido = useMemo(
    () => (parseFloat(editValorBruto) || 0) - (parseFloat(editDescontos) || 0) - (parseFloat(editValorInss) || 0) - (parseFloat(editValorIr) || 0) - editValorVale,
    [editValorBruto, editDescontos, editValorInss, editValorIr, editValorVale]
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
        percentual_fgts: percentualFgts ? parseFloat(percentualFgts) : undefined,
        valor_fgts: valorFgts ? parseFloat(valorFgts) : undefined,
        percentual_dctf: percentualDctf ? parseFloat(percentualDctf) : undefined,
        valor_dctf: valorDctf ? parseFloat(valorDctf) : undefined,
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
      setPercentualFgts(""); setValorFgts(""); setFgtsManual(false);
      setPercentualDctf(""); setValorDctf(""); setDctfManual(false);
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
        percentual_fgts: r.percentual_fgts, valor_fgts: r.valor_fgts,
        percentual_dctf: r.percentual_dctf, valor_dctf: r.valor_dctf,
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
    setEditPercentualFgts(r.percentual_fgts != null ? String(r.percentual_fgts) : "");
    setEditValorFgts(r.valor_fgts != null ? String(r.valor_fgts) : "");
    setEditFgtsManual(true);
    setEditPercentualDctf(r.percentual_dctf != null ? String(r.percentual_dctf) : "");
    setEditValorDctf(r.valor_dctf != null ? String(r.valor_dctf) : "");
    setEditDctfManual(true);
    setEditObservacao(r.observacao || "");
    setEditRecorrente(r.recorrente);
    setEditDiaVencimento(r.dia_vencimento ? String(r.dia_vencimento) : "5");
    setEditValorVale(arredonda2(r.valor_vale || 0));
    setEditValorLiquidoOriginal(r.valor_liquido);
    setEditMsg(null);
  }

  function pedirSalvarEdicao(r: RegistroFolha) {
    if (Math.abs(editValorLiquido - editValorLiquidoOriginal) > 0.005) {
      setConfirmarDivergenciaFolha(r);
    } else {
      salvarEdicao(r);
    }
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
        percentual_fgts: editPercentualFgts ? parseFloat(editPercentualFgts) : undefined,
        valor_fgts: editValorFgts ? parseFloat(editValorFgts) : undefined,
        percentual_dctf: editPercentualDctf ? parseFloat(editPercentualDctf) : undefined,
        valor_dctf: editValorDctf ? parseFloat(editValorDctf) : undefined,
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

  // Índice de FolhaPagamento por id — usado para renderizar a linha rica
  // (expandir detalhe, editar, marcar como pago) dentro da folha unificada.
  const regsPorId = useMemo(() => {
    const m: Record<number, RegistroFolha> = {};
    (regs || []).forEach((r) => { m[r.id] = r; });
    return m;
  }, [regs]);

  // Imprimir holerite (folha completa do mês, todos os funcionários daquela
  // competência) — em PDF (identidade visual de relatórios) ou Excel.
  const [imprimindoHoleriteChave, setImprimindoHoleriteChave] = useState<string | null>(null);
  const [holeriteExportando, setHoleriteExportando] = useState(false);
  async function imprimirHolerites(r: RegistroFolha, formato: "pdf" | "excel") {
    setHoleriteExportando(true);
    try {
      const doMes = (regs || []).filter((x) => x.competencia === r.competencia);
      const secoes: SecaoFicha[] = doMes.map((x) => ({
        titulo: x.pessoa_nome,
        colunas: [{ header: "Item", key: "item" }, { header: "Valor", key: "valor" }],
        linhas: x.detalhe.map((d) => ({ item: d.label, valor: formatBRL(d.valor) })),
      }));
      const base = `holerite_${r.competencia}`;
      if (formato === "pdf") {
        await exportarFichaPDF("Holerite — Folha de pagamento", mesCompLabel(r.competencia), secoes, base);
      } else {
        await exportarMultiExcel("Holerite — Folha de pagamento", secoes, base);
      }
    } finally {
      setHoleriteExportando(false);
      setImprimindoHoleriteChave(null);
    }
  }

  // Imprimir recibo de pagamento (empreitada/contrato/diária) — reaproveita o
  // ReciboModal já usado no financeiro.
  const [reciboLinha, setReciboLinha] = useState<LancamentoRecibo | null>(null);

  return (
    <div>
      <TabBar
        abas={[
          { id: "funcionario" as const, label: "Funcionário" },
          { id: "empreita" as const, label: "Empreita" },
          { id: "contrato" as const, label: "Contrato" },
          { id: "diarias" as const, label: "Diárias" },
          { id: "ferias_decimo" as const, label: "Férias / 13º" },
        ]}
        ativa={subaba}
        onChange={setSubaba}
      />

      {subaba === "empreita" && <EmpreitadaView />}
      {subaba === "contrato" && <ContratoView />}
      {subaba === "diarias" && <DiariaView />}
      {subaba === "ferias_decimo" && <FeriasDecimoTerceiroView />}

      {subaba === "funcionario" && (error ? <div className="alert-critico"><span>Sem dados: {error}.</span></div> : <>
      <AvisoSalvo texto={msg?.tipo === "sucesso" ? msg.texto : null} />
      {anexarAberto && (
        <ModalDivididoDocumento title="Anexar comprovante — leitura automática (despesa)" onClose={() => { setAnexarAberto(false); setArquivoPreview(null); }} arquivo={arquivoPreview}>
          <FormFinanceiro tipo="despesa" responsaveis={RESPONSAVEIS} onArquivoParaLeitura={setArquivoPreview}
            onSalvo={(mensagem) => { setAnexarAberto(false); setArquivoPreview(null); setMsg({ tipo: "sucesso", texto: mensagem }); carregar(); carregarUnificada(); }} />
        </ModalDivididoDocumento>
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
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.5rem", marginBottom: "0.75rem" }}>
          Competência = mês trabalhado. O pagamento (conta a pagar) é lançado no dia 5 do mês seguinte
          {recorrente ? " (ou no dia escolhido abaixo)" : ""}.
        </p>
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
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.5rem", marginBottom: "0.75rem" }}>
          FGTS/DCTF (abaixo) são opcionais — deixe em branco para lançar só o pagamento do funcionário. Preenchidos,
          eles não alteram o valor líquido: servem para projetar as guias mensais consolidadas (todos os
          funcionários) em "Gerar guias de FGTS/DCTF", mais abaixo.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <CampoRetencao
            label="FGTS" percentual={percentualFgts} valor={valorFgts}
            onChangePercentual={(v) => { setPercentualFgts(v); setFgtsManual(false); }}
            onChangeValor={(v) => { setValorFgts(v); setFgtsManual(true); }}
          />
          <CampoRetencao
            label="DCTF" percentual={percentualDctf} valor={valorDctf}
            onChangePercentual={(v) => { setPercentualDctf(v); setDctfManual(false); }}
            onChangeValor={(v) => { setValorDctf(v); setDctfManual(true); }}
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
            <div><label style={labelStyleLote}>Dia de vencimento no mês seguinte (1–28)</label>
              <input type="number" min={1} max={28} style={selStyleLote} value={diaVencimento} onChange={(e) => setDiaVencimento(e.target.value)} /></div>
          )}
        </div>
        {recorrente && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
            A partir do próximo mês, o sistema gera automaticamente o lançamento de folha e a conta a pagar correspondente — não é preciso relançar manualmente.
          </p>
        )}
        {/* Sucesso já aparece no topo (AvisoSalvo) — aqui só o erro, contextual. */}
        {msg?.tipo === "erro" && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
        <button className="btn-primary" title="Salvar o lançamento de folha" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Lançar"}
        </button>
      </SecaoRecolhivel>

      {/* 2) Vale de funcionário */}
      <SecaoRecolhivel titulo="Vale de funcionário" icon={Plus} defaultAberta={false} descricao="Adiantamento pago à parte, descontado da folha">
        <ValeFuncionarioSection pessoas={pessoas} contasCorrentes={contasCorrentes} onLancado={() => { carregar(); carregarUnificada(); carregarVales(); }} />
      </SecaoRecolhivel>

      {/* 3) Guias consolidadas de FGTS/DCTF — projeção de contas a pagar somando o
          FGTS/DCTF lançado em todos os funcionários da competência escolhida. */}
      <SecaoRecolhivel
        titulo="Gerar guias de FGTS/DCTF" icon={Plus} defaultAberta={false}
        descricao="Projeta a guia mensal consolidada de FGTS e de DCTF (todos os funcionários) em Contas a Pagar"
      >
        <GerarGuiasFgtsDctfSection />
      </SecaoRecolhivel>
      </>)}

      {/* KPIs da folha de pagamento unificada (funcionário + empreita + contrato + diária), refletindo os filtros abaixo */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4 mt-4">
        <KPI v={String(unificadaFiltrada.length)} l="Lançamentos" />
        <KPI v={formatBRL(somaUniPendente)} l="Pendente" c="var(--amber)" />
        <KPI v={formatBRL(somaUniPago)} l="Pago" c="var(--green-light)" />
      </div>

      {/* Filtro da folha de pagamento unificada */}
      <div className="card mb-3">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar a folha de pagamento</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div><label style={labelStyleLote}>Vencimento — de</label>
            <input type="date" style={selStyleLote} value={fUniVencDe} onChange={(e) => setFUniVencDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — até</label>
            <input type="date" style={selStyleLote} value={fUniVencAte} onChange={(e) => setFUniVencAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Status</label>
            <select style={selStyleLote} value={fUniStatus} onChange={(e) => setFUniStatus(e.target.value as any)}>
              <option value="">Todos</option><option value="pendente">Pendente</option><option value="pago">Pago</option>
            </select></div>
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={fUniPessoa} onChange={(e) => setFUniPessoa(e.target.value)}>
              <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Tipo</label>
            <select style={selStyleLote} value={fUniTipo} onChange={(e) => setFUniTipo(e.target.value as any)}>
              <option value="">Todos</option>
              {Object.entries(LABEL_TIPO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
        </div>
      </div>

      {/* Folha de pagamento — funcionário, empreita, contrato e diária num único ledger; recolhida por
          padrão, expande ao clicar no cabeçalho. Prioriza pendências (destacando as vencidas em vinho). */}
      <SecaoRecolhivel
        titulo="Folha de pagamento" icon={Filter} defaultAberta={false}
        descricao="Clique para ver todos os lançamentos — funcionário, empreita, contrato e diária"
        badge={<span style={{ fontSize: "0.78rem", fontWeight: 700, whiteSpace: "nowrap" }}>Total filtrado: {formatBRL(somaUnificadaFiltrada)}</span>}
      >
        {erroUnificada ? <div className="alert-critico"><span>Sem dados: {erroUnificada}.</span></div> : (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Tipo" campo="tipo" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th title="Mês de pagamento (quando pago) ou de vencimento (quando pendente)">Mês</th>
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th title="Mês de referência do salário (só funcionário)">Competência</th>
              <ThOrdenavel label="Vencimento" campo="data_vencimento" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <ThOrdenavel label="Valor" campo="valor" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} alinhar="right" />
              <th style={{ textAlign: "right" }}>Descontos de folha</th>
              <th style={{ textAlign: "right" }}>Descontos de vale</th>
              <ThOrdenavel label="Status" campo="status" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th style={{ textAlign: "right" }}>Valor pago</th>
              {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              <th></th>
            </tr></thead>
            <tbody>
              {unificadaOrdenada.map((l) => {
                const chave = `${l.tipo}-${l.origem_subtipo}-${l.origem_id}`;
                if (l.tipo !== "funcionario") {
                  const editavel = podeEditarLinha(l);
                  const editandoLinha = editingLinhaChave === chave;
                  return (
                    <Fragment key={chave}>
                    <tr style={l.vencido ? { background: VENCIDO_BG } : undefined}>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{LABEL_TIPO[l.tipo]}</td>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem", whiteSpace: "nowrap" }}>
                        {(() => { const d = l.data_pagamento || l.data_vencimento; return d ? mesCompLabel(d.slice(0, 7)) : "—"; })()}
                      </td>
                      <td style={{ fontSize: "0.82rem" }}>{l.pessoa_nome}</td>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.data_vencimento ? l.data_vencimento.split("-").reverse().join("/") : "—"}{l.vencido && " ⚠"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(l.valor)}</td>
                      <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td><span style={{ fontSize: "0.72rem", fontWeight: 700, color: l.status === "pago" ? "var(--green-light)" : "var(--amber)" }}>{l.status === "pago" ? "Pago" : "Pendente"}</span></td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{l.status === "pago" ? formatBRL(l.valor) : "—"}</td>
                      {admin && <td>—</td>}
                      <td style={{ textAlign: "right" }}>
                        <span className="flex items-center gap-2" style={{ justifyContent: "flex-end" }}>
                          <button className="btn-ghost" title="Imprimir recibo de pagamento" style={{ fontSize: "0.72rem" }}
                            onClick={() => setReciboLinha({
                              numero_lancamento: `${l.tipo}-${l.origem_id}`,
                              tipo: "despesa",
                              fornecedor: l.pessoa_nome,
                              descricao: l.descricao,
                              valor: l.valor,
                              data_pagamento: l.data_pagamento,
                              data_vencimento: l.data_vencimento,
                            })}>
                            <Printer size={13} />
                          </button>
                          {editavel && (
                            <button className="btn-ghost" title="Editar este lançamento (enquanto não estiver pago)" style={{ fontSize: "0.72rem" }}
                              onClick={() => (editandoLinha ? setEditingLinhaChave(null) : iniciarEdicaoLinha(l))}>
                              <Pencil size={13} />
                            </button>
                          )}
                          {l.pode_excluir && (
                            <button className="btn-ghost" title="Excluir este lançamento pendente" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                              disabled={excluindoChave === chave}
                              onClick={() => { if (window.confirm("Excluir este lançamento de folha pendente?")) excluirLinha(l); }}>
                              <Trash2 size={13} />
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                    {editandoLinha && (
                      <tr>
                        <td colSpan={admin ? 12 : 11} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
                            <div><label style={labelStyleLote}>Vencimento</label>
                              <input type="date" style={selStyleLote} value={editLinhaData} onChange={(e) => setEditLinhaData(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Valor (R$)</label>
                              <input type="number" inputMode="decimal" style={selStyleLote} value={editLinhaValor} onChange={(e) => setEditLinhaValor(e.target.value)} /></div>
                          </div>
                          {editLinhaMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editLinhaMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={salvandoLinha} onClick={() => salvarEdicaoLinha(l)}>
                              <Check size={14} /> {salvandoLinha ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => setEditingLinhaChave(null)}>Cancelar</button>
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                }
                const r = regsPorId[l.origem_id];
                if (!r) return null;
                const expandido = expandedId === r.id;
                const editando = editingId === r.id;
                const descFolha = arredonda2(r.descontos + r.valor_inss + r.valor_ir);
                const descVale = arredonda2(r.valor_vale || 0);
                const descAberto = expandDesc && expandDesc.id === r.id;
                const valeLinhas = r.detalhe.filter((d) => /vale/i.test(d.label));
                return (
                  <Fragment key={chave}>
                    <tr className="row-clickable" title="Clique para ver a discriminação deste lançamento de folha" onClick={() => setExpandedId(expandido ? null : r.id)}
                      style={l.vencido ? { background: VENCIDO_BG } : undefined}>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{LABEL_TIPO.funcionario}</td>
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
                      <td style={{ fontSize: "0.78rem" }}>{r.data_vencimento ? r.data_vencimento.split("-").reverse().join("/") : "—"}{l.vencido && " ⚠"}</td>
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
                        <span className="flex items-center gap-2" style={{ justifyContent: "flex-end" }}>
                          <span style={{ position: "relative" }}>
                            <button className="btn-ghost" title="Imprimir holerite da folha completa deste mês" style={{ fontSize: "0.72rem" }}
                              onClick={() => setImprimindoHoleriteChave(imprimindoHoleriteChave === chave ? null : chave)}>
                              <Printer size={13} />
                            </button>
                            {imprimindoHoleriteChave === chave && (
                              <span className="flex items-center gap-1" style={{ position: "absolute", top: "100%", right: 0, zIndex: 5, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem", whiteSpace: "nowrap" }}>
                                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginRight: "0.2rem" }}>Formato:</span>
                                <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHolerites(r, "pdf")}>PDF</button>
                                <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHolerites(r, "excel")}>Excel</button>
                              </span>
                            )}
                          </span>
                          {r.status === "pendente" && (
                            <>
                              <button className="btn-ghost" title="Registrar o pagamento deste lançamento de folha" style={{ fontSize: "0.72rem" }} onClick={() => { setPagoErro(null); setPagandoId(pagandoId === r.id ? null : r.id); }}>Marcar como pago</button>
                              <button className="btn-ghost" title="Excluir este lançamento pendente" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                                disabled={excluindoChave === chave}
                                onClick={() => { if (window.confirm("Excluir este lançamento de folha pendente?")) excluirLinha(l); }}>
                                <Trash2 size={13} />
                              </button>
                            </>
                          )}
                        </span>
                      </td>
                    </tr>
                    {descAberto && (
                      <tr><td colSpan={admin ? 12 : 11}>
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
                      <tr><td colSpan={admin ? 12 : 11}>
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
                      <tr><td colSpan={admin ? 12 : 11}>
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
                      <tr><td colSpan={admin ? 12 : 11}>
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
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <CampoRetencao
                              label="FGTS" percentual={editPercentualFgts} valor={editValorFgts}
                              onChangePercentual={(v) => { setEditPercentualFgts(v); setEditFgtsManual(false); }}
                              onChangeValor={(v) => { setEditValorFgts(v); setEditFgtsManual(true); }}
                            />
                            <CampoRetencao
                              label="DCTF" percentual={editPercentualDctf} valor={editValorDctf}
                              onChangePercentual={(v) => { setEditPercentualDctf(v); setEditDctfManual(false); }}
                              onChangeValor={(v) => { setEditValorDctf(v); setEditDctfManual(true); }}
                            />
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editObservacao} onChange={(e) => setEditObservacao(e.target.value)} /></div>
                            <div className="flex items-end"><span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Valor líquido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(editValorLiquido)}</strong></span></div>
                          </div>
                          {editValorVale > 0 && (
                            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                              Desconto de vale (já incluído acima): <strong>{formatBRL(editValorVale)}</strong> — para ajustar o valor do vale, edite-o em "Relatório de vales e descontos".
                            </p>
                          )}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
                            <div className="flex items-center gap-2" style={{ paddingBottom: "0.4rem" }}>
                              <input id="folha-edit-recorrente" type="checkbox" checked={editRecorrente} onChange={(e) => setEditRecorrente(e.target.checked)} />
                              <label htmlFor="folha-edit-recorrente" style={{ fontSize: "0.8rem" }}>Recorrente</label>
                            </div>
                            {editRecorrente && (
                              <div><label style={labelStyleLote}>Dia de vencimento no mês seguinte (1–28)</label>
                                <input type="number" min={1} max={28} style={selStyleLote} value={editDiaVencimento} onChange={(e) => setEditDiaVencimento(e.target.value)} /></div>
                            )}
                          </div>
                          {editMsg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{editMsg}</p>}
                          <div className="flex items-center gap-2">
                            <button className="btn-primary" title="Salvar as alterações deste lançamento" style={{ fontSize: "0.78rem" }} onClick={() => pedirSalvarEdicao(r)} disabled={editSalvando}>
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
              {excluirErro && <tr><td colSpan={admin ? 12 : 11} style={{ color: "var(--red)", fontSize: "0.8rem" }}>{excluirErro}</td></tr>}
              {unificada && !unificadaOrdenada.length && <tr><td colSpan={admin ? 12 : 11} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{unificada.length ? "Nenhum lançamento de folha para os filtros escolhidos." : "Nenhum lançamento de folha ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
        )}
      </SecaoRecolhivel>

      {/* Relatório de vales e descontos — vale de funcionário, filtrável e ordenável */}
      <SecaoRecolhivel titulo="Relatório de vales e descontos" icon={Filter} defaultAberta={false} descricao="Vales de funcionário lançados, com parcelamento e status de aplicação">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Data do vale — de</label>
            <input type="date" style={selStyleLote} value={fValeDe} onChange={(e) => setFValeDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Data do vale — até</label>
            <input type="date" style={selStyleLote} value={fValeAte} onChange={(e) => setFValeAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={fValePessoa} onChange={(e) => setFValePessoa(e.target.value)}>
              <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
        </div>
        {excluirValeErro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{excluirValeErro}</p>}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th style={{ width: "1.5rem" }} />
              <ThOrdenavel label="Data" campo="data_pagamento" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Valor bruto" campo="valor_total" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Nº parcelas" campo="parcelas" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Valor da parcela" campo="valor_parcela" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Status" campo="status_desconto" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Valor pago" campo="valor_pago" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <th>Documento</th>
              <th>Conta bancária</th>
              <th>Ações</th>
            </tr></thead>
            <tbody>
              {valesOrdenados.map((v: any) => (
                <Fragment key={v.id}>
                <tr style={{ cursor: "pointer" }} onClick={() => setExpandedValeId(expandedValeId === v.id ? null : v.id)}>
                  <td>{expandedValeId === v.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                  <td style={{ fontSize: "0.78rem" }}>{v.data_pagamento ? v.data_pagamento.split("-").reverse().join("/") : "—"}</td>
                  <td style={{ fontSize: "0.82rem" }}>{v.pessoa_nome}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(v.valor_total)}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{v.parcelas}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(v.valor_parcela)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{v.status_desconto}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(v.valor_pago)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{v.numero_documento_pagamento || "—"}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{rotuloContaVale(v.conta_corrente_id)}</td>
                  <td>
                    <button className="btn-ghost" title="Excluir este vale" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                      disabled={excluindoValeId === v.id}
                      onClick={(e) => { e.stopPropagation(); excluirValeHandler(v); }}>
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
                {expandedValeId === v.id && (
                  <tr>
                    <td colSpan={11} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                      {editingValeId === v.id ? (
                        <div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Pessoa</label>
                              <select style={selStyleLote} value={editValePessoaId} onChange={(e) => setEditValePessoaId(e.target.value)}>
                                {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Valor total (R$)</label>
                              <input type="number" inputMode="decimal" style={selStyleLote} value={editValeValorTotal} onChange={(e) => setEditValeValorTotal(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Forma de pagamento</label>
                              <select style={selStyleLote} value={editValeFormaPagamento} onChange={(e) => setEditValeFormaPagamento(e.target.value)}>
                                {FORMAS_VALE.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Data do pagamento</label>
                              <input type="date" style={selStyleLote} value={editValeDataPagamento} onChange={(e) => setEditValeDataPagamento(e.target.value)} /></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Parcelas do desconto</label>
                              <input type="number" min={1} style={selStyleLote} value={editValeParcelas} onChange={(e) => setEditValeParcelas(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Data do primeiro desconto</label>
                              <input type="month" style={selStyleLote} value={editValeCompetenciaInicio} onChange={(e) => setEditValeCompetenciaInicio(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Nº do documento do pagamento</label>
                              <input style={selStyleLote} value={editValeNumeroDocumento} onChange={(e) => setEditValeNumeroDocumento(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editValeObservacao} onChange={(e) => setEditValeObservacao(e.target.value)} /></div>
                          </div>
                          {contaObrigatoriaVale(editValeFormaPagamento) && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                              <div><label style={labelStyleLote}>Conta bancária</label>
                                <select style={selStyleLote} value={editValeContaCorrenteId} onChange={(e) => setEditValeContaCorrenteId(e.target.value)}>
                                  <option value="">Selecione…</option>
                                  {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                                </select></div>
                            </div>
                          )}
                          {editValeMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editValeMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={editValeSalvando} onClick={() => salvarEdicaoVale(v.id)}>
                              <Check size={14} /> {editValeSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => { setEditingValeId(null); setExpandedValeId(null); }}>Cancelar</button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <table className="fazenda-table" style={{ marginBottom: "0.6rem" }}>
                            <thead><tr><th>Nº parcela</th><th>Competência</th><th style={{ textAlign: "right" }}>Valor</th><th>Situação</th><th></th></tr></thead>
                            <tbody>
                              {(v.parcelas_detalhe || []).map((p: any, i: number) => (
                                <tr key={p.id}>
                                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{i + 1}/{(v.parcelas_detalhe || []).length}</td>
                                  <td style={{ fontSize: "0.78rem" }}>{mesCompLabel(p.competencia)}</td>
                                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>
                                    {editandoParcela?.parcelaId === p.id ? (
                                      <input type="number" inputMode="decimal" autoFocus
                                        style={{ ...selStyleLote, width: "7rem", textAlign: "right", display: "inline-block" }}
                                        value={editParcelaValor} onChange={(e) => setEditParcelaValor(e.target.value)} />
                                    ) : formatBRL(p.valor)}
                                  </td>
                                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{p.aplicada ? "Aplicada na folha" : "Pendente"}</td>
                                  <td>
                                    {editandoParcela?.parcelaId === p.id ? (
                                      <div style={{ display: "flex", gap: "0.3rem" }}>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} disabled={parcelaSalvando}
                                          onClick={() => salvarParcela(v, p)}>
                                          <Check size={13} /> {parcelaSalvando ? "Salvando…" : "Salvar"}
                                        </button>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                                          onClick={() => { setEditandoParcela(null); setParcelaErro(null); }}>Cancelar</button>
                                      </div>
                                    ) : (
                                      <button className="btn-ghost" title="Editar esta parcela" style={{ fontSize: "0.72rem" }}
                                        onClick={() => abrirEdicaoParcela(v, p)}>
                                        <Pencil size={12} />
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {parcelaErro && editandoParcela?.valeId === v.id && (
                            <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{parcelaErro}</p>
                          )}
                          {v.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Observação: {v.observacao}</p>}
                          <button className="btn-ghost" onClick={() => iniciarEdicaoVale(v)}>
                            <Pencil size={12} /> Editar vale
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
              {vales && !valesOrdenados.length && <tr><td colSpan={11} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{vales.length ? "Nenhum vale para os filtros escolhidos." : "Nenhum vale lançado ainda."}</td></tr>}
            </tbody>
          </table>
        </div>

        <p style={{ fontSize: "0.82rem", fontWeight: 600, margin: "1.25rem 0 0.5rem" }}>Vales de empreitada, contrato e diária</p>
        {excluirValeAvulsoErro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{excluirValeAvulsoErro}</p>}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th style={{ width: "1.5rem" }} />
              <ThOrdenavel label="Data" campo="data_pagamento" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <ThOrdenavel label="Origem" campo="origem_descricao" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <th>Parcela</th>
              <ThOrdenavel label="Valor" campo="valor" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} alinhar="right" />
              <ThOrdenavel label="Forma de pagamento" campo="forma_pagamento" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <th>Conta bancária</th>
              <th>Ações</th>
            </tr></thead>
            <tbody>
              {valesAvulsosOrdenados.map((v: any) => (
                <Fragment key={v.id}>
                <tr style={{ cursor: "pointer" }} onClick={() => setExpandedValeAvulsoId(expandedValeAvulsoId === v.id ? null : v.id)}>
                  <td>{expandedValeAvulsoId === v.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                  <td style={{ fontSize: "0.78rem" }}>{v.data_pagamento ? v.data_pagamento.split("-").reverse().join("/") : "—"}</td>
                  <td style={{ fontSize: "0.82rem" }}>{v.pessoa_nome}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{v.origem_descricao}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                    {v.total_parcelas_origem
                      ? (v.parcelas_referenciadas || []).map((r: any) => r.numero_parcela).filter(Boolean).join(", ") || "—"
                      : "—"}
                    {v.total_parcelas_origem ? ` de ${v.total_parcelas_origem}` : ""}
                  </td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(v.valor)}</td>
                  <td style={{ fontSize: "0.78rem" }}>{FORMAS_VALE_AVULSO.find((f) => f.value === v.forma_pagamento)?.label || v.forma_pagamento}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{rotuloContaVale(v.conta_corrente_id)}</td>
                  <td>
                    <button className="btn-ghost" title="Excluir este vale" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                      disabled={excluindoValeAvulsoId === v.id}
                      onClick={(e) => { e.stopPropagation(); excluirValeAvulsoHandler(v); }}>
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
                {expandedValeAvulsoId === v.id && (
                  <tr>
                    <td colSpan={9} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                      {editingValeAvulsoId === v.id ? (
                        <div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Origem</label>
                              <input style={selStyleLote} value={v.origem_descricao} disabled /></div>
                            <div><label style={labelStyleLote}>Valor (R$)</label>
                              <input type="number" inputMode="decimal" style={selStyleLote} value={editValeAvulsoValor} onChange={(e) => setEditValeAvulsoValor(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Forma de pagamento</label>
                              <select style={selStyleLote} value={editValeAvulsoFormaPagamento} onChange={(e) => setEditValeAvulsoFormaPagamento(e.target.value)}>
                                {FORMAS_VALE_AVULSO.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Data do pagamento</label>
                              <input type="date" style={selStyleLote} value={editValeAvulsoDataPagamento} onChange={(e) => setEditValeAvulsoDataPagamento(e.target.value)} /></div>
                          </div>
                          {contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                              <div><label style={labelStyleLote}>Conta bancária</label>
                                <select style={selStyleLote} value={editValeAvulsoContaCorrenteId} onChange={(e) => setEditValeAvulsoContaCorrenteId(e.target.value)}>
                                  <option value="">Selecione…</option>
                                  {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                                </select></div>
                            </div>
                          )}
                          <div className="grid grid-cols-1 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editValeAvulsoObservacao} onChange={(e) => setEditValeAvulsoObservacao(e.target.value)} /></div>
                          </div>
                          {editValeAvulsoMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editValeAvulsoMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={editValeAvulsoSalvando} onClick={() => salvarEdicaoValeAvulso(v)}>
                              <Check size={14} /> {editValeAvulsoSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => { setEditingValeAvulsoId(null); setExpandedValeAvulsoId(null); }}>Cancelar</button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          {v.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Observação: {v.observacao}</p>}
                          <button className="btn-ghost" onClick={() => iniciarEdicaoValeAvulso(v)}>
                            <Pencil size={12} /> Editar vale
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
              {valesAvulsos && !valesAvulsosOrdenados.length && <tr><td colSpan={9} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{valesAvulsos.length ? "Nenhum vale para os filtros escolhidos." : "Nenhum vale de empreitada/contrato/diária lançado ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
      </SecaoRecolhivel>

      {divergenciaParcela && (
        <ModalDivergenciaVale
          valorCalculado={divergenciaParcela.valorCalculado}
          valorInformado={divergenciaParcela.valorInformado}
          itensPendentes={(divergenciaParcela.vale.parcelas_detalhe || [])
            // Só as parcelas POSTERIORES à editada entram na redistribuição —
            // nunca mexe em parcela anterior/já vencida (mesma regra do backend).
            .filter((p: any) => p.id !== divergenciaParcela.parcela.id && !p.aplicada && p.competencia > divergenciaParcela.parcela.competencia)
            .map((p: any) => ({ id: p.id, label: mesCompLabel(p.competencia), valor: p.valor }))}
          salvando={parcelaSalvando}
          onCancelar={() => setDivergenciaParcela(null)}
          onConfirmar={(acao, valoresItens) => salvarParcela(divergenciaParcela.vale, divergenciaParcela.parcela, acao, valoresItens)}
        />
      )}
      {divergenciaTotalParcela && (
        <ModalConfirmarDivergenciaTotal
          valorVale={divergenciaTotalParcela.valorVale}
          valorLancado={divergenciaTotalParcela.valorLancado}
          salvando={parcelaSalvando}
          onCancelar={() => setDivergenciaTotalParcela(null)}
          onConfirmar={() => salvarParcela(
            divergenciaTotalParcela.vale, divergenciaTotalParcela.parcela, "redistribuir_livre",
            divergenciaTotalParcela.valoresItens, true,
          )}
        />
      )}
      {divergenciaValeAvulso && (
        <ModalDivergenciaVale
          valorCalculado={divergenciaValeAvulso.valorCalculado}
          valorInformado={divergenciaValeAvulso.valorInformado}
          itensPendentes={[]}
          permiteRedistribuir={divergenciaValeAvulso.v.origem_tipo !== "diaria"}
          salvando={editValeAvulsoSalvando}
          onCancelar={() => setDivergenciaValeAvulso(null)}
          onConfirmar={(acao) => salvarEdicaoValeAvulso(divergenciaValeAvulso.v, acao)}
        />
      )}
      {confirmarDivergenciaFolha && (
        <Modal title="Valor líquido diferente do lançado" onClose={() => setConfirmarDivergenciaFolha(null)} width="440px">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
            <p>O valor líquido editado é diferente do que estava lançado. Confirma a alteração ou volta para editar?</p>
            <p>Valor líquido anterior: <b>{formatBRL(editValorLiquidoOriginal)}</b></p>
            <p>Valor líquido novo: <b>{formatBRL(editValorLiquido)}</b></p>
            <p>Diferença: <b style={{ color: editValorLiquido - editValorLiquidoOriginal >= 0 ? "var(--green-light)" : "var(--red)" }}>
              {formatBRL(editValorLiquido - editValorLiquidoOriginal)}
            </b></p>
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.3rem" }}>
              <button className="btn-primary" disabled={editSalvando}
                onClick={() => { const r = confirmarDivergenciaFolha; setConfirmarDivergenciaFolha(null); salvarEdicao(r); }}>
                <Check size={14} /> {editSalvando ? "Salvando…" : "Confirmar valor diferente"}
              </button>
              <button className="btn-ghost" onClick={() => setConfirmarDivergenciaFolha(null)}>Voltar ao lançamento</button>
            </div>
          </div>
        </Modal>
      )}
      {reciboLinha && <ReciboModal lanc={reciboLinha} onClose={() => setReciboLinha(null)} />}
      {resultadoDivergencia && (
        <ModalResultadoDivergenciaVale
          valorPago={resultadoDivergencia.valorPago}
          valorDesconto={resultadoDivergencia.valorDesconto}
          onFechar={() => setResultadoDivergencia(null)}
        />
      )}
    </div>
  );
}

const FORMAS_VALE = [
  { value: "dinheiro", label: "Dinheiro" }, { value: "pix", label: "Pix" },
  { value: "transferencia", label: "Transferência" }, { value: "desconto_integral_folha", label: "Desconto integral na próxima folha" },
];

const FORMAS_VALE_AVULSO = [
  { value: "dinheiro", label: "Dinheiro" }, { value: "pix", label: "Pix" },
  { value: "transferencia", label: "Transferência" }, { value: "desconto_proximo_pagamento", label: "Descontar do próximo pagamento" },
];

// Espelha `_validar_conta_vale`/`_validar_conta_vale_avulso` (backend): a
// conta bancária só é obrigatória quando o dinheiro sai AGORA (dinheiro/pix/
// transferência) — "desconto_integral_folha"/"desconto_proximo_pagamento" não
// movimentam banco nenhum na hora do vale.
const contaObrigatoriaVale = (forma: string) => forma !== "desconto_integral_folha";
const contaObrigatoriaValeAvulso = (forma: string) => forma !== "desconto_proximo_pagamento";

/**
 * Vale de funcionário — só o formulário de lançamento. A lista de parcelas
 * geradas não aparece mais aqui: ela vira a expansão da folha listada (na
 * competência em que a parcela é aplicada), por decisão explícita do
 * usuário — ver `_detalhe_folha` no backend.
 */
function ValeFuncionarioSection({
  pessoas, contasCorrentes, onLancado,
}: { pessoas: PessoaFolha[]; contasCorrentes: ContaCorrenteCadastro[]; onLancado: () => void }) {
  const [pessoaId, setPessoaId] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("dinheiro");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState("1");
  const [competenciaInicio, setCompetenciaInicio] = useState(() => new Date().toISOString().slice(0, 7));
  const [observacao, setObservacao] = useState("");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  async function lancar(confirmar = false) {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!valorTotal || parseFloat(valorTotal) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor do vale." }); return; }
    if (!parcelas || Number(parcelas) < 1) { setMsg({ tipo: "erro", texto: "Informe ao menos 1 parcela." }); return; }
    if (contaObrigatoriaVale(formaPagamento) && !contaCorrenteId) {
      setMsg({ tipo: "erro", texto: "Selecione a conta bancária de onde sai o vale." }); return;
    }
    setSalvando(true);
    try {
      await criarVale({
        pessoa_id: Number(pessoaId), valor_total: parseFloat(valorTotal), forma_pagamento: formaPagamento,
        data_pagamento: dataPagamento, parcelas: Number(parcelas), competencia_inicio: competenciaInicio,
        observacao: observacao || undefined, numero_documento_pagamento: numeroDocumentoPagamento || undefined,
        conta_corrente_id: contaObrigatoriaVale(formaPagamento) && contaCorrenteId ? Number(contaCorrenteId) : undefined,
        confirmar,
      });
      setMsg({ tipo: "sucesso", texto: "Vale lançado — o desconto aparecerá na expansão da folha de cada competência afetada." });
      setPessoaId(""); setValorTotal(""); setParcelas("1"); setObservacao(""); setNumeroDocumentoPagamento(""); setContaCorrenteId("");
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
        <div><label style={labelStyleLote}>Data do primeiro desconto</label>
          <input type="month" style={selStyleLote} value={competenciaInicio} onChange={(e) => setCompetenciaInicio(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Nº do documento do pagamento</label>
          <input style={selStyleLote} title="Para controle de extrato" value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Observação</label>
          <input style={selStyleLote} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      </div>
      {contaObrigatoriaVale(formaPagamento) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Conta bancária</label>
            <select style={selStyleLote} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
              <option value="">Selecione…</option>
              {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
            </select></div>
        </div>
      )}
      {msg?.tipo === "erro" ? (
        <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
      ) : (
        <AvisoSalvo texto={msg?.texto ?? null} aviso2="Pronto para lançar outro vale." />
      )}
      <button className="btn-primary" title="Lançar o vale" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={() => lancar(false)} disabled={salvando}>
        <Check size={14} /> {salvando ? "Salvando…" : "Lançar vale"}
      </button>
    </div>
  );
}

/*
 * Guias consolidadas de FGTS/DCTF — só PROJEÇÃO interna de fluxo de caixa:
 * soma o valor_fgts/valor_dctf de TODOS os lançamentos de folha de uma
 * competência e cria duas contas a pagar (Guia FGTS / Guia DCTF), com
 * vencimento no dia 20 do mês seguinte (editável, assim como o valor). Sem
 * fórmula legal real de FGTS/DCTF e sem qualquer integração com sistemas do
 * governo — os valores vêm só do que o usuário/contador lançou na folha.
 * Mostra a soma calculada ANTES de confirmar, e permite ajustar valor/
 * vencimento na hora (o backend também aceita reajuste depois, pela edição
 * normal em Contas a Pagar).
 */
function GerarGuiasFgtsDctfSection() {
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [preview, setPreview] = useState<PreviewGuiasFgtsDctf | null>(null);
  const [valorFgts, setValorFgts] = useState("");
  const [valorDctf, setValorDctf] = useState("");
  const [dataVencimento, setDataVencimento] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [gerando, setGerando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  async function calcularProjecao() {
    setMsg(null);
    setPreview(null);
    if (!competencia) { setMsg({ tipo: "erro", texto: "Informe a competência." }); return; }
    setBuscando(true);
    try {
      const p = await fetchPreviewGuiasFgtsDctf(competencia);
      setPreview(p);
      setValorFgts(String(p.valor_fgts));
      setValorDctf(String(p.valor_dctf));
      setDataVencimento(p.data_vencimento_sugerida);
      if (p.quantidade_lancamentos === 0) {
        setMsg({ tipo: "erro", texto: "Nenhum lançamento de folha encontrado para essa competência." });
      } else if (p.ja_gerado) {
        setMsg({ tipo: "erro", texto: "As guias dessa competência já foram geradas — edite os lançamentos existentes em Contas a Pagar em vez de gerar de novo." });
      }
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao calcular a projeção" });
    } finally {
      setBuscando(false);
    }
  }

  async function confirmarGeracao() {
    if (!preview) return;
    setMsg(null);
    setGerando(true);
    try {
      await gerarGuiasFgtsDctf({
        competencia,
        valor_fgts: valorFgts ? parseFloat(valorFgts) : undefined,
        valor_dctf: valorDctf ? parseFloat(valorDctf) : undefined,
        data_vencimento: dataVencimento || undefined,
      });
      setMsg({ tipo: "sucesso", texto: "Guias de FGTS e DCTF criadas em Contas a Pagar — valor e vencimento continuam editáveis por lá." });
      setPreview(null);
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao gerar as guias" });
    } finally {
      setGerando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Soma o FGTS e o DCTF lançados (opcionalmente) em CADA lançamento de folha da competência escolhida e cria
        duas contas a pagar — "Guia FGTS" e "Guia DCTF" — com vencimento sugerido no dia 20 do mês seguinte. É só
        uma projeção para o fluxo de caixa: ajuste o valor/vencimento antes de confirmar (ou depois, em Contas a
        Pagar). Só é possível gerar uma vez por competência.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
        <div><label style={labelStyleLote}>Competência (mês)</label>
          <input type="month" style={selStyleLote} value={competencia} onChange={(e) => { setCompetencia(e.target.value); setPreview(null); setMsg(null); }} /></div>
        <button className="btn-ghost" title="Calcular a soma projetada de FGTS/DCTF dessa competência" style={{ fontSize: "0.8rem" }} onClick={calcularProjecao} disabled={buscando}>
          <RefreshCw size={13} /> {buscando ? "Calculando…" : "Calcular projeção"}
        </button>
      </div>

      {preview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Guia FGTS projetada (R$) — {preview.quantidade_lancamentos} lançamento(s)</label>
            <input type="number" inputMode="decimal" style={selStyleLote} value={valorFgts} onChange={(e) => setValorFgts(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Guia DCTF projetada (R$) — {preview.quantidade_lancamentos} lançamento(s)</label>
            <input type="number" inputMode="decimal" style={selStyleLote} value={valorDctf} onChange={(e) => setValorDctf(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento das guias</label>
            <input type="date" style={selStyleLote} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} /></div>
        </div>
      )}

      {msg?.tipo === "erro" ? (
        <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
      ) : (
        <AvisoSalvo texto={msg?.texto ?? null} aviso2="Pronto para gerar guias de outra competência." />
      )}

      {preview && !preview.ja_gerado && preview.quantidade_lancamentos > 0 && (
        <button className="btn-primary" title="Criar as duas contas a pagar (Guia FGTS e Guia DCTF)" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={confirmarGeracao} disabled={gerando}>
          <Check size={14} /> {gerando ? "Gerando…" : "Gerar guias de FGTS/DCTF"}
        </button>
      )}
    </div>
  );
}
