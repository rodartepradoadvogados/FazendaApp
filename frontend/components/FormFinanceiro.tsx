"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Upload, FileText, X, Check, AlertTriangle, Loader2, Plus, Trash2, Camera } from "lucide-react";
import {
  fetchOpcoesFinanceiro, fetchEstoque, fetchServicosCadastro, fetchFornecedores, fetchPlanoContas, criarLancamentoFinanceiro, importarXmlFinanceiro,
  lerDocumentoFinanceiro, formatBRL, fetchPedidos, fetchPossiveisDuplicados, anexarArquivoLancamento, type LancamentoParecido,
  fetchCandidatosVinculoSanitarioReprodutivo, vincularEventoSanitarioReprodutivo, type CandidatoVinculoSanitarioReprodutivo,
  FINALIDADES_ESTOQUE,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovaContaGerencial from "@/components/NovaContaGerencial";
import NovoServicoRapido from "@/components/NovoServicoRapido";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import type { ContaPlano } from "@/lib/contaGerencial";
import { onPedidoLancamentoFinanceiro } from "@/lib/estoqueFinanceiroBridge";
import { onPedidoLancamentoFinanceiroDeEvento, type OrigemVinculoSanitarioReprodutivo } from "@/lib/vinculoSanitarioFinanceiroBridge";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

type Parcela = {
  data_vencimento: string; valor: string; numero_boleto?: string;
  // Baixa da parcela já dentro do lançamento parcelado (item 3) — opcional,
  // uma parcela sem `pago` nasce em aberto, como sempre.
  pago?: boolean;
  data_pagamento?: string;
  valor_pago?: string;
  conta_bancaria?: string;
  forma_pagamento?: string;
  numero_documento_pagamento?: string;
};
type TipoItem = "produto" | "servico";
type ModoValor = "unitario" | "total";
type Item = {
  codigo_conta_gerencial: string; nome_conta_gerencial: string;
  tipo_item: TipoItem; produto: string; descricao: string;
  quantidade: string; valor_unitario: string; valor_total: string; modoValor: ModoValor;
};
const itemVazio = (): Item => ({
  codigo_conta_gerencial: "", nome_conta_gerencial: "", tipo_item: "produto", produto: "", descricao: "",
  quantidade: "", valor_unitario: "", valor_total: "", modoValor: "unitario",
});

type Opcoes = {
  contas_gerenciais: { codigo: string; nome: string }[];
  centros_custo: string[];
  fornecedores: string[];
  produtos: string[];
  contas_bancarias: string[];
  tipos_documento: string[];
  formas_pagamento: string[];
};

const OPCOES_VAZIAS: Opcoes = { contas_gerenciais: [], centros_custo: [], fornecedores: [], produtos: [], contas_bancarias: [], tipos_documento: [], formas_pagamento: [] };

function dividirParcelas(valorTotal: number, qtd: number, primeiraData: string): Parcela[] {
  if (qtd <= 0) return [];
  const base = Math.floor((valorTotal / qtd) * 100) / 100;
  const resto = Math.round((valorTotal - base * qtd) * 100) / 100;
  const inicio = primeiraData ? new Date(primeiraData + "T00:00:00") : new Date();
  return Array.from({ length: qtd }, (_, i) => {
    const d = new Date(inicio); d.setMonth(d.getMonth() + i);
    const valor = i === qtd - 1 ? base + resto : base;
    return { data_vencimento: d.toISOString().slice(0, 10), valor: valor.toFixed(2) };
  });
}

/**
 * Lançamento financeiro completo: vários produtos/serviços por nota, desconto
 * e/ou acréscimo sobre o total, parcelamento, conta bancária, documento e
 * importação de XML (reconhece múltiplos itens e as parcelas da NF-e).
 */
export function FormFinanceiro({ tipo, responsaveis, onSujo, onSalvo, onArquivoParaLeitura }: {
  tipo: "despesa" | "receita"; responsaveis: string[]; onSujo?: (sujo: boolean) => void;
  // Recebe a mesma mensagem de sucesso mostrada dentro do formulário — o pai
  // (contas a pagar/receber) reaproveita pra mostrar a confirmação no topo da
  // tela depois que o modal fecha (ver AvisoSalvo em app/financeiro/page.tsx).
  onSalvo?: (mensagem: string) => void;
  // Avisa o pai assim que um PDF/JPEG/PNG é escolhido pra leitura automática —
  // usado pelo ModalDivididoDocumento pra mostrar a prévia do documento ao
  // lado do formulário (ver app/financeiro/page.tsx).
  onArquivoParaLeitura?: (file: File) => void;
}) {
  const [opcoes, setOpcoes] = useState<Opcoes>(OPCOES_VAZIAS);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const carregarPlano = () => fetchPlanoContas().then(setPlanoContas).catch(() => {});
  const carregarOpcoes = () => { fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {}); carregarPlano(); };
  useEffect(() => { carregarOpcoes(); }, []);

  const [produtosEstoque, setProdutosEstoque] = useState<(EstoqueItemPicker & {
    fornecedor_nome: string | null;
    conta_gerencial_despesa_padrao: string | null; conta_gerencial_receita_padrao: string | null;
  })[]>([]);
  const carregarEstoque = () => fetchEstoque().then((d) => setProdutosEstoque((d.itens || []).map((i: any) => ({
    nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
    estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
    fornecedor_nome: i.fornecedor_nome ?? null,
    conta_gerencial_despesa_padrao: i.conta_gerencial_despesa_padrao ?? null,
    conta_gerencial_receita_padrao: i.conta_gerencial_receita_padrao ?? null,
  })))).catch(() => {});
  useEffect(() => { carregarEstoque(); }, []);
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<string[]>([]);
  const [fornecedoresPorId, setFornecedoresPorId] = useState<Map<number, string>>(new Map());
  useEffect(() => {
    fetchFornecedores().then((d) => {
      setFornecedoresCadastro((d || []).map((f: any) => f.nome));
      setFornecedoresPorId(new Map((d || []).map((f: any) => [f.id, f.nome])));
    }).catch(() => {});
  }, []);
  // Resolve o código de conta gerencial padrão (despesa/receita) do produto no plano de contas já carregado.
  function contaGerencialPadrao(codigo: string | null | undefined) {
    if (!codigo) return null;
    const conta = planoContas.find((c) => c.codigo === codigo);
    return conta ? { codigo, nome: conta.nome } : null;
  }
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...opcoes.fornecedores, ...fornecedoresCadastro])).sort(),
    [opcoes.fornecedores, fornecedoresCadastro]
  );
  const [servicos, setServicos] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const carregarServicos = () => fetchServicosCadastro().then(setServicos).catch(() => {});
  useEffect(() => { carregarServicos(); }, []);
  const sugestoesServico = useMemo(() => servicos.filter((s) => s.ativo).map((s) => s.nome).sort((a, b) => a.localeCompare(b, "pt-BR")), [servicos]);

  // Modal "+ Adicionar" (novo produto de estoque, novo serviço ou nova conta
  // gerencial), aberto a partir de um item específico da nota — o item fica
  // marcado em `adicionarPara` para saber onde aplicar o resultado ao salvar.
  const [adicionarPara, setAdicionarPara] = useState<number | null>(null);
  const [modoAdicionar, setModoAdicionar] = useState<"produto" | "servico" | "conta">("produto");
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);

  const [itens, setItens] = useState<Item[]>([itemVazio()]);
  // Pré-preenchimento via query string (ex.: botão "Lançar financeiro" do
  // calendário sanitário → /lancamentos?ir=financeiro_despesa&servico=Exame%20de%20brucelose).
  useEffect(() => {
    const servico = new URLSearchParams(window.location.search).get("servico");
    if (servico) setItens([{ ...itemVazio(), tipo_item: "servico", produto: servico }]);
  }, []);
  // Pré-preenchimento vindo do Balanço de estoque ("gerar movimentação
  // financeira" ao lançar entrada/saída) — puxa produto, conta gerencial,
  // quantidade e valor do movimento; falta só o que é exclusivo do
  // financeiro (pagamento, parcelamento, acréscimo/desconto).
  useEffect(() => onPedidoLancamentoFinanceiro((dados) => {
    if (dados.tipo !== tipo) return;
    const conta = dados.codigo_conta_gerencial ? contaGerencialPadrao(dados.codigo_conta_gerencial) : null;
    setItens([{
      ...itemVazio(),
      tipo_item: "produto",
      produto: dados.produto,
      codigo_conta_gerencial: conta?.codigo || "",
      nome_conta_gerencial: conta?.nome || "",
      quantidade: String(dados.quantidade),
      valor_unitario: dados.valor_unitario != null ? String(dados.valor_unitario) : "",
      valor_total: dados.valor_total != null ? String(dados.valor_total) : "",
      modoValor: dados.valor_total != null && dados.valor_unitario == null ? "total" : "unitario",
    }]);
    if (dados.data_emissao) setDataEmissao(dados.data_emissao);
  }), [tipo, planoContas]);
  const [centroCusto, setCentroCusto] = useState("Pecuária Leiteira");
  const [fornecedor, setFornecedor] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  // Item de consulta À PARTE do número do documento — nº da ordem de serviço
  // (OS) ou do orçamento que originou a compra, quando houver.
  const [numeroOsOrcamento, setNumeroOsOrcamento] = useState("");
  // Nº do boleto (linha digitável) — só para lançamento SEM parcelamento;
  // com parcelamento, cada parcela tem o seu próprio (ver tabela de parcelas).
  const [numeroBoleto, setNumeroBoleto] = useState("");
  const [dataEmissao, setDataEmissao] = useState("");
  const [dataVencimento, setDataVencimento] = useState("");
  const [dataPrevistaEntrada, setDataPrevistaEntrada] = useState("");
  const [dataPedido, setDataPedido] = useState("");
  const [entregue, setEntregue] = useState(false);
  // Uma vez que o usuário mexe manualmente no checkbox "entregue", o
  // auto-preenchimento (ao mudar a data de emissão) para de marcá-lo sozinho —
  // nunca reverte uma edição manual (ver handleDataEmissaoChange abaixo).
  const entregueTocadoRef = useRef(false);
  // Vínculo opcional a um Pedido (módulo Pedidos) — só a partir deste vínculo o
  // pedido passa a refletir em Financeiro; ele mesmo nunca lança nada sozinho.
  const [pedidoId, setPedidoId] = useState("");
  const [pedidosAbertos, setPedidosAbertos] = useState<{ id: number; numero_pedido: string; fornecedor_cliente: string | null; valor_total_estimado: number }[]>([]);
  useEffect(() => {
    fetchPedidos({ tipo: tipo === "despesa" ? "compra" : "venda" })
      .then((lista: any[]) => setPedidosAbertos(lista.filter((p) => p.status !== "cancelado" && p.status !== "atendido")))
      .catch(() => {});
  }, [tipo]);
  const [desconto, setDesconto] = useState("");
  const [acrescimo, setAcrescimo] = useState("");

  // Vínculo sanitário/reprodutivo — dois caminhos possíveis:
  // 1) este lançamento nasceu de "lançar em contas a pagar" a partir de uma
  //    vacina/exame/diagnóstico (origemEvento já identifica o evento; ao
  //    salvar, vincula direto, sem perguntar de novo);
  // 2) o usuário escolheu uma conta gerencial marcada (ex.: Veterinário/
  //    zootecnista) — ao salvar, oferece vincular a um evento recente (popup).
  const [origemEvento, setOrigemEvento] = useState<OrigemVinculoSanitarioReprodutivo | null>(null);
  useEffect(() => onPedidoLancamentoFinanceiroDeEvento((dados) => {
    setOrigemEvento(dados);
    setItens([{ ...itemVazio(), tipo_item: "servico", produto: dados.produto }]);
    if (dados.data_emissao) setDataEmissao(dados.data_emissao);
    if (dados.responsavel) setResponsavel(dados.responsavel);
  }), []);
  const [popupVinculo, setPopupVinculo] = useState<{
    numeroLancamento: string;
    candidatos: { servicos: CandidatoVinculoSanitarioReprodutivo[]; vacinas: CandidatoVinculoSanitarioReprodutivo[]; exames: CandidatoVinculoSanitarioReprodutivo[] };
  } | null>(null);
  const contasQuePedemVinculo = useMemo(
    () => new Set(planoContas.filter((c) => c.pede_vinculo_sanitario_reprodutivo).map((c) => c.codigo)),
    [planoContas]
  );

  const [parcelado, setParcelado] = useState(false);
  const [qtdParcelas, setQtdParcelas] = useState("2");
  const [parcelas, setParcelas] = useState<Parcela[]>([]);
  // Quando a extração do boleto já traz os valores/vencimentos exatos de cada
  // parcela (parcelas_detectadas), guarda aqui pra o efeito de auto-divisão
  // (abaixo) usar esses valores reais em vez de dividir tudo igualmente.
  const parcelasExtraidasRef = useRef<Parcela[] | null>(null);
  // Boleto(s) a anexar ao lançamento quando ele nascer parcelado — sobem
  // depois que o lançamento é criado (o anexo precisa do numero_lancamento).
  const [boletoFiles, setBoletoFiles] = useState<File[]>([]);
  const boletoInputRef = useRef<HTMLInputElement>(null);
  const fotoBoletoInputRef = useRef<HTMLInputElement>(null);
  const [avisoTipoDocumento, setAvisoTipoDocumento] = useState(false);

  const [jaPago, setJaPago] = useState(false);
  const [dataPagamento, setDataPagamento] = useState("");
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");

  const [xmlAberto, setXmlAberto] = useState(false);
  const [xmlTexto, setXmlTexto] = useState("");
  const [importando, setImportando] = useState(false);
  const [erroXml, setErroXml] = useState<string | null>(null);
  const [avisoDocumento, setAvisoDocumento] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [confirmando, setConfirmando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Detecção de possível duplicado — comparação lado a lado antes de salvar.
  const [duplicados, setDuplicados] = useState<LancamentoParecido[]>([]);
  const [confirmandoDuplicado, setConfirmandoDuplicado] = useState(false);
  const [verificandoDuplicado, setVerificandoDuplicado] = useState(false);

  function atualizarItem(idx: number, patch: Partial<Item>) {
    setItens((arr) => arr.map((it, i) => {
      if (i !== idx) return it;
      const novo = { ...it, ...patch };
      const q = Number(novo.quantidade);
      if (novo.modoValor === "total") {
        // Usuário digita o valor total; o unitário é derivado (total ÷ quantidade).
        // Se a quantidade estiver vazia/0, o unitário fica em branco e o total é usado como está.
        const t = Number(novo.valor_total);
        novo.valor_unitario = novo.valor_total && q > 0 ? (t / q).toFixed(2) : "";
      } else {
        // Modo unitário (padrão): usuário digita quantidade e unitário; o total é derivado.
        const v = Number(novo.valor_unitario);
        novo.valor_total = novo.quantidade && novo.valor_unitario ? (q * v).toFixed(2) : "";
      }
      return novo;
    }));
  }
  function acrescentarItem() { setItens((arr) => [...arr, itemVazio()]); }
  function removerItem(idx: number) { setItens((arr) => (arr.length > 1 ? arr.filter((_, i) => i !== idx) : arr)); }

  // Auto-preenchimento de datas a partir da Data de emissão — só preenche
  // campo que estiver VAZIO (nunca sobrescreve edição manual, nunca reverte
  // depois se a emissão mudar de novo). "Data prevista de entrada", "Data do
  // pedido" e o checkbox "entregue" só entram quando algum item da nota é do
  // tipo produto (para serviço não faz sentido "entrada"/"entregue").
  function handleDataEmissaoChange(valor: string) {
    setDataEmissao(valor);
    if (!valor) return;
    setDataVencimento((atual) => atual || valor);
    if (itens.some((i) => i.tipo_item === "produto")) {
      setDataPrevistaEntrada((atual) => atual || valor);
      setDataPedido((atual) => atual || valor);
      if (!entregueTocadoRef.current) setEntregue(true);
    }
  }

  const valorBruto = useMemo(() => itens.reduce((a, i) => a + (Number(i.valor_total) || 0), 0), [itens]);
  const valorLiquido = useMemo(() => Math.round((valorBruto - (Number(desconto) || 0) + (Number(acrescimo) || 0)) * 100) / 100, [valorBruto, desconto, acrescimo]);

  // Regenera as parcelas (divisão igual) quando ligar o parcelamento ou mudar
  // quantidade — EXCETO logo após uma extração de boleto multi-parcela, que já
  // trouxe valor/vencimento reais de cada via (parcelasExtraidasRef): nesse
  // caso usa esses valores exatos uma vez, sem sobrescrever com a divisão igual.
  useEffect(() => {
    if (!parcelado) { setParcelas([]); return; }
    if (parcelasExtraidasRef.current) {
      setParcelas(parcelasExtraidasRef.current);
      parcelasExtraidasRef.current = null;
      return;
    }
    const n = Math.max(1, Math.round(Number(qtdParcelas) || 0));
    setParcelas(dividirParcelas(valorLiquido, n, dataPrevistaEntrada || dataEmissao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcelado, qtdParcelas]);

  const somaParcelas = useMemo(() => parcelas.reduce((a, p) => a + (Number(p.valor) || 0), 0), [parcelas]);
  const diferencaPagamento = useMemo(() => (valorPago ? Math.round((Number(valorPago) - valorLiquido) * 100) / 100 : 0), [valorPago, valorLiquido]);

  // Baixa de UMA parcela dentro do lançamento parcelado (item 3) — marcar o
  // checkbox "Pago" pré-preenche valor pago (com o valor da própria parcela)
  // e data de pagamento (hoje), ambos editáveis; desmarcar limpa a baixa.
  function marcarParcelaPaga(idx: number, pago: boolean) {
    setParcelas((arr) => arr.map((p, i) => {
      if (i !== idx) return p;
      if (!pago) {
        return { ...p, pago: false, data_pagamento: undefined, valor_pago: undefined, conta_bancaria: undefined, forma_pagamento: undefined, numero_documento_pagamento: undefined };
      }
      const hoje = new Date().toISOString().slice(0, 10);
      return { ...p, pago: true, data_pagamento: p.data_pagamento || hoje, valor_pago: p.valor_pago || p.valor };
    }));
  }
  function atualizarBaixaParcela(idx: number, patch: Partial<Parcela>) {
    setParcelas((arr) => arr.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function limpar() {
    setItens([itemVazio()]);
    setCentroCusto("Pecuária Leiteira"); setFornecedor(""); setResponsavel(""); setTipoDocumento("");
    setNumeroDocumento(""); setNumeroOsOrcamento(""); setNumeroBoleto("");
    setDataEmissao(""); setDataVencimento(""); setDataPrevistaEntrada(""); setDataPedido(""); setEntregue(false);
    entregueTocadoRef.current = false;
    setPedidoId("");
    setDesconto(""); setAcrescimo("");
    setParcelado(false); setQtdParcelas("2"); setParcelas([]); setBoletoFiles([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
    setXmlTexto(""); setXmlAberto(false);
  }

  // ── Rascunho automático ──────────────────────────────────────────────
  // O usuário costuma sair do lançamento no meio (ex.: para conferir um
  // cadastro) e perdia tudo. Agora o formulário salva um rascunho sozinho
  // enquanto está preenchido e, ao voltar, oferece retomar ou descartar.
  const RASCUNHO_KEY = `rascunho_financeiro_${tipo}`;
  const [rascunhoPendente, setRascunhoPendente] = useState<any | null>(() => {
    if (typeof window === "undefined") return null;
    try { const raw = localStorage.getItem(RASCUNHO_KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
  });

  function montarRascunho() {
    return {
      itens, centroCusto, fornecedor, responsavel, tipoDocumento, numeroDocumento, numeroOsOrcamento, numeroBoleto,
      dataEmissao, dataVencimento, dataPrevistaEntrada, dataPedido, pedidoId, entregue, desconto, acrescimo,
      parcelado, qtdParcelas, parcelas, jaPago, dataPagamento, valorPago, contaBancaria,
      numeroDocumentoPagamento, formaPagamento, salvoEm: new Date().toISOString(),
    };
  }
  function aplicarRascunho(d: any) {
    if (!d) return;
    setItens(Array.isArray(d.itens) && d.itens.length ? d.itens : [itemVazio()]);
    setCentroCusto(d.centroCusto || "Pecuária Leiteira"); setFornecedor(d.fornecedor || ""); setResponsavel(d.responsavel || "");
    setTipoDocumento(d.tipoDocumento || ""); setNumeroDocumento(d.numeroDocumento || "");
    setNumeroOsOrcamento(d.numeroOsOrcamento || ""); setNumeroBoleto(d.numeroBoleto || "");
    setDataEmissao(d.dataEmissao || ""); setDataVencimento(d.dataVencimento || ""); setDataPrevistaEntrada(d.dataPrevistaEntrada || ""); setDataPedido(d.dataPedido || "");
    setPedidoId(d.pedidoId || "");
    setEntregue(!!d.entregue); setDesconto(d.desconto || ""); setAcrescimo(d.acrescimo || "");
    setParcelado(!!d.parcelado); setQtdParcelas(d.qtdParcelas || "2"); setParcelas(Array.isArray(d.parcelas) ? d.parcelas : []);
    setJaPago(!!d.jaPago); setDataPagamento(d.dataPagamento || ""); setValorPago(d.valorPago || "");
    setContaBancaria(d.contaBancaria || ""); setNumeroDocumentoPagamento(d.numeroDocumentoPagamento || "");
    setFormaPagamento(d.formaPagamento || "");
  }

  // Está "sujo" (com trabalho a perder) se já tem item preenchido ou dados da nota.
  const sujo = useMemo(() => {
    const temItem = itens.some((i) => i.produto.trim() || i.nome_conta_gerencial.trim() || i.valor_total.trim() || i.descricao.trim());
    return Boolean(temItem || fornecedor || numeroDocumento || centroCusto || dataEmissao || Number(desconto) || Number(acrescimo) || jaPago);
  }, [itens, fornecedor, numeroDocumento, centroCusto, dataEmissao, desconto, acrescimo, jaPago]);

  // Salva/limpa o rascunho e avisa o pai enquanto o formulário muda.
  useEffect(() => {
    onSujo?.(sujo);
    try {
      if (sujo) localStorage.setItem(RASCUNHO_KEY, JSON.stringify(montarRascunho()));
      else localStorage.removeItem(RASCUNHO_KEY);
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sujo, itens, centroCusto, fornecedor, responsavel, tipoDocumento, numeroDocumento, numeroOsOrcamento, numeroBoleto, dataEmissao, dataVencimento,
      dataPrevistaEntrada, dataPedido, entregue, desconto, acrescimo, parcelado, qtdParcelas, parcelas,
      jaPago, dataPagamento, valorPago, contaBancaria, numeroDocumentoPagamento, formaPagamento]);

  // Avisa o navegador antes de fechar/atualizar a aba com lançamento em edição.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (sujo) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sujo]);

  function retomarRascunho() { aplicarRascunho(rascunhoPendente); setRascunhoPendente(null); }
  function descartarRascunho() {
    setRascunhoPendente(null);
    try { localStorage.removeItem(RASCUNHO_KEY); } catch { /* ignore */ }
  }

  function aplicarXml(dados: any) {
    if (dados.numero_documento) setNumeroDocumento(dados.numero_documento);
    if (dados.data_emissao) setDataEmissao(dados.data_emissao);
    if (dados.fornecedor_cliente) setFornecedor(dados.fornecedor_cliente);
    setTipoDocumento("Nota fiscal");
    if (Array.isArray(dados.itens) && dados.itens.length) {
      setItens(dados.itens.map((it: any) => ({
        codigo_conta_gerencial: "", nome_conta_gerencial: "", tipo_item: "produto",
        produto: it.produto || "", descricao: "",
        quantidade: it.quantidade != null ? String(it.quantidade) : "",
        valor_unitario: it.valor_unitario != null ? String(it.valor_unitario) : "",
        valor_total: it.valor_total != null ? String(it.valor_total) : "",
        // Preserva o total informado na nota (não recalcula por quantidade × unitário).
        modoValor: it.valor_total != null ? "total" : "unitario",
      })));
    } else if (dados.valor_total != null) {
      setItens([{ ...itemVazio(), produto: "Importado do XML", valor_total: String(dados.valor_total), modoValor: "total" }]);
    }
    if (Array.isArray(dados.parcelas) && dados.parcelas.length) {
      setParcelado(true);
      setQtdParcelas(String(dados.parcelas.length));
      setParcelas(dados.parcelas.map((p: any) => ({ data_vencimento: p.data_vencimento || "", valor: p.valor != null ? String(p.valor) : "" })));
    }
  }

  async function importarXml(texto: string) {
    if (!texto.trim()) return;
    setImportando(true); setErroXml(null);
    try {
      const dados = await importarXmlFinanceiro(texto);
      aplicarXml(dados);
      setXmlAberto(false);
    } catch (e: any) {
      setErroXml(e.message || "Erro ao ler o XML");
    } finally {
      setImportando(false);
    }
  }

  // Nota fiscal ou recibo em PDF/JPEG/PNG — leitura automática via IA.
  // Recibo (já pago) preenche o pagamento imediato; nota fiscal nasce em aberto.
  // Boleto: se a IA achou "parcela X/Y" no próprio boleto, já monta o
  // parcelamento com essa quantidade; senão, deixa como lançamento único e
  // é o usuário quem decide (documento avulso ou marcar como parcelado).
  function aplicarExtracaoDocumento(dados: any) {
    setAvisoDocumento(null);
    aplicarXml(dados);
    const ehRecibo = dados.tipo_documento === "recibo";
    const ehBoleto = dados.tipo_documento === "boleto";
    setTipoDocumento(ehRecibo ? "Recibo" : ehBoleto ? "Boleto" : "Nota fiscal");
    if (ehRecibo) {
      setJaPago(true);
      if (dados.data_pagamento) setDataPagamento(dados.data_pagamento);
      if (dados.valor_total != null) setValorPago(String(dados.valor_total));
      if (dados.conta_bancaria) setContaBancaria(dados.conta_bancaria);
      if (!dados.itens?.length && dados.valor_total != null) {
        setItens([{ ...itemVazio(), produto: dados.observacao || "Recibo anexado", valor_total: String(dados.valor_total), modoValor: "total" }]);
      }
    } else if (ehBoleto) {
      if (dados.data_vencimento) setDataVencimento(dados.data_vencimento);
      if (!dados.itens?.length && dados.valor_total != null) {
        setItens([{ ...itemVazio(), produto: dados.observacao || "Boleto anexado", valor_total: String(dados.valor_total), modoValor: "total" }]);
      }
      const parcelasDetectadas: any[] = Array.isArray(dados.parcelas_detectadas) ? dados.parcelas_detectadas : [];
      if (dados.parcela_num && dados.parcela_total && dados.parcela_total > 1) {
        // O próprio boleto indica "parcela X/Y". Se a leitura conseguiu achar
        // o valor/vencimento de CADA via (uma por página, tipicamente), usa
        // esses valores exatos — não divide o total igualmente entre elas.
        setParcelado(true);
        setQtdParcelas(String(dados.parcela_total));
        if (parcelasDetectadas.length > 1) {
          parcelasExtraidasRef.current = parcelasDetectadas.map((p) => ({
            data_vencimento: p.data_vencimento || "",
            valor: p.valor != null ? String(p.valor) : "",
            numero_boleto: p.linha_digitavel || "",
          }));
        }
      } else if (parcelasDetectadas.length === 1 && parcelasDetectadas[0].linha_digitavel) {
        setNumeroBoleto(parcelasDetectadas[0].linha_digitavel);
        setAvisoDocumento(
          "Boleto avulso: não achei indicação de parcelamento neste documento. Revise se é um lançamento único " +
          "ou marque \"Parcelar\" abaixo se ele fizer parte de um plano.",
        );
      } else if (dados.linha_digitavel) {
        setNumeroBoleto(dados.linha_digitavel);
        setAvisoDocumento(
          "Boleto avulso: não achei indicação de parcelamento neste documento. Revise se é um lançamento único " +
          "ou marque \"Parcelar\" abaixo se ele fizer parte de um plano.",
        );
      } else {
        setAvisoDocumento(
          "Boleto avulso: não achei indicação de parcelamento neste documento. Revise se é um lançamento único " +
          "ou marque \"Parcelar\" abaixo se ele fizer parte de um plano.",
        );
      }
      if (dados.valor_total_corrigido) {
        setAvisoDocumento(
          (prev) => `${prev ? prev + " " : ""}Conferi: este boleto tem ${dados.parcela_total} parcela(s) — o valor total foi ` +
          `ajustado para a soma de todas (${dados.paginas_documento ? `${dados.paginas_documento} página(s) lidas` : "várias vias"}). Revise os valores abaixo.`,
        );
      }
    }
  }

  async function lerDocumentoAnexado(file: File) {
    setImportando(true); setErroXml(null);
    try {
      const dados = await lerDocumentoFinanceiro(file);
      aplicarExtracaoDocumento(dados);
      setXmlAberto(false);
      // O documento usado pra leitura automática NÃO fica anexado ao
      // lançamento por padrão (só os dados extraídos ficam) — a prévia mostra
      // um aviso disso (ver ModalDivididoDocumento). Quem quiser guardar o
      // arquivo mesmo assim usa o dropzone "documentos deste lançamento"
      // abaixo (mesmo arquivo, arraste de novo — ou outro).
    } catch (e: any) {
      setErroXml(e.message || "Erro ao ler o documento");
    } finally {
      setImportando(false);
    }
  }

  function tratarArquivo(file: File) {
    if (file.type === "application/pdf" || file.type === "image/jpeg" || file.type === "image/png") {
      onArquivoParaLeitura?.(file);
      lerDocumentoAnexado(file);
    } else {
      file.text().then(importarXml);
    }
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) tratarArquivo(file);
  }
  function onFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) tratarArquivo(file);
  }

  function montarPayload() {
    return {
      tipo,
      itens: itens
        .filter((i) => i.produto.trim())
        .map((i) => ({
          codigo_conta_gerencial: i.codigo_conta_gerencial || null,
          nome_conta_gerencial: i.nome_conta_gerencial || null,
          produto: i.produto.trim(),
          tipo_item: i.tipo_item,
          descricao: i.descricao || null,
          quantidade: i.quantidade ? Number(i.quantidade) : null,
          valor_unitario: i.valor_unitario ? Number(i.valor_unitario) : null,
          valor_total: Number(i.valor_total) || 0,
        })),
      centro_custo: centroCusto || null,
      fornecedor_cliente: fornecedor || null,
      responsavel: responsavel || null,
      tipo_documento: tipoDocumento || null,
      numero_documento: numeroDocumento || null,
      numero_os_orcamento: numeroOsOrcamento || null,
      // Só vale para lançamento não-parcelado; com parcelamento, o boleto
      // informado aqui (se houver) já foi migrado para parcelas[0] abaixo —
      // nunca duplicado nas demais (regra do item 4; o backend reforça isso
      // de novo, defensivamente).
      numero_boleto: !parcelado ? (numeroBoleto || null) : null,
      data_emissao: dataEmissao || null,
      // Só vale para lançamento não-parcelado; nas parcelas cada uma tem seu vencimento.
      data_vencimento: !parcelado ? (dataVencimento || null) : null,
      data_prevista_entrada: dataPrevistaEntrada || null,
      data_pedido: dataPedido || null,
      pedido_id: pedidoId ? Number(pedidoId) : null,
      entregue,
      desconto: Number(desconto) || 0,
      acrescimo: Number(acrescimo) || 0,
      parcelas: parcelado
        ? parcelas.map((p, i) => ({
            data_vencimento: p.data_vencimento,
            valor: Number(p.valor) || 0,
            // Nº do boleto do lançamento (campo acima), quando preenchido e a
            // própria parcela não tiver o seu, vira o boleto da 1ª parcela.
            numero_boleto: p.numero_boleto || (i === 0 && numeroBoleto ? numeroBoleto : null),
            // Baixa desta parcela dentro do lançamento parcelado (item 3) —
            // só entra quando o usuário marcou "Pago" naquela linha.
            data_pagamento: p.pago ? (p.data_pagamento || null) : null,
            valor_pago: p.pago ? (Number(p.valor_pago) || 0) : null,
            conta_bancaria: p.pago ? (p.conta_bancaria || null) : null,
            forma_pagamento: p.pago ? (p.forma_pagamento || null) : null,
            numero_documento_pagamento: p.pago ? (p.numero_documento_pagamento || null) : null,
          }))
        : [],
      data_pagamento: !parcelado && jaPago ? dataPagamento || null : null,
      valor_pago: !parcelado && jaPago ? Number(valorPago) || 0 : null,
      conta_bancaria: !parcelado && jaPago ? contaBancaria || null : null,
      numero_documento_pagamento: !parcelado && jaPago ? numeroDocumentoPagamento || null : null,
      forma_pagamento: !parcelado && jaPago ? formaPagamento || null : null,
    };
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const validos = itens.filter((i) => i.produto.trim());
    if (!validos.length) { setErro("Informe ao menos um produto ou serviço."); return; }
    if (!centroCusto.trim()) { setErro("Selecione o centro de custo."); return; }
    if (valorLiquido <= 0) { setErro("O valor líquido do lançamento deve ser positivo."); return; }
    if (!confirmandoDuplicado) {
      setVerificandoDuplicado(true);
      try {
        const achados = await fetchPossiveisDuplicados({
          tipo, valor_total: valorLiquido, fornecedor_cliente: fornecedor, data_emissao: dataEmissao || undefined,
        });
        if (achados.length) { setDuplicados(achados); setConfirmandoDuplicado(true); return; }
      } finally {
        setVerificandoDuplicado(false);
      }
    }
    if (!parcelado && jaPago && diferencaPagamento !== 0 && !confirmando) { setConfirmando(true); return; }
    setSalvando(true);
    try {
      const r = await criarLancamentoFinanceiro(montarPayload());
      let avisoAnexo = "";
      if (boletoFiles.length) {
        const falhas = (await Promise.all(boletoFiles.map((f) => anexarArquivoLancamento(r.numero_lancamento, f).then(() => null).catch(() => f.name)))).filter(Boolean);
        if (falhas.length) avisoAnexo = ` (não foi possível anexar: ${falhas.join(", ")})`;
      }
      setSucesso(`Lançamento ${r.numero_lancamento} salvo com sucesso.${avisoAnexo}`);
      // Vínculo sanitário/reprodutivo — 2 caminhos (ver estado `origemEvento`
      // e `contasQuePedemVinculo` acima): se este lançamento nasceu de "lançar
      // em contas a pagar" a partir de um evento, vincula direto; senão, se
      // alguma conta escolhida pede vínculo, oferece associar a um evento
      // recente antes de limpar o formulário.
      if (origemEvento) {
        vincularEventoSanitarioReprodutivo({ tipo: origemEvento.tipo, ids: origemEvento.ids, numero_lancamento: r.numero_lancamento }).catch(() => {});
        setOrigemEvento(null);
      } else if (tipo === "despesa" && itens.some((i) => contasQuePedemVinculo.has(i.codigo_conta_gerencial))) {
        fetchCandidatosVinculoSanitarioReprodutivo()
          .then((candidatos) => setPopupVinculo({ numeroLancamento: r.numero_lancamento, candidatos }))
          .catch(() => {});
      }
      limpar();
      onSujo?.(false);
      onSalvo?.(`Lançamento ${r.numero_lancamento} salvo com sucesso.${avisoAnexo}`);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar lançamento");
    } finally {
      setSalvando(false); setConfirmando(false); setConfirmandoDuplicado(false); setDuplicados([]);
    }
  }

  return (
    <>
      {/* Rascunho não salvo de uma edição anterior — retomar ou descartar */}
      {rascunhoPendente && !sujo && (
        <div className="card mb-3" style={{ border: "1px solid var(--amber)", background: "rgba(217,119,6,0.08)" }}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} style={{ color: "var(--amber)" }} />
            <strong style={{ fontSize: "0.85rem" }}>Há um rascunho de lançamento não salvo</strong>
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Você começou um lançamento e saiu sem salvar
            {rascunhoPendente.salvoEm ? ` (${new Date(rascunhoPendente.salvoEm).toLocaleString("pt-BR")})` : ""}.
            Deseja retomar o rascunho em edição ou descartá-lo?
          </p>
          <div className="flex items-center gap-2">
            <button type="button" className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={retomarRascunho}>
              <Check size={14} /> Retomar rascunho
            </button>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={descartarRascunho}>
              <Trash2 size={13} /> Descartar
            </button>
          </div>
        </div>
      )}

      {/* Importação de XML de nota */}
      <div
        onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        className="card mb-3"
        style={{ border: "1px dashed var(--border)", background: "var(--surface-2)", padding: "0.8rem", textAlign: "center" }}
      >
        <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
          <FileText size={16} style={{ color: "var(--dourado-light)" }} />
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Arraste o XML, PDF, JPEG ou PNG da nota/recibo aqui, ou</span>
          <button type="button" className="btn-ghost" title="Selecionar arquivo XML, PDF, JPEG ou PNG da nota ou recibo" onClick={() => fileInputRef.current?.click()} style={{ fontSize: "0.78rem" }}>
            <Upload size={13} /> selecionar arquivo
          </button>
          <button type="button" className="btn-ghost" title="Colar o código XML da nota fiscal" onClick={() => setXmlAberto((v) => !v)} style={{ fontSize: "0.78rem" }}>colar código XML</button>
          {importando && <Loader2 size={14} className="animate-spin" style={{ color: "var(--dourado-light)" }} />}
        </div>
        <input ref={fileInputRef} type="file" accept=".xml,text/xml,application/pdf,image/jpeg,image/png" onChange={onFileSelect} style={{ display: "none" }} />
        {xmlAberto && (
          <div style={{ marginTop: "0.6rem", textAlign: "left" }}>
            <textarea value={xmlTexto} onChange={(e) => setXmlTexto(e.target.value)} placeholder="Cole aqui o conteúdo do XML da nota fiscal…"
              style={{ ...inputStyle, minHeight: "6rem", fontFamily: "monospace", fontSize: "0.72rem" }} />
            <button type="button" className="btn-primary" title="Importar os dados do XML colado" style={{ marginTop: "0.4rem" }} onClick={() => importarXml(xmlTexto)} disabled={importando}>Importar XML</button>
          </div>
        )}
        {erroXml && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.4rem" }}>{erroXml}</p>}
        {avisoDocumento && <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>{avisoDocumento}</p>}
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          XML reconhece vários produtos/serviços da mesma nota. PDF/JPEG/PNG usa leitura automática por IA — identifica se é
          nota fiscal (nasce em aberto) ou recibo (nasce já pago) — os campos ficam abaixo, todos editáveis.
        </p>
      </div>

      {/* Produtos / serviços da nota */}
      <div className="mt-3 space-y-3">
        {itens.map((it, idx) => (
          <div key={idx} className="card" style={{ background: "var(--fin-produtos-bg)", position: "relative" }}>
            {itens.length > 1 && (
              <button type="button" title="Remover este produto/serviço" onClick={() => removerItem(idx)} className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", fontSize: "0.7rem", color: "var(--red)" }}>
                <Trash2 size={13} />
              </button>
            )}
            <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.5rem" }}>Produto/serviço {idx + 1}</p>
            <div className="flex items-center gap-2 mb-3">
              {(["produto", "servico"] as const).map((t) => (
                <button key={t} type="button" title={t === "produto" ? "Este item é um produto de estoque" : "Este item é um serviço"} onClick={() => atualizarItem(idx, { tipo_item: t, produto: "" })}
                  style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                    border: "1px solid " + (it.tipo_item === t ? "var(--dourado)" : "var(--border)"),
                    background: it.tipo_item === t ? "var(--dourado)" : "transparent",
                    color: it.tipo_item === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: it.tipo_item === t ? 700 : 400 }}>
                  {t === "produto" ? "Produto" : "Serviço"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {it.tipo_item === "servico" ? (
                <Campo label="Serviço">
                  <select style={inputStyle} value={it.produto} onChange={(e) => atualizarItem(idx, { produto: e.target.value })}>
                    <option value="">Selecione…</option>
                    {sugestoesServico.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </Campo>
              ) : (
                <Campo label="Produto">
                  <EstoquePicker itens={produtosEstoque} value={it.produto} finalidades={FINALIDADES_ESTOQUE} onChange={(nomeProduto) => {
                    const match = produtosEstoque.find((p) => p.nome === nomeProduto);
                    const patch: Partial<Item> = { produto: nomeProduto };
                    const conta = contaGerencialPadrao(tipo === "despesa" ? match?.conta_gerencial_despesa_padrao : match?.conta_gerencial_receita_padrao);
                    if (conta) { patch.codigo_conta_gerencial = conta.codigo; patch.nome_conta_gerencial = conta.nome; }
                    atualizarItem(idx, patch);
                    if (match?.fornecedor_nome) setFornecedor(match.fornecedor_nome);
                  }} />
                </Campo>
              )}
              <Campo label="Conta gerencial">
                <SeletorContaGerencial
                  contas={planoContas}
                  tipo={tipo}
                  natureza={it.tipo_item}
                  codigo={it.codigo_conta_gerencial}
                  nome={it.nome_conta_gerencial}
                  onSelect={(codigo, nome) => atualizarItem(idx, { codigo_conta_gerencial: codigo, nome_conta_gerencial: nome })}
                  placeholder="Escolha a conta (só o galho mais baixo)…"
                />
              </Campo>
              <Campo label="Descrição (opcional)">
                <input style={inputStyle} value={it.descricao} onChange={(e) => atualizarItem(idx, { descricao: e.target.value })} />
              </Campo>
            </div>
            <div className="flex items-center gap-2 mt-3 mb-1" style={{ flexWrap: "wrap" }}>
              {(["unitario", "total"] as const).map((m) => (
                <button key={m} type="button"
                  title={m === "unitario" ? "Digitar a quantidade e o valor unitário (o total é calculado)" : "Digitar a quantidade e o valor total (o unitário é calculado)"}
                  onClick={() => atualizarItem(idx, { modoValor: m })}
                  style={{ fontSize: "0.7rem", padding: "0.2rem 0.6rem", borderRadius: "999px", cursor: "pointer",
                    border: "1px solid " + (it.modoValor === m ? "var(--dourado)" : "var(--border)"),
                    background: it.modoValor === m ? "var(--dourado)" : "transparent",
                    color: it.modoValor === m ? "#1a1a1a" : "var(--text-muted)", fontWeight: it.modoValor === m ? 700 : 400 }}>
                  {m === "unitario" ? "Informar valor unitário" : "Informar valor total"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-1">
              <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={it.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
              <Campo label={it.modoValor === "unitario" ? "Valor unitário (R$)" : "Valor unitário (R$) — calculado"}>
                <input type="number" inputMode="decimal"
                  style={it.modoValor === "unitario" ? inputStyle : { ...inputStyle, opacity: 0.55, cursor: "not-allowed" }}
                  value={it.valor_unitario} readOnly={it.modoValor === "total"}
                  onChange={(e) => atualizarItem(idx, { valor_unitario: e.target.value })} />
              </Campo>
              <Campo label={it.modoValor === "total" ? "Valor total (R$)" : "Valor total (R$) — calculado"}>
                <input type="number" inputMode="decimal"
                  style={it.modoValor === "total" ? inputStyle : { ...inputStyle, opacity: 0.55, cursor: "not-allowed" }}
                  value={it.valor_total} readOnly={it.modoValor === "unitario"}
                  onChange={(e) => atualizarItem(idx, { valor_total: e.target.value })} />
              </Campo>
            </div>
            <button type="button" className="btn-ghost" title="Cadastrar um novo produto, serviço ou conta gerencial" style={{ fontSize: "0.75rem", marginTop: "0.6rem" }}
              onClick={() => { setAdicionarPara(idx); setModoAdicionar(it.tipo_item === "servico" ? "servico" : "produto"); }}>
              <Plus size={13} /> Adicionar {it.tipo_item === "servico" ? "serviço" : "produto"} ou conta gerencial novo(a)
            </button>
          </div>
        ))}
        <button type="button" className="btn-ghost" title="Adicionar mais um produto ou serviço à nota" onClick={acrescentarItem} style={{ fontSize: "0.8rem" }}>
          <Plus size={14} /> Acrescentar produto ou serviço
        </button>
      </div>

      {/* Dados da nota (uma vez por lançamento) */}
      <div className="card mt-4" style={{ background: "var(--fin-nota-bg)" }}>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Campo label={tipo === "receita" ? "Cliente" : "Fornecedor"}>
          <div className="flex items-center gap-2">
            <select style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>
              {fornecedoresDisponiveis.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button type="button" className="btn-ghost" title={`Cadastrar novo ${tipo === "receita" ? "cliente" : "fornecedor"}`} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
        </Campo>
        <Campo label="Centro de custo">
          <select style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
            <option value="">Selecione…</option>
            {/* Valor legado que não esteja mais na lista canônica — preservado para não perder o dado. */}
            {centroCusto && !opcoes.centros_custo.includes(centroCusto) && <option value={centroCusto}>{centroCusto}</option>}
            {opcoes.centros_custo.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Campo>
        <Campo label="Responsável pelo lançamento">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Selecione…</option>
            {responsaveis.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo label="Tipo de documento">
          <select style={inputStyle} value={tipoDocumento} onChange={(e) => { setTipoDocumento(e.target.value); if (e.target.value) setAvisoTipoDocumento(false); }}>
            <option value="">Selecione…</option>
            {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
          </select>
        </Campo>

        <Campo label="Número do documento"><input style={inputStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></Campo>
        <Campo label="Nº da OS/Orçamento">
          <input style={inputStyle} value={numeroOsOrcamento} onChange={(e) => setNumeroOsOrcamento(e.target.value)} placeholder="ex.: OS-123 ou ORC-45" />
          <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
            Item de consulta à parte do número do documento — nº da ordem de serviço ou do orçamento, se houver.
          </span>
        </Campo>
        <Campo label="Número do boleto">
          <input style={inputStyle} value={numeroBoleto} onChange={(e) => setNumeroBoleto(e.target.value)} placeholder="linha digitável (opcional)" />
          <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
            {parcelado
              ? "Ao parcelar, vale como o boleto da 1ª parcela — as demais são informadas na tabela de parcelas abaixo."
              : "Linha digitável do boleto único deste lançamento (opcional)."}
          </span>
        </Campo>
        <Campo label="Data de emissão"><input type="date" style={inputStyle} value={dataEmissao} onChange={(e) => handleDataEmissaoChange(e.target.value)} /></Campo>
        {!parcelado && (
          <Campo label="Data de vencimento">
            <input type="date" style={inputStyle} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} />
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
              Usada para lançar em Contas a pagar e na Agenda.
            </span>
          </Campo>
        )}
        <Campo label="Data prevista de entrada"><input type="date" style={inputStyle} value={dataPrevistaEntrada} onChange={(e) => setDataPrevistaEntrada(e.target.value)} /></Campo>
        <Campo label="Data do pedido"><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></Campo>
        <Campo label="Vincular a um pedido (opcional)">
          <select style={inputStyle} value={pedidoId} onChange={(e) => setPedidoId(e.target.value)}>
            <option value="">— Nenhum —</option>
            {pedidosAbertos.map((p) => (
              <option key={p.id} value={p.id}>{p.numero_pedido} — {p.fornecedor_cliente || "sem contraparte"} ({formatBRL(p.valor_total_estimado)})</option>
            ))}
          </select>
          <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
            É só a partir deste vínculo que o pedido passa a refletir aqui em Financeiro.
          </span>
        </Campo>

        <Campo label="Entregue?">
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", marginTop: "0.4rem" }}>
            <input type="checkbox" checked={entregue} onChange={(e) => { entregueTocadoRef.current = true; setEntregue(e.target.checked); }} /> Já entregue / recebido
          </label>
        </Campo>
        <Campo label="Desconto (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={desconto} onChange={(e) => setDesconto(e.target.value)} placeholder="0,00" /></Campo>
        <Campo label="Acréscimo (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={acrescimo} onChange={(e) => setAcrescimo(e.target.value)} placeholder="0,00" /></Campo>
        <div>
          <label style={lbl}>Valor líquido da nota</label>
          <div style={{ ...inputStyle, fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</div>
        </div>
      </div>
      {(Number(desconto) > 0 || Number(acrescimo) > 0) && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          Bruto dos produtos: {formatBRL(valorBruto)}
          {Number(desconto) > 0 && <> · desconto de {formatBRL(Number(desconto))}</>}
          {Number(acrescimo) > 0 && <> · acréscimo de {formatBRL(Number(acrescimo))}</>}
        </p>
      )}
      </div>

      {/* Parcelamento */}
      <div className="card mt-3" style={{ background: "var(--fin-parcelamento-bg)" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
          <input type="checkbox" checked={parcelado} onChange={(e) => setParcelado(e.target.checked)} /> Lançamento parcelado
        </label>
        {parcelado && (
          <div style={{ marginTop: "0.6rem" }}>
            <Campo label="Quantidade de parcelas">
              <input type="number" min={1} style={{ ...inputStyle, maxWidth: "8rem" }} value={qtdParcelas} onChange={(e) => setQtdParcelas(e.target.value)} />
            </Campo>
            <div style={{ overflowX: "auto" }}>
            <table className="fazenda-table mt-2">
              <thead><tr><th>Parcela</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor (R$)</th><th>Nº do boleto</th><th style={{ textAlign: "center" }}>Pago</th></tr></thead>
              <tbody>
                {parcelas.map((p, i) => (
                  <Fragment key={i}>
                    <tr>
                      <td>{i + 1}/{parcelas.length}</td>
                      <td><input type="date" style={inputStyle} value={p.data_vencimento}
                        onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} /></td>
                      <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }} value={p.valor}
                        onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, valor: e.target.value } : x))} /></td>
                      <td><input style={inputStyle} value={p.numero_boleto || ""} placeholder="opcional" title="Linha digitável desta parcela, se houver"
                        onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, numero_boleto: e.target.value } : x))} /></td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" checked={!!p.pago} title={`Marcar esta parcela como já ${tipo === "despesa" ? "paga" : "recebida"}`}
                          onChange={(e) => marcarParcelaPaga(i, e.target.checked)} />
                      </td>
                    </tr>
                    {p.pago && (
                      <tr>
                        <td colSpan={5} style={{ padding: 0, border: 0 }}>
                          <div style={{ padding: "0.6rem", background: "var(--fin-pagamento-bg)", borderRadius: "6px", margin: "0.2rem 0 0.5rem" }}>
                            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                              <Campo label="Data de pagamento">
                                <input type="date" style={inputStyle} value={p.data_pagamento || ""}
                                  onChange={(e) => atualizarBaixaParcela(i, { data_pagamento: e.target.value })} />
                              </Campo>
                              <Campo label="Valor pago (R$)">
                                <input type="number" inputMode="decimal" style={inputStyle} value={p.valor_pago || ""}
                                  onChange={(e) => atualizarBaixaParcela(i, { valor_pago: e.target.value })} />
                              </Campo>
                              <Campo label="Conta bancária">
                                <select style={inputStyle} value={p.conta_bancaria || ""} onChange={(e) => atualizarBaixaParcela(i, { conta_bancaria: e.target.value })}>
                                  <option value="">Selecione…</option>
                                  {opcoes.contas_bancarias.map((c) => <option key={c}>{c}</option>)}
                                </select>
                              </Campo>
                              <Campo label="Nº do documento">
                                <input style={inputStyle} value={p.numero_documento_pagamento || ""}
                                  onChange={(e) => atualizarBaixaParcela(i, { numero_documento_pagamento: e.target.value })} />
                              </Campo>
                              <Campo label="Forma de pagamento">
                                <select style={inputStyle} value={p.forma_pagamento || ""} onChange={(e) => atualizarBaixaParcela(i, { forma_pagamento: e.target.value })}>
                                  <option value="">Selecione…</option>
                                  {opcoes.formas_pagamento.map((f) => <option key={f} value={f}>{f}</option>)}
                                </select>
                              </Campo>
                            </div>
                            {p.valor_pago && Math.abs((Number(p.valor_pago) || 0) - (Number(p.valor) || 0)) > 0.01 && (
                              <p style={{ fontSize: "0.72rem", marginTop: "0.35rem", color: (Number(p.valor_pago) - Number(p.valor)) < 0 ? "var(--green-light)" : "var(--amber)" }}>
                                {(Number(p.valor_pago) - Number(p.valor)) < 0 ? "Desconto" : "Acréscimo"} de {formatBRL(Math.abs((Number(p.valor_pago) || 0) - (Number(p.valor) || 0)))} em relação ao valor desta parcela.
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            </div>
            {Math.abs(somaParcelas - valorLiquido) > 0.01 && (
              <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>
                <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
                Soma das parcelas ({formatBRL(somaParcelas)}) difere do valor líquido ({formatBRL(valorLiquido)}).
              </p>
            )}
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Cada parcela nasce em aberto (conta a {tipo === "despesa" ? "pagar" : "receber"}) — marque &ldquo;Pago&rdquo; na própria
              linha para dar baixa já ao salvar, ou dê baixa individualmente depois.
            </p>
          </div>
        )}
      </div>

      {/* Anexar documento(s) a este lançamento — boleto, nota, comprovante etc.
          Sempre visível (não só quando parcelado): sobe junto ao salvar o
          lançamento, chamando `anexarArquivoLancamento` uma vez por arquivo.
          Exige "Tipo de documento" (campo acima) preenchido ANTES de anexar
          — sem isso não dá pra saber depois se o arquivo anexado era nota
          fiscal, recibo, boleto etc. (decisão do usuário). */}
      <div
        onDrop={(e) => {
          e.preventDefault();
          if (!tipoDocumento) { setAvisoTipoDocumento(true); return; }
          const fs = Array.from(e.dataTransfer.files || []); if (fs.length) setBoletoFiles((arr) => [...arr, ...fs]);
        }}
        onDragOver={(e) => e.preventDefault()}
        className="card mt-3"
        style={{ border: "1px dashed var(--border)", background: "var(--surface-2)", padding: "0.7rem", textAlign: "center" }}
      >
        <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
          <FileText size={15} style={{ color: "var(--dourado-light)" }} />
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
            Arraste o(s) documento(s) deste lançamento aqui (boleto, nota, comprovante — PDF/JPEG/PNG), ou
          </span>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }}
            onClick={() => { if (!tipoDocumento) { setAvisoTipoDocumento(true); return; } boletoInputRef.current?.click(); }}>
            <Upload size={12} /> selecionar arquivo(s)
          </button>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }}
            onClick={() => { if (!tipoDocumento) { setAvisoTipoDocumento(true); return; } fotoBoletoInputRef.current?.click(); }}>
            <Camera size={12} /> tirar foto
          </button>
        </div>
        <input ref={boletoInputRef} type="file" multiple accept="application/pdf,image/jpeg,image/png"
          onChange={(e) => { const fs = Array.from(e.target.files || []); if (fs.length) setBoletoFiles((arr) => [...arr, ...fs]); e.target.value = ""; }}
          style={{ display: "none" }} />
        {/* capture="environment" abre a câmera do celular direto (mesmo padrão do
            app móvel — ver components/mobile/menu/FotosCampo.tsx); em desktop sem
            câmera, cai de volta no seletor de arquivo normal. */}
        <input ref={fotoBoletoInputRef} type="file" accept="image/*" capture="environment"
          onChange={(e) => { const fs = Array.from(e.target.files || []); if (fs.length) setBoletoFiles((arr) => [...arr, ...fs]); e.target.value = ""; }}
          style={{ display: "none" }} />
        {avisoTipoDocumento && (
          <p style={{ color: "var(--red)", fontSize: "0.74rem", marginTop: "0.4rem", fontWeight: 600 }}>
            <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
            Selecione o &ldquo;Tipo de documento&rdquo; acima antes de anexar ou tirar foto.
          </p>
        )}
        {boletoFiles.length > 0 && (
          <ul style={{ marginTop: "0.5rem", textAlign: "left", fontSize: "0.76rem" }}>
            {boletoFiles.map((f, i) => (
              <li key={i} className="flex items-center justify-between" style={{ padding: "0.15rem 0" }}>
                <span>{f.name}</span>
                <button type="button" className="btn-ghost" title="Remover" onClick={() => setBoletoFiles((arr) => arr.filter((_, j) => j !== i))} style={{ padding: "0.1rem 0.3rem" }}>
                  <X size={12} style={{ color: "var(--red)" }} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
          Opcional — fica disponível para consulta neste lançamento; não altera valores nem parcelas.
        </p>
      </div>

      {/* Pagamento imediato (só para lançamento não parcelado) */}
      {!parcelado && (
        <div className="card mt-3" style={{ background: "var(--fin-pagamento-bg)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <input type="checkbox" checked={jaPago} onChange={(e) => {
              const marcado = e.target.checked;
              setJaPago(marcado);
              // Ao marcar, pré-preenche com o valor líquido da nota (já
              // derivado acima) — só se ainda estiver vazio, e continua editável.
              if (marcado) setValorPago((atual) => atual || (valorLiquido > 0 ? valorLiquido.toFixed(2) : atual));
            }} /> Já foi {tipo === "despesa" ? "pago" : "recebido"}
          </label>
          {jaPago && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
              <Campo label="Data de pagamento"><input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></Campo>
              <Campo label="Valor pago (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={valorPago} onChange={(e) => setValorPago(e.target.value)} /></Campo>
              <Campo label="Conta bancária">
                <select style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                  <option value="">Selecione…</option>
                  {opcoes.contas_bancarias.map((c) => <option key={c}>{c}</option>)}
                </select>
              </Campo>
              <Campo label="Número do documento de pagamento"><input style={inputStyle} value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} /></Campo>
              <Campo label="Forma de pagamento">
                <select style={inputStyle} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                  <option value="">Selecione…</option>
                  {opcoes.formas_pagamento.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </Campo>
              {diferencaPagamento !== 0 && (
                <p style={{ gridColumn: "1 / -1", fontSize: "0.78rem", color: diferencaPagamento < 0 ? "var(--green-light)" : "var(--amber)" }}>
                  {diferencaPagamento < 0 ? `Desconto de ${formatBRL(Math.abs(diferencaPagamento))}` : `Acréscimo de ${formatBRL(diferencaPagamento)}`} em relação ao valor líquido (na baixa do pagamento, diferente do desconto/acréscimo da nota acima).
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" title="Salvar este lançamento financeiro" onClick={salvar} disabled={salvando || verificandoDuplicado}>
          {salvando ? "Salvando…" : verificandoDuplicado ? "Verificando…" : "Salvar lançamento"}
        </button>
      </div>

      {adicionarPara !== null && (
        <Modal title="Adicionar produto, serviço ou conta gerencial" onClose={() => setAdicionarPara(null)} width="900px">
          <div className="flex items-center gap-2 mb-3">
            <button type="button" title="Cadastrar um novo produto de estoque" onClick={() => setModoAdicionar("produto")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "produto" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "produto" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "produto" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "produto" ? 700 : 500 }}>
              Novo produto (estoque)
            </button>
            <button type="button" title="Cadastrar um novo serviço" onClick={() => setModoAdicionar("servico")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "servico" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "servico" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "servico" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "servico" ? 700 : 500 }}>
              Novo serviço
            </button>
            <button type="button" title="Cadastrar uma nova conta gerencial" onClick={() => setModoAdicionar("conta")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionar === "conta" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionar === "conta" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionar === "conta" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionar === "conta" ? 700 : 500 }}>
              Nova conta gerencial
            </button>
          </div>
          {modoAdicionar === "produto" ? (
            <NovoItemEstoque
              onCriado={(item) => {
                if (item?.nome && adicionarPara !== null) {
                  const patch: Partial<Item> = { produto: item.nome };
                  const conta = contaGerencialPadrao(tipo === "despesa" ? item.conta_gerencial_despesa_padrao : item.conta_gerencial_receita_padrao);
                  if (conta) { patch.codigo_conta_gerencial = conta.codigo; patch.nome_conta_gerencial = conta.nome; }
                  atualizarItem(adicionarPara, patch);
                  const nomeFornecedor = item.fornecedor_id ? fornecedoresPorId.get(item.fornecedor_id) : null;
                  if (nomeFornecedor) setFornecedor(nomeFornecedor);
                }
                carregarEstoque();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          ) : modoAdicionar === "servico" ? (
            <NovoServicoRapido
              onCriado={(servico) => {
                if (servico?.nome && adicionarPara !== null) atualizarItem(adicionarPara, { produto: servico.nome });
                carregarServicos();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          ) : (
            <NovaContaGerencial
              tipoSugerido={tipo}
              onCriado={(conta) => {
                if (adicionarPara !== null) atualizarItem(adicionarPara, { codigo_conta_gerencial: conta.codigo, nome_conta_gerencial: conta.nome });
                carregarOpcoes();
                setAdicionarPara(null);
              }}
              onCancelar={() => setAdicionarPara(null)}
            />
          )}
        </Modal>
      )}

      {abrirNovoFornecedor && (
        <Modal title={`Novo ${tipo === "receita" ? "cliente" : "fornecedor"}`} onClose={() => setAbrirNovoFornecedor(false)} width="480px">
          <NovoFornecedorRapido
            tipoSugerido={tipo}
            onCriado={(f) => {
              if (f?.nome) setFornecedor(f.nome);
              carregarOpcoes();
              fetchFornecedores().then((d) => setFornecedoresCadastro((d || []).map((x: any) => x.nome))).catch(() => {});
              setAbrirNovoFornecedor(false);
            }}
            onCancelar={() => setAbrirNovoFornecedor(false)}
          />
        </Modal>
      )}

      {confirmandoDuplicado && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "560px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Possível lançamento duplicado</strong></div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              Já existe {duplicados.length > 1 ? "lançamentos parecidos" : "um lançamento parecido"} com o mesmo fornecedor/cliente,
              valor próximo e data próxima. Confira antes de salvar de novo.
            </p>
            <div style={{ overflowX: "auto" }}>
              <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th></th><th>Novo lançamento</th>{duplicados.map((d) => <th key={d.id}>Nº {d.numero_lancamento || d.id}</th>)}</tr></thead>
                <tbody>
                  <tr><td style={{ color: "var(--text-muted)" }}>Fornecedor/cliente</td><td>{fornecedor || "—"}</td>{duplicados.map((d) => <td key={d.id}>{d.fornecedor_cliente || "—"}</td>)}</tr>
                  <tr><td style={{ color: "var(--text-muted)" }}>Valor</td><td>{formatBRL(valorLiquido)}</td>{duplicados.map((d) => <td key={d.id}>{formatBRL(d.valor_total || 0)}</td>)}</tr>
                  <tr><td style={{ color: "var(--text-muted)" }}>Data de emissão</td><td>{dataEmissao || "—"}</td>{duplicados.map((d) => <td key={d.id}>{d.data_emissao || d.data_competencia || "—"}</td>)}</tr>
                  <tr><td style={{ color: "var(--text-muted)" }}>Nº documento</td><td>{numeroDocumento || "—"}</td>{duplicados.map((d) => <td key={d.id}>{d.numero_documento || "—"}</td>)}</tr>
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-primary" title="Salvar mesmo assim (não é duplicado)" onClick={salvar}><Check size={14} /> Salvar mesmo assim</button>
              <button className="btn-ghost" title="Cancelar e revisar os dados" onClick={() => { setConfirmandoDuplicado(false); setDuplicados([]); }}><X size={14} /> Cancelar</button>
            </div>
          </div>
        </div>
      )}

      {confirmando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "420px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Confirmar diferença de valor</strong></div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Valor líquido: <strong style={{ color: "var(--text)" }}>{formatBRL(valorLiquido)}</strong><br />
              Valor {tipo === "despesa" ? "pago" : "recebido"}: <strong style={{ color: "var(--text)" }}>{formatBRL(Number(valorPago) || 0)}</strong><br />
              {diferencaPagamento < 0 ? "Desconto" : "Acréscimo"}: <strong style={{ color: diferencaPagamento < 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(Math.abs(diferencaPagamento))}</strong>
            </p>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-primary" title="Confirmar a diferença e salvar o lançamento" onClick={salvar}><Check size={14} /> Confirmar e salvar</button>
              <button className="btn-ghost" title="Cancelar sem salvar" onClick={() => setConfirmando(false)}><X size={14} /> Cancelar</button>
            </div>
          </div>
        </div>
      )}

      {popupVinculo && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "560px", maxWidth: "95vw" }}>
            <strong style={{ display: "block", marginBottom: "0.4rem" }}>Vincular a uma aplicação de vacina, exame ou visita reprodutiva?</strong>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              Lançamento {popupVinculo.numeroLancamento} salvo em conta que costuma pagar serviços reprodutivos, vacinas ou exames.
              Escolha um evento recente para vincular (rastreabilidade financeiro ↔ sanitário/reprodutivo) ou pule.
            </p>
            <div style={{ maxHeight: "40vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {[...popupVinculo.candidatos.servicos, ...popupVinculo.candidatos.vacinas, ...popupVinculo.candidatos.exames].map((c, i) => (
                <button key={`${c.tipo}-${i}`} type="button" className="btn-ghost"
                  style={{ textAlign: "left", fontSize: "0.82rem", padding: "0.5rem 0.7rem", border: "1px solid var(--border)", borderRadius: 6 }}
                  onClick={() => {
                    vincularEventoSanitarioReprodutivo({ tipo: c.tipo, ids: c.ids, numero_lancamento: popupVinculo.numeroLancamento })
                      .catch(() => {})
                      .finally(() => setPopupVinculo(null));
                  }}>
                  <strong>{c.rotulo}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                    {c.data ? new Date(c.data + "T00:00:00").toLocaleDateString("pt-BR") : "sem data"}{c.responsavel ? ` · ${c.responsavel}` : ""}
                  </div>
                </button>
              ))}
              {!popupVinculo.candidatos.servicos.length && !popupVinculo.candidatos.vacinas.length && !popupVinculo.candidatos.exames.length && (
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum evento recente ainda não vinculado.</p>
              )}
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-ghost" onClick={() => setPopupVinculo(null)}><X size={14} /> Não se aplica</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
