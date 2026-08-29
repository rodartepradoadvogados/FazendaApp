"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Upload, FileText, X, Check, AlertTriangle, Loader2, Plus, Trash2, Camera } from "lucide-react";
import {
  fetchOpcoesFinanceiro, fetchEstoque, fetchServicosCadastro, fetchFornecedores, fetchPlanoContas, criarLancamentoFinanceiro, importarXmlFinanceiro,
  lerDocumentoFinanceiro, formatBRL, fetchPedidos, fetchPossiveisDuplicados, anexarArquivoLancamento, type LancamentoParecido,
  type SugestoesCadastro, type SugestaoCadastroItem, criarTipoDocumento, criarFornecedorApelido, criarClassificacao,
  fetchContextoFornecedor, type ContextoFornecedor as ContextoFornecedorTipo,
  fetchCandidatosVinculoSanitarioReprodutivo, vincularEventoSanitarioReprodutivo, type CandidatoVinculoSanitarioReprodutivo,
  type PatrimonioPayload, fetchUltimoPrecoProduto, type UltimoPrecoProduto, today,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import ValeItemModal, { type ValeItemDados } from "@/components/ValeItemModal";
import { CampoMoeda } from "@/components/CampoMoeda";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovaContaGerencial from "@/components/NovaContaGerencial";
import NovoServicoRapido from "@/components/NovoServicoRapido";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { ServicoPicker } from "@/components/ServicoPicker";
import type { ContaPlano } from "@/lib/contaGerencial";
import { onPedidoLancamentoFinanceiro } from "@/lib/estoqueFinanceiroBridge";
import { onPedidoLancamentoFinanceiroDeEvento, type OrigemVinculoSanitarioReprodutivo } from "@/lib/vinculoSanitarioFinanceiroBridge";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
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
  // Override do centro de custo da nota (centroCusto, abaixo) só para este
  // item — "" (a maioria) usa o centro de custo da nota inteira. Útil quando
  // uma mesma nota/comprovante cobre itens de centros de custo diferentes.
  centro_custo: string;
  tipo_item: TipoItem; produto: string; descricao: string;
  quantidade: string; valor_unitario: string; valor_total: string; modoValor: ModoValor;
  // "estoque" escolhe de um item já cadastrado (EstoquePicker); "livre" digita
  // qualquer nome — compra de algo que não está (e não precisa estar) no
  // catálogo de estoque, ex.: "Supermercado", "Material de escritório". Some
  // não tem por que travar o lançamento a um cadastro prévio.
  modoProduto: "estoque" | "livre";
  // Checkbox "É vale de funcionário?" da linha do item — quando preenchido,
  // ao salvar o lançamento este item vira um vale de verdade (funcionário:
  // desconto na folha; empreiteiro/diarista: abatimento de empreitada/
  // contrato/diária) e some dos relatórios gerenciais (ver ValeItemModal e
  // rules/vale_item.py no backend). null (padrão) = item normal da fazenda.
  vale: ValeItemDados | null;
  // true só quando o produto/serviço veio de leitura automática (XML/OCR,
  // ver aplicarXml) — usado pra destacar quando o nome extraído não bate com
  // nada do catálogo (Estoque/ServicoCadastro). Item digitado manualmente em
  // "texto livre" NÃO entra nesse aviso: aquele modo existe justamente pra
  // compra que nunca vai virar item de estoque (ex.: "Supermercado") — a
  // inconsistência real é só quando o sistema "adivinhou" um nome sozinho.
  veioDeDocumento?: boolean;
};
const itemVazio = (): Item => ({
  codigo_conta_gerencial: "", nome_conta_gerencial: "", centro_custo: "", tipo_item: "produto", produto: "", descricao: "",
  quantidade: "", valor_unitario: "", valor_total: "", modoValor: "unitario", modoProduto: "estoque",
  vale: null,
});

type Opcoes = {
  contas_gerenciais: { codigo: string; nome: string }[];
  centros_custo: string[];
  fornecedores: string[];
  produtos: string[];
  contas_bancarias: string[];
  tipos_documento: string[];
  formas_pagamento: string[];
  classificacoes: string[];
};

const OPCOES_VAZIAS: Opcoes = { contas_gerenciais: [], centros_custo: [], fornecedores: [], produtos: [], contas_bancarias: [], tipos_documento: [], formas_pagamento: [], classificacoes: [] };

// Valor de nascença do centro de custo — perfil típico da fazenda (ver
// mesmo default no backend, financeiro.py:criar_lancamento). Nasce assim
// sozinho, sem o usuário tocar em nada: por isso a checagem de "sujo" (ver
// `sujo` abaixo) compara centroCusto contra ESTE valor, não testa "é
// não-vazio" — do contrário todo formulário nasceria sujo (bug já corrigido).
const CENTRO_CUSTO_PADRAO = "Pecuária Leiteira";

// Mini-observação abaixo do produto/serviço escolhido no item — último valor
// unitário pago (ou recebido) naquele mesmo item, independente da quantidade
// ou do valor deste lançamento (vale tanto pra produto do estoque quanto pra
// serviço). Sem histórico não inventa número: some por completo, nunca
// mostra "R$ 0,00" nem "sem dados" (ver fetchUltimoPrecoProduto em lib/api.ts).
function UltimoPrecoObservacao({ produto, tipo }: { produto: string; tipo: "despesa" | "receita" }) {
  const [ultimo, setUltimo] = useState<UltimoPrecoProduto>(null);
  useEffect(() => {
    const nome = produto.trim();
    if (!nome) { setUltimo(null); return; }
    let cancelado = false;
    fetchUltimoPrecoProduto(nome).then((r) => { if (!cancelado) setUltimo(r); }).catch(() => { if (!cancelado) setUltimo(null); });
    return () => { cancelado = true; };
  }, [produto]);
  if (!ultimo) return null;
  const dataFmt = ultimo.data ? new Date(`${ultimo.data}T00:00:00`).toLocaleDateString("pt-BR") : null;
  return (
    <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
      {tipo === "receita" ? "Último valor recebido" : "Último valor pago"}: <strong style={{ color: "var(--text)" }}>{formatBRL(ultimo.valor_unitario)}</strong>
      {dataFmt ? ` em ${dataFmt}` : ""}{ultimo.numero_lancamento ? ` (${ultimo.numero_lancamento})` : ""}
    </p>
  );
}

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
export type PrefillPedido = {
  id: number;
  fornecedorCliente?: string | null;
  itens: {
    produto: string; tipo_item: "produto" | "servico"; quantidade?: number | null;
    valor_unitario_estimado?: number | null; valor_total_estimado: number;
    codigo_conta_gerencial?: string | null; nome_conta_gerencial?: string | null;
  }[];
};

export function FormFinanceiro({ tipo, responsaveis, onSujo, onSalvo, onArquivoParaLeitura, apresentacaoModais, prefillPedido }: {
  tipo: "despesa" | "receita"; responsaveis: string[]; onSujo?: (sujo: boolean) => void;
  // Recebe a mesma mensagem de sucesso mostrada dentro do formulário — o pai
  // (contas a pagar/receber) reaproveita pra mostrar a confirmação no topo da
  // tela depois que o modal fecha (ver AvisoSalvo em app/financeiro/page.tsx).
  onSalvo?: (mensagem: string) => void;
  // Avisa o pai assim que um PDF/JPEG/PNG é escolhido pra leitura automática —
  // usado pelo ModalDivididoDocumento pra mostrar a prévia do documento ao
  // lado do formulário (ver app/financeiro/page.tsx).
  onArquivoParaLeitura?: (file: File) => void;
  // Como o ValeItemModal (checkbox "É vale de funcionário?" de cada item)
  // aparece: "modal" (pop-up, desktop) ou "tela" (tela cheia com botão
  // voltar, app mobile — ver components/mobile/lancar/FormFinanceiroApp.tsx).
  // Default "modal": os demais usos deste formulário fora do app não passam
  // a prop e continuam com o pop-up.
  apresentacaoModais?: "modal" | "tela";
  // Pré-preenche a partir de um Pedido — vincula pedido_id e carrega os itens
  // dele, prontos pra só completar o que é exclusivo do financeiro (pagamento,
  // parcelamento, anexo). Ver botão "Lançar pagamento" em app/pedidos/page.tsx.
  prefillPedido?: PrefillPedido | null;
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

  // Um item lido automaticamente de XML/OCR (`veioDeDocumento`) que não bate
  // (nome exato, sem diferenciar maiúsculas) com nada do catálogo — sem essa
  // checagem, um nome que o sistema "adivinhou" sozinho (ex.: "TEATSEAL",
  // vindo de uma nota fiscal) entrava no lançamento como texto solto: sem
  // estocável, sem centro de custo padrão, invisível pras telas de aplicação.
  // Item digitado manualmente em "texto livre" não entra aqui de propósito.
  function itemNaoCadastradoDeDocumento(it: Item): boolean {
    if (!it.veioDeDocumento || !it.produto.trim()) return false;
    const nome = it.produto.trim().toLowerCase();
    if (it.tipo_item === "servico") return !sugestoesServico.some((s) => s.toLowerCase() === nome);
    return !produtosEstoque.some((p) => p.nome.toLowerCase() === nome);
  }

  // Modal "+ Adicionar" (novo produto de estoque, novo serviço ou nova conta
  // gerencial), aberto a partir de um item específico da nota — o item fica
  // marcado em `adicionarPara` para saber onde aplicar o resultado ao salvar.
  const [adicionarPara, setAdicionarPara] = useState<number | null>(null);
  const [modoAdicionar, setModoAdicionar] = useState<"produto" | "servico" | "conta">("produto");
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  // "Associar a produto/serviço já existente" — alternativa a "cadastrar
  // novo" para um item vindo do documento lido sem bater com o cadastro
  // (ver itemNaoCadastradoDeDocumento). Nada foi salvo ainda neste ponto —
  // associar aqui é só trocar o texto do item pelo nome já cadastrado.
  const [associarPara, setAssociarPara] = useState<number | null>(null);

  // Checkbox "É vale de funcionário?" de cada item — `valeAbertoPara` é o
  // índice do item cujo ValeItemModal está aberto (marcar ou "alterar" um já
  // marcado); `desmarcandoVale` é o índice pedindo confirmação antes de
  // remover a marcação de um item AINDA NÃO SALVO (aqui não existe vale de
  // verdade a excluir — essa pergunta acontece em FormEditarLancamento,
  // app/financeiro/page.tsx, para um item já salvo com vale já criado).
  const [valeAbertoPara, setValeAbertoPara] = useState<number | null>(null);
  const [desmarcandoVale, setDesmarcandoVale] = useState<number | null>(null);
  function pedirDesmarcarVale(idx: number) { setDesmarcandoVale(idx); }
  // 409 de "estourou 40% do salário" recebido ao SALVAR O LANÇAMENTO inteiro
  // (não da marcação isolada de um item, que aqui só grava estado local — o
  // vale de verdade só nasce no POST /financeiro/lancamentos, ver salvar()
  // abaixo). Reabre o ValeItemModal do item ofensor já mostrando o aviso: a
  // 1ª tentativa de confirmar dentro do modal reproduz o mesmo erro (ver
  // onConfirmar do ValeItemModal, JSX abaixo); ao clicar "Lançar mesmo
  // assim", o item guarda `confirmar: true` para a próxima tentativa de
  // salvar. Heurística (o backend não devolve QUAL item estourou): o
  // primeiro item marcado como vale de folha que ainda não tem `confirmar`.
  const [pendingErro409, setPendingErro409] = useState<{ idx: number; mensagem: string; competencias_excedidas: { competencia: string; total: number }[] } | null>(null);

  const [itens, setItens] = useState<Item[]>([itemVazio()]);
  // Pré-preenchimento via query string (ex.: botão "Lançar financeiro" do
  // calendário sanitário → /lancamentos?ir=financeiro_despesa&servico=Exame%20de%20brucelose).
  // "patrimonio_*" vem de Controle Financeiro > Patrimônio > "+ Novo
  // patrimônio" > "É uma compra agora?" — a criação do item de Patrimônio só
  // acontece quando ESTE lançamento for salvo (ver criarPatrimonio abaixo e
  // POST /financeiro/lancamentos, campo criar_patrimonio).
  const [criarPatrimonio, setCriarPatrimonio] = useState<PatrimonioPayload | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const servico = params.get("servico");
    if (servico) setItens([{ ...itemVazio(), tipo_item: "servico", produto: servico }]);
    const patrimonioNome = params.get("patrimonio_nome");
    if (patrimonioNome) {
      const valor = params.get("patrimonio_valor") || "";
      setItens([{ ...itemVazio(), tipo_item: "produto", produto: patrimonioNome, valor_total: valor, modoValor: "total" }]);
      setCriarPatrimonio({
        nome: patrimonioNome,
        tipo: params.get("patrimonio_tipo") || null,
        valor_total: valor ? Number(valor) : null,
        depreciavel: params.get("patrimonio_depreciavel") !== "0",
      });
    }
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
  // "Pecuária Leiteira" é o valor padrão do centro de custo, não trabalho do
  // usuário — a checagem de "sujo" logo abaixo compara contra ESTE valor em
  // vez de testar "é não-vazio" (ver CENTRO_CUSTO_PADRAO).
  const [centroCusto, setCentroCusto] = useState(CENTRO_CUSTO_PADRAO);
  const [classificacao, setClassificacao] = useState("");
  const [novaClassificacaoAberta, setNovaClassificacaoAberta] = useState(false);
  const [novaClassificacaoNome, setNovaClassificacaoNome] = useState("");
  const [salvandoClassificacao, setSalvandoClassificacao] = useState(false);
  const [fornecedor, setFornecedor] = useState("");
  // Coluna de contexto (esquerda): histórico do fornecedor/cliente escolhido
  // acima — em aberto, último lançamento, últimos lançamentos, documentos já
  // anexados. Só leitura; recarrega sempre que o fornecedor muda.
  const [contextoFornecedor, setContextoFornecedor] = useState<ContextoFornecedorTipo | null>(null);
  useEffect(() => {
    const nome = fornecedor.trim();
    if (!nome) { setContextoFornecedor(null); return; }
    let cancelado = false;
    fetchContextoFornecedor(nome, tipo).then((ctx) => { if (!cancelado) setContextoFornecedor(ctx); }).catch(() => { if (!cancelado) setContextoFornecedor(null); });
    return () => { cancelado = true; };
  }, [fornecedor, tipo]);
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
  // Pré-preenchimento vindo de um Pedido (ver app/pedidos/page.tsx, botão
  // "Lançar pagamento"/"Transformar em compra") — vincula o pedido_id e já
  // traz os itens dele, faltando só o que é exclusivo do financeiro
  // (pagamento, parcelamento, anexo). Um pedido já "atendido" fica de fora de
  // `pedidosAbertos` (linha acima) — sem isto o seletor mostraria em branco
  // mesmo com o vínculo funcionando por baixo.
  useEffect(() => {
    if (!prefillPedido) return;
    setPedidoId(String(prefillPedido.id));
    setPedidosAbertos((prev) => (prev.some((p) => p.id === prefillPedido.id) ? prev : [
      ...prev,
      { id: prefillPedido.id, numero_pedido: `Pedido #${prefillPedido.id}`, fornecedor_cliente: prefillPedido.fornecedorCliente || null, valor_total_estimado: prefillPedido.itens.reduce((a, i) => a + i.valor_total_estimado, 0) },
    ]));
    if (prefillPedido.fornecedorCliente) setFornecedor(prefillPedido.fornecedorCliente);
    if (prefillPedido.itens.length) {
      setItens(prefillPedido.itens.map((i) => ({
        ...itemVazio(),
        tipo_item: i.tipo_item,
        produto: i.produto,
        codigo_conta_gerencial: i.codigo_conta_gerencial || "",
        nome_conta_gerencial: i.nome_conta_gerencial || "",
        quantidade: i.quantidade != null ? String(i.quantidade) : "",
        valor_unitario: i.valor_unitario_estimado != null ? String(i.valor_unitario_estimado) : "",
        valor_total: String(i.valor_total_estimado),
        modoValor: i.valor_unitario_estimado != null ? "unitario" : "total",
      })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillPedido?.id]);
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
  // Anexos deste lançamento — UM local só (dropzone acima, "leitura
  // automática"), pra qualquer documento: nota, boleto, orçamento,
  // comprovante de pagamento etc. Antes eram 3 dropzones separadas (esta +
  // uma dentro do bloco "já foi pago" + o próprio arquivo usado na leitura
  // automática, que nunca ficava anexado) — juntar tudo aqui é o que faz
  // "arrastar o documento" também GUARDAR o arquivo, não só ler os dados.
  // Cada arquivo carrega sua PRÓPRIA categoria/número/data (um lançamento
  // pode reunir vários tipos de documento — ver Central de Documentos).
  // `decidido`: false enquanto o usuário ainda não passou pelo popup "Deseja
  // importar os dados desse documento?" (ver `resolverImportacaoAnexos`) —
  // é o que torna a leitura automática uma ESCOLHA explícita depois de
  // "Salvar" em vez de disparar sozinha ao anexar (ver stageArquivo).
  type AnexoStaged = { file: File; categoria: string; numero_documento: string; data_documento: string; decidido: boolean };
  const [anexosStaged, setAnexosStaged] = useState<AnexoStaged[]>([]);
  // Popup "Deseja importar os dados desse documento?" (ou, com mais de um
  // pendente, "de qual documento?") — aberto pelo botão "Salvar" da área de
  // anexo. Só existem enquanto há algum anexo com `decidido: false`.
  const [importarPopupAberto, setImportarPopupAberto] = useState(false);
  const anexosPendentesImportacao = anexosStaged.filter((a) => !a.decidido);
  const anexoInputRef = useRef<HTMLInputElement>(null);
  const fotoAnexoInputRef = useRef<HTMLInputElement>(null);
  // Popup "miniatura + tipo de documento" que abre logo depois de anexar —
  // guarda o próprio File (não um índice) porque vários arquivos podem ser
  // processados em sequência, cada um com sua leitura assíncrona; um índice
  // ficaria velho entre um `await` e outro, a identidade do arquivo não.
  const [categoriaPopupFile, setCategoriaPopupFile] = useState<File | null>(null);
  const [novoTipoDocumentoAberto, setNovoTipoDocumentoAberto] = useState(false);
  const [novoTipoDocumentoNome, setNovoTipoDocumentoNome] = useState("");
  const [salvandoTipoDocumento, setSalvandoTipoDocumento] = useState(false);
  // A partir do 2º documento anexado, cada novo documento tenta identificar
  // MAIS dados do lançamento: campo que já está em branco é preenchido
  // direto (com um aviso do que foi acrescentado); campo que já tem um
  // valor DIFERENTE do que este documento traz vira uma divergência — o
  // usuário escolhe manter o atual ou usar o deste documento (nunca
  // sobrescreve sozinho).
  const [notaCamposIdentificados, setNotaCamposIdentificados] = useState<string | null>(null);
  const [divergenciasDocumento, setDivergenciasDocumento] = useState<
    { campo: string; atual: string; novo: string; escolha: "atual" | "novo" }[] | null
  >(null);
  // Quando a leitura não bate EXATO com nada do cadastro de fornecedores
  // (nem sugestão "provável"), oferece guardar o texto bruto da nota como
  // apelido — da próxima vez que aparecer, resolve sozinho (ver
  // FornecedorClienteApelido, por fazenda).
  const [apelidoBanner, setApelidoBanner] = useState<{ nomeBruto: string } | null>(null);
  const [salvandoApelido, setSalvandoApelido] = useState(false);

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
  const [confirmandoItemNaoCadastrado, setConfirmandoItemNaoCadastrado] = useState(false);
  const [verificandoDuplicado, setVerificandoDuplicado] = useState(false);

  // Sugestões de casamento com o cadastro (fornecedor/produto/serviço
  // parecido, mas não idêntico) devolvidas junto da leitura de XML/documento —
  // ver aplicarXml abaixo e backend/fazenda/rules/sugestao_documento.py.
  // Cada checkbox nasce marcada (linha ausente de `sugestoesEscolhidas` conta
  // como "usar", ver aplicarSugestoesEscolhidas).
  const [sugestoesCadastro, setSugestoesCadastro] = useState<SugestoesCadastro | null>(null);
  const [sugestoesEscolhidas, setSugestoesEscolhidas] = useState<Record<string, boolean>>({});

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
    // O <input type="date"> dispara onChange a cada dígito digitado (não só
    // quando a data fica completa) — ao digitar o ano dígito a dígito, o
    // primeiro dígito chega aqui como um ano de 1 dígito só, zero-padado pelo
    // próprio input (ex.: "0002-08-05" ao digitar o "2" de 2026, já com
    // dia/mês prontos). O regex sozinho NÃO pega esse caso — "0002-08-05" já
    // tem 4 dígitos no ano, então batia como "completo" mesmo sendo um ano
    // ainda em digitação — por isso o bug persistia mesmo com a checagem de
    // formato (relatado: vencimento/previsão de entrada/data do pedido
    // nascendo em "0002"). Precisa também rejeitar ano implausível.
    if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) return;
    if (Number(valor.slice(0, 4)) < 1900) return;
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

  // ── Resumo fixo (rodapé sticky) ──────────────────────────────────────
  // Só leitura, nenhum cálculo novo — reaproveita os mesmos valores já
  // derivados acima (valorLiquido, parcelas, centroCusto...) e só resume
  // o que este lançamento reflete em estoque/pedido/DRE, pra ficar visível
  // sem precisar rolar até o fim de nenhuma das duas colunas.
  const numeroParcelasResumo = parcelado ? (parcelas.length || Math.max(1, Math.round(Number(qtdParcelas) || 0))) : 1;
  const primeiroVencimentoResumo = parcelado ? (parcelas[0]?.data_vencimento || null) : (dataVencimento || null);
  // Itens que de fato mexem em saldo de estoque (produto do estoque E
  // marcado como estocável no cadastro — os demais são só organização
  // financeira, ver comentário de `modoProduto` acima).
  const itensComReflexoEstoque = useMemo(
    () => itens.filter((i) => i.tipo_item === "produto" && i.produto.trim() && i.modoProduto === "estoque"
      && produtosEstoque.some((p) => p.nome === i.produto && p.estocavel)),
    [itens, produtosEstoque],
  );
  const pedidoVinculadoResumo = useMemo(
    () => (pedidoId ? pedidosAbertos.find((p) => String(p.id) === pedidoId) || null : null),
    [pedidoId, pedidosAbertos],
  );

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
    setCentroCusto(CENTRO_CUSTO_PADRAO); setClassificacao(""); setFornecedor(""); setResponsavel(""); setTipoDocumento("");
    setNumeroDocumento(""); setNumeroOsOrcamento(""); setNumeroBoleto("");
    setDataEmissao(""); setDataVencimento(""); setDataPrevistaEntrada(""); setDataPedido(""); setEntregue(false);
    entregueTocadoRef.current = false;
    setPedidoId("");
    setDesconto(""); setAcrescimo("");
    setParcelado(false); setQtdParcelas("2"); setParcelas([]); setAnexosStaged([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
    setXmlTexto(""); setXmlAberto(false);
    setNotaCamposIdentificados(null); setDivergenciasDocumento(null); setApelidoBanner(null);
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
      itens, centroCusto, classificacao, fornecedor, responsavel, tipoDocumento, numeroDocumento, numeroOsOrcamento, numeroBoleto,
      dataEmissao, dataVencimento, dataPrevistaEntrada, dataPedido, pedidoId, entregue, desconto, acrescimo,
      parcelado, qtdParcelas, parcelas, jaPago, dataPagamento, valorPago, contaBancaria,
      numeroDocumentoPagamento, formaPagamento, salvoEm: new Date().toISOString(),
    };
  }
  function aplicarRascunho(d: any) {
    if (!d) return;
    setItens(Array.isArray(d.itens) && d.itens.length ? d.itens : [itemVazio()]);
    setCentroCusto(d.centroCusto || CENTRO_CUSTO_PADRAO); setClassificacao(d.classificacao || ""); setFornecedor(d.fornecedor || ""); setResponsavel(d.responsavel || "");
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

  // Está "sujo" (com trabalho a perder) se já tem item preenchido ou dados da
  // nota. `centroCusto` nasce com um valor padrão (CENTRO_CUSTO_PADRAO) — não
  // é trabalho do usuário, então entra na conta comparado contra o padrão,
  // não testado como "é não-vazio" (senão o formulário nasceria sujo).
  const sujo = useMemo(() => {
    const temItem = itens.some((i) => i.produto.trim() || i.nome_conta_gerencial.trim() || i.valor_total.trim() || i.descricao.trim());
    const centroCustoAlterado = centroCusto !== CENTRO_CUSTO_PADRAO;
    return Boolean(temItem || fornecedor || numeroDocumento || centroCustoAlterado || dataEmissao || Number(desconto) || Number(acrescimo) || jaPago);
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

  // Normaliza pra comparar (maiúscula/espaço não conta como divergência de verdade).
  function normalizarComparacao(v: string): string {
    return v.trim().toLowerCase().replace(/\s+/g, " ");
  }

  // Aplica um campo de texto simples SEM nunca sobrescrever silenciosamente:
  // vazio → preenche e anota em `preenchidos`; já preenchido e IGUAL → nada;
  // já preenchido e DIFERENTE → vira divergência (usuário decide depois, ver
  // `divergenciasDocumento`). É a base do "documento a partir do 2º tenta
  // identificar mais dados, com confirmação" pedido pelo usuário.
  function aplicarCampoIdentificado(
    label: string, atual: string, novo: string | null | undefined,
    aplicar: (v: string) => void, preenchidos: string[], conflitos: { campo: string; atual: string; novo: string; escolha: "atual" | "novo" }[],
  ) {
    if (!novo) return;
    if (!atual.trim()) { aplicar(novo); preenchidos.push(`${label}: ${novo}`); return; }
    if (normalizarComparacao(atual) !== normalizarComparacao(novo)) {
      conflitos.push({ campo: label, atual, novo, escolha: "atual" });
    }
  }

  function aplicarXml(dados: any) {
    const preenchidos: string[] = [];
    const conflitos: { campo: string; atual: string; novo: string; escolha: "atual" | "novo" }[] = [];

    aplicarCampoIdentificado("Número do documento", numeroDocumento, dados.numero_documento, setNumeroDocumento, preenchidos, conflitos);
    aplicarCampoIdentificado("Data de emissão", dataEmissao, dados.data_emissao, setDataEmissao, preenchidos, conflitos);
    aplicarCampoIdentificado("Fornecedor/cliente", fornecedor, dados.fornecedor_cliente, setFornecedor, preenchidos, conflitos);
    if (!tipoDocumento) setTipoDocumento("Nota fiscal");

    // Itens: só substitui a lista enquanto ela ainda está no estado "vazio
    // padrão" (nenhum item com produto preenchido) — um 2º documento que
    // também lista itens NUNCA sobrescreve os que o usuário já revisou;
    // só avisa que existem itens ali, pra conferência manual.
    const itensAindaVazios = itens.length <= 1 && !itens.some((i) => i.produto.trim());
    if (Array.isArray(dados.itens) && dados.itens.length) {
      if (itensAindaVazios) {
        setItens(dados.itens.map((it: any) => ({
          codigo_conta_gerencial: "", nome_conta_gerencial: "", centro_custo: "", tipo_item: "produto",
          produto: it.produto || "", descricao: "",
          quantidade: it.quantidade != null ? String(it.quantidade) : "",
          valor_unitario: it.valor_unitario != null ? String(it.valor_unitario) : "",
          valor_total: it.valor_total != null ? String(it.valor_total) : "",
          // Preserva o total informado na nota (não recalcula por quantidade × unitário).
          modoValor: it.valor_total != null ? "total" : "unitario",
          // Nome extraído da nota, não necessariamente igual a um item já
          // cadastrado no estoque — começa em texto livre pra não forçar o
          // usuário a bater o nome exato antes de poder editar.
          modoProduto: "livre",
          vale: null,
          veioDeDocumento: true,
        })));
        preenchidos.push(`${dados.itens.length} item(ns) do documento`);
      } else {
        conflitos.push({ campo: "Itens", atual: `${itens.length} item(ns) já preenchido(s)`, novo: `${dados.itens.length} item(ns) neste documento`, escolha: "atual" });
      }
    } else if (dados.valor_total != null && itensAindaVazios) {
      setItens([{ ...itemVazio(), produto: "Importado do XML", valor_total: String(dados.valor_total), modoValor: "total" }]);
    }
    if (Array.isArray(dados.parcelas) && dados.parcelas.length && !parcelado) {
      setParcelado(true);
      setQtdParcelas(String(dados.parcelas.length));
      setParcelas(dados.parcelas.map((p: any) => ({ data_vencimento: p.data_vencimento || "", valor: p.valor != null ? String(p.valor) : "" })));
    }

    setNotaCamposIdentificados(preenchidos.length && anexosStaged.length > 0 ? `Também identifiquei neste documento: ${preenchidos.join("; ")}.` : null);
    setDivergenciasDocumento(conflitos.length ? conflitos : null);

    // Fornecedor/produto/serviço parecido mas não idêntico no cadastro —
    // mostra o quadro de confirmação (ver JSX abaixo) só quando há alguma
    // sugestão de verdade; senão limpa qualquer sugestão de uma leitura anterior.
    const sug: SugestoesCadastro | undefined = dados.sugestoes_cadastro;
    if (sug && (sug.fornecedor || sug.itens.length)) {
      setSugestoesCadastro(sug);
      setSugestoesEscolhidas({});
    } else {
      setSugestoesCadastro(null);
    }
    // Nome bruto da nota não bateu EXATO com nada do cadastro (nem sugestão
    // "provável") — oferece ensinar o sistema pra próxima vez (ver
    // FornecedorClienteApelido). "exato" e já resolvido por apelido salvo
    // não precisam de nada.
    if (dados.fornecedor_cliente && !dados.fornecedor_resolvido_por_apelido
      && sug?.fornecedor_confianca && sug.fornecedor_confianca !== "exato") {
      setApelidoBanner({ nomeBruto: dados.fornecedor_cliente });
    } else {
      setApelidoBanner(null);
    }
  }

  function aplicarEscolhaDivergencia(indice: number, escolha: "atual" | "novo") {
    setDivergenciasDocumento((arr) => arr ? arr.map((d, i) => i === indice ? { ...d, escolha } : d) : arr);
  }

  function confirmarDivergencias() {
    if (!divergenciasDocumento) return;
    for (const d of divergenciasDocumento) {
      if (d.escolha !== "novo") continue;
      if (d.campo === "Número do documento") setNumeroDocumento(d.novo);
      else if (d.campo === "Data de emissão") setDataEmissao(d.novo);
      else if (d.campo === "Fornecedor/cliente") setFornecedor(d.novo);
      // "Itens" não tem valor pra aplicar automaticamente (a lista já
      // preenchida não é substituída sozinha) — usar "novo" aqui só serve
      // de lembrete visual de que há itens do documento pra conferir à mão.
    }
    setDivergenciasDocumento(null);
  }

  async function salvarApelidoFornecedor() {
    if (!apelidoBanner) return;
    setSalvandoApelido(true);
    try {
      await criarFornecedorApelido(apelidoBanner.nomeBruto, fornecedor);
      setApelidoBanner(null);
    } catch {
      // Falha ao salvar apelido não impede seguir com o lançamento — só
      // mantém o banner pra tentar de novo, sem travar o formulário.
    } finally {
      setSalvandoApelido(false);
    }
  }

  function aplicarSugestoesEscolhidas() {
    if (!sugestoesCadastro) return;
    if (sugestoesCadastro.fornecedor && sugestoesEscolhidas["fornecedor"] !== false) {
      setFornecedor(sugestoesCadastro.fornecedor.candidato);
    }
    if (sugestoesCadastro.itens.length) {
      const porIndice = new Map(
        sugestoesCadastro.itens
          .filter((s) => s.indice != null && sugestoesEscolhidas[`item-${s.indice}`] !== false)
          .map((s) => [s.indice as number, s]),
      );
      if (porIndice.size) {
        setItens((arr) => arr.map((it, idx) => {
          const s = porIndice.get(idx);
          return s ? { ...it, produto: s.candidato, tipo_item: s.tipo === "servico" ? "servico" : "produto" } : it;
        }));
      }
    }
    setSugestoesCadastro(null);
  }

  async function importarXml(texto: string, arquivo?: File) {
    if (!texto.trim()) return;
    setImportando(true); setErroXml(null);
    try {
      const dados = await importarXmlFinanceiro(texto);
      aplicarXml(dados);
      setXmlAberto(false);
      if (arquivo) preencherAnexoAposLeitura(arquivo, "Nota fiscal", dados);
    } catch (e: any) {
      setErroXml(e.message || "Erro ao ler o XML");
    } finally {
      setImportando(false);
    }
  }

  // Adiciona o arquivo à lista de anexos deste lançamento (staged — sobe de
  // verdade só ao salvar, ver `salvar()`) e abre o popup de categorização
  // (miniatura + tipo de documento, com opção de criar um tipo novo).
  // `categoriaSugerida`: "Nota fiscal"/"Recibo"/"Boleto" quando dá pra
  // adivinhar pelo próprio documento; senão usa o Tipo de documento já
  // escolhido no lançamento (se houver) ou deixa em branco pro usuário decidir.
  function stageArquivo(file: File, categoriaSugerida?: string) {
    setAnexosStaged((arr) => [...arr, { file, categoria: categoriaSugerida || tipoDocumento || "", numero_documento: "", data_documento: "", decidido: false }]);
    setCategoriaPopupFile(file);
  }

  // Depois que a leitura automática roda, pré-preenche número/data DESTE
  // arquivo especificamente (o que está impresso no próprio documento) —
  // poupa o usuário de digitar nos dois lugares (nº do lançamento vs. nº do
  // anexo, que podem ser o mesmo dado, mas nem sempre: um lançamento com
  // nota + boleto tem um número de cada).
  function preencherAnexoAposLeitura(file: File, categoria: string, dados: any) {
    setAnexosStaged((arr) => arr.map((a) => a.file === file ? {
      ...a, categoria: a.categoria || categoria,
      numero_documento: a.numero_documento || dados.numero_documento || dados.linha_digitavel || "",
      data_documento: a.data_documento || dados.data_emissao || dados.data_vencimento || "",
    } : a));
  }

  // Nota fiscal ou recibo em PDF/JPEG/PNG — leitura automática via IA.
  // Recibo (já pago) preenche o pagamento imediato; nota fiscal nasce em aberto.
  // Boleto: se a IA achou "parcela X/Y" no próprio boleto, já monta o
  // parcelamento com essa quantidade; senão, deixa como lançamento único e
  // é o usuário quem decide (documento avulso ou marcar como parcelado).
  function aplicarExtracaoDocumento(dados: any, file: File) {
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
    preencherAnexoAposLeitura(file, ehRecibo ? "Recibo" : ehBoleto ? "Boleto" : "Nota fiscal", dados);
  }

  async function lerDocumentoAnexado(file: File) {
    setImportando(true); setErroXml(null);
    try {
      const dados = await lerDocumentoFinanceiro(file);
      aplicarExtracaoDocumento(dados, file);
      setXmlAberto(false);
    } catch (e: any) {
      setErroXml(e.message || "Erro ao ler o documento");
    } finally {
      setImportando(false);
    }
  }

  // Antes, só passava pela leitura automática (IA) quando file.type fosse
  // EXATAMENTE "application/pdf"/"image/jpeg"/"image/png" — qualquer outra
  // coisa (foto salva como "image/jpg" por câmera/app mais antigo, WEBP,
  // HEIC/HEIF de iPhone, ou MIME vazio, comum em drag-and-drop de alguns
  // gerenciadores de arquivo) caía no ramo de XML: o binário da imagem era
  // lido como texto e mandado pro parser de NF-e, que sempre falhava com
  // 400 "Não foi possível ler o XML" — daí o erro 400 ao anexar/arrastar
  // documento normal em Contas a pagar. O backend (/financeiro/ler-documento)
  // já tolera esses formatos (ver MIME_ACEITOS em leitura_documento.py); a
  // checagem aqui só precisa distinguir XML (rota de texto) do resto
  // (rota de leitura de documento/imagem via IA).
  function ehArquivoXml(file: File) {
    return file.type === "text/xml" || file.type === "application/xml" || /\.xml$/i.test(file.name);
  }

  // Processa UM arquivo: só anexa (staged) — NUNCA dispara leitura automática
  // sozinho. Antes, anexar E ler eram a mesma ação implícita: qualquer PDF/
  // imagem solto aqui já saía chamando a API de leitura na hora, então um
  // documento grande (OCR demorado, ver run_in_threadpool no backend) ou uma
  // instabilidade de rede naquele instante fazia o anexo inteiro falhar —
  // mesmo o arquivo já estando só localmente "staged", sem depender de rede
  // nenhuma pra isso. Agora anexar é sempre local (nunca falha por causa da
  // API); ler os dados é uma escolha explícita do usuário depois de "Salvar"
  // (ver `resolverImportacaoAnexos`, disparado pelo popup "Deseja importar os
  // dados desse documento?").
  function tratarArquivo(file: File) {
    stageArquivo(file, ehArquivoXml(file) ? "Nota fiscal" : undefined);
    if (!ehArquivoXml(file)) onArquivoParaLeitura?.(file);
  }
  function processarArquivos(files: File[]) {
    files.forEach(tratarArquivo);
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) processarArquivos(files);
  }
  function onFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length) processarArquivos(files);
    e.target.value = "";
  }

  // Chamado pelo popup "Deseja importar os dados desse documento?" (botão
  // "Salvar" da área de anexo — ver JSX abaixo). `arquivoEscolhido`: o
  // documento cujos dados o usuário quer usar pra pré-preencher o
  // formulário, ou null se a resposta foi "Não"/"Não importar". TODOS os
  // anexos que estavam pendentes de decisão (não só o escolhido) saem
  // marcados como `decidido` — o usuário só importa de UM documento por vez;
  // os outros ficam anexados normalmente, sem leitura.
  async function resolverImportacaoAnexos(arquivoEscolhido: File | null) {
    const pendentes = anexosPendentesImportacao.map((a) => a.file);
    setAnexosStaged((arr) => arr.map((a) => (pendentes.includes(a.file) ? { ...a, decidido: true } : a)));
    setImportarPopupAberto(false);
    if (!arquivoEscolhido) return;
    if (ehArquivoXml(arquivoEscolhido)) {
      await importarXml(await arquivoEscolhido.text(), arquivoEscolhido);
    } else {
      await lerDocumentoAnexado(arquivoEscolhido);
    }
  }

  function montarPayload() {
    return {
      tipo,
      itens: itens
        .filter((i) => i.produto.trim())
        .map((i) => ({
          codigo_conta_gerencial: i.codigo_conta_gerencial || null,
          nome_conta_gerencial: i.nome_conta_gerencial || null,
          centro_custo: i.centro_custo || null,
          produto: i.produto.trim(),
          tipo_item: i.tipo_item,
          descricao: i.descricao || null,
          quantidade: i.quantidade ? Number(i.quantidade) : null,
          valor_unitario: i.valor_unitario ? Number(i.valor_unitario) : null,
          valor_total: Number(i.valor_total) || 0,
          // Só os campos do contrato (ValeItemNovoIn) — pessoa_nome/origem_label
          // são de UI (ver checkbox acima e ValeItemModal), não vão no payload.
          vale: i.vale ? {
            pessoa_id: i.vale.pessoa_id, modo: i.vale.modo,
            parcelas: i.vale.parcelas, competencia_inicio: i.vale.competencia_inicio || null,
            origem_tipo: i.vale.origem_tipo || null, origem_id: i.vale.origem_id || null,
            observacao: i.vale.observacao || null, confirmar: i.vale.confirmar || false,
          } : null,
        })),
      centro_custo: centroCusto || null,
      classificacao: classificacao || null,
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
      criar_patrimonio: criarPatrimonio,
    };
  }

  async function salvar() {
    setErro(null); setSucesso(null); setErroXml(null);
    const validos = itens.filter((i) => i.produto.trim());
    if (!validos.length) { setErro("Informe ao menos um produto ou serviço."); return; }
    if (!centroCusto.trim()) { setErro("Selecione o centro de custo."); return; }
    if (valorLiquido <= 0) { setErro("O valor líquido do lançamento deve ser positivo."); return; }
    if (itens.some((i) => i.vale && (Number(i.valor_total) || 0) <= 0)) {
      setErro("Item marcado como vale precisa de valor maior que zero."); return;
    }
    if (!confirmandoItemNaoCadastrado && itens.some((i) => itemNaoCadastradoDeDocumento(i))) {
      setConfirmandoItemNaoCadastrado(true); return;
    }
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
      // O lançamento em si já está salvo neste ponto — cada anexo é
      // pego individualmente (nunca deixa o catch propagar) para que uma
      // falha aqui (rede caindo bem no meio do upload, mais exposto que o
      // POST do lançamento por mexer com arquivo maior) NUNCA apareça pro
      // usuário como se o lançamento inteiro tivesse falhado.
      let avisoAnexo = "";
      const falhasAnexo = (await Promise.all(
        anexosStaged.map((f) => anexarArquivoLancamento(r.numero_lancamento, f.file, f.categoria || undefined, f.numero_documento || undefined, f.data_documento || undefined).then(() => null).catch(() => f.file.name)),
      )).filter(Boolean);
      if (falhasAnexo.length) {
        avisoAnexo = falhasAnexo.length === 1
          ? ` O anexo ${falhasAnexo[0]} não pôde ser enviado — tente anexar de novo.`
          : ` Estes anexos não puderam ser enviados — tente anexar de novo: ${falhasAnexo.join(", ")}.`;
      }
      // avisos_estoque: ex. "X não está no estoque desta fazenda" — o backend
      // já calcula, mas até aqui ninguém no frontend lia a resposta pra
      // mostrar isso ao usuário (a nota salvava normal, o aviso se perdia).
      const avisoEstoque = (r.avisos_estoque || []).length ? ` ${r.avisos_estoque.join(" ")}` : "";
      setSucesso(`Lançamento ${r.numero_lancamento} salvo com sucesso.${avisoAnexo}${avisoEstoque}`);
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
      onSalvo?.(`Lançamento ${r.numero_lancamento} salvo com sucesso.${avisoAnexo}${avisoEstoque}`);
    } catch (e: any) {
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const idx = itens.findIndex((i) => i.vale?.modo === "folha" && !i.vale?.confirmar);
        if (idx !== -1) {
          setErro("Um dos itens marcados como vale passa do limite de 40% do salário na competência. Revise a marcação destacada abaixo.");
          setPendingErro409({ idx, mensagem: e.detail.mensagem, competencias_excedidas: e.detail.competencias_excedidas || [] });
          setValeAbertoPara(idx);
        } else {
          setErro(e.message || "Erro ao salvar lançamento");
        }
      } else {
        setErro(e.message || "Erro ao salvar lançamento");
      }
    } finally {
      setSalvando(false); setConfirmando(false); setConfirmandoDuplicado(false); setDuplicados([]);
      setConfirmandoItemNaoCadastrado(false);
    }
  }

  return (
    <>
      {criarPatrimonio && (
        <div className="card mb-3" style={{ border: "1px solid var(--dourado)", background: "rgba(94,26,46,0.08)" }}>
          <p style={{ fontSize: "0.8rem", margin: 0 }}>
            Ao salvar, esta compra cria o item de patrimônio <strong>{criarPatrimonio.nome}</strong>
            {criarPatrimonio.tipo ? ` (${criarPatrimonio.tipo})` : ""} já vinculado a este lançamento.
          </p>
        </div>
      )}
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

      {/* Duas colunas, cada uma com rolagem própria: esquerda = dados do
          lançamento (editável) + contexto/histórico do fornecedor (só
          leitura); direita = produtos/serviços, pagamento e anexos — mesmo
          padrão já usado em Alimentação > Nova dieta. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>

      {/* Dados da nota (uma vez por lançamento) */}
      <div className="card" style={{ background: "var(--fin-nota-bg)" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
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
        <Campo label="Classificação">
          {!novaClassificacaoAberta ? (
            <div className="flex items-center gap-2">
              <select style={inputStyle} value={classificacao} onChange={(e) => setClassificacao(e.target.value)}>
                <option value="">Selecione…</option>
                {classificacao && !opcoes.classificacoes.includes(classificacao) && <option value={classificacao}>{classificacao}</option>}
                {opcoes.classificacoes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button type="button" className="btn-ghost" title="Cadastrar nova classificação" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setNovaClassificacaoAberta(true)}>
                <Plus size={13} /> Nova
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <input style={inputStyle} value={novaClassificacaoNome} onChange={(e) => setNovaClassificacaoNome(e.target.value)} placeholder="ex.: Medicamentos" autoFocus />
              <button type="button" className="btn-primary" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} disabled={salvandoClassificacao || !novaClassificacaoNome.trim()} onClick={async () => {
                setSalvandoClassificacao(true);
                try {
                  await criarClassificacao({ nome: novaClassificacaoNome.trim() });
                  const nome = novaClassificacaoNome.trim();
                  setClassificacao(nome);
                  await carregarOpcoes();
                  setNovaClassificacaoNome(""); setNovaClassificacaoAberta(false);
                } catch (e: any) {
                  setErro(e.message || "Erro ao criar classificação");
                } finally {
                  setSalvandoClassificacao(false);
                }
              }}>{salvandoClassificacao ? "Salvando…" : "Salvar"}</button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => { setNovaClassificacaoAberta(false); setNovaClassificacaoNome(""); }}>Cancelar</button>
            </div>
          )}
        </Campo>
        <Campo label="Responsável pelo lançamento">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Selecione…</option>
            {responsaveis.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo label="Tipo de documento">
          <select style={inputStyle} value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}>
            <option value="">Selecione…</option>
            {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Comprovante", "Folha de pagamento", "Fatura", "Contrato", "Boleto", "Ordem de serviço"]).map((t) => <option key={t}>{t}</option>)}
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
        <Campo label="Desconto (R$)"><CampoMoeda style={inputStyle} value={Number(desconto) || 0} onChange={(v) => setDesconto(v ? String(v) : "")} /></Campo>
        <Campo label="Acréscimo (R$)"><CampoMoeda style={inputStyle} value={Number(acrescimo) || 0} onChange={(v) => setAcrescimo(v ? String(v) : "")} /></Campo>
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

      {/* Contexto do fornecedor/cliente — só leitura, histórico pra decidir
          antes de lançar (em aberto, último lançamento, últimos
          lançamentos, documentos já anexados a alguma nota dele). */}
      {fornecedor.trim() && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Contexto do {tipo === "receita" ? "cliente" : "fornecedor"}
          </p>
          {!contextoFornecedor ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.65rem" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Em aberto</div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 700 }}>{formatBRL(contextoFornecedor.em_aberto)}</div>
                </div>
                <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.65rem" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Último lançamento</div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 700 }}>
                    {contextoFornecedor.ultimo_lancamento ? new Date(contextoFornecedor.ultimo_lancamento + "T00:00:00").toLocaleDateString("pt-BR") : "—"}
                  </div>
                </div>
              </div>
              {contextoFornecedor.ultimos_lancamentos.length > 0 && (
                <>
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.3rem" }}>
                    Últimos lançamentos
                  </p>
                  <div style={{ overflowX: "auto", marginBottom: "0.7rem" }}>
                    <table className="fazenda-table" style={{ margin: 0, fontSize: "0.78rem" }}>
                      <thead><tr><th>Data</th><th>Nº doc.</th><th style={{ textAlign: "right" }}>Valor</th><th>Situação</th></tr></thead>
                      <tbody>
                        {contextoFornecedor.ultimos_lancamentos.map((l, i) => (
                          <tr key={i}>
                            <td>{l.data ? new Date(l.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                            <td>{l.numero_documento || "—"}</td>
                            <td style={{ textAlign: "right" }}>{formatBRL(l.valor)}</td>
                            <td>
                              <span style={{ fontSize: "0.7rem", fontWeight: 700, color: l.pago ? "var(--green-light)" : "var(--amber)" }}>
                                {l.pago ? "Pago" : "Em aberto"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {contextoFornecedor.documentos_anexados.length > 0 && (
                <>
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.3rem" }}>
                    Documentos já anexados
                  </p>
                  {contextoFornecedor.documentos_anexados.map((d, i) => (
                    <div key={i} className="card" style={{ padding: "0.4rem 0.6rem", marginBottom: "0.3rem", background: "var(--surface)" }}>
                      <div style={{ fontSize: "0.78rem", fontWeight: 600 }}>{d.nome_arquivo}</div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{d.categoria || "—"} · {new Date(d.criado_em).toLocaleDateString("pt-BR")}</div>
                    </div>
                  ))}
                </>
              )}
              {!contextoFornecedor.ultimos_lancamentos.length && !contextoFornecedor.documentos_anexados.length && (
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum lançamento anterior com este nome.</p>
              )}
            </>
          )}
        </div>
      )}

      </div>
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>

      {/* Anexo e leitura automática — UM local só pra qualquer documento
          deste lançamento (nota, boleto, orçamento, comprovante de
          pagamento...). Cada arquivo é lido (extrai dados) E fica anexado —
          antes eram 3 pontos separados de anexo e o arquivo lido não ficava
          guardado. */}
      <div
        onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        className="card mb-3"
        style={{ border: "1px dashed var(--border)", background: "var(--surface-2)", padding: "0.8rem", textAlign: "center" }}
      >
        <div className="flex items-center justify-center gap-2" style={{ flexWrap: "wrap" }}>
          <FileText size={16} style={{ color: "var(--dourado-light)" }} />
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Arraste um ou mais documentos (XML, PDF, JPEG, PNG — nota, boleto, orçamento, comprovante...) aqui, ou</span>
          <button type="button" className="btn-ghost" title="Selecionar um ou mais arquivos" onClick={() => fileInputRef.current?.click()} style={{ fontSize: "0.78rem" }}>
            <Upload size={13} /> selecionar arquivo(s)
          </button>
          <button type="button" className="btn-ghost" title="Tirar foto do documento" onClick={() => fotoAnexoInputRef.current?.click()} style={{ fontSize: "0.78rem" }}>
            <Camera size={13} /> tirar foto
          </button>
          <button type="button" className="btn-ghost" title="Colar o código XML da nota fiscal" onClick={() => setXmlAberto((v) => !v)} style={{ fontSize: "0.78rem" }}>colar código XML</button>
          {importando && <Loader2 size={14} className="animate-spin" style={{ color: "var(--dourado-light)" }} />}
        </div>
        <input ref={fileInputRef} type="file" multiple accept=".xml,text/xml,application/pdf,image/jpeg,image/jpg,image/png,image/webp,image/gif,image/heic,image/heif" onChange={onFileSelect} style={{ display: "none" }} />
        <input ref={fotoAnexoInputRef} type="file" accept="image/*" capture="environment" onChange={onFileSelect} style={{ display: "none" }} />
        {xmlAberto && (
          <div style={{ marginTop: "0.6rem", textAlign: "left" }}>
            <textarea value={xmlTexto} onChange={(e) => setXmlTexto(e.target.value)} placeholder="Cole aqui o conteúdo do XML da nota fiscal…"
              style={{ ...inputStyle, minHeight: "6rem", fontFamily: "monospace", fontSize: "0.72rem" }} />
            <button type="button" className="btn-primary" title="Importar os dados do XML colado" style={{ marginTop: "0.4rem" }} onClick={() => importarXml(xmlTexto)} disabled={importando}>Importar XML</button>
          </div>
        )}
        {erroXml && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.4rem" }}>{erroXml}</p>}
        {avisoDocumento && <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>{avisoDocumento}</p>}
        {notaCamposIdentificados && (
          <p style={{ color: "var(--green-light)", fontSize: "0.75rem", marginTop: "0.4rem" }}>
            {notaCamposIdentificados}{" "}
            <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem" }} onClick={() => setNotaCamposIdentificados(null)}>ok</button>
          </p>
        )}
        {apelidoBanner && (
          <div style={{ marginTop: "0.5rem", background: "rgba(94,26,46,0.15)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", textAlign: "left" }}>
            <p style={{ fontSize: "0.76rem" }}>
              &ldquo;{apelidoBanner.nomeBruto}&rdquo; não bate exatamente com nada do cadastro. Salvar &ldquo;{fornecedor}&rdquo; como
              {" "}{tipo === "despesa" ? "fornecedor" : "cliente"} padrão pra próxima vez que esse nome aparecer numa nota?
            </p>
            <div className="flex items-center gap-2 mt-1">
              <button type="button" className="btn-secondary" style={{ fontSize: "0.72rem" }} disabled={salvandoApelido || !fornecedor.trim()} onClick={salvarApelidoFornecedor}>
                {salvandoApelido ? "Salvando…" : "Sim, lembrar"}
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setApelidoBanner(null)}>Não, obrigado</button>
            </div>
          </div>
        )}
        {anexosStaged.length > 0 && (
          <ul style={{ marginTop: "0.6rem", textAlign: "left", fontSize: "0.76rem", listStyle: "none", padding: 0 }}>
            {anexosStaged.map((f, i) => {
              const ehImagem = f.file.type.startsWith("image/");
              return (
                <li key={i} className="card" style={{ padding: "0.4rem 0.5rem", marginBottom: "0.35rem", background: "var(--surface)" }}>
                  <div className="flex items-center gap-2">
                    {ehImagem ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={URL.createObjectURL(f.file)} alt="" style={{ width: 32, height: 32, objectFit: "cover", borderRadius: "var(--r-sm)", flexShrink: 0 }} />
                    ) : (
                      <FileText size={20} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
                    )}
                    <a href={URL.createObjectURL(f.file)} target="_blank" rel="noreferrer" title="Abrir este documento numa aba nova"
                      style={{ color: "var(--dourado-light)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {f.file.name}
                    </a>
                    <button type="button" className="btn-ghost" title="Editar tipo de documento" onClick={() => setCategoriaPopupFile(f.file)} style={{ padding: "0.1rem 0.3rem", flexShrink: 0, fontSize: "0.72rem" }}>
                      {f.categoria || "definir tipo"}
                    </button>
                    <button type="button" className="btn-ghost" title="Remover" onClick={() => setAnexosStaged((arr) => arr.filter((_, j) => j !== i))} style={{ padding: "0.1rem 0.3rem", flexShrink: 0 }}>
                      <X size={12} style={{ color: "var(--red)" }} />
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2" style={{ marginTop: "0.3rem" }}>
                    <input style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} placeholder="Número do documento" value={f.numero_documento}
                      onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, numero_documento: e.target.value } : x))} />
                    <input type="date" style={{ ...inputStyle, fontSize: "0.74rem", padding: "0.25rem 0.4rem" }} title="Data deste documento" value={f.data_documento}
                      onChange={(e) => setAnexosStaged((arr) => arr.map((x, j) => j === i ? { ...x, data_documento: e.target.value } : x))} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {anexosStaged.length > 0 && (
          <div className="flex items-center justify-center gap-2" style={{ marginTop: "0.5rem" }}>
            <button type="button" className="btn-primary" style={{ fontSize: "0.78rem" }}
              title={anexosPendentesImportacao.length > 0 ? "Salvar o(s) anexo(s) e decidir se importa os dados de algum deles" : "Todos os anexos já foram salvos"}
              disabled={anexosPendentesImportacao.length === 0}
              onClick={() => setImportarPopupAberto(true)}>
              <Check size={13} /> {anexosPendentesImportacao.length > 0 ? "Salvar" : "Anexo(s) salvo(s)"}
            </button>
          </div>
        )}
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          Anexar aqui só guarda o(s) documento(s) neste lançamento — não lê nada sozinho. Clique em &ldquo;Salvar&rdquo; pra
          decidir se importa os dados de algum deles (XML/PDF/JPEG/PNG reconhecem vários produtos/serviços da mesma nota). A
          partir do 2º documento importado, tenta identificar mais dados (com aviso do que foi acrescentado) e avisa se algum
          dado divergir do que já está preenchido.
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
                  <ServicoPicker servicos={sugestoesServico.map((nome) => ({ nome }))}
                    value={it.produto} onChange={(v) => atualizarItem(idx, { produto: v })} />
                  <UltimoPrecoObservacao produto={it.produto} tipo={tipo} />
                </Campo>
              ) : (
                <div>
                  <div className="flex items-center justify-between" style={{ marginBottom: "0.25rem" }}>
                    <label style={lbl}>Produto</label>
                    <select style={{ background: "transparent", color: "var(--text-muted)", border: "none", fontSize: "0.68rem", cursor: "pointer" }}
                      value={it.modoProduto} onChange={(e) => atualizarItem(idx, { modoProduto: e.target.value as "estoque" | "livre" })}
                      title="Do estoque: escolhe um item já cadastrado. Texto livre: qualquer compra, mesmo sem cadastro — não entra automaticamente no estoque.">
                      <option value="estoque">do estoque</option>
                      <option value="livre">texto livre</option>
                    </select>
                  </div>
                  {it.modoProduto === "estoque" ? (
                    <>
                      {/* incluirNaoEstocaveis: aqui é lançamento financeiro, não
                          consumo de estoque — um item cadastrado só para
                          organização financeira (sem controle de saldo) tem que
                          aparecer igual a um estocável. */}
                      <EstoquePicker itens={produtosEstoque} value={it.produto} todasFinalidades incluirNaoEstocaveis onChange={(nomeProduto) => {
                        const match = produtosEstoque.find((p) => p.nome === nomeProduto);
                        const patch: Partial<Item> = { produto: nomeProduto };
                        const conta = contaGerencialPadrao(tipo === "despesa" ? match?.conta_gerencial_despesa_padrao : match?.conta_gerencial_receita_padrao);
                        if (conta) { patch.codigo_conta_gerencial = conta.codigo; patch.nome_conta_gerencial = conta.nome; }
                        atualizarItem(idx, patch);
                        if (match?.fornecedor_nome) setFornecedor(match.fornecedor_nome);
                      }} />
                      <UltimoPrecoObservacao produto={it.produto} tipo={tipo} />
                    </>
                  ) : (
                    <>
                      <input list={`produtos-financeiro-${idx}`} style={inputStyle} value={it.produto}
                        onChange={(e) => atualizarItem(idx, { produto: e.target.value })}
                        placeholder="ex.: Supermercado, Material de escritório…" />
                      {/* Histórico de nomes já usados em lançamentos — não precisa
                          estar no estoque pra sugerir aqui (ver Opcoes.produtos). */}
                      <datalist id={`produtos-financeiro-${idx}`}>
                        {opcoes.produtos.map((p) => <option key={p} value={p} />)}
                      </datalist>
                    </>
                  )}
                </div>
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
              <Campo label="Centro de custo (opcional — só este item)">
                <select style={inputStyle} value={it.centro_custo || ""} onChange={(e) => atualizarItem(idx, { centro_custo: e.target.value })}
                  title="Deixe em branco para usar o centro de custo da nota inteira (acima). Preencha só quando este item, especificamente, for de outro centro.">
                  <option value="">— Usar o da nota ({centroCusto || "—"}) —</option>
                  {it.centro_custo && !opcoes.centros_custo.includes(it.centro_custo) && <option value={it.centro_custo}>{it.centro_custo}</option>}
                  {opcoes.centros_custo.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Campo>
              <Campo label="Descrição (opcional)">
                <input style={inputStyle} value={it.descricao} onChange={(e) => atualizarItem(idx, { descricao: e.target.value })} />
              </Campo>
            </div>
            {itemNaoCadastradoDeDocumento(it) && (
              <div className="flex items-center gap-2 mt-2" style={{ flexWrap: "wrap", background: "rgba(180,120,0,0.14)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
                <AlertTriangle size={14} style={{ color: "var(--amber)", flexShrink: 0 }} />
                <span style={{ fontSize: "0.78rem", color: "var(--amber)" }}>
                  &ldquo;{it.produto}&rdquo; veio do documento lido, mas não está cadastrado no {it.tipo_item === "servico" ? "cadastro de serviços" : "estoque"} —
                  sem cadastro, este item fica sem centro de custo padrão e não aparece pra seleção em telas de aplicação/consumo.
                </span>
                <button type="button" className="btn-secondary" style={{ fontSize: "0.74rem", whiteSpace: "nowrap" }}
                  onClick={() => { setAdicionarPara(idx); setModoAdicionar(it.tipo_item === "servico" ? "servico" : "produto"); }}>
                  <Plus size={13} /> Cadastrar {it.tipo_item === "servico" ? "serviço" : "produto"} novo
                </button>
                <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem", whiteSpace: "nowrap" }}
                  onClick={() => setAssociarPara(idx)}>
                  Associar a {it.tipo_item === "servico" ? "serviço" : "produto"} já existente
                </button>
              </div>
            )}
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
                <CampoMoeda
                  style={it.modoValor === "unitario" ? inputStyle : { ...inputStyle, opacity: 0.55, cursor: "not-allowed" }}
                  value={Number(it.valor_unitario) || 0} disabled={it.modoValor === "total"}
                  onChange={(v) => atualizarItem(idx, { valor_unitario: v ? String(v) : "" })} />
              </Campo>
              <Campo label={it.modoValor === "total" ? "Valor total (R$)" : "Valor total (R$) — calculado"}>
                <CampoMoeda
                  style={it.modoValor === "total" ? inputStyle : { ...inputStyle, opacity: 0.55, cursor: "not-allowed" }}
                  value={Number(it.valor_total) || 0} disabled={it.modoValor === "unitario"}
                  onChange={(v) => atualizarItem(idx, { valor_total: v ? String(v) : "" })} />
              </Campo>
            </div>
            {tipo === "despesa" && (
              <div className="flex items-center gap-2 mt-3" style={{ flexWrap: "wrap" }}>
                <input id={`vale-item-${idx}`} type="checkbox" checked={!!it.vale}
                  onChange={(e) => e.target.checked ? setValeAbertoPara(idx) : pedirDesmarcarVale(idx)} />
                <label htmlFor={`vale-item-${idx}`} style={{ fontSize: "0.8rem" }}>É vale de funcionário?</label>
                {it.vale && (
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {it.vale.pessoa_nome} — {it.vale.modo === "folha"
                      ? `${it.vale.parcelas}x na folha a partir de ${it.vale.competencia_inicio}`
                      : it.vale.origem_label}
                    {" "}
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }}
                      onClick={() => setValeAbertoPara(idx)}>alterar</button>
                  </span>
                )}
              </div>
            )}
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
                      <td><CampoMoeda style={{ ...inputStyle, textAlign: "right" }} value={Number(p.valor) || 0}
                        onChange={(v) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, valor: v ? String(v) : "" } : x))} /></td>
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
                          <div style={{ padding: "0.6rem", background: "var(--fin-pagamento-bg)", borderRadius: "var(--r-sm)", margin: "0.2rem 0 0.5rem" }}>
                            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
                              <Campo label="Data de pagamento">
                                <input type="date" style={inputStyle} value={p.data_pagamento || ""}
                                  onChange={(e) => atualizarBaixaParcela(i, { data_pagamento: e.target.value })} />
                              </Campo>
                              <Campo label="Valor pago (R$)">
                                <CampoMoeda style={inputStyle} value={Number(p.valor_pago) || 0}
                                  onChange={(v) => atualizarBaixaParcela(i, { valor_pago: v ? String(v) : "" })} />
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

      {/* Pagamento imediato (só para lançamento não parcelado) */}
      {!parcelado && (
        <div className="card mt-3" style={{ background: "var(--fin-pagamento-bg)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <input type="checkbox" checked={jaPago} onChange={(e) => {
              const marcado = e.target.checked;
              setJaPago(marcado);
              // Ao marcar, pré-preenche com o valor líquido da nota, a data de
              // hoje e a primeira conta bancária cadastrada — só se ainda
              // estiverem vazios, e tudo continua editável.
              if (marcado) {
                setValorPago((atual) => atual || (valorLiquido > 0 ? valorLiquido.toFixed(2) : atual));
                setDataPagamento((atual) => atual || today());
                setContaBancaria((atual) => atual || opcoes.contas_bancarias[0] || atual);
              }
            }} /> Já foi {tipo === "despesa" ? "pago" : "recebido"}
          </label>
          {jaPago && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
              <Campo label="Data de pagamento"><input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></Campo>
              <Campo label="Valor pago (R$)"><CampoMoeda style={inputStyle} value={Number(valorPago) || 0} onChange={(v) => setValorPago(v ? String(v) : "")} /></Campo>
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
              <p style={{ gridColumn: "1 / -1", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                Comprovante de pagamento: anexe no bloco de documentos no início do formulário (categoria &ldquo;Comprovante&rdquo;).
              </p>
            </div>
          )}
        </div>
      )}

      </div>
      </div>

      {/* Resumo fixo — sticky no rodapé (fora das duas colunas de rolagem
          própria acima), sempre visível: total, nº de parcelas, data do 1º
          vencimento e o que este lançamento reflete em estoque/pedido/DRE.
          Só leitura, mesmos valores já calculados nas colunas (ver
          numeroParcelasResumo/primeiroVencimentoResumo/itensComReflexoEstoque/
          pedidoVinculadoResumo acima) — nenhuma conta nova, e o botão
          "Salvar lançamento" (com o mesmo onClick/disabled de sempre) mora
          aqui agora, junto do erro/sucesso, pra não sumir rolando a coluna. */}
      <div className="card" style={{
        position: "sticky", bottom: 0, marginTop: "1rem", zIndex: 5,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap",
        boxShadow: "0 -2px 10px rgba(20,30,45,0.16)",
      }}>
        <div className="flex items-center gap-4" style={{ flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Total do lançamento</div>
            <div style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Parcelas</div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{numeroParcelasResumo}x{!parcelado ? " (à vista)" : ""}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>1º vencimento</div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>
              {primeiroVencimentoResumo ? new Date(primeiroVencimentoResumo + "T00:00:00").toLocaleDateString("pt-BR") : "—"}
            </div>
          </div>
          {itensComReflexoEstoque.length > 0 && (
            <div>
              <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Estoque</div>
              <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{itensComReflexoEstoque.length} item(ns) atualiza(m) saldo</div>
            </div>
          )}
          {pedidoVinculadoResumo && (
            <div>
              <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Pedido</div>
              <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{pedidoVinculadoResumo.numero_pedido}</div>
            </div>
          )}
          <div>
            <div style={{ fontSize: "0.66rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>DRE</div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{centroCusto || "—"}{classificacao ? ` · ${classificacao}` : ""}</div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.3rem" }}>
          {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", margin: 0, maxWidth: "22rem", textAlign: "right" }}>{erro}</p>}
          {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", margin: 0, maxWidth: "22rem", textAlign: "right" }}>{sucesso}</p>}
          <button className="btn-primary" title="Salvar este lançamento financeiro" onClick={salvar} disabled={salvando || verificandoDuplicado}>
            {salvando ? "Salvando…" : verificandoDuplicado ? "Verificando…" : "Salvar lançamento"}
          </button>
        </div>
      </div>

      {importarPopupAberto && anexosPendentesImportacao.length > 0 && (
        <Modal
          title={anexosPendentesImportacao.length === 1 ? "Importar dados do documento?" : "Importar dados de qual documento?"}
          onClose={() => resolverImportacaoAnexos(null)}
          width="440px" zIndex={96}
        >
          {anexosPendentesImportacao.length === 1 ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                {anexosPendentesImportacao[0].file.type.startsWith("image/") ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={URL.createObjectURL(anexosPendentesImportacao[0].file)} alt="" style={{ width: 48, height: 48, objectFit: "cover", borderRadius: "var(--r-sm)", flexShrink: 0 }} />
                ) : (
                  <FileText size={36} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
                )}
                <span style={{ fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{anexosPendentesImportacao[0].file.name}</span>
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
                Deseja importar os dados desse documento? A leitura automática pré-preenche os campos do lançamento — tudo
                fica editável antes de salvar.
              </p>
              <div className="flex items-center justify-end gap-2">
                <button type="button" className="btn-ghost" onClick={() => resolverImportacaoAnexos(null)}>Não</button>
                <button type="button" className="btn-primary" onClick={() => resolverImportacaoAnexos(anexosPendentesImportacao[0].file)}>Sim, importar</button>
              </div>
            </>
          ) : (
            <>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Você anexou mais de um documento. Escolha qual deles usar pra pré-preencher os campos do lançamento (só dá
                pra importar de um por vez) — ou não importar nenhum.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                {anexosPendentesImportacao.map((a, i) => (
                  <button key={i} type="button" className="btn-secondary" style={{ fontSize: "0.78rem", justifyContent: "flex-start", gap: "0.5rem" }}
                    onClick={() => resolverImportacaoAnexos(a.file)}>
                    {a.file.type.startsWith("image/") ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={URL.createObjectURL(a.file)} alt="" style={{ width: 24, height: 24, objectFit: "cover", borderRadius: "var(--r-sm)", flexShrink: 0 }} />
                    ) : (
                      <FileText size={16} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
                    )}
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.file.name}</span>
                  </button>
                ))}
              </div>
              <div className="flex justify-end mt-3">
                <button type="button" className="btn-ghost" onClick={() => resolverImportacaoAnexos(null)}>Não importar</button>
              </div>
            </>
          )}
        </Modal>
      )}

      {categoriaPopupFile && (() => {
        const entrada = anexosStaged.find((a) => a.file === categoriaPopupFile);
        if (!entrada) return null;
        const ehImagem = entrada.file.type.startsWith("image/");
        return (
          <Modal title="Tipo de documento" onClose={() => setCategoriaPopupFile(null)} width="480px" zIndex={95}>
            <div className="flex items-center gap-3 mb-3">
              {ehImagem ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={URL.createObjectURL(entrada.file)} alt="" style={{ width: 64, height: 64, objectFit: "cover", borderRadius: "var(--r-sm)", flexShrink: 0 }} />
              ) : (
                <FileText size={40} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
              )}
              <span style={{ fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entrada.file.name}</span>
            </div>
            {!novoTipoDocumentoAberto ? (
              <>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" }}>Este documento é um(a):</label>
                <select style={inputStyle} value={entrada.categoria}
                  onChange={(e) => setAnexosStaged((arr) => arr.map((a) => a.file === categoriaPopupFile ? { ...a, categoria: e.target.value } : a))}>
                  <option value="">Selecione…</option>
                  {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Comprovante", "Fatura", "Orçamento", "Boleto", "Ordem de serviço"]).map((t) => <option key={t}>{t}</option>)}
                </select>
                <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", marginTop: "0.5rem" }} onClick={() => setNovoTipoDocumentoAberto(true)}>
                  <Plus size={13} /> Criar novo tipo de documento
                </button>
                <div className="flex justify-end mt-3">
                  <button type="button" className="btn-primary" onClick={() => setCategoriaPopupFile(null)}>Concluir</button>
                </div>
              </>
            ) : (
              <>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" }}>Nome do novo tipo de documento</label>
                <input style={inputStyle} value={novoTipoDocumentoNome} onChange={(e) => setNovoTipoDocumentoNome(e.target.value)} placeholder="ex.: Contrato" />
                <div className="flex items-center gap-2 mt-3">
                  <button type="button" className="btn-primary" disabled={salvandoTipoDocumento || !novoTipoDocumentoNome.trim()} onClick={async () => {
                    setSalvandoTipoDocumento(true);
                    try {
                      await criarTipoDocumento({ nome: novoTipoDocumentoNome.trim() });
                      const nome = novoTipoDocumentoNome.trim();
                      setAnexosStaged((arr) => arr.map((a) => a.file === categoriaPopupFile ? { ...a, categoria: nome } : a));
                      await carregarOpcoes();
                      setNovoTipoDocumentoNome(""); setNovoTipoDocumentoAberto(false);
                    } catch (e: any) {
                      setErro(e.message || "Erro ao criar tipo de documento");
                    } finally {
                      setSalvandoTipoDocumento(false);
                    }
                  }}>
                    {salvandoTipoDocumento ? "Salvando…" : "Salvar"}
                  </button>
                  <button type="button" className="btn-ghost" onClick={() => setNovoTipoDocumentoAberto(false)}>Cancelar</button>
                </div>
              </>
            )}
          </Modal>
        );
      })()}

      {divergenciasDocumento && (
        <Modal title="Este documento diverge do que já está preenchido" onClose={() => setDivergenciasDocumento(null)} width="560px" zIndex={95}>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
            Escolha, campo a campo, se mantém o que já estava preenchido ou passa a usar o que este documento traz.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {divergenciasDocumento.map((d, i) => (
              <div key={i} className="card" style={{ padding: "0.5rem 0.7rem" }}>
                <p style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: "0.3rem" }}>{d.campo}</p>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  <button type="button" className={d.escolha === "atual" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.74rem" }}
                    onClick={() => aplicarEscolhaDivergencia(i, "atual")}>
                    Manter: {d.atual}
                  </button>
                  <button type="button" className={d.escolha === "novo" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.74rem" }}
                    onClick={() => aplicarEscolhaDivergencia(i, "novo")}>
                    Usar deste documento: {d.novo}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-3">
            <button type="button" className="btn-primary" onClick={confirmarDivergencias}>Aplicar escolhas</button>
          </div>
        </Modal>
      )}

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
              // Pré-preenche com o nome já lançado (ex.: veio do XML/OCR e não
              // batia com nada do estoque) — cadastrar com o MESMO texto é o
              // que faz esse item "virar" reconhecido: o resto do sistema
              // reconhece por igualdade de nome, não por vínculo.
              prefill={adicionarPara !== null && itens[adicionarPara]?.produto.trim() ? { nome: itens[adicionarPara].produto.trim() } : undefined}
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
              prefillNome={adicionarPara !== null ? itens[adicionarPara]?.produto.trim() : undefined}
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

      {associarPara !== null && (
        <Modal title={`Associar a ${itens[associarPara]?.tipo_item === "servico" ? "serviço" : "produto"} já existente`} onClose={() => setAssociarPara(null)} width="600px">
          {itens[associarPara]?.tipo_item === "servico" ? (
            <ServicoPicker servicos={sugestoesServico.map((nome) => ({ nome }))}
              value="" onChange={(nomeEscolhido) => {
                if (!nomeEscolhido) return;
                atualizarItem(associarPara, { produto: nomeEscolhido });
                setAssociarPara(null);
              }} />
          ) : (
            <EstoquePicker itens={produtosEstoque} value="" todasFinalidades incluirNaoEstocaveis
              onChange={(nomeProduto) => {
                if (!nomeProduto) return;
                const match = produtosEstoque.find((p) => p.nome === nomeProduto);
                const patch: Partial<Item> = { produto: nomeProduto };
                const conta = contaGerencialPadrao(tipo === "despesa" ? match?.conta_gerencial_despesa_padrao : match?.conta_gerencial_receita_padrao);
                if (conta) { patch.codigo_conta_gerencial = conta.codigo; patch.nome_conta_gerencial = conta.nome; }
                atualizarItem(associarPara, patch);
                setAssociarPara(null);
              }} />
          )}
          <div className="flex justify-end mt-3">
            <button type="button" className="btn-ghost" onClick={() => setAssociarPara(null)}>Cancelar</button>
          </div>
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

      {confirmandoItemNaoCadastrado && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "560px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Produto/serviço não cadastrado</strong></div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
              Este(s) item(ns) veio(vieram) do documento lido, mas não estão no cadastro — vão salvar como texto solto, sem
              centro de custo padrão e sem aparecer pra seleção em telas de aplicação/consumo:
            </p>
            <ul style={{ fontSize: "0.82rem", marginBottom: "0.7rem", paddingLeft: "1.2rem" }}>
              {itens.filter((i) => itemNaoCadastradoDeDocumento(i)).map((i, idx) => <li key={idx}>{i.produto}</li>)}
            </ul>
            <div className="flex items-center gap-3">
              <button className="btn-primary" title="Salvar mesmo assim, sem cadastrar" onClick={salvar}><Check size={14} /> Salvar mesmo assim</button>
              <button className="btn-ghost" title="Voltar e cadastrar o produto/serviço" onClick={() => setConfirmandoItemNaoCadastrado(false)}><X size={14} /> Cancelar e cadastrar</button>
            </div>
          </div>
        </div>
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

      {sugestoesCadastro && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "620px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} /><strong>Parecido com algo já cadastrado</strong></div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              O texto da nota não bate exatamente com o cadastro, mas achei algo parecido. Confira, edite a marcação
              se quiser manter o texto original, e aplique — ou mantenha tudo como veio da nota.
            </p>
            <div style={{ overflowX: "auto" }}>
              <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
                <thead><tr><th></th><th>A nota diz</th><th>O cadastro tem parecido</th><th style={{ textAlign: "center" }}>Usar sugestão</th></tr></thead>
                <tbody>
                  {sugestoesCadastro.fornecedor && (
                    <tr>
                      <td style={{ color: "var(--text-muted)" }}>Fornecedor/cliente</td>
                      <td>{sugestoesCadastro.fornecedor.texto}</td>
                      <td style={{ color: "var(--dourado-light)" }}>
                        {sugestoesCadastro.fornecedor.candidato} <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>({Math.round(sugestoesCadastro.fornecedor.score * 100)}% parecido)</span>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" checked={sugestoesEscolhidas["fornecedor"] !== false}
                          onChange={(e) => setSugestoesEscolhidas((s) => ({ ...s, fornecedor: e.target.checked }))} />
                      </td>
                    </tr>
                  )}
                  {sugestoesCadastro.itens.map((it: SugestaoCadastroItem) => (
                    <tr key={it.indice}>
                      <td style={{ color: "var(--text-muted)" }}>{it.tipo === "servico" ? "Serviço" : "Produto"}</td>
                      <td>{it.texto}</td>
                      <td style={{ color: "var(--dourado-light)" }}>
                        {it.candidato} <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>({Math.round(it.score * 100)}% parecido)</span>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" checked={sugestoesEscolhidas[`item-${it.indice}`] !== false}
                          onChange={(e) => setSugestoesEscolhidas((s) => ({ ...s, [`item-${it.indice}`]: e.target.checked }))} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn-primary" title="Aplicar as sugestões marcadas acima" onClick={aplicarSugestoesEscolhidas}><Check size={14} /> Aplicar marcadas</button>
              <button className="btn-ghost" title="Manter tudo como veio da nota, sem aplicar nenhuma sugestão" onClick={() => setSugestoesCadastro(null)}><X size={14} /> Manter como veio da nota</button>
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

      {valeAbertoPara !== null && (
        <ValeItemModal apresentacao={apresentacaoModais ?? "modal"}
          valorItem={Number(itens[valeAbertoPara].valor_total) || 0}
          dataItem={dataEmissao || new Date().toISOString().slice(0, 10)}
          produtoItem={itens[valeAbertoPara].produto}
          inicial={itens[valeAbertoPara].vale}
          onConfirmar={(d) => {
            // Reabertura após 409 de 40% do salário (ver `pendingErro409` e o
            // catch de salvar() acima): a 1ª tentativa de confirmar dentro do
            // modal reproduz o mesmo erro recebido do backend — o modal
            // mostra o aviso e troca o botão para "Lançar mesmo assim"; só
            // na 2ª tentativa (já com `confirmar: true`) o vínculo é
            // gravado localmente, pronto para o usuário clicar de novo em
            // "Salvar lançamento".
            if (pendingErro409 && pendingErro409.idx === valeAbertoPara) {
              const detalhe = pendingErro409;
              setPendingErro409(null);
              const err: any = new Error(detalhe.mensagem);
              err.status = 409; err.detail = { mensagem: detalhe.mensagem, competencias_excedidas: detalhe.competencias_excedidas };
              return Promise.reject(err);
            }
            atualizarItem(valeAbertoPara, { vale: d });
            setValeAbertoPara(null);
          }}
          onCancelar={() => { setPendingErro409(null); setValeAbertoPara(null); }} />
      )}

      {desmarcandoVale !== null && (
        <Modal title="Remover o vale deste item?" onClose={() => setDesmarcandoVale(null)} width="440px">
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            Este item ainda não foi salvo, então nenhum vale foi criado. Remover a marcação vai descartar os
            dados informados (beneficiário e forma de desconto). Confirmar?
          </p>
          <div className="flex items-center gap-3 mt-3">
            <button className="btn-primary" onClick={() => { atualizarItem(desmarcandoVale, { vale: null }); setDesmarcandoVale(null); }}>
              <Check size={14} /> Sim, remover
            </button>
            <button className="btn-ghost" onClick={() => setDesmarcandoVale(null)}><X size={14} /> Não, manter</button>
          </div>
        </Modal>
      )}
    </>
  );
}
