"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3, Filter, Wallet, BookOpen, FileText, Clock, CheckCircle2, Circle, Receipt, X, Check, Building2, Layers, Search, Users, Plus,
  Paperclip, Pencil, ShoppingCart, Target, TrendingUp, Compass, Trash2, Wrench, AlertTriangle, Repeat, CreditCard, ArrowLeft, Award, Undo2,
} from "lucide-react";
import {
  fetchLancamentos, marcarPagoFinanceiro, criarBaixaLote, criarBaixaLoteDetalhada, fetchOpcoesFinanceiro, fetchPlanoContas, fetchPatrimonio,
  atualizarPlanoManutencaoPatrimonio, fetchManutencoesPatrimonio, registrarManutencaoPatrimonio,
  criarPatrimonio, atualizarPatrimonio, atualizarValorMercadoPatrimonio, vincularLancamentoPatrimonio, fetchPatrimonioListaSimples, type PatrimonioPayload,
  fetchPessoas, fetchRmca, fetchCustoLitroLeite, fetchCustoHectare, fetchCustoVacaLote, fetchCustoSafra, fetchSafras, formatBRL, formatDate,
  atualizarLancamentoFinanceiro, ehAdmin, ehConsultor, fetchRelatorioCompraVendaAnimais, type LinhaRelatorioCompraVendaAnimal,
  fetchRelatorioCompraSemen, type LinhaRelatorioCompraSemen,
  fetchSupabaseDashboardUrl,
  fetchCentrosCusto,
  fetchOrcamento, criarItemOrcamento, atualizarItemOrcamento, excluirItemOrcamento, fetchComparativoOrcado,
  fetchCenarios, criarCenario, atualizarCenario, excluirCenario,
  fetchItensCenario, criarItemCenario, atualizarItemCenario, excluirItemCenario, fetchProjecaoCenario,
  importarParaPedido, type OrcamentoItemPayload, type CenarioPayload, type PlanejamentoItemPayload,
  anexarArquivoLancamentoPorId, anexarComprovanteEmLote, listarAnexosLancamentoPorId, excluirAnexoLancamento, urlAnexoLancamento, type AnexoLancamento,
  fetchCartoesCredito, fetchCartaoCredito, criarCartaoCredito, atualizarCartaoCredito, fetchExtratoCartao, fetchFaturasCartao,
  criarLancamentoCartao, fecharFaturaCartao, pagarFaturaCartao,
  type CartaoCredito, type CartaoCreditoPayload, type FaturaCartao, type LancamentoCartao,
  marcarItemComoVale, desmarcarItemComoVale,
  estornarPagamentoLancamento, type EstornoLancamentoOut,
  fetchEstoque, fetchServicosCadastro,
  vincularProdutoItem, fetchClassificacoesCadastro, criarClassificacao,
} from "@/lib/api";
import ValeItemModal, { type ValeItemDados } from "@/components/ValeItemModal";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { ServicoPicker } from "@/components/ServicoPicker";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovoServicoRapido from "@/components/NovoServicoRapido";
import {
  ComposedChart, Bar, Line, LineChart, BarChart, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Cell, CartesianGrid,
} from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { Dropzone } from "@/components/Dropzone";
import { ReciboModal } from "@/components/ReciboModal";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { ModalDivididoDocumento } from "@/components/ModalDivididoDocumento";
import { AvisoSalvo } from "@/components/AvisoSalvo";
import { FiltrosSalvos } from "@/components/FiltrosSalvos";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import type { ContaPlano } from "@/lib/contaGerencial";
import { TabBar, SecaoRecolhivel, Indicador } from "@/components/ui";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import FolhaPagamentoView from "@/components/FolhaPagamentoView";
import RelatorioFolhaPagamentoView from "@/components/RelatorioFolhaPagamentoView";
import { DocumentosFiscais } from "@/components/DocumentosFiscais";
import LancamentosRecorrentesView from "@/components/LancamentosRecorrentesView";
import { casaBusca } from "@/lib/busca";

const COLUNAS_LANCAMENTOS = [
  { header: "Nº lanç.", key: "numero_lancamento" }, { header: "Data", key: "data" },
  { header: "Descrição", key: "descricao" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
  { header: "Centro custo", key: "centro_custo" }, { header: "Documento", key: "documento" },
  { header: "Valor", key: "valor" }, { header: "Pago", key: "valor_pago" }, { header: "Conta bancária", key: "conta_bancaria" },
  // Comprovante em arquivo (inclusive o comprovante único de um pagamento em
  // lote, compartilhado por todas as notas da remessa) — ver
  // `tem_comprovante` em listar_lancamentos no backend.
  { header: "Comprovante", key: "comprovante_txt" },
];
const COLUNAS_LIVRO = [
  { header: "Data", key: "dataFmt" }, { header: "Descrição", key: "descricao" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
  { header: "Entrada", key: "entrada" }, { header: "Saída", key: "saida" }, { header: "Saldo", key: "saldo" },
];

type Lanc = {
  id: number; numero_lancamento: string | null;
  tipo: string; valor: number; valor_pago: number | null; desconto_acrescimo: number | null;
  centro_custo: string; classificacao?: string | null; codigo_conta: string; conta_completa: string;
  descricao: string; fornecedor: string; responsavel: string | null;
  tipo_documento: string | null; numero_documento: string | null; numero_os_orcamento: string | null; numero_documento_pagamento: string | null;
  numero_boleto?: string | null;
  // Tem comprovante/anexo em arquivo — inclusive o comprovante único de um
  // pagamento em lote, que é o mesmo arquivo para todas as notas da remessa.
  tem_comprovante?: boolean;
  conta_bancaria: string | null; forma_pagamento: string | null; data_vencimento_cartao: string | null; entregue: boolean | null;
  parcela_num: number | null; parcela_total: number | null;
  data_competencia: string | null; data_pagamento: string | null; data_vencimento: string | null; data_emissao: string | null;
  mes_competencia: string | null; mes_caixa: string | null;
  itens?: { id: number; produto: string; tipo_item?: string | null; valor_total: number; descricao?: string | null;
            eh_vale: boolean; vale_tipo: "funcionario" | "avulso" | null; vale_id: number | null;
            vale_pessoa_id: number | null; vale_pessoa_nome: string | null }[];
  usuario_nome?: string | null;
  patrimonio_id?: number | null;
};

type Rel = "fluxo" | "dre" | "livro" | "a_pagar" | "a_receber" | "pagas" | "recebidas" | "folha_relatorio" | "extrato" | "patrimonio" | "lote" | "pagamento" | "recebimento" | "folha" | "rmca" | "custo_litro_leite" | "custo_hectare" | "custo_vaca_lote" | "custo_safra" | "compra_venda_animais" | "compra_semen" | "orcamento" | "planejamento_financeiro" | "documentos" | "recorrentes" | "cartao_credito";
const RELATORIOS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "fluxo", label: "Fluxo de Caixa", icon: Wallet, desc: "Entradas × saídas por regime de caixa" },
  { id: "dre", label: "DRE Gerencial", icon: FileText, desc: "Resultado por competência" },
  { id: "livro", label: "Livro Caixa", icon: BookOpen, desc: "Lançamentos com saldo acumulado" },
  { id: "extrato", label: "Extrato completo", icon: Receipt, desc: "Todos os lançamentos, com ou sem baixa" },
  { id: "rmca", label: "RMCA", icon: BarChart3, desc: "Receita do leite menos custo de alimentação — gerencial e físico lado a lado" },
  { id: "custo_litro_leite", label: "Custo p/L de leite", icon: BarChart3, desc: "Custo de alimentação do período dividido pelos litros de leite entregues" },
  { id: "custo_hectare", label: "Custo por hectare", icon: BarChart3, desc: "Despesas do período divididas pela área total da fazenda" },
  { id: "custo_vaca_lote", label: "Custo por vaca/lote", icon: BarChart3, desc: "Despesas do período divididas pelo nº de vacas em lactação, por lote" },
  { id: "custo_safra", label: "Custo por safra", icon: BarChart3, desc: "Despesas do centro de custo e período da safra divididas por hectare/tonelada" },
  { id: "compra_venda_animais", label: "Compra/Venda de animais", icon: ShoppingCart, desc: "Consulta por animal, período, documento ou GTA" },
  { id: "compra_semen", label: "Compra de sêmen", icon: ShoppingCart, desc: "Consulta por touro, período, documento ou vendedor" },
];
const CONTAS: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "a_pagar", label: "Contas a pagar", icon: Clock, desc: "Despesas em aberto (sem data de pagamento)" },
  { id: "a_receber", label: "Contas a receber", icon: Clock, desc: "Receitas em aberto (sem data de recebimento)" },
  { id: "pagas", label: "Contas pagas", icon: CheckCircle2, desc: "Despesas já quitadas" },
  { id: "recebidas", label: "Contas recebidas", icon: CheckCircle2, desc: "Receitas já recebidas" },
  { id: "folha_relatorio", label: "Folha de Pagamento", icon: Users, desc: "Relatório da folha — pagos e a vencer, com exportação" },
  { id: "extrato", label: "Todas", icon: Receipt, desc: "Todos os lançamentos, com ou sem baixa" },
];
const ACOES: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "pagamento", label: "Pagamento", icon: Wallet, desc: "Lançar/quitar uma nota de despesa" },
  { id: "recebimento", label: "Recebimento", icon: Wallet, desc: "Lançar/quitar uma nota de receita" },
  { id: "lote", label: "Pagamento/recebimento em lote", icon: Layers, desc: "Dar baixa em várias notas de uma vez" },
  { id: "folha", label: "Folha de pagamento", icon: Users, desc: "Lançamento e acompanhamento da folha" },
  { id: "recorrentes", label: "Lançamentos recorrentes", icon: Repeat, desc: "Contas que se repetem todo mês (energia, internet, aluguel...) — cadastre uma vez, gere só com o valor do período" },
];
const PLANEJAMENTO: { id: Rel; label: string; icon: any; desc: string }[] = [
  { id: "orcamento", label: "Orçamento", icon: Target, desc: "Planilha orçamentária por conta gerencial/centro de custo/mês, comparada ao realizado" },
  { id: "planejamento_financeiro", label: "Planejamento financeiro", icon: TrendingUp, desc: "Cenários (otimista/realista/pessimista) com projeção de fluxo de caixa" },
];
const CONTAS_IDS = new Set(CONTAS.map((c) => c.id));
const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;
const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };
const fmtMes = (m: string) => m?.slice(2) ?? "";
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
// "2026-07" → "jul/2026" (rótulo legível do mês de competência)
const mesCompLabel = (comp: string) => {
  const [a, m] = (comp || "").split("-");
  const idx = parseInt(m, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_ABREV[idx]}/${a}` : (comp || "");
};

function KPI({ v, l, c }: { v: string; l: string; c?: string }) {
  return <Indicador valor={v} rotulo={l} categoria="financeiro" cor={c} />;
}

// ── Ordenação client-side genérica das listas de notas ──
// Cada coluna clicável tem uma função que extrai o valor de comparação; o
// primeiro clique ordena crescente e o seguinte alterna para decrescente.
// Ordena sempre a lista JÁ FILTRADA que recebe — nunca a lista bruta.
type OrdemDir = "asc" | "desc";
function useOrdenacao<T>(itens: T[], getters: Record<string, (r: T) => string | number>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<OrdemDir>("asc");
  const ordenar = (chave: string) => {
    if (sortKey === chave) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(chave); setSortDir("asc"); }
  };
  const ordenados = useMemo(() => {
    const g = sortKey ? getters[sortKey] : null;
    if (!g) return itens;
    return [...itens].sort((a, b) => {
      const va = g(a), vb = g(b);
      const cmp = typeof va === "number" && typeof vb === "number"
        ? va - vb
        : String(va).localeCompare(String(vb), "pt-BR", { numeric: true, sensitivity: "base" });
      return sortDir === "asc" ? cmp : -cmp;
    });
    // getters é estável em lógica; recomputa quando muda a lista ou a ordem.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itens, sortKey, sortDir]);
  return { ordenados, sortKey, sortDir, ordenar };
}

// Cabeçalho de coluna clicável, com indicador ▲/▼ na coluna ativa.
function ThOrd({ rotulo, chave, sortKey, sortDir, onSort, style }: {
  rotulo: string; chave: string; sortKey: string | null; sortDir: OrdemDir;
  onSort: (chave: string) => void; style?: React.CSSProperties;
}) {
  const ativo = sortKey === chave;
  return (
    <th onClick={() => onSort(chave)} title="Clique para ordenar por esta coluna"
      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", color: ativo ? "var(--dourado-light)" : undefined, ...style }}>
      {rotulo}{ativo ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
    </th>
  );
}

// Código da conta gerencial de um lançamento (folha, ou o resumo por nível 1).
const contaDoLanc = (r: Lanc) => r.conta_completa || r.codigo_conta || "";
// Uma conta selecionada casa com o próprio código e com todos os descendentes
// ("3.01" casa "3.01", "3.01.02"…) — filtro por conta e toda a subárvore.
const casaContaGerencial = (r: Lanc, sel: string) => {
  if (!sel) return true;
  const c = contaDoLanc(r);
  return c === sel || c.startsWith(sel + ".");
};

/**
 * Filtro por CONTA GERENCIAL em árvore — reusa o mesmo SeletorContaGerencial
 * dos Lançamentos (árvore, só folha selecionável, estilo por nível). Quando o
 * contexto mistura receita e despesa (extrato, DRE, fluxo), mostra as duas
 * árvores; quando é só um tipo, mostra uma. "Limpar" volta para "Todas".
 */
function FiltroContaGerencial({ contas, tipos, codigo, nome, onChange }: {
  contas: ContaPlano[]; tipos: ("despesa" | "receita")[];
  codigo: string; nome: string; onChange: (codigo: string, nome: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", minWidth: "220px" }}>
      {tipos.map((t) => (
        <SeletorContaGerencial
          key={t}
          contas={contas}
          tipo={t}
          codigo={codigo}
          nome={nome}
          onSelect={onChange}
          placeholder={tipos.length > 1 ? `Conta de ${t === "receita" ? "receita" : "despesa"}…` : "Todas as contas…"}
        />
      ))}
      {codigo && (
        <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem", alignSelf: "flex-start" }}
          title="Voltar a considerar todas as contas gerenciais" onClick={() => onChange("", "")}>
          Limpar conta
        </button>
      )}
    </div>
  );
}

export default function FinanceiroPage() {
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rel, setRel] = useState<Rel>("a_pagar");
  // Link pro banco de dados externo (Supabase) — só busca quando o usuário
  // entra numa sub-aba de Relatórios financeiros, e só se não for consultor
  // (backend já bloqueia; aqui é só pra não mostrar o botão à toa).
  const [supabaseUrl, setSupabaseUrl] = useState<string | null>(null);
  useEffect(() => {
    if (RELATORIOS.some((r) => r.id === rel) && !ehConsultor() && supabaseUrl === null) {
      fetchSupabaseDashboardUrl().then((d) => setSupabaseUrl(d.url || "")).catch(() => setSupabaseUrl(""));
    }
  }, [rel]);
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  // Único filtro de período das sub-abas de Contas (a pagar/receber/pagas/
  // recebidas/extrato) — antes eram 2-3 filtros de data sobrepostos e
  // ambíguos (um sem rótulo de campo + vencimento + pagamento dentro de
  // TabelaContas); agora é um seletor de campo + um único De/Até.
  const [campoPeriodoContas, setCampoPeriodoContas] = useState<"emissao" | "vencimento" | "pagamento">("emissao");
  const [centro, setCentro] = useState("");
  const [contaBanco, setContaBanco] = useState("");
  const [exp, setExp] = useState<Set<string>>(new Set());
  const toggleExp = (k: string) => setExp((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const [contasBancarias, setContasBancarias] = useState<string[]>([]);
  // Nota a tratar (pré-selecionada) quando se chega às sub-abas de
  // Pagamento/Recebimento vindo da lista de Contas a pagar/receber ou da Agenda.
  const [notaAlvoRef, setNotaAlvoRef] = useState<string | null>(null);
  const [editando, setEditando] = useState<Lanc | null>(null);
  // #— bug do recibo: além do Lanc em si, carrega a(s) parcela(s) nova(s)
  // criada(s) pelo reparcelamento do restante não pago nesta baixa (quando
  // houver) — ver `reparcelamentoDoRecibo` logo abaixo.
  const [recibo, setRecibo] = useState<(Lanc & { reparcelamento?: { valor: number; data_vencimento: string | null; parcela_num: number | null }[] }) | null>(null);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [visaoFluxo, setVisaoFluxo] = useState<"mensal" | "diario">("mensal");
  // Opções de fornecedor/cliente e produto/serviço para os filtros dos relatórios.
  const [opcoesRel, setOpcoesRel] = useState<{ fornecedores: string[]; produtos: string[] }>({ fornecedores: [], produtos: [] });
  // Filtros extras dos relatórios (fluxo/DRE/livro) — além de período e centro.
  const [relTipo, setRelTipo] = useState<"" | "receita" | "despesa">("");
  const [relFornecedor, setRelFornecedor] = useState("");
  const [relProduto, setRelProduto] = useState("");
  const [relDocumento, setRelDocumento] = useState("");
  const [relConta, setRelConta] = useState("");
  const [relContaNome, setRelContaNome] = useState("");

  // Filtros salvos (ver components/FiltrosSalvos.tsx) — cada aba de relatório
  // tem seu próprio conjunto ("tela" = `financeiro_${rel}`), com o formato de
  // filtro variando conforme a aba seja uma "Conta" (período+centro+banco) ou
  // um dos outros relatórios (tipo/fornecedor/produto/documento/conta gerencial).
  function filtrosAtuais(): Record<string, any> {
    return CONTAS_IDS.has(rel)
      ? { campoPeriodoContas, inicio, fim, centro, contaBanco }
      : { inicio, fim, centro, relTipo, relFornecedor, relProduto, relDocumento, relConta, relContaNome };
  }
  function aplicarFiltrosSalvos(f: Record<string, any>) {
    if ("campoPeriodoContas" in f) setCampoPeriodoContas(f.campoPeriodoContas || "emissao");
    if ("inicio" in f) setInicio(f.inicio || "");
    if ("fim" in f) setFim(f.fim || "");
    if ("centro" in f) setCentro(f.centro || "");
    if ("contaBanco" in f) setContaBanco(f.contaBanco || "");
    if ("relTipo" in f) setRelTipo(f.relTipo || "");
    if ("relFornecedor" in f) setRelFornecedor(f.relFornecedor || "");
    if ("relProduto" in f) setRelProduto(f.relProduto || "");
    if ("relDocumento" in f) setRelDocumento(f.relDocumento || "");
    if ("relConta" in f) setRelConta(f.relConta || "");
    if ("relContaNome" in f) setRelContaNome(f.relContaNome || "");
  }

  // Acha, entre TODOS os lançamentos carregados (`regs`), a(s) parcela(s)
  // nova(s) que nasceram do reparcelamento do restante desta baixa parcial —
  // ver PUT /financeiro/lancamentos/{id}/pagar (`parcelas_diferenca`): elas
  // compartilham numero_lancamento, ainda não têm data_pagamento e a soma
  // delas bate com a diferença (valor da conta − valor pago). Sem essa soma
  // bater, não arrisca mostrar parcelas de outro reparcelamento/pendência
  // não relacionada — o recibo simplesmente não exibe a seção.
  function reparcelamentoDoRecibo(l: Lanc): { valor: number; data_vencimento: string | null; parcela_num: number | null }[] {
    if (l.valor_pago == null) return [];
    const restante = Math.round((l.valor - l.valor_pago) * 100) / 100;
    // desconto_acrescimo != 0 nesta baixa significa que a diferença foi
    // absorvida como desconto/acréscimo, não reparcelada — nada a mostrar.
    if (restante <= 0 || Math.round((l.desconto_acrescimo || 0) * 100) !== 0 || !l.numero_lancamento || !regs) return [];
    const candidatas = regs.filter((s) =>
      s.numero_lancamento === l.numero_lancamento && s.id !== l.id &&
      !s.data_pagamento && s.valor_pago == null && (s.parcela_num ?? 0) > (l.parcela_num ?? 0),
    );
    const soma = Math.round(candidatas.reduce((acc, s) => acc + (s.valor || 0), 0) * 100) / 100;
    if (!candidatas.length || soma !== restante) return [];
    return candidatas.map((s) => ({ valor: s.valor, data_vencimento: s.data_vencimento, parcela_num: s.parcela_num }));
  }

  const recarregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    recarregar();
    fetchOpcoesFinanceiro().then((d) => {
      setContasBancarias(d.contas_bancarias || []);
      setOpcoesRel({ fornecedores: d.fornecedores || [], produtos: d.produtos || [] });
    }).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
  }, []);

  // Vindo da Agenda (link "Ir para Financeiro" de uma conta a pagar/receber
  // vencendo) — abre a sub-aba de Pagamento/Recebimento certa e já pré-seleciona
  // a nota informada, em vez de dar baixa direto na lista.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const ir = qs.get("ir");
    if (ir === "a_pagar") setRel("pagamento");
    else if (ir === "a_receber") setRel("recebimento");
    // "folha" — vem do card de diária da Agenda ("Contar diária"/"Descartar
    // diária" clicam no card, não nos botões, pra abrir direto em Financeiro
    // > Ações > Folha de pagamento; a sub-aba/diária específica dentro dela é
    // lida pelo próprio FolhaPagamentoView a partir de categoria/diaria/
    // calendario, ver useEffect lá).
    else if (ir === "folha") setRel("folha");
    else if (ir && ["pagas", "recebidas", "extrato"].includes(ir)) setRel(ir as Rel);
    const ref = qs.get("ref");
    if (ref) setNotaAlvoRef(ref);
  }, []);

  // Árvore de sub-navegação — a Sidebar desenha isto no lugar da lista de
  // módulos enquanto Financeiro estiver aberto (mesmo padrão de Lançamentos).
  const subNavTree: SubNavNode[] = useMemo(() => [
    { id: "contas-grupo", label: "Contas", icon: Wallet, children: CONTAS.map((r) => ({ id: r.id, label: r.label, icon: r.icon })) },
    { id: "acoes-grupo", label: "Ações", icon: Layers, children: ACOES.map((r) => ({ id: r.id, label: r.label, icon: r.icon })) },
    { id: "relatorios-grupo", label: "Relatórios", icon: FileText, children: RELATORIOS.map((r) => ({ id: r.id, label: r.label, icon: r.icon })) },
    { id: "planejamento-grupo", label: "Planejamento", icon: Compass, children: PLANEJAMENTO.map((r) => ({ id: r.id, label: r.label, icon: r.icon })) },
    // Patrimônio, Cartão de crédito e Documentos são destinos únicos — viram
    // folha direta (sem grupo "guarda-chuva" de 1 item só), economizando um
    // nível/clique da árvore de navegação.
    { id: "patrimonio", label: "Patrimônio", icon: Building2 },
    { id: "cartao_credito", label: "Cartão de crédito", icon: CreditCard },
    { id: "documentos", label: "Documentos", icon: Paperclip },
  ], []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: rel, onSelect: (id: string) => setRel(id as Rel) }), [subNavTree, rel]));

  // Nome real de cada código do plano de contas — usado para dar nome à
  // hierarquia no DRE e no detalhamento por conta do Fluxo de Caixa, em vez
  // de mostrar só o código ou a descrição solta de cada lançamento.
  const nomePorCodigo = useMemo(() => new Map(planoContas.map((p) => [p.codigo, p.nome])), [planoContas]);

  useEffect(() => {
    // Contas em aberto/pagas (CONTAS_IDS) não ganham período padrão: a lista
    // "filtrados" já trata ausência de período como "mostra tudo" — contas
    // vencidas ou a vencer não podem sumir por um filtro implícito de hoje.
    // O padrão vale só para os relatórios (Fluxo, DRE, Livro Caixa etc.),
    // que precisam de algum período para não ficar vazios.
    //
    // BUG corrigido: o padrão era literalmente hoje-hoje (1 dia só). Isso
    // esconde qualquer lançamento cuja data de competência não seja HOJE —
    // o que é o caso da imensa maioria dos lançamentos "automáticos" de RH
    // (Rescisão/Férias/13º/Folha usam a data do evento — desligamento,
    // competência etc. — não o dia em que o usuário clicou em "Fechar"), e
    // foi relatado como "rescisão fechada não aparece na DRE". Mês corrente
    // (1º dia até hoje) é um padrão muito mais útil e ainda "só um período",
    // sem virar uma varredura de todo o histórico.
    if (regs && !inicio && !CONTAS_IDS.has(rel)) {
      const hoje = new Date();
      const inicioMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
      setInicio(inicioMes);
      setFim(hoje.toISOString().slice(0, 10));
    }
  }, [regs, inicio, rel]);

  // Aplica o centro de custo padrão só na 1ª carga — do contrário, este efeito
  // reagia à própria mudança de `centro` e desfazia a escolha de "Todos"
  // (valor "") assim que o usuário selecionava, sempre voltando pra Pecuária
  // Leiteira (bug relatado no filtro "Todos"/"Sem centro de custo").
  const centroInicializado = useRef(false);
  useEffect(() => {
    if (regs && !centroInicializado.current) {
      centroInicializado.current = true;
      setCentro((atual) => atual || "Pecuária Leiteira");
    }
  }, [regs]);

  const centros = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo))).sort(), [regs]);
  // Produto/serviço: opções vindas do backend + nomes efetivamente lançados nas
  // notas (produto e serviço dividem o campo `produto` do item).
  const opcoesProdutoRel = useMemo(() => {
    const s = new Set<string>(opcoesRel.produtos);
    (regs ?? []).forEach((r) => (r.itens || []).forEach((it) => { if (it.produto) s.add(it.produto); }));
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [opcoesRel.produtos, regs]);

  // Base de cada sub-aba de contas: em aberto (sem data de pagamento) ou já quitadas.
  const contasBase = useMemo(() => {
    if (!regs) return [];
    switch (rel) {
      case "a_pagar": return regs.filter((r) => r.tipo === "despesa" && !r.data_pagamento);
      case "a_receber": return regs.filter((r) => r.tipo === "receita" && !r.data_pagamento);
      case "pagas": return regs.filter((r) => r.tipo === "despesa" && r.data_pagamento);
      case "recebidas": return regs.filter((r) => r.tipo === "receita" && r.data_pagamento);
      case "extrato": return regs;
      default: return regs;
    }
  }, [regs, rel]);

  // "Pagamento" não existe em contas ainda em aberto — se o usuário estava
  // numa aba que tem esse campo e troca para a_pagar/a_receber, volta para
  // o padrão (emissão) em vez de manter um filtro que nunca bate com nada.
  useEffect(() => {
    if ((rel === "a_pagar" || rel === "a_receber") && campoPeriodoContas === "pagamento") setCampoPeriodoContas("emissao");
  }, [rel, campoPeriodoContas]);

  // Data relevante por aba: DRE = competência; Contas = campo escolhido no
  // filtro único de período (emissão por padrão); fluxo/livro = pagamento.
  const campoData = (r: Lanc) => {
    if (rel === "dre") return r.data_competencia;
    if (CONTAS_IDS.has(rel)) {
      if (campoPeriodoContas === "emissao") return r.data_emissao || r.data_competencia;
      if (campoPeriodoContas === "vencimento") return r.data_vencimento || r.data_competencia;
      return r.data_pagamento;
    }
    return r.data_pagamento;
  };
  const campoMes = (r: Lanc) => (rel === "dre" ? r.mes_competencia : r.mes_caixa);

  const filtrados = useMemo(() => {
    if (CONTAS_IDS.has(rel)) {
      // Sem período definido, mostra tudo — contas em aberto não devem sumir por falta de filtro.
      return contasBase.filter((r) => {
        const d = campoData(r);
        // Início e fim funcionam como limites independentes — só um dos dois
        // já filtra (ex.: só "início" = "a partir desta data em diante").
        // BUG corrigido: antes, um lançamento sem data nesse campo passava
        // SEMPRE, mesmo com início/fim escolhidos pelo usuário — o filtro de
        // período (e, por tabela, o de centro de custo junto dele) parecia
        // simplesmente não fazer nada, porque a maioria das contas em aberto
        // não tem "data de pagamento" preenchida. Agora esse "não filtra por
        // falta de dado" só vale quando NENHUM período foi definido (início E
        // fim vazios) — que é o caso que a regra original queria cobrir.
        const semPeriodoDefinido = !inicio && !fim;
        const dentroPeriodo = semPeriodoDefinido || (d != null && d !== "" && (!inicio || d >= inicio) && (!fim || d <= fim));
        return dentroPeriodo && (!centro || r.centro_custo === centro) && (!contaBanco || r.conta_bancaria === contaBanco);
      });
    }
    if (!regs) return [];
    // Busca por documento é GLOBAL: quem digita um número de nota quer achar
    // aquela nota, não "aquela nota dentro deste período e deste centro de
    // custo". Antes, procurar uma NF exigia acertar antes o período — e a
    // data comparada aqui é a de PAGAMENTO, então uma compra a prazo (nota de
    // sêmen parcelada, por exemplo) era descartada antes de o filtro de
    // documento sequer rodar: a nota existia e simplesmente não aparecia.
    const buscaPorDocumento = !!relDocumento.trim();
    if (!buscaPorDocumento && (!inicio || !fim)) return [];
    return regs.filter((r) => {
      const d = campoData(r);
      if (!buscaPorDocumento && !(d && d >= inicio && d <= fim)) return false;
      if (!buscaPorDocumento && centro && r.centro_custo !== centro) return false;
      if (relTipo && r.tipo !== relTipo) return false;
      if (relFornecedor && r.fornecedor !== relFornecedor) return false;
      if (relProduto && !(r.itens || []).some((it) => it.produto === relProduto)) return false;
      if (relDocumento && !casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""} ${r.numero_boleto || ""}`, relDocumento)) return false;
      if (!casaContaGerencial(r, relConta)) return false;
      return true;
    });
  }, [regs, contasBase, rel, inicio, fim, centro, contaBanco, relTipo, relFornecedor, relProduto, relDocumento, relConta, campoPeriodoContas]);

  const receitas = filtrados.filter((r) => r.tipo === "receita").reduce((a, r) => a + r.valor, 0);
  const despesas = filtrados.filter((r) => r.tipo === "despesa").reduce((a, r) => a + r.valor, 0);
  const resultado = receitas - despesas;

  // Panorama da coluna esquerda de Contas a pagar/a receber (ver tela
  // "Consultar" do plano de duas colunas) — só faz sentido "vencido"/"a
  // vencer" nessas duas abas (contas ainda em aberto); pagas/recebidas/
  // extrato mostram só o total do período filtrado.
  const kpisContas = useMemo(() => {
    if (!CONTAS_IDS.has(rel)) return null;
    const total = filtrados.reduce((s, r) => s + (r.valor || 0), 0);
    if (rel !== "a_pagar" && rel !== "a_receber") return { total, vencido: null as number | null, aVencer: null as number | null };
    const hoje = new Date().toISOString().slice(0, 10);
    const em7dias = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
    const abertos = filtrados.filter((r) => r.valor_pago == null);
    const vencido = abertos.filter((r) => r.data_vencimento && r.data_vencimento < hoje).reduce((s, r) => s + (r.valor || 0), 0);
    const aVencer = abertos.filter((r) => r.data_vencimento && r.data_vencimento >= hoje && r.data_vencimento <= em7dias).reduce((s, r) => s + (r.valor || 0), 0);
    return { total, vencido, aVencer };
  }, [filtrados, rel]);

  // Fluxo de caixa mensal (com saldo acumulado)
  const fluxoMensal = useMemo(() => {
    const by = new Map<string, { mes: string; entradas: number; saidas: number }>();
    filtrados.forEach((r) => {
      const m = campoMes(r); if (!m) return;
      const e = by.get(m) ?? { mes: m, entradas: 0, saidas: 0 };
      if (r.tipo === "receita") e.entradas += r.valor; else e.saidas += r.valor;
      by.set(m, e);
    });
    let acc = 0;
    return Array.from(by.values()).sort((a, b) => a.mes.localeCompare(b.mes)).map((x) => {
      acc += x.entradas - x.saidas;
      return { ...x, saldo: x.entradas - x.saidas, acumulado: Math.round(acc) };
    });
  }, [filtrados, rel]);

  // Fluxo de caixa diário (mesma lógica do mensal, por data em vez de mês) —
  // acompanhamento dia a dia, igual ao extrato bancário.
  const fluxoDiario = useMemo(() => {
    const by = new Map<string, { dia: string; entradas: number; saidas: number }>();
    filtrados.forEach((r) => {
      const d = campoData(r); if (!d) return;
      const e = by.get(d) ?? { dia: d, entradas: 0, saidas: 0 };
      if (r.tipo === "receita") e.entradas += r.valor; else e.saidas += r.valor;
      by.set(d, e);
    });
    let acc = 0;
    return Array.from(by.values()).sort((a, b) => a.dia.localeCompare(b.dia)).map((x) => {
      acc += x.entradas - x.saidas;
      return { ...x, saldo: x.entradas - x.saidas, acumulado: Math.round(acc) };
    });
  }, [filtrados, rel]);

  // Propaga o valor de um lançamento por TODOS os níveis do código (ex.:
  // "2.01.01.01" também soma em "2.01.01", "2.01" e "2") — é assim que uma
  // conta de grupo (sem lançamento direto) mostra o total dos filhos.
  const propagarPorHierarquia = (codigoFolha: string): string[] => {
    const partes = codigoFolha.split(".");
    return partes.map((_, i) => partes.slice(0, i + 1).join("."));
  };

  // DRE por conta gerencial — hierárquico, usando o NOME real do plano de
  // contas (Configurações > Importar dados). Lançamentos sem conta classificada
  // continuam aparecendo à parte, por descrição (comportamento antigo).
  const dreContas = useMemo(() => {
    const by = new Map<string, { conta: string; nome: string; codigo: string; nivel: number; receitas: number; despesas: number }>();
    filtrados.forEach((r) => {
      const codigoFolha = r.conta_completa || r.codigo_conta || "";
      if (!codigoFolha) {
        const k = r.descricao || "(sem conta)";
        const e = by.get(k) ?? { conta: k, nome: k, codigo: "", nivel: 0, receitas: 0, despesas: 0 };
        if (r.tipo === "receita") e.receitas += r.valor; else e.despesas += r.valor;
        by.set(k, e);
        return;
      }
      const niveis = propagarPorHierarquia(codigoFolha);
      niveis.forEach((codigo, i) => {
        const nomeConhecido = nomePorCodigo.get(codigo);
        const ehFolha = i === niveis.length - 1;
        if (!nomeConhecido && !ehFolha) return; // nível intermediário sem nome cadastrado — não gera linha "só número"
        const nome = nomeConhecido || (r.descricao || codigo);
        const e = by.get(codigo) ?? { conta: codigo, nome, codigo, nivel: i + 1, receitas: 0, despesas: 0 };
        if (r.tipo === "receita") e.receitas += r.valor; else e.despesas += r.valor;
        by.set(codigo, e);
      });
    });
    return Array.from(by.values()).map((x) => ({ ...x, saldo: x.receitas - x.despesas })).sort((a, b) => a.conta.localeCompare(b.conta));
  }, [filtrados, nomePorCodigo]);

  // Meses presentes no período filtrado (para as colunas do detalhamento).
  const mesesFluxo = useMemo(() => Array.from(new Set(filtrados.map(campoMes).filter(Boolean))).sort() as string[], [filtrados, rel]);

  // Detalhamento por conta do Fluxo de Caixa — mesma hierarquia do DRE, mas
  // com uma coluna por mês (igual ao "Fluxo mensal detalhado" de referência).
  const detalhePorContaMensal = useMemo(() => {
    const by = new Map<string, { codigo: string; nome: string; nivel: number; porMes: Record<string, number>; total: number }>();
    filtrados.forEach((r) => {
      const codigoFolha = r.conta_completa || r.codigo_conta || "";
      const mes = campoMes(r);
      if (!codigoFolha || !mes) return;
      const niveis = propagarPorHierarquia(codigoFolha);
      niveis.forEach((codigo, i) => {
        const nomeConhecido = nomePorCodigo.get(codigo);
        const ehFolha = i === niveis.length - 1;
        if (!nomeConhecido && !ehFolha) return; // nível intermediário sem nome cadastrado — não gera linha "só número"
        const nome = nomeConhecido || (r.descricao || codigo);
        const e = by.get(codigo) ?? { codigo, nome, nivel: i + 1, porMes: {}, total: 0 };
        e.porMes[mes] = Math.round(((e.porMes[mes] || 0) + r.valor) * 100) / 100;
        e.total = Math.round((e.total + r.valor) * 100) / 100;
        by.set(codigo, e);
      });
    });
    return Array.from(by.values()).sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [filtrados, nomePorCodigo, rel]);

  // Livro caixa (cronológico com saldo acumulado)
  const livro = useMemo(() => {
    let acc = 0;
    return [...filtrados].filter((r) => r.data_pagamento).sort((a, b) => (a.data_pagamento! < b.data_pagamento! ? -1 : 1)).map((r) => {
      const entrada = r.tipo === "receita" ? r.valor : 0;
      const saida = r.tipo === "despesa" ? r.valor : 0;
      acc += entrada - saida;
      return { data: r.data_pagamento, descricao: r.descricao, fornecedor: r.fornecedor, entrada, saida, saldo: Math.round(acc) };
    });
  }, [filtrados]);
  // Ordenação do Livro Caixa — "Saldo" fica de fora de propósito: é acumulado
  // na ordem cronológica original, então ordenar por ele não faz sentido.
  const { ordenados: livroOrdenado, sortKey: sortKeyLivro, sortDir: sortDirLivro, ordenar: ordenarLivro } = useOrdenacao(livro, {
    data: (r) => r.data || "",
    descricao: (r) => (r.descricao || "").toLowerCase(),
    fornecedor: (r) => (r.fornecedor || "").toLowerCase(),
    entrada: (r) => r.entrada,
    saida: (r) => r.saida,
  });
  const pagLivro = usePaginacao(livroOrdenado);

  const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  // Cartão de filtros — reaproveitado tanto na coluna esquerda de Contas
  // (a pagar/a receber/pagas/recebidas/extrato, ver kpisContas acima) quanto
  // no layout de coluna única dos outros relatórios (Fluxo/DRE/Livro...).
  const filtrosCard = (
    <div className="card mb-4">
      <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
      <div className="mb-3">
        <FiltrosSalvos tela={`financeiro_${rel}`} valor={filtrosAtuais()} aoAplicar={aplicarFiltrosSalvos} />
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        {CONTAS_IDS.has(rel) ? (
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Período por</label>
            <div className="flex gap-2">
              <select style={inputStyle} value={campoPeriodoContas} onChange={(e) => setCampoPeriodoContas(e.target.value as any)}>
                <option value="emissao">Emissão</option>
                <option value="vencimento">Vencimento</option>
                {rel !== "a_pagar" && rel !== "a_receber" && <option value="pagamento">Pagamento</option>}
              </select>
              <input type="date" style={inputStyle} value={inicio} onChange={(e) => setInicio(e.target.value)} title="De" />
              <input type="date" style={inputStyle} value={fim} onChange={(e) => setFim(e.target.value)} title="Até" />
            </div>
          </div>
        ) : <>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Início</label><input type="date" style={inputStyle} value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Fim</label><input type="date" style={inputStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
        </>}
        <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Centro de custo</label>
          <select style={inputStyle} value={centro} onChange={(e) => setCentro(e.target.value)}><option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}</select></div>
        {CONTAS_IDS.has(rel) && (
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Conta bancária</label>
            <select style={inputStyle} value={contaBanco} onChange={(e) => setContaBanco(e.target.value)}><option value="">Todas</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}</select></div>
        )}
        {!CONTAS_IDS.has(rel) && <>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Tipo</label>
            <select style={inputStyle} value={relTipo} onChange={(e) => setRelTipo(e.target.value as any)}>
              <option value="">Receitas e despesas</option><option value="receita">Só receitas</option><option value="despesa">Só despesas</option>
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Fornecedor / cliente</label>
            <select style={inputStyle} value={relFornecedor} onChange={(e) => setRelFornecedor(e.target.value)}>
              <option value="">Todos</option>{opcoesRel.fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Produto / serviço</label>
            <select style={inputStyle} value={relProduto} onChange={(e) => setRelProduto(e.target.value)}>
              <option value="">Todos</option>{opcoesProdutoRel.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...inputStyle, paddingLeft: "1.6rem" }} value={relDocumento} onChange={(e) => setRelDocumento(e.target.value)} placeholder="ex.: 4521" /></div></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Conta gerencial</label>
            <FiltroContaGerencial contas={planoContas}
              tipos={relTipo === "receita" ? ["receita"] : relTipo === "despesa" ? ["despesa"] : ["despesa", "receita"]}
              codigo={relConta} nome={relContaNome}
              onChange={(c, n) => { setRelConta(c); setRelContaNome(n); }} /></div>
        </>}
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", paddingBottom: "0.4rem" }}>
          {!CONTAS_IDS.has(rel) && <>Regime: <strong style={{ color: "var(--dourado-light)" }}>{rel === "dre" ? "competência" : "caixa"}</strong> · </>}
          {filtrados.length} lançamento{filtrados.length === 1 ? "" : "s"}
        </span>
      </div>
    </div>
  );

  return (
    <div className="p-6 animate-in">
      <div className="mb-4 flex items-start justify-between gap-3" style={{ flexWrap: "wrap" }}>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><BarChart3 size={22} style={{ color: "var(--dourado)" }} /> Controle Financeiro</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Escolha o relatório, o período e o centro de custo — indicadores, consolidado e gráfico.</p>
        </div>
        {RELATORIOS.some((r) => r.id === rel) && !!supabaseUrl && (
          <a href={supabaseUrl} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: "0.78rem", whiteSpace: "nowrap" }}>
            <Layers size={13} /> Banco de dados (Supabase)
          </a>
        )}
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os lançamentos financeiros</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && regs.length === 0 && !error && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <BarChart3 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-muted)" }}>Nenhum lançamento financeiro no banco.</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
            Suba o <strong>CONTA_GERENCIAL.csv</strong> na tela de <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importar dados</a>.
            Se você já subiu e sumiu, o banco de produção não está persistindo — confira o Postgres no Railway.
          </p>
        </div>
      )}

      {regs && regs.length > 0 && <>
        {rel === "patrimonio" ? <PatrimonioView />
          : rel === "cartao_credito" ? <CartaoCreditoView />
          : rel === "documentos" ? <DocumentosFiscais />
          : rel === "recorrentes" ? <LancamentosRecorrentesView onFeito={recarregar} />
          : rel === "pagamento" ? <PagamentoIndividualView key="despesa" tipo="despesa" contasBancarias={contasBancarias} notaAlvoRef={notaAlvoRef} onNotaTratada={() => setNotaAlvoRef(null)} onFeito={recarregar} />
          : rel === "recebimento" ? <PagamentoIndividualView key="receita" tipo="receita" contasBancarias={contasBancarias} notaAlvoRef={notaAlvoRef} onNotaTratada={() => setNotaAlvoRef(null)} onFeito={recarregar} />
          : rel === "lote" ? <PagamentoLoteView contasBancarias={contasBancarias} onFeito={recarregar} /> : rel === "folha" ? <FolhaPagamentoView />
          : rel === "folha_relatorio" ? <RelatorioFolhaPagamentoView /> : rel === "rmca" ? <RmcaView />
          : rel === "custo_litro_leite" ? <CustoLitroLeiteView />
          : rel === "custo_hectare" ? <CustoHectareView />
          : rel === "custo_vaca_lote" ? <CustoVacaLoteView />
          : rel === "custo_safra" ? <CustoSafraView />
          : rel === "compra_venda_animais" ? <RelatorioCompraVendaAnimaisView />
          : rel === "compra_semen" ? <RelatorioCompraSemenView />
          : rel === "orcamento" ? <OrcamentoView planoContas={planoContas} fornecedores={opcoesRel.fornecedores} />
          : rel === "planejamento_financeiro" ? <PlanejamentoFinanceiroView planoContas={planoContas} fornecedores={opcoesRel.fornecedores} /> : <>
        {CONTAS_IDS.has(rel) ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
              <div className="mb-4">
                {kpisContas?.vencido != null ? (
                  // Um número dominante (o que decide se precisa agir agora) em vez
                  // de 3 cartões do mesmo peso competindo pelo olhar — vencido e
                  // "vence em 7 dias" continuam os mesmos dados, só menores.
                  <div className="card" style={{ padding: "1.1rem 1.3rem" }}>
                    <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                      {rel === "a_pagar" ? "Total em aberto" : "Total a receber"}
                    </div>
                    <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--dourado-light)", marginTop: "0.25rem", fontVariantNumeric: "tabular-nums" }}>
                      {formatBRL(kpisContas.total)}
                    </div>
                    <div style={{ display: "flex", gap: "1.6rem", marginTop: "0.9rem", paddingTop: "0.8rem", borderTop: "1px solid var(--border)" }}>
                      <div>
                        <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--red)", fontVariantNumeric: "tabular-nums" }}>{formatBRL(kpisContas.vencido)}</div>
                        <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "0.1rem" }}>Vencido</div>
                      </div>
                      <div>
                        <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--amber)", fontVariantNumeric: "tabular-nums" }}>{formatBRL(kpisContas.aVencer ?? 0)}</div>
                        <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "0.1rem" }}>Vence em 7 dias</div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2">
                    <KPI v={formatBRL(kpisContas?.total ?? 0)} l="Total do período" c="var(--dourado-light)" />
                  </div>
                )}
              </div>
              {filtrosCard}
            </div>
            <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto" }}>
              <TabelaContas key={rel} rel={rel} itens={filtrados} planoContas={planoContas}
                onTratar={(l) => { setRel(l.tipo === "receita" ? "recebimento" : "pagamento"); setNotaAlvoRef(l.numero_lancamento || l.numero_documento || null); }}
                onEditar={(l) => setEditando(l)}
                onRecibo={(l) => setRecibo({ ...l, reparcelamento: reparcelamentoDoRecibo(l) })}
                onEstornado={recarregar} />
            </div>
          </div>
        ) : <>
        {filtrosCard}
        {/* Indicadores consolidados */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {rel === "fluxo" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo do período" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={fluxoMensal.length ? formatBRL(fluxoMensal[fluxoMensal.length - 1].acumulado) : "—"} l="Saldo acumulado" c="var(--dourado-light)" />
          </>}
          {rel === "dre" && <>
            <KPI v={formatBRL(receitas)} l="Receita" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Despesa" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Resultado" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={receitas > 0 ? `${Math.round((1000 * resultado) / receitas) / 10}%` : "—"} l="Margem" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
          </>}
          {rel === "livro" && <>
            <KPI v={formatBRL(receitas)} l="Entradas" c="var(--green-light)" />
            <KPI v={formatBRL(despesas)} l="Saídas" c="var(--red)" />
            <KPI v={formatBRL(resultado)} l="Saldo final" c={resultado >= 0 ? "var(--green-light)" : "var(--amber)"} />
            <KPI v={String(livro.length)} l="Lançamentos" />
          </>}
        </div>

        {/* Diário/Mensal — só se aplica ao Fluxo de Caixa */}
        {rel === "fluxo" && (
          <TabBar
            abas={[
              { id: "mensal", label: "Mensal", title: "Fluxo agrupado por mês de caixa" },
              { id: "diario", label: "Diário", title: "Fluxo dia a dia, como o extrato bancário" },
            ] as const}
            ativa={visaoFluxo}
            onChange={setVisaoFluxo}
          />
        )}

        {/* Gráfico do consolidado */}
        <div className="card mb-4">
          <div className="card-header mb-3">{rel === "fluxo" ? `Fluxo de Caixa ${visaoFluxo === "diario" ? "diário" : "mensal"} (entradas × saídas × acumulado)` : rel === "dre" ? "Receita × Despesa × Resultado" : "Saldo Acumulado"}</div>
          {rel === "fluxo" && visaoFluxo === "mensal" && (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={fluxoMensal}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="mes" tickFormatter={fmtMes} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="entradas" name="Entradas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="var(--red)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {rel === "fluxo" && visaoFluxo === "diario" && (<>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={fluxoDiario.filter((_, i) => i % Math.ceil(fluxoDiario.length / 200 || 1) === 0)}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="dia" tickFormatter={(d) => (d ? d.slice(5) : "")} tick={{ fill: "var(--text-muted)", fontSize: 9 }} minTickGap={30} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(d: any) => formatDate(d as string)} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
                <Bar dataKey="entradas" name="Entradas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="saidas" name="Saídas" fill="var(--red)" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="acumulado" name="Acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
            {Math.ceil(fluxoDiario.length / 200 || 1) > 1 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem", textAlign: "center" }}>
                Exibindo 1 a cada {Math.ceil(fluxoDiario.length / 200 || 1)} pontos para legibilidade.
              </p>
            )}
          </>)}
          {rel === "dre" && (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={[{ n: "Receita", v: receitas, f: "var(--green-light)" }, { n: "Despesa", v: despesas, f: "var(--red)" }, { n: "Resultado", v: Math.abs(resultado), f: resultado >= 0 ? "var(--dourado)" : "var(--amber)" }]}>
                <XAxis dataKey="n" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="v" barSize={70}>{[0, 1, 2].map((i) => <Cell key={i} fill={["var(--green-light)", "var(--red)", resultado >= 0 ? "var(--dourado)" : "var(--amber)"][i]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {rel === "livro" && (<>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={livro.filter((_, i) => i % Math.ceil(livro.length / 150 || 1) === 0)}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="data" tickFormatter={(d) => (d ? d.slice(5) : "")} tick={{ fill: "var(--text-muted)", fontSize: 9 }} minTickGap={30} />
                <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(d: any) => formatDate(d as string)} contentStyle={tip} />
                <Line type="monotone" dataKey="saldo" name="Saldo acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            {Math.ceil(livro.length / 150 || 1) > 1 && (
              <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem", textAlign: "center" }}>
                Exibindo 1 a cada {Math.ceil(livro.length / 150 || 1)} pontos para legibilidade.
              </p>
            )}
          </>)}
        </div>

        {/* Detalhamento do relatório */}
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.4rem" }}>
            <span>
              {rel === "fluxo" ? `Fluxo ${visaoFluxo === "diario" ? "Diário" : "Mensal"}` : rel === "dre" ? "Detalhamento por Conta Gerencial" : "Lançamentos"}
              {rel !== "livro" && <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}> (clique numa linha para ver os lançamentos)</span>}
            </span>
            {rel === "livro" && (
              <ExportarBotoes titulo="Livro Caixa" nomeArquivoBase="livro_caixa" colunas={COLUNAS_LIVRO}
                linhas={livro.map((l) => ({ ...l, dataFmt: formatDate(l.data || "") }))} />
            )}
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: rel === "livro" ? "460px" : "460px" }}>
            {rel === "fluxo" && visaoFluxo === "mensal" && (
              <table className="fazenda-table">
                <thead><tr><th></th><th>Mês</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Acumulado</th></tr></thead>
                <tbody>{fluxoMensal.map((m) => {
                  const aberto = exp.has("fluxo:" + m.mes);
                  const itens = aberto ? filtrados.filter((r) => campoMes(r) === m.mes).sort((a, b) => ((a.data_pagamento || "") < (b.data_pagamento || "") ? -1 : 1)) : [];
                  return (
                    <Fragment key={m.mes}>
                      <tr onClick={() => toggleExp("fluxo:" + m.mes)} title="Clique para ver os lançamentos deste mês" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600 }}>{m.mes}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={m.mes + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{formatDate(r.data_pagamento || "")} · {r.descricao}</td>
                          <td colSpan={2} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.fornecedor}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            )}
            {rel === "fluxo" && visaoFluxo === "diario" && (
              <table className="fazenda-table">
                <thead><tr><th></th><th>Data</th><th style={{ textAlign: "right" }}>Entradas</th><th style={{ textAlign: "right" }}>Saídas</th><th style={{ textAlign: "right" }}>Saldo diário</th><th style={{ textAlign: "right" }}>Saldo acumulado</th></tr></thead>
                <tbody>{fluxoDiario.map((m) => {
                  const aberto = exp.has("fluxodia:" + m.dia);
                  const itens = aberto ? filtrados.filter((r) => campoData(r) === m.dia) : [];
                  return (
                    <Fragment key={m.dia}>
                      <tr onClick={() => toggleExp("fluxodia:" + m.dia)} title="Clique para ver os lançamentos deste dia" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{formatDate(m.dia)}</td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{formatBRL(m.entradas)}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{formatBRL(m.saidas)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: m.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(m.saldo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--dourado-light)" }}>{formatBRL(m.acumulado)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={m.dia + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{r.descricao}</td>
                          <td colSpan={2} style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.fornecedor}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            )}
            {rel === "dre" && (<>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                Resultado por <strong>conta gerencial</strong> do seu plano de contas (por competência), com a
                hierarquia completa — uma conta de grupo soma o total das contas abaixo dela. Clique numa conta{" "}
                <span style={{ color: "var(--text-muted)" }}>▾</span> para ver os lançamentos.
              </p>
              <table className="fazenda-table">
                <thead><tr><th></th><th>Conta gerencial</th><th style={{ textAlign: "right" }}>Receitas</th><th style={{ textAlign: "right" }}>Despesas</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>{dreContas.map((c) => {
                  const aberto = exp.has("dre:" + c.conta);
                  const itens = aberto ? filtrados.filter((r) => {
                    const codigo = r.conta_completa || r.codigo_conta || "";
                    if (!c.codigo) return (r.descricao || "(sem conta)") === c.conta;
                    return codigo === c.codigo || codigo.startsWith(c.codigo + ".");
                  }).sort((a, b) => b.valor - a.valor) : [];
                  return (
                    <Fragment key={c.conta}>
                      <tr onClick={() => toggleExp("dre:" + c.conta)} title="Clique para ver os lançamentos desta conta" style={{ cursor: "pointer" }}>
                        <td style={{ width: 18, color: "var(--text-muted)" }}>{aberto ? "▾" : "▸"}</td>
                        <td style={{ fontWeight: c.nivel <= 1 ? 700 : 600, paddingLeft: `${Math.max(0, c.nivel - 1) * 1.1}rem` }}>
                          {c.nome}{c.codigo && c.codigo !== c.nome ? <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.4rem" }}>{c.codigo}</span> : null}
                        </td>
                        <td style={{ textAlign: "right", color: "var(--green-light)" }}>{c.receitas ? formatBRL(c.receitas) : "—"}</td>
                        <td style={{ textAlign: "right", color: "var(--red)" }}>{c.despesas ? formatBRL(c.despesas) : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: c.saldo >= 0 ? "var(--green-light)" : "var(--amber)" }}>{formatBRL(c.saldo)}</td>
                      </tr>
                      {aberto && itens.map((r, i) => (
                        <tr key={c.conta + ":" + i} style={{ background: "var(--surface-2)" }}>
                          <td></td>
                          <td colSpan={2} style={{ fontSize: "0.75rem" }}>{formatDate(r.data_pagamento || r.data_competencia || "")} <span style={{ color: "var(--text-muted)" }}>· {r.fornecedor || "—"}</span></td>
                          <td colSpan={2} style={{ textAlign: "right", fontSize: "0.78rem", color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{r.tipo === "receita" ? "+" : "−"}{formatBRL(r.valor)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            </>)}
            {rel === "livro" && (
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrd rotulo="Data" chave="data" sortKey={sortKeyLivro} sortDir={sortDirLivro} onSort={ordenarLivro} />
                  <ThOrd rotulo="Descrição" chave="descricao" sortKey={sortKeyLivro} sortDir={sortDirLivro} onSort={ordenarLivro} />
                  <ThOrd rotulo="Fornecedor/Cliente" chave="fornecedor" sortKey={sortKeyLivro} sortDir={sortDirLivro} onSort={ordenarLivro} />
                  <ThOrd rotulo="Entrada" chave="entrada" sortKey={sortKeyLivro} sortDir={sortDirLivro} onSort={ordenarLivro} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="Saída" chave="saida" sortKey={sortKeyLivro} sortDir={sortDirLivro} onSort={ordenarLivro} style={{ textAlign: "right" }} />
                  <th style={{ textAlign: "right" }} title="Saldo acumulado na ordem cronológica — não ordenável">Saldo</th>
                </tr></thead>
                <tbody>{pagLivro.linhasPagina.map((l, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{formatDate(l.data || "")}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.descricao}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{l.fornecedor}</td>
                    <td style={{ textAlign: "right", color: "var(--green-light)" }}>{l.entrada ? formatBRL(l.entrada) : ""}</td>
                    <td style={{ textAlign: "right", color: "var(--red)" }}>{l.saida ? formatBRL(l.saida) : ""}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: l.saldo >= 0 ? "var(--dourado-light)" : "var(--amber)" }}>{formatBRL(l.saldo)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            {rel === "livro" && (
              <Paginacao pagina={pagLivro.pagina} totalPaginas={pagLivro.totalPaginas} totalLinhas={pagLivro.totalLinhas}
                tamanhoPagina={pagLivro.tamanhoPagina} onMudarPagina={pagLivro.setPagina} onMudarTamanho={pagLivro.setTamanhoPagina} />
            )}
          </div>
        </div>

        {/* Detalhamento por conta gerencial, mês a mês — só no Fluxo de Caixa */}
        {rel === "fluxo" && mesesFluxo.length > 0 && (
          <SecaoRecolhivel
            titulo="Detalhamento por conta gerencial (mês a mês)"
            defaultAberta={false}
            descricao="Uma coluna por mês, com a hierarquia completa do plano de contas"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{detalhePorContaMensal.length} conta(s)</span>}
          >
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
              Mesma hierarquia do plano de contas — uma conta de grupo soma o total das contas abaixo dela.
            </p>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <th>Conta</th><th style={{ textAlign: "right" }}>Total</th>
                    {mesesFluxo.map((m) => <th key={m} style={{ textAlign: "right" }}>{fmtMes(m)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {detalhePorContaMensal.map((c) => (
                    <tr key={c.codigo}>
                      <td style={{ fontWeight: c.nivel <= 1 ? 700 : 500, fontSize: "0.82rem", paddingLeft: `${Math.max(0, c.nivel - 1) * 1.1}rem`, whiteSpace: "nowrap" }}>
                        {c.nome}<span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.7rem", marginLeft: "0.4rem" }}>{c.codigo}</span>
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(c.total)}</td>
                      {mesesFluxo.map((m) => (
                        <td key={m} style={{ textAlign: "right", fontSize: "0.78rem", color: (c.porMes[m] || 0) === 0 ? "var(--text-muted)" : undefined }}>
                          {c.porMes[m] ? formatBRL(c.porMes[m]) : "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {!detalhePorContaMensal.length && (
                    <tr><td colSpan={2 + mesesFluxo.length} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento com conta gerencial classificada neste período.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>
        )}
        </>}
        </>}
      </>}
      {editando && (
        <Modal title={`Editar lançamento${editando.numero_lancamento ? ` ${editando.numero_lancamento}` : ""}`} onClose={() => setEditando(null)} width="720px">
          <FormEditarLancamento lanc={editando} centros={centros} planoContas={planoContas} produtos={opcoesProdutoRel}
            fornecedores={opcoesRel.fornecedores}
            onCancelar={() => setEditando(null)}
            onSalvo={() => { setEditando(null); recarregar(); }}
            onVerRelatorioVales={() => { setEditando(null); setRel("folha"); }} />
        </Modal>
      )}
      {recibo && <ReciboModal lanc={recibo} onClose={() => setRecibo(null)} />}
    </div>
  );
}

const selStyleLote: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyleLote: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
// Cabeçalho fixo ao rolar as tabelas de notas (Contas a pagar/receber/pagas/
// recebidas/extrato, Pagamento/Recebimento e Pagamento em lote) — o
// contêiner por baixo já tem overflow-y com altura máxima; sem isso, o
// cabeçalho some assim que a lista rola.
const theadStickyStyle: React.CSSProperties = { position: "sticky", top: 0, zIndex: 1, background: "var(--thead-bg)" };

/**
 * Pagamento/recebimento em lote — filtra notas (despesa ou receita, aberta
 * ou já baixada) por nota/documento, fornecedor, produto e datas; o usuário
 * seleciona quais notas EM ABERTO quer baixar de uma vez, com um único
 * pagamento (data, conta corrente, forma de pagamento, comprovante).
 */
export function PagamentoLoteView({ contasBancarias, onFeito }: { contasBancarias: string[]; onFeito?: () => void }) {
  const admin = ehAdmin();
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [error, setError] = useState<string | null>(null);
  const [opcoes, setOpcoes] = useState<{ fornecedores: string[]; produtos: string[] }>({ fornecedores: [], produtos: [] });

  const [tipoFiltro, setTipoFiltro] = useState<"todos" | "despesa" | "receita">("todos");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [produto, setProduto] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [emissaoDe, setEmissaoDe] = useState("");
  const [emissaoAte, setEmissaoAte] = useState("");
  const [vencimentoDe, setVencimentoDe] = useState("");
  const [vencimentoAte, setVencimentoAte] = useState("");

  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [contaBancaria, setContaBancaria] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [dataVencimentoCartao, setDataVencimentoCartao] = useState("");
  const [numeroComprovante, setNumeroComprovante] = useState("");
  // "unico" = mesmo pagamento p/ todas; "linha" = data/valor/conta/forma por nota.
  const [modoLote, setModoLote] = useState<"unico" | "linha">("unico");
  type LinhaPag = { data: string; valor: string; conta: string; forma: string; vencCartao: string; comprovante: string };
  const [porLinha, setPorLinha] = useState<Record<number, LinhaPag>>({});
  const patchLinha = (id: number, patch: Partial<LinhaPag>) => setPorLinha((p) => ({ ...p, [id]: { ...p[id], ...patch } }));
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  // Comprovante em ARQUIVO da remessa — o banco emite um só para o lote
  // inteiro, e ele precisa aparecer em todas as notas daquele pagamento no
  // relatório de Contas pagas. Diferente de `numeroComprovante`, que é apenas
  // o número digitado. Sobe DEPOIS da baixa confirmada: sem baixa não há o
  // que comprovar, e assim uma falha no upload nunca desfaz o pagamento.
  const [comprovanteArquivo, setComprovanteArquivo] = useState<File | null>(null);
  const [anexarAberto, setAnexarAberto] = useState(false);
  const [arquivoPreview, setArquivoPreview] = useState<File | null>(null);

  const carregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchOpcoesFinanceiro().then((d) => setOpcoes({ fornecedores: d.fornecedores || [], produtos: d.produtos || [] })).catch(() => {});
  }, []);

  const centrosCusto = useMemo(() => Array.from(new Set((regs ?? []).map((r) => r.centro_custo).filter(Boolean))).sort(), [regs]);
  // Opções de "Produto / serviço": une os produtos vindos das opções com os
  // nomes efetivamente lançados nas notas (produtos E serviços ficam no mesmo
  // campo `produto` do item), para que um serviço também possa ser encontrado.
  const opcoesProdutoServico = useMemo(() => {
    const s = new Set<string>(opcoes.produtos);
    (regs ?? []).forEach((r) => (r.itens || []).forEach((it) => { if (it.produto) s.add(it.produto); }));
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [opcoes.produtos, regs]);

  // Só notas em aberto entram na visualização — esta tela é para dar baixa,
  // não para consultar histórico (isso já existe em Contas pagas/recebidas).
  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      !r.data_pagamento &&
      (tipoFiltro === "todos" || r.tipo === tipoFiltro) &&
      casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""} ${r.numero_boleto || ""}`, numeroDocumento) &&
      (!fornecedor || r.fornecedor === fornecedor) &&
      (!produto || (r.itens || []).some((it) => it.produto === produto)) &&
      (!centroCusto || r.centro_custo === centroCusto) &&
      (!emissaoDe || (r.data_emissao || "") >= emissaoDe) && (!emissaoAte || (r.data_emissao || "") <= emissaoAte) &&
      (!vencimentoDe || (r.data_vencimento || "") >= vencimentoDe) && (!vencimentoAte || (r.data_vencimento || "") <= vencimentoAte)
    );
  }, [regs, tipoFiltro, numeroDocumento, fornecedor, produto, centroCusto, emissaoDe, emissaoAte, vencimentoDe, vencimentoAte]);

  const toggle = (id: number) => setSelecionados((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleTodos = () => setSelecionados((p) =>
    p.size === filtrados.length && filtrados.length ? new Set() : new Set(filtrados.map((r) => r.id))
  );
  const totalSelecionado = useMemo(() => filtrados.filter((r) => selecionados.has(r.id)).reduce((a, r) => a + r.valor, 0), [filtrados, selecionados]);
  const totalFiltrado = useMemo(() => filtrados.reduce((a, r) => a + r.valor, 0), [filtrados]);
  const notasSelecionadas = useMemo(() => filtrados.filter((r) => selecionados.has(r.id)), [filtrados, selecionados]);

  // Garante uma linha de pagamento para cada nota selecionada (default: data e
  // conta/forma do pagamento único; valor = valor cheio da nota).
  useEffect(() => {
    setPorLinha((p) => {
      const n = { ...p };
      for (const r of notasSelecionadas) {
        if (!n[r.id]) n[r.id] = { data: dataPagamento, valor: String(r.valor), conta: contaBancaria, forma: formaPagamento, vencCartao: "", comprovante: "" };
      }
      return n;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notasSelecionadas]);
  const totalPagoLinha = useMemo(() => notasSelecionadas.reduce((a, r) => a + (Number(porLinha[r.id]?.valor) || 0), 0), [notasSelecionadas, porLinha]);

  // Ordenação clicável sobre o resultado JÁ filtrado.
  const { ordenados, sortKey, sortDir, ordenar } = useOrdenacao(filtrados, {
    numero: (r) => (r.numero_documento || r.numero_lancamento || "").toLowerCase(),
    emissao: (r) => r.data_emissao || "",
    vencimento: (r) => r.data_vencimento || "",
    produto: (r) => (r.itens || []).map((it) => it.produto).join(", ").toLowerCase(),
    valor: (r) => r.valor,
  });

  async function darBaixaEmLote() {
    setMsg(null);
    if (!selecionados.size) { setMsg({ tipo: "erro", texto: "Selecione ao menos uma nota em aberto." }); return; }
    setSalvando(true);
    try {
      let r;
      if (modoLote === "linha") {
        for (const n of notasSelecionadas) {
          const l = porLinha[n.id];
          if (l?.forma === "credito" && !l.vencCartao) { setMsg({ tipo: "erro", texto: `Informe o vencimento do cartão da nota ${n.numero_documento || n.numero_lancamento || n.id}.` }); setSalvando(false); return; }
        }
        r = await criarBaixaLoteDetalhada(notasSelecionadas.map((n) => {
          const l = porLinha[n.id];
          return {
            lancamento_id: n.id, data_pagamento: l?.data || dataPagamento, valor_pago: Number(l?.valor) || 0,
            conta_bancaria: l?.conta || undefined, forma_pagamento: l?.forma || undefined,
            data_vencimento_cartao: l?.forma === "credito" ? l.vencCartao : undefined,
            numero_documento_pagamento: l?.comprovante || undefined,
          };
        }));
      } else {
        if (formaPagamento === "credito" && !dataVencimentoCartao) { setMsg({ tipo: "erro", texto: "Informe a data de vencimento do cartão." }); setSalvando(false); return; }
        r = await criarBaixaLote({
          lancamento_ids: Array.from(selecionados), data_pagamento: dataPagamento,
          conta_bancaria: contaBancaria || undefined, forma_pagamento: formaPagamento || undefined,
          data_vencimento_cartao: formaPagamento === "credito" ? dataVencimentoCartao : undefined,
          numero_documento_pagamento: numeroComprovante || undefined,
        });
      }
      // Comprovante do lote: sobe DEPOIS da baixa, sobre os ids que acabaram
      // de ser baixados. Se o upload falhar, a baixa continua valendo — o
      // aviso diferencia os dois casos para o usuário saber o que refazer.
      let aviso = `${r.baixados} lançamento(s) baixado(s) com sucesso.`;
      if (comprovanteArquivo) {
        try {
          const a = await anexarComprovanteEmLote(Array.from(selecionados), comprovanteArquivo);
          aviso += ` Comprovante "${a.nome_arquivo}" anexado a ${a.anexados} lançamento(s).`;
        } catch (e: any) {
          setMsg({ tipo: "erro", texto: `Baixa concluída, mas o comprovante não foi anexado: ${e.message}. Anexe pela tela de pagamento.` });
          setSelecionados(new Set()); setNumeroComprovante(""); setPorLinha({}); setComprovanteArquivo(null);
          carregar(); onFeito?.();
          return;
        }
      }
      setMsg({ tipo: "sucesso", texto: aviso });
      setSelecionados(new Set()); setNumeroComprovante(""); setPorLinha({}); setComprovanteArquivo(null);
      carregar();
      onFeito?.();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao dar baixa em lote" });
    } finally {
      setSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;
  if (!regs) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <AvisoSalvo texto={msg?.tipo === "sucesso" ? msg.texto : null} />
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Filtros</span>
          <button className="btn-ghost" title="Abre um lançamento NOVO a partir de um documento (nota fiscal, boleto ou recibo) — leitura automática, não anexa a nenhuma nota já existente" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Lançar por nota fiscal, boleto ou recibo…
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Tipo</label>
            <select style={selStyleLote} title="Filtrar por tipo de nota: a pagar, a receber ou ambas" value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value as any)}>
              <option value="todos">Despesas e receitas</option><option value="despesa">Só despesas (a pagar)</option><option value="receita">Só receitas (a receber)</option>
            </select></div>
          <div><label style={labelStyleLote}>Nota fiscal / nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" />
            </div></div>
          <div><label style={labelStyleLote}>Fornecedor / cliente</label>
            <select style={selStyleLote} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Todos</option>{opcoes.fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Produto / serviço</label>
            <select style={selStyleLote} value={produto} onChange={(e) => setProduto(e.target.value)}>
              <option value="">Todos</option>{opcoesProdutoServico.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Emissão — de</label><input type="date" style={selStyleLote} value={emissaoDe} onChange={(e) => setEmissaoDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Emissão — até</label><input type="date" style={selStyleLote} value={emissaoAte} onChange={(e) => setEmissaoAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — de</label><input type="date" style={selStyleLote} value={vencimentoDe} onChange={(e) => setVencimentoDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — até</label><input type="date" style={selStyleLote} value={vencimentoAte} onChange={(e) => setVencimentoAte(e.target.value)} /></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>
              {centrosCusto.map((c) => (<option key={c} value={c}>{c}</option>))}
            </select></div>
        </div>
      </div>

      {anexarAberto && (
        <ModalDivididoDocumento title="Novo lançamento — leitura automática" onClose={() => { setAnexarAberto(false); setArquivoPreview(null); }} arquivo={arquivoPreview}>
          <FormFinanceiro tipo={tipoFiltro === "receita" ? "receita" : "despesa"} responsaveis={nomesResponsaveis}
            onArquivoParaLeitura={setArquivoPreview}
            onSalvo={(mensagem) => { setAnexarAberto(false); setArquivoPreview(null); setMsg({ tipo: "sucesso", texto: mensagem }); carregar(); }} />
        </ModalDivididoDocumento>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden", marginBottom: "1rem" }}>
        <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.4rem" }}>
          <span style={{ fontSize: "0.85rem" }}>
            {filtrados.length} nota(s) em aberto no filtro — total {formatBRL(totalFiltrado)}
            {selecionados.size > 0 && <> · {selecionados.size} selecionada(s) — {formatBRL(totalSelecionado)}</>}
          </span>
          <button className="btn-ghost" title="Selecionar ou limpar todas as notas do filtro" style={{ fontSize: "0.72rem" }} onClick={toggleTodos} disabled={!filtrados.length}>
            {selecionados.size === filtrados.length && filtrados.length ? "Limpar seleção" : `Selecionar todas (${filtrados.length})`}
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead style={theadStickyStyle}><tr>
              <th style={theadStickyStyle}></th>
              <ThOrd rotulo="Nota / lançamento" chave="numero" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Emissão" chave="emissao" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Vencimento" chave="vencimento" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <th style={theadStickyStyle}>Situação</th>
              <ThOrd rotulo="Produto/Serviços" chave="produto" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Valor" chave="valor" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={{ ...theadStickyStyle, textAlign: "right" }} />
              {admin && <th style={{ ...theadStickyStyle, textAlign: "left" }}>Usuário</th>}
            </tr></thead>
            <tbody>
              {ordenados.map((r) => {
                const produtos = (r.itens || []).map((it) => it.produto).filter(Boolean).join(", ");
                return (
                  <tr key={r.id} className="row-clickable" title="Clique para selecionar esta nota" onClick={() => toggle(r.id)}>
                    <td><input type="checkbox" checked={selecionados.has(r.id)} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} /></td>
                    <td style={{ fontSize: "0.78rem" }}>
                      <strong>{r.numero_documento || r.numero_lancamento || "—"}</strong>
                      {r.numero_documento && r.numero_lancamento && <span style={{ color: "var(--text-muted)" }}> · {r.numero_lancamento}</span>}
                      <br /><span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{r.fornecedor || "—"} · {r.descricao}</span>
                    </td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_emissao ? formatDate(r.data_emissao) : "—"}</td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</td>
                    <td>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--amber)" }}>
                        {r.tipo === "receita" ? "A receber" : "A pagar"}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{produtos || "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    {admin && <td>{r.usuario_nome ?? "—"}</td>}
                  </tr>
                );
              })}
              {!filtrados.length && <tr><td colSpan={admin ? 8 : 7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma nota em aberto no filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {selecionados.size > 0 ? (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span>Baixa de {selecionados.size} lançamento(s) — {formatBRL(totalSelecionado)}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setModoLote("unico")} style={{ fontSize: "0.74rem", padding: "0.3rem 0.7rem", borderRadius: 999, cursor: "pointer", border: "1px solid " + (modoLote === "unico" ? "var(--dourado)" : "var(--border)"), background: modoLote === "unico" ? "rgba(94,26,46,0.4)" : "transparent", color: modoLote === "unico" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoLote === "unico" ? 700 : 500 }}>Pagamento único</button>
              <button onClick={() => setModoLote("linha")} style={{ fontSize: "0.74rem", padding: "0.3rem 0.7rem", borderRadius: 999, cursor: "pointer", border: "1px solid " + (modoLote === "linha" ? "var(--dourado)" : "var(--border)"), background: modoLote === "linha" ? "rgba(94,26,46,0.4)" : "transparent", color: modoLote === "linha" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoLote === "linha" ? 700 : 500 }}>Ajustar por linha</button>
            </div>
          </div>

          {modoLote === "unico" ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div><label style={labelStyleLote}>Data do pagamento</label>
                  <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
                <div><label style={labelStyleLote}>Conta corrente</label>
                  <select style={selStyleLote} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                    <option value="">Selecione…</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
                  </select></div>
                <div><label style={labelStyleLote}>Forma</label>
                  <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                    <option value="">Selecione…</option>{Object.entries(LABEL_FORMA_PAGAMENTO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select></div>
                {formaPagamento === "credito" ? (
                  <div><label style={labelStyleLote}>Vencimento do cartão</label>
                    <input type="date" style={selStyleLote} value={dataVencimentoCartao} onChange={(e) => setDataVencimentoCartao(e.target.value)} /></div>
                ) : (
                  <div><label style={labelStyleLote}>Nº do comprovante de pagamento</label>
                    <input style={selStyleLote} value={numeroComprovante} onChange={(e) => setNumeroComprovante(e.target.value)} /></div>
                )}
              </div>
              {formaPagamento === "credito" && (
                <div className="mb-3" style={{ maxWidth: "280px" }}>
                  <label style={labelStyleLote}>Nº do comprovante de pagamento</label>
                  <input style={selStyleLote} value={numeroComprovante} onChange={(e) => setNumeroComprovante(e.target.value)} />
                </div>
              )}
            </>
          ) : (
            <div className="mb-3">
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                Cada nota com sua própria data, valor, conta e forma. Valor diferente do total vira desconto/acréscimo.
                Total a pagar: <strong style={{ color: "var(--text)" }}>{formatBRL(totalPagoLinha)}</strong> (de {formatBRL(totalSelecionado)}).
              </p>
              <div className="overflow-x-auto" style={{ maxHeight: "340px" }}>
                <table className="fazenda-table" style={{ margin: 0, fontSize: "0.78rem" }}>
                  <thead><tr>
                    <th>Nota / fornecedor</th><th style={{ textAlign: "right" }}>Valor</th>
                    <th>Data pgto</th><th>Valor pago</th><th>Conta</th><th>Forma</th><th>Compr.</th>
                  </tr></thead>
                  <tbody>
                    {notasSelecionadas.map((n) => {
                      const l = porLinha[n.id] || { data: dataPagamento, valor: String(n.valor), conta: "", forma: "", vencCartao: "", comprovante: "" };
                      return (
                        <tr key={n.id}>
                          <td style={{ maxWidth: 180 }}>
                            <strong>{n.numero_documento || n.numero_lancamento || "—"}</strong>
                            <br /><span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>{n.fornecedor || "—"}</span>
                          </td>
                          <td style={{ textAlign: "right", color: n.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(n.valor)}</td>
                          <td><input type="date" style={{ ...selStyleLote, minWidth: 130 }} value={l.data} onChange={(e) => patchLinha(n.id, { data: e.target.value })} /></td>
                          <td><CampoMoeda style={{ ...selStyleLote, width: 100 }} value={Number(l.valor) || 0} onChange={(v) => patchLinha(n.id, { valor: v ? String(v) : "" })} /></td>
                          <td>
                            <select style={{ ...selStyleLote, minWidth: 110 }} value={l.conta} onChange={(e) => patchLinha(n.id, { conta: e.target.value })}>
                              <option value="">—</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
                            </select>
                          </td>
                          <td>
                            <select style={{ ...selStyleLote, minWidth: 110 }} value={l.forma} onChange={(e) => patchLinha(n.id, { forma: e.target.value })}>
                              <option value="">—</option>{Object.entries(LABEL_FORMA_PAGAMENTO).map(([v, lb]) => <option key={v} value={v}>{lb}</option>)}
                            </select>
                            {l.forma === "credito" && <input type="date" title="Vencimento do cartão" style={{ ...selStyleLote, minWidth: 110, marginTop: 3 }} value={l.vencCartao} onChange={(e) => patchLinha(n.id, { vencCartao: e.target.value })} />}
                          </td>
                          <td><input style={{ ...selStyleLote, width: 90 }} value={l.comprovante} onChange={(e) => patchLinha(n.id, { comprovante: e.target.value })} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {/* Comprovante único da remessa — vale para os dois modos (pagamento
              igual para todas ou linha a linha): o que define o lote é a
              seleção, não o modo. Fica fora do card de "pagamento único" por
              isso. */}
          {selecionados.size > 0 && (
            <div className="card mb-4">
              <div className="card-header mb-2">Comprovante do lote <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.75rem" }}>(opcional)</span></div>
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.6rem" }}>
                Um arquivo só — o mesmo comprovante fica vinculado às {selecionados.size} nota(s) selecionada(s) e aparece
                no relatório de Contas pagas de cada uma.
              </p>
              {comprovanteArquivo ? (
                <div className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}>
                  <FileText size={14} style={{ color: "var(--dourado-light)" }} />
                  <span>{comprovanteArquivo.name}</span>
                  <button type="button" onClick={() => setComprovanteArquivo(null)} className="btn-ghost" title="Remover comprovante" aria-label="Remover comprovante"><X size={14} /></button>
                </div>
              ) : (
                <Dropzone compact label="Arraste o comprovante do pagamento" hint="PDF ou imagem, até 15 MB"
                  onFiles={(fs) => setComprovanteArquivo(fs[0] || null)} />
              )}
            </div>
          )}
          {/* Sucesso vai pro aviso persistente no topo (AvisoSalvo) — este
              limpa a seleção no mesmo clique, então um sucesso mostrado aqui
              dentro nunca chegaria a ser visto. Erro continua aqui, perto do
              botão, contextual (não limpa nada, então fica visível). */}
          {msg?.tipo === "erro" && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
          <button className="btn-primary" title={modoLote === "linha" ? "Baixar cada nota com o seu próprio pagamento" : "Baixar todas as notas selecionadas com este pagamento único"} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={darBaixaEmLote} disabled={salvando}>
            <Check size={14} /> {salvando ? "Salvando…" : `Dar baixa em ${selecionados.size} lançamento(s)`}
          </button>
        </div>
      ) : (
        <div className="card" style={{ textAlign: "center", padding: "2.4rem 1rem" }}>
          <Check size={22} style={{ color: "var(--text-muted)", margin: "0 auto 0.6rem" }} />
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione uma ou mais notas à esquerda para ver os dados da baixa.</p>
        </div>
      )}
      </div>
      </div>
    </div>
  );
}

type ItemPatrimonio = {
  id: number; tipo: string | null; nome: string; numero: string | null;
  atividade_cultura: string | null; data_imobilizacao: string | null;
  metodo_depreciacao: string | null; vida_util: string | null; valor_residual: number | null;
  quantidade: number | null; unidade: string | null; valor_total: number | null; data_baixa: string | null;
  depreciacao_acumulada: number | null; valor_atual: number | null; vida_util_anos: number | null; inconsistencia: string | null;
  frequencia_manutencao_meses: number | null; data_ultima_manutencao: string | null;
  data_proxima_manutencao: string | null; observacao_manutencao: string | null;
  situacao_manutencao: "vencida" | "proxima" | "ok" | null; dias_para_manutencao: number | null;
  // Não depreciável (ex.: terra) — acompanha valor de mercado em vez de depreciar.
  depreciavel: boolean; valor_mercado_atual: number | null;
  data_ultima_atualizacao_valor_mercado: string | null; atualizacao_valor_mercado_frequencia_meses: number | null;
  proxima_atualizacao_valor_mercado: string | null;
};
type InconsistenciaPatrimonio = { item: string; numero: string | null; motivo: string };

/** Selo da situação da manutenção — vermelho vencida, âmbar perto de vencer
 * (até 15 dias, mesma janela do backend), neutro em dia, "—" sem plano. */
function SeloManutencao({ item }: { item: ItemPatrimonio }) {
  if (!item.data_proxima_manutencao) return <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Sem plano</span>;
  const cor = item.situacao_manutencao === "vencida" ? "var(--red)" : item.situacao_manutencao === "proxima" ? "var(--amber)" : "var(--text-muted)";
  const rotulo = item.situacao_manutencao === "vencida"
    ? `Vencida há ${Math.abs(item.dias_para_manutencao ?? 0)} dia(s)`
    : item.situacao_manutencao === "proxima"
    ? `Em ${item.dias_para_manutencao} dia(s)`
    : formatDate(item.data_proxima_manutencao);
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.78rem", color: cor, fontWeight: item.situacao_manutencao === "vencida" ? 700 : 500 }}>
      {item.situacao_manutencao === "vencida" && <AlertTriangle size={12} />}
      {rotulo}
    </span>
  );
}

function PatrimonioView() {
  if (!ehAdmin()) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <Building2 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
        <p style={{ color: "var(--text-muted)" }}>Controle Financeiro &gt; Patrimônio é restrito a administradores da fazenda.</p>
      </div>
    );
  }
  return <PatrimonioViewAdmin />;
}

function PatrimonioViewAdmin() {
  const [dados, setDados] = useState<{ itens: ItemPatrimonio[]; total: number; valor_total: number; valor_atual_total: number; inconsistencias: InconsistenciaPatrimonio[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [itemManutencao, setItemManutencao] = useState<ItemPatrimonio | null>(null);
  const [itemEditando, setItemEditando] = useState<ItemPatrimonio | "novo" | null>(null);
  const [itemValorMercado, setItemValorMercado] = useState<ItemPatrimonio | null>(null);

  const carregar = () => { fetchPatrimonio().then(setDados).catch((e) => setErro(e.message)); };
  useEffect(carregar, []);

  // Hook chamado incondicionalmente (antes dos "return" abaixo) — usa a
  // vida útil em anos (numérica) já calculada pelo backend como valor bruto
  // de ordenação, em vez do texto livre exibido na coluna "Vida útil".
  const { ordenados: bensOrdenados, sortKey: sortKeyBens, sortDir: sortDirBens, ordenar: ordenarBens } = useOrdenacao(dados?.itens ?? [], {
    tipo: (i) => (i.tipo || "").toLowerCase(),
    nome: (i) => (i.nome || "").toLowerCase(),
    numero: (i) => (i.numero || "").toLowerCase(),
    vidaUtil: (i) => i.vida_util_anos ?? -1,
    valorResidual: (i) => i.valor_residual ?? -1,
    quantidade: (i) => i.quantidade ?? -1,
    valorTotal: (i) => i.valor_total ?? -1,
    depreciacaoAcumulada: (i) => i.depreciacao_acumulada ?? -1,
    valorAtual: (i) => i.valor_atual ?? -1,
    proximaManutencao: (i) => i.data_proxima_manutencao || "",
  });

  if (erro) return <div className="alert-critico"><span>Sem dados: {erro}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe o patrimônio</a>.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  if (!dados.itens.length) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
        <Building2 size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
        <p style={{ color: "var(--text-muted)" }}>Nenhum item de patrimônio no banco.</p>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Suba o <strong>LISTA_DE_PATRIMONIO.csv</strong> na tela de <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importar dados</a>.
        </p>
      </div>
    );
  }

  const vencidas = dados.itens.filter((i) => i.situacao_manutencao === "vencida").length;
  const proximas = dados.itens.filter((i) => i.situacao_manutencao === "proxima").length;

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String(dados.total)} l="Itens" />
        <KPI v={formatBRL(dados.valor_total)} l="Valor total (histórico)" c="var(--text-muted)" />
        <KPI v={formatBRL(dados.valor_atual_total)} l="Valor atual (após depreciação)" c="var(--dourado-light)" />
        <KPI v={String(dados.itens.filter((i) => i.data_baixa).length)} l="Com baixa" c="var(--text-muted)" />
      </div>
      {(vencidas > 0 || proximas > 0) && (
        <div className="card mb-4" style={{ borderColor: vencidas > 0 ? "var(--red)" : "var(--amber)" }}>
          <div className="card-header mb-1 flex items-center gap-2" style={{ color: vencidas > 0 ? "var(--red)" : "var(--amber)" }}>
            <Wrench size={14} /> Manutenção preventiva
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            {vencidas > 0 && <>{vencidas} item(ns) com manutenção <strong style={{ color: "var(--red)" }}>vencida</strong>. </>}
            {proximas > 0 && <>{proximas} item(ns) com manutenção <strong style={{ color: "var(--amber)" }}>próxima</strong> (até 15 dias).</>}
          </p>
        </div>
      )}
      {dados.inconsistencias.length > 0 && (
        <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
          <div className="card-header mb-2" style={{ color: "var(--amber)" }}>Inconsistências na depreciação ({dados.inconsistencias.length})</div>
          <ul style={{ fontSize: "0.8rem", color: "var(--text-muted)", paddingLeft: "1.2rem" }}>
            {dados.inconsistencias.map((inc, i) => (
              <li key={i}>{inc.item}{inc.numero ? ` (Nº ${inc.numero})` : ""}: {inc.motivo}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="card">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Bens</span>
          <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={() => setItemEditando("novo")}>
            <Plus size={13} /> Novo patrimônio
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} />
                <ThOrd rotulo="Nome" chave="nome" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} />
                <ThOrd rotulo="Nº" chave="numero" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} />
                <th>Imobilização</th>
                <th>Método</th>
                <ThOrd rotulo="Vida útil" chave="vidaUtil" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} />
                <ThOrd rotulo="Vlr. residual" chave="valorResidual" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Qtd." chave="quantidade" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Vlr. total" chave="valorTotal" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Depreciação acum." chave="depreciacaoAcumulada" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Valor atual" chave="valorAtual" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} style={{ textAlign: "right" }} />
                <th>Baixa</th>
                <ThOrd rotulo="Próxima manutenção" chave="proximaManutencao" sortKey={sortKeyBens} sortDir={sortDirBens} onSort={ordenarBens} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {bensOrdenados.map((i) => (
                <tr key={i.id} style={i.data_baixa ? { opacity: 0.55 } : undefined}>
                  <td style={{ fontSize: "0.78rem" }}>{i.tipo || "—"}</td>
                  <td style={{ fontWeight: 600, fontSize: "0.83rem" }}>
                    {i.nome}
                    {!i.depreciavel && <span title="Não depreciável — acompanha valor de mercado" style={{ marginLeft: "0.35rem", fontSize: "0.68rem", color: "var(--dourado-light)", border: "1px solid var(--dourado)", borderRadius: "999px", padding: "0.05rem 0.4rem" }}>valor de mercado</span>}
                  </td>
                  <td style={{ fontSize: "0.78rem" }}>{i.numero || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.data_imobilizacao ? formatDate(i.data_imobilizacao) : "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.depreciavel ? (i.metodo_depreciacao || "—") : "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{i.depreciavel ? (i.vida_util || "—") : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.depreciavel && i.valor_residual != null ? formatBRL(i.valor_residual) : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, fontSize: "0.83rem" }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>
                    {!i.depreciavel ? "—" : i.depreciacao_acumulada != null ? formatBRL(i.depreciacao_acumulada) : <span title={i.inconsistencia || undefined} style={{ color: "var(--amber)" }}>—</span>}
                  </td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600, color: "var(--dourado-light)" }}>{i.valor_atual != null ? formatBRL(i.valor_atual) : "—"}</td>
                  <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{i.data_baixa ? formatDate(i.data_baixa) : "—"}</td>
                  <td>
                    {i.data_baixa ? <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>—</span>
                      : i.depreciavel ? <SeloManutencao item={i} />
                      : i.proxima_atualizacao_valor_mercado ? (
                        <span style={{ fontSize: "0.75rem", color: new Date(i.proxima_atualizacao_valor_mercado) < new Date() ? "var(--red)" : "var(--text-muted)" }}>
                          Atualizar valor até {formatDate(i.proxima_atualizacao_valor_mercado)}
                        </span>
                      ) : <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Sem agenda</span>}
                  </td>
                  <td>
                    <div className="flex items-center gap-1">
                      <button className="btn-ghost" title="Editar" style={{ padding: "0.25rem" }} onClick={() => setItemEditando(i)}>
                        <Pencil size={14} />
                      </button>
                      {!i.data_baixa && i.depreciavel && (
                        <button className="btn-ghost" title="Plano de manutenção" style={{ padding: "0.25rem" }} onClick={() => setItemManutencao(i)}>
                          <Wrench size={14} />
                        </button>
                      )}
                      {!i.data_baixa && !i.depreciavel && (
                        <button className="btn-ghost" title="Atualizar valor de mercado" style={{ padding: "0.25rem" }} onClick={() => setItemValorMercado(i)}>
                          <TrendingUp size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {itemManutencao && (
        <ModalManutencaoPatrimonio item={itemManutencao} onClose={() => setItemManutencao(null)} onSalvo={() => { carregar(); }} />
      )}
      {itemEditando && (
        <ModalNovoPatrimonio item={itemEditando === "novo" ? null : itemEditando} onClose={() => setItemEditando(null)} onSalvo={() => { setItemEditando(null); carregar(); }} />
      )}
      {itemValorMercado && (
        <ModalValorMercadoPatrimonio item={itemValorMercado} onClose={() => setItemValorMercado(null)} onSalvo={() => { setItemValorMercado(null); carregar(); }} />
      )}
    </>
  );
}

/** Cadastro manual de um item de patrimônio (substitui o upload de CSV) —
 * cria diretamente, ou, se marcado "é uma compra agora?", redireciona para
 * Lançar > Financeiro > Contas a pagar com o item pré-preenchido; a criação
 * de fato acontece quando ESSE lançamento for salvo (ver FormFinanceiro e
 * POST /financeiro/lancamentos, campo criar_patrimonio). */
function ModalNovoPatrimonio({ item, onClose, onSalvo }: { item: ItemPatrimonio | null; onClose: () => void; onSalvo: () => void }) {
  const [ehCompraAgora, setEhCompraAgora] = useState(false);
  const [nome, setNome] = useState(item?.nome || "");
  const [tipo, setTipo] = useState(item?.tipo || "");
  const [numero, setNumero] = useState(item?.numero || "");
  const [dataImobilizacao, setDataImobilizacao] = useState(item?.data_imobilizacao || "");
  const [quantidade, setQuantidade] = useState(item?.quantidade != null ? String(item.quantidade) : "");
  const [unidade, setUnidade] = useState(item?.unidade || "");
  const [valorTotal, setValorTotal] = useState(item?.valor_total != null ? String(item.valor_total) : "");
  const [depreciavel, setDepreciavel] = useState(item?.depreciavel ?? true);
  const [metodoDepreciacao, setMetodoDepreciacao] = useState(item?.metodo_depreciacao || "");
  const [vidaUtil, setVidaUtil] = useState(item?.vida_util || "");
  const [valorResidual, setValorResidual] = useState(item?.valor_residual != null ? String(item.valor_residual) : "");
  const [frequenciaValorMercado, setFrequenciaValorMercado] = useState(
    item?.atualizacao_valor_mercado_frequencia_meses != null ? String(item.atualizacao_valor_mercado_frequencia_meses) : ""
  );
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    const payload: PatrimonioPayload = {
      nome: nome.trim(), tipo: tipo || null, numero: numero || null,
      data_imobilizacao: dataImobilizacao || null,
      quantidade: quantidade ? Number(quantidade) : null, unidade: unidade || null,
      valor_total: valorTotal ? Number(valorTotal) : null,
      depreciavel,
      metodo_depreciacao: depreciavel ? (metodoDepreciacao || null) : null,
      vida_util: depreciavel ? (vidaUtil || null) : null,
      valor_residual: depreciavel && valorResidual ? Number(valorResidual) : null,
      atualizacao_valor_mercado_frequencia_meses: !depreciavel && frequenciaValorMercado ? Number(frequenciaValorMercado) : null,
    };
    if (ehCompraAgora && !item) {
      const params = new URLSearchParams({
        ir: "financeiro_despesa", patrimonio_nome: payload.nome,
        patrimonio_tipo: payload.tipo || "", patrimonio_valor: payload.valor_total != null ? String(payload.valor_total) : "",
        patrimonio_depreciavel: depreciavel ? "1" : "0",
      });
      window.location.href = `/lancamentos?${params.toString()}`;
      return;
    }
    setSalvando(true); setErro("");
    try {
      if (item) await atualizarPatrimonio(item.id, payload);
      else await criarPatrimonio(payload);
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  const inputStyle: React.CSSProperties = {
    background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
  };
  const label: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

  return (
    <Modal title={item ? `Editar patrimônio — ${item.nome}` : "Novo patrimônio"} onClose={onClose} width="640px">
      <div className="space-y-3">
        {!item && (
          <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", background: "var(--surface-2)", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)" }}>
            <input type="checkbox" checked={ehCompraAgora} onChange={(e) => setEhCompraAgora(e.target.checked)} />
            É uma compra agora? (leva para Lançar &gt; Financeiro já com estes dados — o patrimônio é criado junto com o lançamento)
          </label>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div style={{ gridColumn: "1 / -1" }}><label style={label}>Nome</label>
            <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Trator Massey Ferguson" /></div>
          <div><label style={label}>Tipo</label>
            <input style={inputStyle} value={tipo} onChange={(e) => setTipo(e.target.value)} placeholder="ex.: Máquinas, Terra, Benfeitoria" /></div>
          <div><label style={label}>Nº patrimônio</label>
            <input style={inputStyle} value={numero} onChange={(e) => setNumero(e.target.value)} /></div>
          <div><label style={label}>Data de imobilização</label>
            <input type="date" style={inputStyle} value={dataImobilizacao} onChange={(e) => setDataImobilizacao(e.target.value)} /></div>
          <div><label style={label}>Valor {depreciavel ? "de aquisição" : "inicial (de mercado)"} (R$)</label>
            <CampoMoeda style={inputStyle} value={Number(valorTotal) || 0} onChange={(v) => setValorTotal(v ? String(v) : "")} /></div>
          <div><label style={label}>Quantidade</label>
            <input type="number" style={inputStyle} value={quantidade} onChange={(e) => setQuantidade(e.target.value)} /></div>
          <div><label style={label}>Unidade</label>
            <input style={inputStyle} value={unidade} onChange={(e) => setUnidade(e.target.value)} /></div>
        </div>

        <div className="flex items-center gap-2 mt-2" style={{ flexWrap: "wrap" }}>
          <button type="button" className={depreciavel ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }} onClick={() => setDepreciavel(true)}>Deprecia normalmente</button>
          <button type="button" className={!depreciavel ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }} onClick={() => setDepreciavel(false)}>
            Não depreciável (ex.: terra) — só valoriza
          </button>
        </div>

        {depreciavel ? (
          <div className="grid grid-cols-2 gap-3">
            <div><label style={label}>Método de depreciação</label>
              <input style={inputStyle} value={metodoDepreciacao} onChange={(e) => setMetodoDepreciacao(e.target.value)} placeholder="ex.: Linear" /></div>
            <div><label style={label}>Vida útil</label>
              <input style={inputStyle} value={vidaUtil} onChange={(e) => setVidaUtil(e.target.value)} placeholder="ex.: 10 Anos" /></div>
            <div><label style={label}>Valor residual (R$)</label>
              <CampoMoeda style={inputStyle} value={Number(valorResidual) || 0} onChange={(v) => setValorResidual(v ? String(v) : "")} /></div>
          </div>
        ) : (
          <div>
            <label style={label}>Frequência de atualização do valor de mercado (meses)</label>
            <input type="number" min={0} style={{ ...inputStyle, maxWidth: "220px" }} value={frequenciaValorMercado}
              onChange={(e) => setFrequenciaValorMercado(e.target.value)} placeholder="vazio = usa o padrão do sistema; 0 = nunca" />
          </div>
        )}

        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
          <button className="btn-primary" onClick={salvar} disabled={salvando}>
            {salvando ? "Salvando…" : ehCompraAgora && !item ? "Ir para o lançamento" : "Salvar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** Registra uma nova avaliação de valor de mercado — só para patrimônio não
 * depreciável (ver ItemPatrimonio.depreciavel). */
function ModalValorMercadoPatrimonio({ item, onClose, onSalvo }: { item: ItemPatrimonio; onClose: () => void; onSalvo: () => void }) {
  const [valor, setValor] = useState(item.valor_mercado_atual != null ? String(item.valor_mercado_atual) : "");
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const salvar = async () => {
    if (!valor) { setErro("Informe o valor de mercado."); return; }
    setSalvando(true); setErro("");
    try {
      await atualizarValorMercadoPatrimonio(item.id, Number(valor), data);
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  const inputStyle: React.CSSProperties = {
    background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
  };
  const label: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

  return (
    <Modal title={`Atualizar valor de mercado — ${item.nome}`} onClose={onClose} width="420px">
      <div className="space-y-3">
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          Última avaliação: {item.valor_mercado_atual != null ? formatBRL(item.valor_mercado_atual) : "—"}
          {item.data_ultima_atualizacao_valor_mercado ? ` (${formatDate(item.data_ultima_atualizacao_valor_mercado)})` : ""}
        </p>
        <div><label style={label}>Novo valor de mercado (R$)</label>
          <CampoMoeda style={inputStyle} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
        <div><label style={label}>Data da avaliação</label>
          <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></div>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * Plano de manutenção preventiva de um item de patrimônio: frequência (em
 * meses) + última/próxima data, registro de manutenção paga/realizada (com
 * link opcional para Contas a Pagar) e histórico das manutenções já feitas.
 */
function ModalManutencaoPatrimonio({ item, onClose, onSalvo }: { item: ItemPatrimonio; onClose: () => void; onSalvo: () => void }) {
  const [frequencia, setFrequencia] = useState(item.frequencia_manutencao_meses != null ? String(item.frequencia_manutencao_meses) : "");
  const [dataUltima, setDataUltima] = useState(item.data_ultima_manutencao || "");
  const [dataProxima, setDataProxima] = useState(item.data_proxima_manutencao || "");
  const [observacaoPlano, setObservacaoPlano] = useState(item.observacao_manutencao || "");
  const [salvandoPlano, setSalvandoPlano] = useState(false);
  const [erroPlano, setErroPlano] = useState("");

  const [historico, setHistorico] = useState<any[] | null>(null);
  useEffect(() => { fetchManutencoesPatrimonio(item.id).then(setHistorico).catch(() => setHistorico([])); }, [item.id]);
  const { ordenados: historicoOrdenado, sortKey: sortKeyHist, sortDir: sortDirHist, ordenar: ordenarHist } = useOrdenacao(historico ?? [], {
    data: (h) => h.data_realizacao || "",
    descricao: (h) => (h.descricao || "").toLowerCase(),
    fornecedor: (h) => (h.fornecedor || "").toLowerCase(),
    valor: (h) => h.valor ?? -1,
    status: (h) => h.status || "",
  });

  const [mostrarRegistro, setMostrarRegistro] = useState(false);
  const [dataRealizacao, setDataRealizacao] = useState(new Date().toISOString().slice(0, 10));
  const [descricaoServico, setDescricaoServico] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [valor, setValor] = useState("");
  const [statusManut, setStatusManut] = useState<"pago" | "pendente">("pago");
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [gerarConta, setGerarConta] = useState(true);
  const [salvandoRegistro, setSalvandoRegistro] = useState(false);
  const [erroRegistro, setErroRegistro] = useState("");

  const salvarPlano = async () => {
    setSalvandoPlano(true); setErroPlano("");
    try {
      await atualizarPlanoManutencaoPatrimonio(item.id, {
        frequencia_manutencao_meses: frequencia ? parseInt(frequencia, 10) : null,
        data_ultima_manutencao: dataUltima || null,
        data_proxima_manutencao: dataProxima || null,
        observacao_manutencao: observacaoPlano || null,
      });
      onSalvo();
    } catch (e: any) { setErroPlano(e.message); } finally { setSalvandoPlano(false); }
  };

  const registrarManutencao = async () => {
    if (gerarConta && !valor) { setErroRegistro("Informe o valor para gerar a conta a pagar (ou desmarque a opção)."); return; }
    setSalvandoRegistro(true); setErroRegistro("");
    try {
      await registrarManutencaoPatrimonio(item.id, {
        data_realizacao: dataRealizacao, descricao: descricaoServico || null, fornecedor: fornecedor || null,
        valor: valor ? parseFloat(valor.replace(",", ".")) : null, status: statusManut,
        data_pagamento: statusManut === "pago" ? dataPagamento : null, gerar_conta_a_pagar: gerarConta,
      });
      setMostrarRegistro(false);
      setDescricaoServico(""); setFornecedor(""); setValor("");
      onSalvo();
      fetchManutencoesPatrimonio(item.id).then(setHistorico).catch(() => {});
      // O plano pode ter avançado (nova última/próxima data) — recarrega a modal com os dados atuais.
      fetchPatrimonio().then((d: any) => {
        const atualizado = d.itens.find((x: ItemPatrimonio) => x.id === item.id);
        if (atualizado) { setDataUltima(atualizado.data_ultima_manutencao || ""); setDataProxima(atualizado.data_proxima_manutencao || ""); }
      }).catch(() => {});
    } catch (e: any) { setErroRegistro(e.message); } finally { setSalvandoRegistro(false); }
  };

  const inputStyle: React.CSSProperties = {
    background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
  };
  const label: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

  return (
    <Modal title={`Manutenção preventiva — ${item.nome}`} onClose={onClose} width="640px">
      <div className="space-y-4">
        <div>
          <div className="card-header mb-2" style={{ fontSize: "0.9rem" }}>Plano (opcional)</div>
          <div className="grid grid-cols-2 gap-3">
            <div><label style={label}>Frequência (meses)</label>
              <input type="number" min={1} style={inputStyle} value={frequencia} onChange={(e) => setFrequencia(e.target.value)} placeholder="ex.: 6" /></div>
            <div><label style={label}>Última manutenção</label>
              <input type="date" style={inputStyle} value={dataUltima} onChange={(e) => setDataUltima(e.target.value)} /></div>
            <div><label style={label}>Próxima manutenção {frequencia && dataUltima ? "(calculada — ajuste se quiser)" : ""}</label>
              <input type="date" style={inputStyle} value={dataProxima} onChange={(e) => setDataProxima(e.target.value)} /></div>
            <div><label style={label}>Observação</label>
              <input style={inputStyle} value={observacaoPlano} onChange={(e) => setObservacaoPlano(e.target.value)} placeholder="ex.: troca de óleo, filtros…" /></div>
          </div>
          {erroPlano && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.4rem" }}>{erroPlano}</p>}
          <button className="btn-primary mt-2" style={{ fontSize: "0.8rem" }} onClick={salvarPlano} disabled={salvandoPlano}>
            {salvandoPlano ? "Salvando…" : "Salvar plano"}
          </button>
        </div>

        <div style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
          <div className="flex items-center justify-between mb-2">
            <div className="card-header" style={{ margin: 0, fontSize: "0.9rem" }}>Registrar manutenção realizada</div>
            {!mostrarRegistro && (
              <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setMostrarRegistro(true)}>
                <Plus size={13} /> Registrar
              </button>
            )}
          </div>
          {mostrarRegistro && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-3">
                <div><label style={label}>Data da manutenção</label>
                  <input type="date" style={inputStyle} value={dataRealizacao} onChange={(e) => setDataRealizacao(e.target.value)} /></div>
                <div><label style={label}>Valor (R$)</label>
                  <CampoMoeda style={inputStyle} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
                <div><label style={label}>Fornecedor/Oficina</label>
                  <input style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)} /></div>
                <div><label style={label}>Descrição do serviço</label>
                  <input style={inputStyle} value={descricaoServico} onChange={(e) => setDescricaoServico(e.target.value)} placeholder="ex.: troca de óleo e filtros" /></div>
                <div><label style={label}>Status</label>
                  <select style={inputStyle} value={statusManut} onChange={(e) => setStatusManut(e.target.value as "pago" | "pendente")}>
                    <option value="pago">Pago</option>
                    <option value="pendente">Pendente (fica em Contas a Pagar)</option>
                  </select>
                </div>
                {statusManut === "pago" && (
                  <div><label style={label}>Data do pagamento</label>
                    <input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
                )}
              </div>
              <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                <input type="checkbox" checked={gerarConta} onChange={(e) => setGerarConta(e.target.checked)} />
                Gerar lançamento em Contas a Pagar
              </label>
              {erroRegistro && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erroRegistro}</p>}
              <div className="flex gap-2">
                <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={registrarManutencao} disabled={salvandoRegistro}>
                  {salvandoRegistro ? "Salvando…" : "Confirmar manutenção"}
                </button>
                <button className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={() => setMostrarRegistro(false)}>Cancelar</button>
              </div>
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
          <div className="card-header mb-2" style={{ fontSize: "0.9rem" }}>Histórico</div>
          {historico == null ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando…</p>
          ) : historico.length === 0 ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhuma manutenção registrada ainda.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrd rotulo="Data" chave="data" sortKey={sortKeyHist} sortDir={sortDirHist} onSort={ordenarHist} />
                  <ThOrd rotulo="Descrição" chave="descricao" sortKey={sortKeyHist} sortDir={sortDirHist} onSort={ordenarHist} />
                  <ThOrd rotulo="Fornecedor" chave="fornecedor" sortKey={sortKeyHist} sortDir={sortDirHist} onSort={ordenarHist} />
                  <ThOrd rotulo="Valor" chave="valor" sortKey={sortKeyHist} sortDir={sortDirHist} onSort={ordenarHist} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="Status" chave="status" sortKey={sortKeyHist} sortDir={sortDirHist} onSort={ordenarHist} />
                  <th>Lançamento</th>
                </tr></thead>
                <tbody>
                  {historicoOrdenado.map((h) => (
                    <tr key={h.id}>
                      <td style={{ fontSize: "0.78rem" }}>{formatDate(h.data_realizacao)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{h.descricao || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{h.fornecedor || "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{h.valor != null ? formatBRL(h.valor) : "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{h.status === "pago" ? "Pago" : "Pendente"}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{h.numero_lancamento_gerado || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────── Cartão de crédito ───────────────────────
const cartaoInputStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
};
const cartaoLabelStyle: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

function CartaoVisual({ cartao }: { cartao: CartaoCredito }) {
  return (
    <div style={{
      background: "linear-gradient(135deg, var(--vinho, #0E2A47) 0%, var(--vinho-dark, #0A1F36) 100%)",
      borderRadius: "var(--r-sm)", padding: "1rem 1.1rem", color: "#fff", display: "grid", gap: "0.5rem",
      position: "relative", overflow: "hidden", minHeight: "110px",
    }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 85% 15%, rgba(232,199,102,0.25), transparent 55%)" }} />
      <div style={{ fontSize: "0.68rem", letterSpacing: "0.06em", textTransform: "uppercase", opacity: 0.85, position: "relative" }}>
        {cartao.banco_emissor || "Cartão de crédito"}
      </div>
      <div style={{ fontSize: "1.05rem", fontWeight: 700, position: "relative" }}>{cartao.apelido}</div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", opacity: 0.9, position: "relative" }}>
        <span>Fecha dia {cartao.dia_fechamento} · Vence dia {cartao.dia_vencimento}</span>
        {cartao.bandeira && <span style={{ fontStyle: "italic", color: "#C9A44C" }}>{cartao.bandeira}</span>}
      </div>
      {!cartao.ativo && <span style={{ fontSize: "0.68rem", opacity: 0.85, position: "relative" }}>Inativo</span>}
    </div>
  );
}

function CartaoCreditoView() {
  const [cartoes, setCartoes] = useState<CartaoCredito[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [novoAberto, setNovoAberto] = useState(false);
  const [editando, setEditando] = useState<CartaoCredito | null>(null);
  const [selecionado, setSelecionado] = useState<CartaoCredito | null>(null);

  const carregar = () => { fetchCartoesCredito().then(setCartoes).catch((e) => setErro(e.message)); };
  useEffect(carregar, []);

  if (erro) return <div className="alert-critico"><span>Sem dados: {erro}.</span></div>;
  if (!cartoes) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  if (selecionado) {
    return (
      <DetalheCartaoView
        cartao={cartoes.find((c) => c.id === selecionado.id) || selecionado}
        onVoltar={() => setSelecionado(null)}
        onAtualizado={carregar}
      />
    );
  }

  return (
    <>
      {!cartoes.length ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <CreditCard size={38} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-muted)" }}>Nenhum cartão de crédito cadastrado ainda.</p>
          <button className="btn-primary mt-3" style={{ fontSize: "0.82rem" }} onClick={() => setNovoAberto(true)}>
            <Plus size={14} /> Novo cartão
          </button>
        </div>
      ) : (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2"><CreditCard size={16} /> Cartões cadastrados</span>
            <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={() => setNovoAberto(true)}>
              <Plus size={13} /> Novo cartão
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {cartoes.map((c) => (
              <div key={c.id} style={{ cursor: "pointer" }} onClick={() => setSelecionado(c)}>
                <CartaoVisual cartao={c} />
                <div className="flex items-center justify-between mt-1">
                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                    {c.limite != null ? `Limite ${formatBRL(c.limite)}` : "Sem limite cadastrado"}
                  </span>
                  <button className="btn-ghost" style={{ padding: "0.2rem" }} title="Editar cartão"
                    onClick={(e) => { e.stopPropagation(); setEditando(c); }}>
                    <Pencil size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {(novoAberto || editando) && (
        <ModalNovoCartao
          cartao={editando}
          onClose={() => { setNovoAberto(false); setEditando(null); }}
          onSalvo={() => { setNovoAberto(false); setEditando(null); carregar(); }}
        />
      )}
    </>
  );
}

function ModalNovoCartao({ cartao, onClose, onSalvo }: { cartao: CartaoCredito | null; onClose: () => void; onSalvo: () => void }) {
  const [apelido, setApelido] = useState(cartao?.apelido || "");
  const [bandeira, setBandeira] = useState(cartao?.bandeira || "");
  const [bancoEmissor, setBancoEmissor] = useState(cartao?.banco_emissor || "");
  const [diaFechamento, setDiaFechamento] = useState(cartao?.dia_fechamento != null ? String(cartao.dia_fechamento) : "");
  const [diaVencimento, setDiaVencimento] = useState(cartao?.dia_vencimento != null ? String(cartao.dia_vencimento) : "");
  const [limite, setLimite] = useState(cartao?.limite != null ? String(cartao.limite) : "");
  const [controlaMilhas, setControlaMilhas] = useState(cartao?.controla_milhas ?? false);
  const [milhasPorReal, setMilhasPorReal] = useState(cartao?.milhas_por_real != null ? String(cartao.milhas_por_real) : "");
  const [ativo, setAtivo] = useState(cartao?.ativo ?? true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const salvar = async () => {
    if (!apelido.trim()) { setErro("Apelido é obrigatório."); return; }
    if (!diaFechamento || !diaVencimento) { setErro("Informe o dia de fechamento e o dia de vencimento."); return; }
    const payload: CartaoCreditoPayload = {
      apelido: apelido.trim(), bandeira: bandeira || null, banco_emissor: bancoEmissor || null,
      dia_fechamento: Number(diaFechamento), dia_vencimento: Number(diaVencimento),
      limite: limite ? Number(limite) : null, controla_milhas: controlaMilhas,
      milhas_por_real: controlaMilhas && milhasPorReal ? Number(milhasPorReal) : null, ativo,
    };
    setSalvando(true); setErro("");
    try {
      if (cartao) await atualizarCartaoCredito(cartao.id, payload);
      else await criarCartaoCredito(payload);
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  return (
    <Modal title={cartao ? `Editar cartão — ${cartao.apelido}` : "Novo cartão de crédito"} onClose={onClose} width="520px">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div style={{ gridColumn: "1 / -1" }}><label style={cartaoLabelStyle}>Apelido</label>
            <input style={cartaoInputStyle} value={apelido} onChange={(e) => setApelido(e.target.value)} placeholder="ex.: Nubank PJ" /></div>
          <div><label style={cartaoLabelStyle}>Bandeira</label>
            <input style={cartaoInputStyle} value={bandeira} onChange={(e) => setBandeira(e.target.value)} placeholder="Visa, Mastercard, Elo…" /></div>
          <div><label style={cartaoLabelStyle}>Banco emissor</label>
            <input style={cartaoInputStyle} value={bancoEmissor} onChange={(e) => setBancoEmissor(e.target.value)} /></div>
          <div><label style={cartaoLabelStyle}>Dia de fechamento</label>
            <input type="number" min={1} max={31} style={cartaoInputStyle} value={diaFechamento} onChange={(e) => setDiaFechamento(e.target.value)} /></div>
          <div><label style={cartaoLabelStyle}>Dia de vencimento</label>
            <input type="number" min={1} max={31} style={cartaoInputStyle} value={diaVencimento} onChange={(e) => setDiaVencimento(e.target.value)} /></div>
          <div><label style={cartaoLabelStyle}>Limite (R$)</label>
            <CampoMoeda style={cartaoInputStyle} value={Number(limite) || 0} onChange={(v) => setLimite(v ? String(v) : "")} /></div>
          <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Ativo</label></div>
        </div>
        <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
          <input type="checkbox" checked={controlaMilhas} onChange={(e) => setControlaMilhas(e.target.checked)} /> Este cartão acumula milhas/pontos
        </label>
        {controlaMilhas && (
          <div style={{ maxWidth: "220px" }}>
            <label style={cartaoLabelStyle}>Milhas por real gasto</label>
            <input type="number" step="0.01" style={cartaoInputStyle} value={milhasPorReal} onChange={(e) => setMilhasPorReal(e.target.value)} placeholder="ex.: 1.2" />
          </div>
        )}
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </div>
    </Modal>
  );
}

const STATUS_FATURA_LABEL: Record<string, string> = { aberta: "Aberta", fechada: "Fechada — aguardando pagamento", paga: "Paga" };
const STATUS_FATURA_COR: Record<string, string> = { aberta: "var(--dourado-light)", fechada: "var(--amber)", paga: "var(--green-light)" };

function DetalheCartaoView({ cartao, onVoltar, onAtualizado }: { cartao: CartaoCredito; onVoltar: () => void; onAtualizado: () => void }) {
  const [extrato, setExtrato] = useState<{ cartao: CartaoCredito; fatura: FaturaCartao; lancamentos: LancamentoCartao[] } | null>(null);
  const [faturas, setFaturas] = useState<FaturaCartao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [novaCompraAberta, setNovaCompraAberta] = useState(false);
  const [pagando, setPagando] = useState<FaturaCartao | null>(null);
  const [acao, setAcao] = useState<{ tipo: "fechar"; id: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => {
    fetchExtratoCartao(cartao.id).then(setExtrato).catch((e) => setErro(e.message));
    fetchFaturasCartao(cartao.id).then(setFaturas).catch(() => {});
  };
  useEffect(carregar, [cartao.id]);

  const fechar = async (faturaId: number) => {
    setAcao({ tipo: "fechar", id: faturaId }); setMsg(null);
    try {
      await fecharFaturaCartao(faturaId);
      carregar(); onAtualizado();
    } catch (e: any) { setMsg(e.message); }
    finally { setAcao(null); }
  };

  if (erro) return <div className="alert-critico"><span>Sem dados: {erro}.</span></div>;

  return (
    <>
      <button className="btn-ghost mb-3" style={{ fontSize: "0.78rem" }} onClick={onVoltar}>
        <ArrowLeft size={13} /> Voltar aos cartões
      </button>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div><CartaoVisual cartao={cartao} /></div>
        <div className="grid grid-cols-2 gap-3" style={{ gridColumn: "span 2" }}>
          <KPI v={extrato ? formatBRL(extrato.fatura.valor_total || 0) : "…"} l={`Fatura atual (${extrato?.fatura.competencia || ""})`} c="var(--dourado-light)" />
          <KPI v={extrato ? STATUS_FATURA_LABEL[extrato.fatura.status] : "…"} l="Status" />
          {cartao.limite != null && <KPI v={formatBRL(cartao.limite)} l="Limite" c="var(--text-muted)" />}
          {cartao.controla_milhas && (
            <div className="kpi-card">
              <div className="flex items-center gap-1" style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}><Award size={12} /> Milhas acumuladas</div>
              <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--dourado-light)" }}>{cartao.milhas_totais ?? 0}</div>
            </div>
          )}
        </div>
      </div>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{msg}</p>}

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Extrato — fatura {extrato?.fatura.status === "aberta" ? "em aberto" : extrato?.fatura.competencia}</span>
          {extrato?.fatura.status === "aberta" && (
            <div className="flex items-center gap-2">
              <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => fechar(extrato.fatura.id)} disabled={acao?.id === extrato.fatura.id}>
                {acao?.id === extrato.fatura.id ? "Fechando…" : "Fechar fatura agora"}
              </button>
              <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={() => setNovaCompraAberta(true)}>
                <Plus size={13} /> Nova compra
              </button>
            </div>
          )}
        </div>
        {!extrato ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !extrato.lancamentos.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma compra lançada nesta fatura ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th style={{ textAlign: "right" }}>Valor</th></tr></thead>
              <tbody>
                {extrato.lancamentos.map((l) => (
                  <tr key={l.id}>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.data_compra)}</td>
                    <td style={{ fontSize: "0.82rem" }}>
                      {l.descricao}{l.parcela_num && l.parcela_total ? <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}> ({l.parcela_num}/{l.parcela_total})</span> : null}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.nome_conta_gerencial || "—"}</td>
                    <td style={{ textAlign: "right", fontSize: "0.82rem", fontWeight: 600 }}>{formatBRL(l.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-header mb-3">Faturas anteriores</div>
        {!faturas ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : !faturas.filter((f) => f.status !== "aberta").length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma fatura fechada ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Competência</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {faturas.filter((f) => f.status !== "aberta").map((f) => (
                  <tr key={f.id}>
                    <td style={{ fontSize: "0.82rem", fontWeight: 600 }}>{f.competencia}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(f.data_vencimento)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{f.valor_total != null ? formatBRL(f.valor_total) : "—"}</td>
                    <td style={{ fontSize: "0.78rem", fontWeight: 600, color: STATUS_FATURA_COR[f.status] }}>{STATUS_FATURA_LABEL[f.status] || f.status}</td>
                    <td style={{ textAlign: "right" }}>
                      {f.status === "fechada" && (
                        <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={() => setPagando(f)}>Pagar</button>
                      )}
                      {f.status === "paga" && f.numero_lancamento && (
                        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lanç. {f.numero_lancamento}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {novaCompraAberta && (
        <ModalNovaCompraCartao cartaoId={cartao.id} onClose={() => setNovaCompraAberta(false)} onSalvo={() => { setNovaCompraAberta(false); carregar(); }} />
      )}
      {pagando && (
        <ModalPagarFatura fatura={pagando} cartao={cartao} onClose={() => setPagando(null)} onSalvo={() => { setPagando(null); carregar(); onAtualizado(); }} />
      )}
    </>
  );
}

function ModalNovaCompraCartao({ cartaoId, onClose, onSalvo }: { cartaoId: number; onClose: () => void; onSalvo: () => void }) {
  const [dataCompra, setDataCompra] = useState(new Date().toISOString().slice(0, 10));
  const [descricao, setDescricao] = useState("");
  const [categoria, setCategoria] = useState("");
  const [valor, setValor] = useState("");
  const [parcelaTotal, setParcelaTotal] = useState("1");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const salvar = async () => {
    if (!descricao.trim()) { setErro("Descrição é obrigatória."); return; }
    if (!valor || Number(valor) <= 0) { setErro("Informe um valor positivo."); return; }
    setSalvando(true); setErro("");
    try {
      const totalParcelas = Math.max(1, Number(parcelaTotal) || 1);
      await criarLancamentoCartao(cartaoId, {
        data_compra: dataCompra, descricao: descricao.trim(), nome_conta_gerencial: categoria || null,
        valor: Number(valor), parcela_num: totalParcelas > 1 ? 1 : null, parcela_total: totalParcelas > 1 ? totalParcelas : null,
        observacao: observacao || null,
      });
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  return (
    <Modal title="Nova compra no cartão" onClose={onClose} width="460px">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div><label style={cartaoLabelStyle}>Data da compra</label>
            <input type="date" style={cartaoInputStyle} value={dataCompra} onChange={(e) => setDataCompra(e.target.value)} /></div>
          <div><label style={cartaoLabelStyle}>Valor (R$)</label>
            <CampoMoeda style={cartaoInputStyle} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
          <div style={{ gridColumn: "1 / -1" }}><label style={cartaoLabelStyle}>Descrição</label>
            <input style={cartaoInputStyle} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="ex.: Peças trator" /></div>
          <div><label style={cartaoLabelStyle}>Categoria (opcional)</label>
            <input style={cartaoInputStyle} value={categoria} onChange={(e) => setCategoria(e.target.value)} placeholder="ex.: Manutenção" /></div>
          <div><label style={cartaoLabelStyle}>Parcelas</label>
            <input type="number" min={1} style={cartaoInputStyle} value={parcelaTotal} onChange={(e) => setParcelaTotal(e.target.value)} /></div>
          <div style={{ gridColumn: "1 / -1" }}><label style={cartaoLabelStyle}>Observação</label>
            <input style={cartaoInputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
        </div>
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
          Cai automaticamente na fatura certa: até o dia de fechamento entra na competência atual, depois do fechamento entra na fatura seguinte.
        </p>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Lançar"}</button>
        </div>
      </div>
    </Modal>
  );
}

function ModalPagarFatura({ fatura, cartao, onClose, onSalvo }: { fatura: FaturaCartao; cartao: CartaoCredito; onClose: () => void; onSalvo: () => void }) {
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const pagar = async () => {
    setSalvando(true); setErro("");
    try {
      await pagarFaturaCartao(fatura.id, { data_pagamento: dataPagamento });
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  return (
    <Modal title={`Pagar fatura — ${cartao.apelido} (${fatura.competencia})`} onClose={onClose} width="420px">
      <div className="space-y-3">
        <p style={{ fontSize: "0.85rem" }}>
          Valor da fatura: <strong>{fatura.valor_total != null ? formatBRL(fatura.valor_total) : "—"}</strong>
        </p>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          Gera uma Conta a Pagar de verdade em Financeiro (mesmo fluxo de baixa de qualquer outro lançamento) — dá pra editar
          conta gerencial e centro de custo depois, em Contas a pagar.
        </p>
        <div><label style={cartaoLabelStyle}>Data do pagamento</label>
          <input type="date" style={cartaoInputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        <div className="flex gap-2 justify-end">
          <button className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
          <button className="btn-primary" onClick={pagar} disabled={salvando}>{salvando ? "Pagando…" : "Confirmar pagamento"}</button>
        </div>
      </div>
    </Modal>
  );
}

const inputStyleRelCompraVenda: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
};
const COLUNAS_REL_COMPRA_VENDA_ANIMAL = [
  { header: "Tipo", key: "tipoLabel" }, { header: "Nº animal", key: "numero_animal" },
  { header: "Contraparte", key: "contraparte" }, { header: "Data", key: "data" },
  { header: "Valor (por animal)", key: "valor" }, { header: "GTA", key: "gta" },
  { header: "Documento", key: "numero_documento" }, { header: "Lançamento", key: "numero_lancamento" },
  { header: "Centro de custo", key: "centro_custo" },
];

/**
 * Relatório financeiro de compra/venda de animais — consulta unificada das
 * duas pontas (Comprar/Vender animal em Lançamentos), filtrável por número do
 * animal, período (de/até), documento ou GTA.
 */
function RelatorioCompraVendaAnimaisView() {
  const [numero, setNumero] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [gta, setGta] = useState("");
  const [linhas, setLinhas] = useState<LinhaRelatorioCompraVendaAnimal[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const buscar = () => {
    setCarregando(true); setErro(null);
    fetchRelatorioCompraVendaAnimais({ numero, dataDe, dataAte, numeroDocumento, gta })
      .then(setLinhas)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  useEffect(buscar, []);

  const totalCompra = useMemo(() => (linhas ?? []).filter((l) => l.tipo === "compra").reduce((a, l) => a + l.valor, 0), [linhas]);
  const totalVenda = useMemo(() => (linhas ?? []).filter((l) => l.tipo === "venda").reduce((a, l) => a + l.valor, 0), [linhas]);
  const linhasExport = useMemo(() => (linhas ?? []).map((l) => ({ ...l, tipoLabel: l.tipo === "compra" ? "Compra" : "Venda" })), [linhas]);
  const { ordenados: linhasOrdenadas, sortKey: sortKeyAnimais, sortDir: sortDirAnimais, ordenar: ordenarAnimais } = useOrdenacao(linhas ?? [], {
    tipo: (l) => l.tipo,
    numero_animal: (l) => l.numero_animal || "",
    contraparte: (l) => (l.contraparte || "").toLowerCase(),
    data: (l) => l.data || "",
    valor: (l) => l.valor,
    gta: (l) => l.gta || "",
    numero_documento: (l) => l.numero_documento || "",
    numero_lancamento: (l) => l.numero_lancamento || "",
    centro_custo: (l) => l.centro_custo || "",
  });

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Número do animal</label>
            <input style={inputStyleRelCompraVenda} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="ex.: 950" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>De</label>
            <input type="date" style={inputStyleRelCompraVenda} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Até</label>
            <input type="date" style={inputStyleRelCompraVenda} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Nº do documento</label>
            <input style={inputStyleRelCompraVenda} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>GTA</label>
            <input style={inputStyleRelCompraVenda} value={gta} onChange={(e) => setGta(e.target.value)} /></div>
          <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={buscar} disabled={carregando}>
            <Search size={13} /> {carregando ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      {linhas && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <KPI v={String(linhas.length)} l="Lançamentos" />
            <KPI v={formatBRL(totalCompra)} l="Total comprado" c="var(--red)" />
            <KPI v={formatBRL(totalVenda)} l="Total vendido" c="var(--green-light)" />
          </div>
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Compras e vendas</div>
              <ExportarBotoes titulo="Compra/Venda de animais" colunas={COLUNAS_REL_COMPRA_VENDA_ANIMAL} linhas={linhasExport} nomeArquivoBase="compra_venda_animais" disabled={!linhas.length} />
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Nº animal" chave="numero_animal" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Contraparte" chave="contraparte" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Data" chave="data" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Valor (por animal)" chave="valor" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="GTA" chave="gta" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Documento" chave="numero_documento" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Lançamento" chave="numero_lancamento" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                  <ThOrd rotulo="Centro de custo" chave="centro_custo" sortKey={sortKeyAnimais} sortDir={sortDirAnimais} onSort={ordenarAnimais} />
                </tr></thead>
                <tbody>
                  {linhasOrdenadas.map((l, i) => (
                    <tr key={i}>
                      <td>
                        <span style={{
                          fontSize: "0.72rem", padding: "0.15rem 0.5rem", borderRadius: "999px", fontWeight: 700,
                          background: l.tipo === "compra" ? "rgba(220,38,38,0.12)" : "rgba(22,163,74,0.12)",
                          color: l.tipo === "compra" ? "var(--red)" : "var(--green-light)",
                        }}>{l.tipo === "compra" ? "Compra" : "Venda"}</span>
                      </td>
                      <td style={{ fontWeight: 700 }}>{l.numero_animal}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.contraparte}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.data}</td>
                      <td style={{ textAlign: "right" }}>{formatBRL(l.valor)}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.gta || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.numero_documento || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.numero_lancamento || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.centro_custo || "—"}</td>
                    </tr>
                  ))}
                  {!linhas.length && <tr><td colSpan={9} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhuma compra ou venda de animal encontrada para o filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

const COLUNAS_REL_COMPRA_SEMEN = [
  { header: "Touro", key: "touro_nome" }, { header: "NAAB", key: "naab" }, { header: "Tipo", key: "tipo" },
  { header: "Doses", key: "doses" }, { header: "Valor/dose", key: "valor_unitario" }, { header: "Valor total", key: "valor_total" },
  { header: "Data", key: "data_compra" }, { header: "Vendedor", key: "vendedor" }, { header: "Documento", key: "numero_documento" },
  { header: "Lançamento", key: "numero_lancamento" }, { header: "Centro de custo", key: "centro_custo" },
];

/**
 * Relatório financeiro de compra de sêmen — espelho de
 * RelatorioCompraVendaAnimaisView, consultando CompraSemen (em vez de
 * CompraAnimal/VendaAnimal), filtrável por touro, NAAB, vendedor, período ou
 * número do documento.
 */
function RelatorioCompraSemenView() {
  const [touro, setTouro] = useState("");
  const [vendedor, setVendedor] = useState("");
  const [dataDe, setDataDe] = useState("");
  const [dataAte, setDataAte] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [linhas, setLinhas] = useState<LinhaRelatorioCompraSemen[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const buscar = () => {
    setCarregando(true); setErro(null);
    fetchRelatorioCompraSemen({ touro, vendedor, dataDe, dataAte, numeroDocumento })
      .then(setLinhas)
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  useEffect(buscar, []);

  const totalDoses = useMemo(() => (linhas ?? []).reduce((a, l) => a + l.doses, 0), [linhas]);
  const totalGasto = useMemo(() => (linhas ?? []).reduce((a, l) => a + l.valor_total, 0), [linhas]);
  const { ordenados: linhasOrdenadas, sortKey: sortKeySemen, sortDir: sortDirSemen, ordenar: ordenarSemen } = useOrdenacao(linhas ?? [], {
    touro_nome: (l) => l.touro_nome || "",
    naab: (l) => l.naab || "",
    tipo: (l) => l.tipo || "",
    doses: (l) => l.doses,
    valor_unitario: (l) => l.valor_unitario,
    valor_total: (l) => l.valor_total,
    data_compra: (l) => l.data_compra || "",
    vendedor: (l) => (l.vendedor || "").toLowerCase(),
    numero_documento: (l) => l.numero_documento || "",
    numero_lancamento: (l) => l.numero_lancamento || "",
    centro_custo: (l) => l.centro_custo || "",
  });

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Touro</label>
            <input style={inputStyleRelCompraVenda} value={touro} onChange={(e) => setTouro(e.target.value)} placeholder="ex.: Coors" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Vendedor</label>
            <input style={inputStyleRelCompraVenda} value={vendedor} onChange={(e) => setVendedor(e.target.value)} placeholder="ex.: ABS" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>De</label>
            <input type="date" style={inputStyleRelCompraVenda} value={dataDe} onChange={(e) => setDataDe(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Até</label>
            <input type="date" style={inputStyleRelCompraVenda} value={dataAte} onChange={(e) => setDataAte(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Nº do documento</label>
            <input style={inputStyleRelCompraVenda} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></div>
          <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={buscar} disabled={carregando}>
            <Search size={13} /> {carregando ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      {linhas && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <KPI v={String(linhas.length)} l="Compras" />
            <KPI v={String(totalDoses)} l="Doses compradas" />
            <KPI v={formatBRL(totalGasto)} l="Total gasto" c="var(--red)" />
          </div>
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Compras de sêmen</div>
              <ExportarBotoes titulo="Compra de sêmen" colunas={COLUNAS_REL_COMPRA_SEMEN} linhas={linhas} nomeArquivoBase="compra_semen" disabled={!linhas.length} />
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrd rotulo="Touro" chave="touro_nome" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="NAAB" chave="naab" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Doses" chave="doses" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="Valor/dose" chave="valor_unitario" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="Valor total" chave="valor_total" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} style={{ textAlign: "right" }} />
                  <ThOrd rotulo="Data" chave="data_compra" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Vendedor" chave="vendedor" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Documento" chave="numero_documento" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Lançamento" chave="numero_lancamento" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                  <ThOrd rotulo="Centro de custo" chave="centro_custo" sortKey={sortKeySemen} sortDir={sortDirSemen} onSort={ordenarSemen} />
                </tr></thead>
                <tbody>
                  {linhasOrdenadas.map((l, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{l.touro_nome}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.naab || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.tipo === "sexado" ? "Sexado" : "Convencional"}</td>
                      <td style={{ textAlign: "right" }}>{l.doses}</td>
                      <td style={{ textAlign: "right" }}>{formatBRL(l.valor_unitario)}</td>
                      <td style={{ textAlign: "right" }}>{formatBRL(l.valor_total)}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.data_compra}</td>
                      <td style={{ fontSize: "0.8rem" }}>{l.vendedor}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.numero_documento || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.numero_lancamento || "—"}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.centro_custo || "—"}</td>
                    </tr>
                  ))}
                  {!linhas.length && <tr><td colSpan={11} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhuma compra de sêmen encontrada para o filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

/**
 * Edição de um lançamento financeiro já salvo (uma nota / uma parcela). Serve
 * para contas a pagar, a receber, pagas e recebidas — edita valor, descrição,
 * fornecedor/cliente, centro de custo, conta gerencial, datas e documento sem
 * precisar dar baixa. Não mexe no pagamento (isso é o fluxo "Tratar").
 */
type ItemLancEditar = NonNullable<Lanc["itens"]>[number];

function FormEditarLancamento({ lanc, centros, planoContas, produtos, fornecedores, onSalvo, onCancelar, onVerRelatorioVales }: {
  lanc: Lanc; centros: string[]; planoContas: ContaPlano[]; produtos: string[]; fornecedores: string[]; onSalvo: () => void; onCancelar: () => void;
  // Leva o usuário até "Financeiro > Ações > Folha de pagamento > Relatório
  // de vales e descontos" (ver chamada em app/financeiro/page.tsx) — usado
  // pelo link "ver no relatório de vales" do bloco de itens abaixo.
  onVerRelatorioVales?: () => void;
}) {
  const [descricao, setDescricao] = useState(lanc.descricao || "");
  const [fornecedor, setFornecedor] = useState(lanc.fornecedor || "");
  // Produto/serviço do item — só é seguro editar quando a nota tem 0 (ex.:
  // importada sem vínculo) ou exatamente 1 item; com vários itens, trocar
  // "o" produto seria ambíguo (qual deles?), então a tela só informa.
  const itensDoLanc = lanc.itens || [];
  const podeEditarProduto = itensDoLanc.length <= 1;
  const [produto, setProduto] = useState(itensDoLanc[0]?.produto || "");
  // Mesmo padrão de seleção de produto/serviço do lançamento novo
  // (FormFinanceiro): toggle produto×serviço, EstoquePicker em janela
  // suspensa (não mais <input list> com <datalist> nativo) e botão para
  // cadastrar produto/serviço novo sem sair da edição — antes a edição usava
  // uma implementação própria, mais simples, que nunca ganhou esse picker.
  const [tipoItem, setTipoItem] = useState<"produto" | "servico">("produto");
  const [modoProduto, setModoProduto] = useState<"estoque" | "livre">("estoque");
  const [produtosEstoqueEdicao, setProdutosEstoqueEdicao] = useState<EstoqueItemPicker[]>([]);
  // Lista completa (model_dump() do Estoque, não só o formato reduzido do
  // picker) — precisa dela pra abrir "editar cadastro" de um item já
  // registrado direto da lista de itens da nota (ver `editarItemEstoque`).
  const [estoqueCompletoEdicao, setEstoqueCompletoEdicao] = useState<Record<string, any>[]>([]);
  const carregarEstoqueEdicao = () => fetchEstoque().then((d) => {
    setEstoqueCompletoEdicao(d.itens || []);
    setProdutosEstoqueEdicao((d.itens || []).map((i: any) => ({
      nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
      estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
    })));
  }).catch(() => {});
  useEffect(() => { carregarEstoqueEdicao(); }, []);
  const [servicosEdicao, setServicosEdicao] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const carregarServicosEdicao = () => fetchServicosCadastro().then(setServicosEdicao).catch(() => {});
  useEffect(() => { carregarServicosEdicao(); }, []);
  const sugestoesServicoEdicao = useMemo(
    () => servicosEdicao.filter((s) => s.ativo).map((s) => s.nome).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [servicosEdicao]
  );
  // Um item da nota "existe de verdade" no catálogo quando o nome bate
  // (exato, sem diferenciar maiúsculas) com um Estoque ou ServicoCadastro
  // ativo — vale não entra nessa checagem (não é produto/serviço de
  // catálogo, é adiantamento a uma pessoa). Sem isso, um item lido de XML/
  // OCR que não batia com nada do catálogo (ex.: "TEATSEAL") ficava salvo
  // como texto solto: sem estocável, sem centro de custo padrão, invisível
  // pras telas de aplicação — e sem jeito de perceber isso na edição.
  function itemCadastrado(it: { produto: string; eh_vale: boolean; tipo_item?: string | null }): boolean {
    if (it.eh_vale || !it.produto?.trim()) return true;
    const nome = it.produto.trim().toLowerCase();
    if (it.tipo_item === "servico") return sugestoesServicoEdicao.some((s) => s.toLowerCase() === nome);
    return produtosEstoqueEdicao.some((p) => p.nome.toLowerCase() === nome);
  }
  const [catalogarItem, setCatalogarItem] = useState<{ id: number; nome: string; tipo: "produto" | "servico" } | null>(null);
  const [editarItemEstoque, setEditarItemEstoque] = useState<Record<string, any> | null>(null);
  // Chute do tipo (produto × serviço) a partir do nome já salvo — só uma vez,
  // assim que o cadastro de serviços carrega; depois disso quem manda é o
  // toggle clicado pelo usuário (evita "brigar" com a escolha dele).
  const tipoInicializado = useRef(false);
  useEffect(() => {
    if (!tipoInicializado.current && servicosEdicao.length) {
      tipoInicializado.current = true;
      if (produto && sugestoesServicoEdicao.includes(produto)) setTipoItem("servico");
    }
  }, [servicosEdicao, sugestoesServicoEdicao, produto]);
  const [adicionarNovoAberto, setAdicionarNovoAberto] = useState(false);
  const [modoAdicionarEdicao, setModoAdicionarEdicao] = useState<"produto" | "servico">("produto");
  const [centroCusto, setCentroCusto] = useState(lanc.centro_custo || "");
  const [classificacao, setClassificacao] = useState(lanc.classificacao || "");
  const [classificacoes, setClassificacoes] = useState<string[]>([]);
  const [novaClassificacaoAberta, setNovaClassificacaoAberta] = useState(false);
  const [novaClassificacaoNome, setNovaClassificacaoNome] = useState("");
  const [salvandoClassificacao, setSalvandoClassificacao] = useState(false);
  // Associar um item já lançado (não cadastrado no catálogo) a um produto/
  // serviço JÁ EXISTENTE — alternativa a "cadastrar novo" (ver catalogarItem
  // abaixo). `avisoAssociar` mostra o retorno do backend (ex.: entrada de
  // estoque retroativa dada na hora de associar).
  const [associarItem, setAssociarItem] = useState<{ id: number; nome: string; tipo: "produto" | "servico" } | null>(null);
  const [salvandoAssociar, setSalvandoAssociar] = useState(false);
  const [avisoAssociar, setAvisoAssociar] = useState<string[] | null>(null);
  const [codigoConta, setCodigoConta] = useState(lanc.codigo_conta || "");
  const [nomeConta, setNomeConta] = useState(lanc.conta_completa || "");
  const [valor, setValor] = useState(String(lanc.valor ?? ""));
  const [dataEmissao, setDataEmissao] = useState((lanc.data_emissao || "").slice(0, 10));
  const [dataVencimento, setDataVencimento] = useState((lanc.data_vencimento || "").slice(0, 10));
  const [dataCompetencia, setDataCompetencia] = useState((lanc.data_competencia || "").slice(0, 10));
  const [numeroNota, setNumeroNota] = useState(lanc.numero_documento || "");
  const [numeroOsOrcamento, setNumeroOsOrcamento] = useState(lanc.numero_os_orcamento || "");
  const [numeroPagamento, setNumeroPagamento] = useState(lanc.numero_documento_pagamento || "");
  const [tipoDocumento, setTipoDocumento] = useState(lanc.tipo_documento || "");
  const [tiposDocumento, setTiposDocumento] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  const [anexos, setAnexos] = useState<AnexoLancamento[] | null>(null);
  const [enviandoAnexo, setEnviandoAnexo] = useState(false);
  const [categoriaAnexo, setCategoriaAnexo] = useState(lanc.tipo_documento || "");
  // Número/data do PRÓXIMO arquivo a anexar — cada documento deste
  // lançamento (orçamento, pedido, nota fiscal, boleto, comprovante...) pode
  // ter seu próprio número/data, achável depois na Central de Documentos.
  const [numeroDocAnexo, setNumeroDocAnexo] = useState("");
  const [dataDocAnexo, setDataDocAnexo] = useState("");
  // Vincular esta compra/venda a um item de Patrimônio (entrada/saída de
  // patrimônio) — FK de verdade, editável tanto aqui quanto pela tela de
  // Patrimônio (mesmo endpoint, ver vincularLancamentoPatrimonio).
  const [patrimonioId, setPatrimonioId] = useState(lanc.patrimonio_id ? String(lanc.patrimonio_id) : "");
  const [patrimonios, setPatrimonios] = useState<{ id: number; nome: string; tipo: string | null }[]>([]);
  useEffect(() => { fetchPatrimonioListaSimples().then(setPatrimonios).catch(() => {}); }, []);
  const tipoConta = lanc.tipo === "receita" ? "receita" : "despesa";
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...(fornecedor ? [fornecedor] : []), ...fornecedores])).sort(),
    [fornecedores, fornecedor]
  );
  const centrosOpcoes = useMemo(() => Array.from(new Set([lanc.centro_custo, ...centros].filter(Boolean))).sort(), [centros, lanc.centro_custo]);

  // Checkbox "É vale de funcionário?" por item da nota (item já salvo — o
  // vale é de verdade, criado/excluído já no backend, ver lib/api.ts). Marcar
  // abre o ValeItemModal; desmarcar SEMPRE pergunta antes de excluir o vale
  // vinculado (decisão do usuário — nunca em silêncio, nunca vínculo
  // pendurado sem perguntar).
  const [valeModalItem, setValeModalItem] = useState<ItemLancEditar | null>(null);
  const [confirmarDesmarcar, setConfirmarDesmarcar] = useState<ItemLancEditar | null>(null);
  const [desmarcando, setDesmarcando] = useState(false);
  const [desmarcarErro, setDesmarcarErro] = useState<string | null>(null);

  async function marcarVale(item: ItemLancEditar, dados: ValeItemDados) {
    await marcarItemComoVale(item.id, {
      pessoa_id: dados.pessoa_id, modo: dados.modo, parcelas: dados.parcelas,
      competencia_inicio: dados.competencia_inicio || undefined,
      origem_tipo: dados.origem_tipo, origem_id: dados.origem_id,
      observacao: dados.observacao, confirmar: dados.confirmar,
    });
    setValeModalItem(null);
    onSalvo();
  }

  async function desmarcarVale(item: ItemLancEditar, excluirVale: boolean) {
    setDesmarcando(true); setDesmarcarErro(null);
    try {
      await desmarcarItemComoVale(item.id, excluirVale);
      setConfirmarDesmarcar(null);
      onSalvo();
    } catch (e: any) {
      setDesmarcarErro(e.message || "Erro ao desmarcar vale");
    } finally {
      setDesmarcando(false);
    }
  }
  useEffect(() => { fetchOpcoesFinanceiro().then((d) => { setTiposDocumento(d.tipos_documento || []); setClassificacoes(d.classificacoes || []); }).catch(() => {}); }, []);
  useEffect(() => {
    listarAnexosLancamentoPorId(lanc.id).then(setAnexos).catch(() => setAnexos([]));
  }, [lanc.id]);

  const enviarAnexo = async (file: File) => {
    setEnviandoAnexo(true); setErro("");
    try {
      const novo = await anexarArquivoLancamentoPorId(lanc.id, file, categoriaAnexo || null, numeroDocAnexo || null, dataDocAnexo || null);
      setAnexos((p) => [...(p || []), novo]);
      setNumeroDocAnexo(""); setDataDocAnexo("");
    } catch (e: any) { setErro(e.message); }
    finally { setEnviandoAnexo(false); }
  };

  const removerAnexo = async (id: number) => {
    try {
      await excluirAnexoLancamento(id);
      setAnexos((p) => (p || []).filter((a) => a.id !== id));
    } catch (e: any) { setErro(e.message); }
  };

  // Associa um item já lançado (LancamentoItem) a um produto/serviço do
  // catálogo — usado tanto por "cadastrar novo" quanto por "associar
  // existente" acima. Explícito (por id), não depende do nome bater sozinho.
  async function vincularProduto(itemId: number, nomeProduto: string) {
    try {
      const r = await vincularProdutoItem(itemId, nomeProduto);
      setAvisoAssociar(r.avisos_estoque || []);
      onSalvo();
    } catch (e: any) {
      setErro(e.message || "Erro ao associar o produto/serviço a este item");
    }
  }

  const salvar = async () => {
    setSalvando(true); setErro("");
    try {
      await atualizarLancamentoFinanceiro(lanc.id, {
        descricao, fornecedor_cliente: fornecedor, centro_custo: centroCusto || null, classificacao: classificacao || null,
        codigo_conta: codigoConta || null, valor_total: parseFloat(valor.replace(",", ".")) || 0,
        data_emissao: dataEmissao || null, data_vencimento: dataVencimento || null,
        data_competencia: dataCompetencia || null, numero_nota: numeroNota || null,
        numero_os_orcamento: numeroOsOrcamento || null,
        numero_documento_pagamento: numeroPagamento || null, tipo_documento: tipoDocumento || null,
        ...(podeEditarProduto && produto.trim() ? { produto: produto.trim() } : {}),
      });
      const novoPatrimonioId = patrimonioId ? Number(patrimonioId) : null;
      if (novoPatrimonioId !== (lanc.patrimonio_id ?? null) && lanc.numero_lancamento) {
        await vincularLancamentoPatrimonio(lanc.numero_lancamento, novoPatrimonioId);
      }
      onSalvo();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  };

  return (
    <div className="space-y-3">
      {lanc.parcela_total && lanc.parcela_total > 1 && (
        <p style={{ fontSize: "0.75rem", color: "var(--amber)", background: "rgba(180,120,0,0.12)", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)" }}>
          Esta é a parcela {lanc.parcela_num}/{lanc.parcela_total}. A edição altera <strong>só esta parcela</strong> — as outras seguem como estão.
        </p>
      )}
      {lanc.valor_pago != null && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          Esta conta já tem baixa (valor pago/recebido {formatBRL(lanc.valor_pago)}). Editar aqui muda os dados do lançamento, não o pagamento.
        </p>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyleLote}>Descrição</label>
          <input style={selStyleLote} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          {itensDoLanc.length > 0 && (
            <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
              Gerada automaticamente a partir dos itens — edite aqui só se quiser um resumo diferente para os relatórios.
              Veja/edite cada item em &ldquo;Produtos/serviços desta nota&rdquo;, abaixo.
            </p>
          )}
        </div>
        <div><label style={labelStyleLote}>{tipoConta === "receita" ? "Cliente" : "Fornecedor"}</label>
          <div className="flex items-center gap-2">
            <select style={selStyleLote} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>
              {fornecedoresDisponiveis.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button type="button" className="btn-ghost" title={`Cadastrar novo ${tipoConta === "receita" ? "cliente" : "fornecedor"}`} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
        </div>
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyleLote}>Produto / serviço</label>
          {podeEditarProduto ? (
            <>
              <div className="flex items-center gap-2 mb-2">
                {(["produto", "servico"] as const).map((t) => (
                  <button key={t} type="button" title={t === "produto" ? "Este item é um produto de estoque" : "Este item é um serviço"}
                    onClick={() => { setTipoItem(t); setProduto(""); }}
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                      border: "1px solid " + (tipoItem === t ? "var(--dourado)" : "var(--border)"),
                      background: tipoItem === t ? "var(--dourado)" : "transparent",
                      color: tipoItem === t ? "#1a1a1a" : "var(--text-muted)", fontWeight: tipoItem === t ? 700 : 400 }}>
                    {t === "produto" ? "Produto" : "Serviço"}
                  </button>
                ))}
              </div>
              {tipoItem === "servico" ? (
                <ServicoPicker servicos={sugestoesServicoEdicao.map((nome) => ({ nome }))}
                  value={produto} onChange={setProduto} />
              ) : (
                <div>
                  <div className="flex items-center justify-between" style={{ marginBottom: "0.25rem" }}>
                    <select style={{ background: "transparent", color: "var(--text-muted)", border: "none", fontSize: "0.68rem", cursor: "pointer" }}
                      value={modoProduto} onChange={(e) => setModoProduto(e.target.value as "estoque" | "livre")}
                      title="Do estoque: escolhe um item já cadastrado. Texto livre: qualquer compra, mesmo sem cadastro.">
                      <option value="estoque">do estoque</option>
                      <option value="livre">texto livre</option>
                    </select>
                  </div>
                  {modoProduto === "estoque" ? (
                    <EstoquePicker itens={produtosEstoqueEdicao} value={produto} todasFinalidades incluirNaoEstocaveis onChange={setProduto} />
                  ) : (
                    <>
                      <input list="produtos-editar-lancamento" style={selStyleLote} value={produto} onChange={(e) => setProduto(e.target.value)}
                        placeholder="ex.: Supermercado, Material de escritório…" />
                      <datalist id="produtos-editar-lancamento">{produtos.map((p) => <option key={p} value={p} />)}</datalist>
                    </>
                  )}
                </div>
              )}
              {itensDoLanc.length === 0 && (
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>Sem vínculo — escolha ou cadastre um produto/serviço.</p>
              )}
              <button type="button" className="btn-ghost" title="Cadastrar um novo produto ou serviço"
                style={{ fontSize: "0.72rem", marginTop: "0.4rem" }}
                onClick={() => { setModoAdicionarEdicao(tipoItem === "servico" ? "servico" : "produto"); setAdicionarNovoAberto(true); }}>
                <Plus size={13} /> Adicionar {tipoItem === "servico" ? "serviço" : "produto"} novo(a)
              </button>
            </>
          ) : (
            <p style={{ ...selStyleLote, background: "transparent", border: "none", padding: "0.45rem 0", color: "var(--text-muted)", fontSize: "0.75rem" }}>
              Nota com {itensDoLanc.length} produtos/serviços — edite pelo lançamento original.
            </p>
          )}
        </div>
        {itensDoLanc.length > 0 && (
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyleLote}>Produtos/serviços desta nota</label>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginTop: "0.3rem" }}>
              {itensDoLanc.map((it) => {
                const cadastrado = itemCadastrado(it);
                return (
                  <div key={it.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", flexWrap: "wrap",
                    ...(cadastrado ? {} : { background: "rgba(180,120,0,0.12)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem" }) }}>
                    {tipoConta === "despesa" && (
                      <input id={`vale-lanc-item-${it.id}`} type="checkbox" checked={it.eh_vale}
                        onChange={(e) => e.target.checked ? setValeModalItem(it) : setConfirmarDesmarcar(it)} />
                    )}
                    {tipoConta === "despesa" && (
                      <label htmlFor={`vale-lanc-item-${it.id}`} style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>É vale de funcionário?</label>
                    )}
                    {cadastrado ? (
                      <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem", padding: 0, textDecoration: "underline" }}
                        title="Abrir o cadastro deste produto/serviço"
                        onClick={() => {
                          if (it.tipo_item === "servico") return; // sem tela de edição de serviço avulsa ainda
                          const item = estoqueCompletoEdicao.find((e) => (e.nome || "").toLowerCase() === it.produto.trim().toLowerCase());
                          if (item) setEditarItemEstoque(item);
                        }}>
                        {it.produto}
                      </button>
                    ) : (
                      <span style={{ color: "var(--amber)" }}>
                        <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.25rem", verticalAlign: "-1px" }} />
                        {it.produto} — não cadastrado
                      </span>
                    )}
                    <span>— {formatBRL(it.valor_total)}</span>
                    {!cadastrado && (
                      <>
                        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }}
                          onClick={() => setCatalogarItem({ id: it.id, nome: it.produto, tipo: it.tipo_item === "servico" ? "servico" : "produto" })}>
                          <Plus size={12} /> Cadastrar {it.tipo_item === "servico" ? "serviço" : "produto"} novo
                        </button>
                        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }}
                          onClick={() => setAssociarItem({ id: it.id, nome: it.produto, tipo: it.tipo_item === "servico" ? "servico" : "produto" })}>
                          Associar a {it.tipo_item === "servico" ? "serviço" : "produto"} já existente
                        </button>
                      </>
                    )}
                    {it.eh_vale && (
                      <span style={{ color: "var(--dourado-light)", fontSize: "0.74rem" }}>
                        → vale de {it.vale_pessoa_nome}
                        {" "}
                        <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem" }}
                          onClick={() => onVerRelatorioVales?.()}>
                          ver no relatório de vales
                        </button>
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <div><label style={labelStyleLote}>Valor (R$)</label>
          <CampoMoeda style={selStyleLote} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
        <div><label style={labelStyleLote}>Centro de custo</label>
          <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
            <option value="">—</option>{centrosOpcoes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Conta gerencial</label>
          <SeletorContaGerencial contas={planoContas} tipo={tipoConta} codigo={codigoConta} nome={nomeConta}
            onSelect={(c, n) => { setCodigoConta(c); setNomeConta(n); }} placeholder="Escolha a conta…" /></div>
        <div><label style={labelStyleLote}>Data de emissão</label>
          <input type="date" style={selStyleLote} value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Data de vencimento</label>
          <input type="date" style={selStyleLote} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Competência</label>
          <input type="date" style={selStyleLote} value={dataCompetencia} onChange={(e) => setDataCompetencia(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Tipo de documento</label>
          <select style={selStyleLote} value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}>
            <option value="">—</option>
            {tipoDocumento && !tiposDocumento.includes(tipoDocumento) && <option value={tipoDocumento}>{tipoDocumento}</option>}
            {(tiposDocumento.length ? tiposDocumento : ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Classificação</label>
          {!novaClassificacaoAberta ? (
            <div className="flex items-center gap-2">
              <select style={selStyleLote} value={classificacao} onChange={(e) => setClassificacao(e.target.value)}>
                <option value="">—</option>
                {classificacao && !classificacoes.includes(classificacao) && <option value={classificacao}>{classificacao}</option>}
                {classificacoes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button type="button" className="btn-ghost" title="Cadastrar nova classificação" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setNovaClassificacaoAberta(true)}>
                <Plus size={13} /> Nova
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <input style={selStyleLote} value={novaClassificacaoNome} onChange={(e) => setNovaClassificacaoNome(e.target.value)} placeholder="ex.: Medicamentos" autoFocus />
              <button type="button" className="btn-primary" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} disabled={salvandoClassificacao || !novaClassificacaoNome.trim()} onClick={async () => {
                setSalvandoClassificacao(true);
                try {
                  await criarClassificacao({ nome: novaClassificacaoNome.trim() });
                  const nome = novaClassificacaoNome.trim();
                  setClassificacao(nome);
                  setClassificacoes((prev) => Array.from(new Set([...prev, nome])).sort());
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
        </div>
        <div><label style={labelStyleLote}>Nº do documento</label>
          <input style={selStyleLote} value={numeroNota} onChange={(e) => setNumeroNota(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Nº da OS/Orçamento</label>
          <input style={selStyleLote} value={numeroOsOrcamento} onChange={(e) => setNumeroOsOrcamento(e.target.value)} placeholder="ex.: OS-123 ou ORC-45" /></div>
        <div><label style={labelStyleLote}>Número do pagamento</label>
          <input style={selStyleLote} value={numeroPagamento} onChange={(e) => setNumeroPagamento(e.target.value)} placeholder="ex.: comprovante, nº do PIX…" /></div>
        <div><label style={labelStyleLote}>Vincular a patrimônio (entrada/saída de bem)</label>
          <select style={selStyleLote} value={patrimonioId} onChange={(e) => setPatrimonioId(e.target.value)}>
            <option value="">— Nenhum</option>
            {patrimonioId && !patrimonios.some((p) => String(p.id) === patrimonioId) && (
              <option value={patrimonioId}>Item vinculado (Nº {patrimonioId})</option>
            )}
            {patrimonios.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.tipo ? ` — ${p.tipo}` : ""}</option>)}
          </select></div>
      </div>
      {/* Sempre visível: antes o bloco inteiro sumia quando o lançamento não
          tinha `numero_lancamento` (todo lançamento importado da planilha),
          e não havia como anexar comprovante nesses. Agora o anexo é pelo id
          e o backend emite a numeração na primeira anexação. */}
      {(
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
          <label style={labelStyleLote}>Anexos</label>
          {/* Um lançamento pode reunir vários documentos diferentes (orçamento,
              pedido, nota fiscal, boleto, comprovante...) — cada um com sua
              própria categoria/número/data, achável depois na Central de
              Documentos mesmo sabendo só um desses dados. */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-2">
            <select style={selStyleLote} value={categoriaAnexo} onChange={(e) => setCategoriaAnexo(e.target.value)}>
              <option value="">Categoria do anexo…</option>
              {(tiposDocumento.length ? tiposDocumento : ["Nota fiscal", "Recibo", "Comprovante", "Fatura", "Orçamento", "Boleto", "Ordem de serviço", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
            </select>
            <input style={selStyleLote} placeholder="Número do documento" value={numeroDocAnexo} onChange={(e) => setNumeroDocAnexo(e.target.value)} />
            <input type="date" style={selStyleLote} title="Data deste documento" value={dataDocAnexo} onChange={(e) => setDataDocAnexo(e.target.value)} />
          </div>
          <Dropzone
            compact
            accept="application/pdf,image/jpeg,image/png"
            disabled={enviandoAnexo}
            label={enviandoAnexo ? "Enviando…" : "Arraste o comprovante/nota/boleto aqui, ou"}
            onFiles={(files) => enviarAnexo(files[0])}
          />
          {anexos === null ? (
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Carregando anexos…</p>
          ) : anexos.length === 0 ? (
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Nenhum anexo ainda.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {anexos.map((a) => (
                <li key={a.id} className="flex items-center gap-2" style={{ padding: "0.25rem 0", fontSize: "0.78rem" }}>
                  <a href={urlAnexoLancamento(a.id)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", flex: 1 }}
                    title="Abrir este documento numa aba nova">
                    {a.nome_arquivo}{a.categoria ? ` — ${a.categoria}` : ""}{a.numero_documento ? ` (${a.numero_documento})` : ""}
                  </a>
                  <button type="button" className="btn-ghost" title="Excluir anexo" onClick={() => removerAnexo(a.id)}><Trash2 size={13} /></button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2 justify-end">
        <button className="btn-ghost" onClick={onCancelar} disabled={salvando}>Cancelar</button>
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar alterações"}</button>
      </div>
      {abrirNovoFornecedor && (
        // zIndex explícito acima do Modal "Editar lançamento" que já envolve
        // este formulário (ambos nascem com o mesmo zIndex=90 padrão do
        // Modal.tsx, então sem isso a ordem de empilhamento dependia da
        // ordem de montagem no DOM e podia abrir "por baixo").
        <Modal title={`Novo ${tipoConta === "receita" ? "cliente" : "fornecedor"}`} onClose={() => setAbrirNovoFornecedor(false)} width="480px" zIndex={100}>
          <NovoFornecedorRapido
            tipoSugerido={tipoConta}
            onCriado={(f) => { if (f?.nome) setFornecedor(f.nome); setAbrirNovoFornecedor(false); }}
            onCancelar={() => setAbrirNovoFornecedor(false)}
          />
        </Modal>
      )}

      {adicionarNovoAberto && (
        <Modal title={`Adicionar ${modoAdicionarEdicao === "servico" ? "serviço" : "produto"} novo(a)`} onClose={() => setAdicionarNovoAberto(false)} width="700px" zIndex={100}>
          <div className="flex items-center gap-2 mb-3">
            <button type="button" onClick={() => setModoAdicionarEdicao("produto")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionarEdicao === "produto" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionarEdicao === "produto" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionarEdicao === "produto" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionarEdicao === "produto" ? 700 : 500 }}>
              Novo produto (estoque)
            </button>
            <button type="button" onClick={() => setModoAdicionarEdicao("servico")}
              style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
                border: "1px solid " + (modoAdicionarEdicao === "servico" ? "var(--dourado)" : "var(--border)"),
                background: modoAdicionarEdicao === "servico" ? "rgba(94,26,46,0.4)" : "transparent",
                color: modoAdicionarEdicao === "servico" ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modoAdicionarEdicao === "servico" ? 700 : 500 }}>
              Novo serviço
            </button>
          </div>
          {modoAdicionarEdicao === "produto" ? (
            <NovoItemEstoque
              onCriado={(item) => {
                if (item?.nome) { setTipoItem("produto"); setModoProduto("estoque"); setProduto(item.nome); }
                carregarEstoqueEdicao();
                setAdicionarNovoAberto(false);
              }}
              onCancelar={() => setAdicionarNovoAberto(false)}
            />
          ) : (
            <NovoServicoRapido
              onCriado={(servico) => {
                if (servico?.nome) { setTipoItem("servico"); setProduto(servico.nome); }
                carregarServicosEdicao();
                setAdicionarNovoAberto(false);
              }}
              onCancelar={() => setAdicionarNovoAberto(false)}
            />
          )}
        </Modal>
      )}

      {catalogarItem && (
        // Cadastro rápido pra um item específico da nota que veio sem
        // correspondência no catálogo (ex.: "TEATSEAL" lido de um XML/PDF) —
        // pré-preenchido com o nome já lançado. Depois de cadastrar, o item
        // da nota é EXPLICITAMENTE associado ao produto/serviço recém-criado
        // (PUT /financeiro/itens/{id}/vincular-produto) — não depende do
        // nome bater sozinho (o usuário pode ter ajustado o nome no cadastro).
        // Para produto, isso também dá entrada retroativa no estoque com a
        // quantidade já lançada nesta nota, se ainda não tiver dado entrada.
        <Modal title={`Cadastrar ${catalogarItem.tipo === "servico" ? "serviço" : "produto"} — ${catalogarItem.nome}`}
          onClose={() => setCatalogarItem(null)} width="700px" zIndex={100}>
          {catalogarItem.tipo === "servico" ? (
            <NovoServicoRapido
              prefillNome={catalogarItem.nome}
              onCriado={(servico) => {
                const id = catalogarItem.id;
                carregarServicosEdicao();
                setCatalogarItem(null);
                if (servico?.nome) vincularProduto(id, servico.nome);
              }}
              onCancelar={() => setCatalogarItem(null)}
            />
          ) : (
            <>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                A quantidade deste item já lançada nesta nota entra automaticamente como entrada de estoque ao cadastrar —
                deixe o &ldquo;saldo inicial&rdquo; abaixo em branco, a menos que a fazenda já tivesse estoque deste produto
                ANTES desta compra.
              </p>
              <NovoItemEstoque
                prefill={{ nome: catalogarItem.nome }}
                onCriado={(item) => {
                  const id = catalogarItem.id;
                  carregarEstoqueEdicao();
                  setCatalogarItem(null);
                  if (item?.nome) vincularProduto(id, item.nome);
                }}
                onCancelar={() => setCatalogarItem(null)}
              />
            </>
          )}
        </Modal>
      )}

      {associarItem && (
        // "Associar a produto/serviço já existente" — alternativa a
        // cadastrar novo, para quando o item da nota (ex.: nome vindo de
        // XML/OCR ligeiramente diferente) na verdade já corresponde a algo
        // do catálogo. Mesmo endpoint de vínculo do fluxo de cadastro acima.
        <Modal title={`Associar "${associarItem.nome}" a um ${associarItem.tipo === "servico" ? "serviço" : "produto"} já existente`}
          onClose={() => setAssociarItem(null)} width="600px" zIndex={100}>
          {associarItem.tipo === "servico" ? (
            <ServicoPicker servicos={sugestoesServicoEdicao.map((nome) => ({ nome }))}
              value="" onChange={(nomeEscolhido) => {
                if (!nomeEscolhido) return;
                const id = associarItem.id;
                setAssociarItem(null);
                vincularProduto(id, nomeEscolhido);
              }} />
          ) : (
            <EstoquePicker itens={produtosEstoqueEdicao} value="" todasFinalidades incluirNaoEstocaveis
              onChange={(nomeEscolhido) => {
                if (!nomeEscolhido) return;
                const id = associarItem.id;
                setAssociarItem(null);
                vincularProduto(id, nomeEscolhido);
              }} />
          )}
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
            Se for produto de estoque com quantidade já lançada nesta nota e ainda sem entrada registrada, a entrada é
            dada automaticamente ao associar.
          </p>
          <div className="flex justify-end mt-2">
            <button type="button" className="btn-ghost" onClick={() => setAssociarItem(null)}>Cancelar</button>
          </div>
        </Modal>
      )}
      {avisoAssociar && (
        <Modal title="Estoque atualizado" onClose={() => setAvisoAssociar(null)} width="480px" zIndex={110}>
          {avisoAssociar.length === 0 ? (
            <p style={{ fontSize: "0.85rem" }}>Produto/serviço associado a esta nota.</p>
          ) : (
            <ul style={{ fontSize: "0.82rem", paddingLeft: "1.1rem" }}>
              {avisoAssociar.map((a, i) => <li key={i} style={{ marginBottom: "0.3rem" }}>{a}</li>)}
            </ul>
          )}
          <div className="flex justify-end mt-2">
            <button type="button" className="btn-primary" onClick={() => setAvisoAssociar(null)}>Entendi</button>
          </div>
        </Modal>
      )}

      {editarItemEstoque && (
        <Modal title={`Editar cadastro — ${editarItemEstoque.nome}`} onClose={() => setEditarItemEstoque(null)} width="700px" zIndex={100}>
          <NovoItemEstoque
            editando={editarItemEstoque as any}
            onCriado={() => { carregarEstoqueEdicao(); setEditarItemEstoque(null); }}
            onCancelar={() => setEditarItemEstoque(null)}
          />
        </Modal>
      )}

      {valeModalItem && (
        <ValeItemModal apresentacao="modal"
          valorItem={valeModalItem.valor_total}
          dataItem={dataEmissao || dataCompetencia || ""}
          produtoItem={valeModalItem.produto}
          inicial={null}
          onConfirmar={(d) => marcarVale(valeModalItem, d)}
          onCancelar={() => setValeModalItem(null)} />
      )}

      {confirmarDesmarcar && (
        <Modal title="Excluir também o vale?" onClose={() => { setConfirmarDesmarcar(null); setDesmarcarErro(null); }} width="480px">
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            Este item gerou o vale de {confirmarDesmarcar.vale_pessoa_nome} no valor de {formatBRL(confirmarDesmarcar.valor_total)}.
            Ao desmarcar, o item volta a contar como despesa da fazenda nos relatórios. <strong>Excluir também o vale?</strong>
          </p>
          {desmarcarErro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.4rem" }}>{desmarcarErro}</p>}
          <div className="flex items-center gap-2 mt-3" style={{ flexWrap: "wrap" }}>
            <button className="btn-primary" disabled={desmarcando} onClick={() => desmarcarVale(confirmarDesmarcar, true)}>
              {desmarcando ? "Excluindo…" : "Sim, excluir o vale"}
            </button>
            <button className="btn-ghost" disabled={desmarcando} onClick={() => desmarcarVale(confirmarDesmarcar, false)}>
              Não, manter o vale
            </button>
            <button className="btn-ghost" disabled={desmarcando} onClick={() => { setConfirmarDesmarcar(null); setDesmarcarErro(null); }}>
              Cancelar
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function TabelaContas({ rel, itens, planoContas, onTratar, onEditar, onRecibo, onEstornado }: { rel: Rel; itens: Lanc[]; planoContas: ContaPlano[]; onTratar: (l: Lanc) => void; onEditar: (l: Lanc) => void; onRecibo: (l: Lanc) => void; onEstornado: () => void }) {
  const admin = ehAdmin();
  const emAberto = rel === "a_pagar" || rel === "a_receber";

  // G2 — reverte a baixa (o lançamento volta para "em aberto"); não exclui o
  // lançamento. Se a baixa criou parcela(s) para cobrir a diferença de valor
  // pago, a API responde 409 com as parcelas — pedimos confirmação numa
  // segunda etapa antes de apagá-las junto.
  const [estornando, setEstornando] = useState<number | null>(null);
  const [confirmarParcelas, setConfirmarParcelas] = useState<{ lanc: Lanc; mensagem: string; parcelas: any[] } | null>(null);
  const [erroEstorno, setErroEstorno] = useState<string | null>(null);

  const estornar = async (l: Lanc, confirmarParcelasDiferenca = false) => {
    if (!confirmarParcelasDiferenca) {
      if (!window.confirm("Estornar a baixa deste lançamento? Ele volta para contas a pagar/receber.")) return;
    }
    setEstornando(l.id); setErroEstorno(null);
    try {
      const r: EstornoLancamentoOut = await estornarPagamentoLancamento(l.id, { confirmar_parcelas_diferenca: confirmarParcelasDiferenca });
      setConfirmarParcelas(null);
      if (r.avisos?.length) window.alert(r.avisos.join("\n"));
      onEstornado();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.parcelas) {
        setConfirmarParcelas({ lanc: l, mensagem: e.detail.mensagem, parcelas: e.detail.parcelas });
      } else {
        setErroEstorno(e.message);
      }
    } finally {
      setEstornando(null);
    }
  };
  const hoje = new Date().toISOString().slice(0, 10);
  const rotuloContraparte = rel === "a_receber" || rel === "recebidas" ? "Cliente" : rel === "extrato" ? "Fornecedor/Cliente" : "Fornecedor";
  // Tipo desta aba (para a árvore de conta gerencial). Extrato mistura os dois.
  const tiposConta: ("despesa" | "receita")[] =
    rel === "a_receber" || rel === "recebidas" ? ["receita"]
    : rel === "extrato" ? ["despesa", "receita"] : ["despesa"];

  // Filtros próprios da lista (além do período/centro globais, já filtrados
  // pelo período único de Contas antes de chegar em `itens`): produto/serviço,
  // fornecedor/cliente, nº do documento, conta gerencial e tipo (extrato).
  // Todos client-side.
  const [fProduto, setFProduto] = useState("");
  const [fContraparte, setFContraparte] = useState("");
  const [fDocumento, setFDocumento] = useState("");
  const [fConta, setFConta] = useState("");
  const [fContaNome, setFContaNome] = useState("");
  const [fTipo, setFTipo] = useState<"" | "receita" | "despesa">("");

  const opcoesProdutoServico = useMemo(() => {
    const s = new Set<string>();
    itens.forEach((r) => (r.itens || []).forEach((it) => { if (it.produto) s.add(it.produto); }));
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [itens]);
  const opcoesContraparte = useMemo(() => {
    const s = new Set<string>();
    itens.forEach((r) => { if (r.fornecedor) s.add(r.fornecedor); });
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [itens]);

  const filtradosLocal = useMemo(() => itens.filter((r) =>
    (!fProduto || (r.itens || []).some((it) => it.produto === fProduto)) &&
    (!fContraparte || r.fornecedor === fContraparte) &&
    casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""}`, fDocumento) &&
    casaContaGerencial(r, fConta) &&
    (rel !== "extrato" || !fTipo || r.tipo === fTipo)
  ), [itens, fProduto, fContraparte, fDocumento, fConta, fTipo, rel]);

  const { ordenados, sortKey, sortDir, ordenar } = useOrdenacao(filtradosLocal, {
    numero: (r) => (r.numero_lancamento || "").toLowerCase(),
    data: (r) => (emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento)) || "",
    descricao: (r) => (r.descricao || "").toLowerCase(),
    fornecedor: (r) => (r.fornecedor || "").toLowerCase(),
    valor: (r) => r.valor,
    pago: (r) => r.valor_pago ?? 0,
  });
  const pagContas = usePaginacao(ordenados);

  // Somatórios refletem a lista já filtrada (o que está visível na tabela,
  // antes de paginar) — não devem cair para a soma só da página atual.
  const total = filtradosLocal.reduce((a, r) => a + r.valor, 0);
  const totalPago = filtradosLocal.reduce((a, r) => a + (r.valor_pago ?? 0), 0);
  const totalDesconto = filtradosLocal.reduce((a, r) => a + (r.desconto_acrescimo ?? 0), 0);

  return (
    <>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar a lista</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={labelStyleLote}>Nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={fDocumento} onChange={(e) => setFDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" />
            </div></div>
          <div><label style={labelStyleLote}>Produto / serviço</label>
            <select style={selStyleLote} value={fProduto} onChange={(e) => setFProduto(e.target.value)}>
              <option value="">Todos</option>{opcoesProdutoServico.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>{rotuloContraparte}</label>
            <select style={selStyleLote} value={fContraparte} onChange={(e) => setFContraparte(e.target.value)}>
              <option value="">Todos</option>{opcoesContraparte.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          {rel === "extrato" && (
            <div><label style={labelStyleLote}>Tipo</label>
              <select style={selStyleLote} value={fTipo} onChange={(e) => setFTipo(e.target.value as any)}>
                <option value="">Receitas e despesas</option><option value="receita">Só receitas</option><option value="despesa">Só despesas</option>
              </select></div>
          )}
          <div><label style={labelStyleLote}>Conta gerencial</label>
            <FiltroContaGerencial contas={planoContas} tipos={tiposConta}
              codigo={fConta} nome={fContaNome} onChange={(c, n) => { setFConta(c); setFContaNome(n); }} /></div>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <KPI v={String(filtradosLocal.length)} l="Lançamentos" />
        <KPI v={formatBRL(total)} l={emAberto ? "Valor em aberto" : "Valor total"} c={rel === "a_pagar" || rel === "pagas" ? "var(--red)" : rel === "extrato" ? undefined : "var(--green-light)"} />
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalPago)} l="Valor pago/recebido" c="var(--dourado-light)" />}
        {!emAberto && rel !== "extrato" && <KPI v={formatBRL(totalDesconto)} l="Desconto/acréscimo" c={totalDesconto <= 0 ? "var(--green-light)" : "var(--amber)"} />}
      </div>
      <div className="card">
        <div className="card-header mb-3 flex items-center justify-between">
          <span>Lançamentos</span>
          <ExportarBotoes titulo={CONTAS.find((c) => c.id === rel)?.label || "Lançamentos"} nomeArquivoBase={`financeiro_${rel}`}
            colunas={COLUNAS_LANCAMENTOS}
            linhas={ordenados.map((r) => ({ ...r, data: formatDate((emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento)) || ""), documento: `${r.tipo_documento ? `${r.tipo_documento} ` : ""}${r.numero_documento || ""}`, comprovante_txt: r.tem_comprovante ? "Sim" : "" }))} />
        </div>
        <div className="overflow-x-auto" style={{ maxHeight: "520px" }}>
          <table className="fazenda-table">
            <thead style={theadStickyStyle}>
              <tr>
                <ThOrd rotulo="Nº lanç." chave="numero" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
                <ThOrd rotulo={emAberto ? "Vencimento" : "Data"} chave="data" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
                <ThOrd rotulo="Descrição" chave="descricao" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
                <ThOrd rotulo="Fornecedor/Cliente" chave="fornecedor" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
                <ThOrd rotulo="Valor" chave="valor" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={{ ...theadStickyStyle, textAlign: "right" }} />
                {!emAberto && <ThOrd rotulo="Pago" chave="pago" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={{ ...theadStickyStyle, textAlign: "right" }} />}
                {!emAberto && <th style={theadStickyStyle}>Conta bancária</th>}
                {admin && <th style={{ ...theadStickyStyle, textAlign: "left" }}>Usuário</th>}
                <th style={{ ...theadStickyStyle, textAlign: "right" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {pagContas.linhasPagina.map((r) => {
                const vencido = emAberto && r.data_vencimento && r.data_vencimento < hoje;
                return (
                  <tr key={r.id}>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{r.numero_lancamento}{r.parcela_total && r.parcela_total > 1 ? ` (${r.parcela_num}/${r.parcela_total})` : ""}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem", color: vencido ? "var(--red)" : undefined, fontWeight: vencido ? 700 : undefined }}>
                      {formatDate((emAberto ? r.data_vencimento : (r.data_pagamento || r.data_vencimento)) || "")}{vencido ? " ⚠" : ""}
                    </td>
                    <td style={{ fontSize: "0.78rem" }}>
                      {r.descricao || "—"}
                      {(r.itens || []).some((it) => it.eh_vale) && (
                        <span title="Item lançado como vale — fora dos relatórios gerenciais"
                          style={{ marginLeft: "0.4rem", fontSize: "0.65rem", fontWeight: 700, color: "var(--dourado-light)",
                            border: "1px solid var(--dourado-light)", borderRadius: "999px", padding: "0.05rem 0.4rem" }}>
                          vale
                        </span>
                      )}
                      {/* Centro de custo e documento não são ordenáveis nem filtrados
                          por coluna própria (o filtro de documento já busca aqui
                          também) — viram apoio dentro da célula em vez de coluna
                          fixa, pra reduzir a rolagem horizontal em notebook. */}
                      {(r.centro_custo || r.tipo_documento || r.numero_documento) && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", marginTop: "0.25rem" }}>
                          {r.centro_custo && (
                            <span style={{ fontSize: "0.64rem", padding: "0.08rem 0.42rem", borderRadius: "999px", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                              {r.centro_custo}
                            </span>
                          )}
                          {(r.tipo_documento || r.numero_documento) && (
                            <span style={{ fontSize: "0.64rem", padding: "0.08rem 0.42rem", borderRadius: "999px", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                              {r.tipo_documento ? `${r.tipo_documento} ` : ""}{r.numero_documento || ""}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    {!emAberto && <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.valor_pago != null ? formatBRL(r.valor_pago) : "—"}</td>}
                    {!emAberto && <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{r.conta_bancaria || "—"}</td>}
                    {admin && <td>{r.usuario_nome ?? "—"}</td>}
                    <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                      <button className="btn-ghost" title="Editar este lançamento (valor, datas, fornecedor, conta…)" style={{ fontSize: "0.72rem" }} onClick={() => onEditar(r)}><Pencil size={12} /> Editar</button>
                      {emAberto && <button className="btn-ghost" title="Tratar a baixa desta nota (data, conta, forma e comprovante)" style={{ fontSize: "0.72rem", marginLeft: "0.3rem" }} onClick={() => onTratar(r)}>Tratar</button>}
                      {!emAberto && (
                        <button className="btn-ghost" title="Estornar a baixa — o lançamento volta para contas a pagar/receber"
                          style={{ fontSize: "0.72rem", marginLeft: "0.3rem" }} disabled={estornando === r.id} onClick={() => estornar(r)}>
                          <Undo2 size={12} /> Estornar
                        </button>
                      )}
                      <button className="btn-ghost" title="Emitir recibo deste lançamento (salvar PDF ou enviar por e-mail)" style={{ fontSize: "0.72rem", marginLeft: "0.3rem" }} onClick={() => onRecibo(r)}><Receipt size={12} /> Recibo</button>
                    </td>
                  </tr>
                );
              })}
              {!ordenados.length && <tr><td colSpan={admin ? 9 : 8} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum lançamento nesta aba.</td></tr>}
            </tbody>
          </table>
        </div>
        {ordenados.length > 0 && (
          <div style={{ padding: "0 0.9rem 0.6rem" }}>
            <Paginacao pagina={pagContas.pagina} totalPaginas={pagContas.totalPaginas} totalLinhas={pagContas.totalLinhas}
              tamanhoPagina={pagContas.tamanhoPagina} onMudarPagina={pagContas.setPagina} onMudarTamanho={pagContas.setTamanhoPagina} />
          </div>
        )}
      </div>

      {erroEstorno && (
        <div className="alert-critico mt-3"><AlertTriangle size={18} /><span>{erroEstorno}</span></div>
      )}

      {confirmarParcelas && (
        <Modal title="Estornar com parcelas de diferença" onClose={() => setConfirmarParcelas(null)} width="560px">
          <p style={{ fontSize: "0.85rem" }}>{confirmarParcelas.mensagem}</p>
          <div className="overflow-x-auto" style={{ maxHeight: "40vh", margin: "0.75rem 0" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Parcela</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor</th></tr></thead>
              <tbody>
                {confirmarParcelas.parcelas.map((p: any) => (
                  <tr key={p.id}>
                    <td style={{ fontSize: "0.8rem" }}>{p.parcela_num}/{p.parcela_total}</td>
                    <td style={{ fontSize: "0.8rem" }}>{formatDate(p.data_vencimento)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{formatBRL(p.valor_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setConfirmarParcelas(null)} disabled={estornando !== null}>Cancelar</button>
            <button className="btn-primary" onClick={() => estornar(confirmarParcelas.lanc, true)} disabled={estornando !== null}>
              Estornar e remover as parcelas
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

const LABEL_FORMA_PAGAMENTO: Record<string, string> = { pix: "Pix", transferencia: "Transferência", boleto: "Boleto", credito: "Crédito", debito: "Débito" };

// Divide a diferença entre valor pago e valor do lançamento em `qtd`
// parcelas mensais iguais (a última absorve o resto do arredondamento) —
// mesmo algoritmo de `dividirParcelas` em FormFinanceiro.tsx, para o botão
// "Parcelar a diferença" do pagamento.
function dividirDiferenca(valorTotal: number, qtd: number, primeiraData: string): { data_vencimento: string; valor: string }[] {
  if (qtd <= 0) return [];
  const base = Math.floor((valorTotal / qtd) * 100) / 100;
  const resto = Math.round((valorTotal - base * qtd) * 100) / 100;
  const inicio = primeiraData ? new Date(primeiraData + "T00:00:00") : new Date();
  return Array.from({ length: qtd }, (_, i) => {
    const d = new Date(inicio); d.setMonth(d.getMonth() + i + 1);
    const valor = i === qtd - 1 ? base + resto : base;
    return { data_vencimento: d.toISOString().slice(0, 10), valor: valor.toFixed(2) };
  });
}

/**
 * Pagamento (despesa) ou Recebimento (receita) individual — escolhe UMA nota
 * em aberto (fornecedor/cliente e produto por lista, nunca texto livre) e
 * trata a baixa dela: data, conta corrente, forma de pagamento (com débito)
 * e número do comprovante. Substitui a antiga baixa direto na lista de
 * Contas a pagar/receber — "Tratar" leva para cá em vez de abrir um modal.
 */
export function PagamentoIndividualView({ tipo, contasBancarias, notaAlvoRef, onNotaTratada, onFeito }: {
  tipo: "despesa" | "receita"; contasBancarias: string[]; notaAlvoRef: string | null;
  onNotaTratada?: () => void; onFeito?: () => void;
}) {
  const admin = ehAdmin();
  const [regs, setRegs] = useState<Lanc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opcoes, setOpcoes] = useState<{ fornecedores: string[]; produtos: string[] }>({ fornecedores: [], produtos: [] });
  const { nomes: nomesResponsaveis } = usePessoasAtivas();

  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [produto, setProduto] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [vencimentoDe, setVencimentoDe] = useState("");
  const [vencimentoAte, setVencimentoAte] = useState("");

  const [notaId, setNotaId] = useState<number | null>(null);
  const [dataPagamento, setDataPagamento] = useState(new Date().toISOString().slice(0, 10));
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [dataVencimentoCartao, setDataVencimentoCartao] = useState("");
  const [numeroDocPagamento, setNumeroDocPagamento] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const [anexarAberto, setAnexarAberto] = useState(false);
  const [arquivoPreview, setArquivoPreview] = useState<File | null>(null);
  // Diferença entre valor pago e valor do lançamento (item 4 do pedido do
  // usuário): em vez de sempre virar desconto/acréscimo, o usuário escolhe.
  const [modoDiferenca, setModoDiferenca] = useState<"desconto" | "parcelar">("desconto");
  const [qtdParcelasDiferenca, setQtdParcelasDiferenca] = useState(2);
  const [parcelasDiferenca, setParcelasDiferenca] = useState<{ data_vencimento: string; valor: string }[]>([]);
  // Comprovante de pagamento anexado à PRÓPRIA nota selecionada (não abre um
  // novo lançamento) — reaproveita o mesmo mecanismo de FormEditarLancamento.
  const [anexosPagamento, setAnexosPagamento] = useState<AnexoLancamento[] | null>(null);
  const [enviandoAnexoPagamento, setEnviandoAnexoPagamento] = useState(false);

  const carregar = () => fetchLancamentos().then((d) => setRegs(d.lancamentos)).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchOpcoesFinanceiro().then((d) => setOpcoes({ fornecedores: d.fornecedores || [], produtos: d.produtos || [] })).catch(() => {});
  }, []);

  const abertas = useMemo(() => (regs ?? []).filter((r) => r.tipo === tipo && !r.data_pagamento), [regs, tipo]);
  const centrosCusto = useMemo(() => Array.from(new Set(abertas.map((r) => r.centro_custo).filter(Boolean))).sort(), [abertas]);
  // "Produto / serviço": produtos das opções + nomes lançados nas notas (produto
  // e serviço compartilham o campo `produto` do item), para achar serviços também.
  const opcoesProdutoServico = useMemo(() => {
    const s = new Set<string>(opcoes.produtos);
    (regs ?? []).forEach((r) => (r.itens || []).forEach((it) => { if (it.produto) s.add(it.produto); }));
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [opcoes.produtos, regs]);

  const filtradas = useMemo(() => abertas.filter((r) =>
    casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""}`, numeroDocumento) &&
    (!fornecedor || r.fornecedor === fornecedor) &&
    (!produto || (r.itens || []).some((it) => it.produto === produto)) &&
    (!centroCusto || r.centro_custo === centroCusto) &&
    (!vencimentoDe || (r.data_vencimento || "") >= vencimentoDe) && (!vencimentoAte || (r.data_vencimento || "") <= vencimentoAte)
  ), [abertas, numeroDocumento, fornecedor, produto, centroCusto, vencimentoDe, vencimentoAte]);
  const totalFiltrado = useMemo(() => filtradas.reduce((a, r) => a + r.valor, 0), [filtradas]);

  // Ordenação clicável sobre o resultado JÁ filtrado.
  const { ordenados, sortKey, sortDir, ordenar } = useOrdenacao(filtradas, {
    numero: (r) => (r.numero_documento || r.numero_lancamento || "").toLowerCase(),
    vencimento: (r) => r.data_vencimento || "",
    fornecedor: (r) => (r.fornecedor || "").toLowerCase(),
    produto: (r) => (r.itens || []).map((it) => it.produto).join(", ").toLowerCase(),
    valor: (r) => r.valor,
  });
  const pagNotas = usePaginacao(ordenados);

  function selecionar(nota: Lanc) {
    setNotaId(nota.id);
    setValorPago(String(nota.valor));
    setDataPagamento(new Date().toISOString().slice(0, 10));
    setContaBancaria(""); setFormaPagamento(""); setDataVencimentoCartao(""); setNumeroDocPagamento("");
    setModoDiferenca("desconto"); setQtdParcelasDiferenca(2); setParcelasDiferenca([]);
    setAnexosPagamento(null);
    setMsg(null);
  }

  // Chega da lista de Contas a pagar/receber ou da Agenda com uma nota específica já em mente.
  useEffect(() => {
    if (!notaAlvoRef || !regs) return;
    const alvo = abertas.find((r) => (r.numero_lancamento || r.numero_documento) === notaAlvoRef);
    if (alvo) selecionar(alvo);
    onNotaTratada?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaAlvoRef, regs]);

  const notaSelecionada = useMemo(() => abertas.find((r) => r.id === notaId) || null, [abertas, notaId]);
  const diferenca = notaSelecionada ? Math.round((Number(valorPago) - notaSelecionada.valor) * 100) / 100 : 0;
  const somaParcelasDiferenca = useMemo(() => parcelasDiferenca.reduce((a, p) => a + (Number(p.valor) || 0), 0), [parcelasDiferenca]);
  const parcelasDiferencaBatem = Math.round((somaParcelasDiferenca - Math.abs(diferenca)) * 100) / 100 === 0;

  // Carrega os anexos já existentes desta nota (comprovante, boleto, nota
  // fiscal…) assim que ela é selecionada para pagamento.
  useEffect(() => {
    if (!notaSelecionada) { setAnexosPagamento([]); return; }
    listarAnexosLancamentoPorId(notaSelecionada.id).then(setAnexosPagamento).catch(() => setAnexosPagamento([]));
  }, [notaSelecionada?.id]);

  // Regenera a divisão da diferença (igual, mês a mês) ao ligar "parcelar"
  // ou mudar a quantidade — não depende do valor da diferença em si para não
  // apagar edições manuais do usuário a cada tecla digitada em "valor pago"
  // (mesmo padrão de `dividirParcelas` em FormFinanceiro.tsx).
  useEffect(() => {
    if (modoDiferenca !== "parcelar") { setParcelasDiferenca([]); return; }
    setParcelasDiferenca(dividirDiferenca(Math.abs(diferenca), qtdParcelasDiferenca, dataPagamento));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modoDiferenca, qtdParcelasDiferenca, notaId]);

  async function enviarAnexoPagamento(file: File) {
    if (!notaSelecionada) return;
    setEnviandoAnexoPagamento(true); setMsg(null);
    try {
      const novo = await anexarArquivoLancamentoPorId(notaSelecionada.id, file, null);
      setAnexosPagamento((p) => [...(p || []), novo]);
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao anexar arquivo" });
    } finally {
      setEnviandoAnexoPagamento(false);
    }
  }

  async function removerAnexoPagamento(id: number) {
    try {
      await excluirAnexoLancamento(id);
      setAnexosPagamento((p) => (p || []).filter((a) => a.id !== id));
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao remover anexo" });
    }
  }

  async function confirmar() {
    if (!notaSelecionada) return;
    if (formaPagamento === "credito" && !dataVencimentoCartao) { setMsg({ tipo: "erro", texto: "Informe a data de vencimento do cartão." }); return; }
    if (diferenca !== 0 && modoDiferenca === "parcelar" && !parcelasDiferencaBatem) {
      setMsg({ tipo: "erro", texto: "A soma das parcelas precisa bater com a diferença a parcelar." });
      return;
    }
    setSalvando(true); setMsg(null);
    try {
      await marcarPagoFinanceiro(notaSelecionada.id, {
        data_pagamento: dataPagamento, valor_pago: Number(valorPago) || 0,
        conta_bancaria: contaBancaria || undefined, numero_documento_pagamento: numeroDocPagamento || undefined,
        forma_pagamento: formaPagamento || undefined, data_vencimento_cartao: formaPagamento === "credito" ? dataVencimentoCartao : undefined,
        parcelas_diferenca: diferenca !== 0 && modoDiferenca === "parcelar"
          ? parcelasDiferenca.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 }))
          : undefined,
      });
      setMsg({ tipo: "sucesso", texto: `${tipo === "receita" ? "Recebimento" : "Pagamento"} registrado com sucesso.` });
      setNotaId(null);
      carregar();
      onFeito?.();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao tratar a nota" });
    } finally {
      setSalvando(false);
    }
  }

  if (error) return <div className="alert-critico"><span>Sem dados: {error}.</span></div>;
  if (!regs) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  return (
    <div>
      <AvisoSalvo texto={msg?.tipo === "sucesso" ? msg.texto : null} />
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Filtrar notas em aberto</span>
          <button className="btn-ghost" title="Abre um lançamento NOVO a partir de um documento (nota fiscal, boleto ou recibo) — leitura automática, não anexa a nenhuma nota já existente" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Lançar por nota fiscal, boleto ou recibo…
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={labelStyleLote}>Nota fiscal / nº do documento</label>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" />
            </div></div>
          <div><label style={labelStyleLote}>{tipo === "receita" ? "Cliente" : "Fornecedor"}</label>
            <select style={selStyleLote} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Todos</option>{opcoes.fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Produto / serviço</label>
            <select style={selStyleLote} value={produto} onChange={(e) => setProduto(e.target.value)}>
              <option value="">Todos</option>{opcoesProdutoServico.map((p) => <option key={p} value={p}>{p}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>{centrosCusto.map((c) => <option key={c} value={c}>{c}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Vencimento — de</label><input type="date" style={selStyleLote} value={vencimentoDe} onChange={(e) => setVencimentoDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Vencimento — até</label><input type="date" style={selStyleLote} value={vencimentoAte} onChange={(e) => setVencimentoAte(e.target.value)} /></div>
        </div>
      </div>

      {anexarAberto && (
        <ModalDivididoDocumento title={`Novo lançamento — leitura automática (${tipo === "receita" ? "recebimento" : "pagamento"})`}
          onClose={() => { setAnexarAberto(false); setArquivoPreview(null); }} arquivo={arquivoPreview}>
          <FormFinanceiro tipo={tipo} responsaveis={nomesResponsaveis}
            onArquivoParaLeitura={setArquivoPreview}
            onSalvo={(mensagem) => { setAnexarAberto(false); setArquivoPreview(null); setMsg({ tipo: "sucesso", texto: mensagem }); carregar(); }} />
        </ModalDivididoDocumento>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden", marginBottom: "1rem" }}>
        <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem" }}>
          <span style={{ fontSize: "0.85rem" }}>{filtradas.length} nota(s) em aberto no filtro — total {formatBRL(totalFiltrado)}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead style={theadStickyStyle}><tr>
              <ThOrd rotulo="Nota / lançamento" chave="numero" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Vencimento" chave="vencimento" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo={tipo === "receita" ? "Cliente" : "Fornecedor"} chave="fornecedor" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Produto/Serviços" chave="produto" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={theadStickyStyle} />
              <ThOrd rotulo="Valor" chave="valor" sortKey={sortKey} sortDir={sortDir} onSort={ordenar} style={{ ...theadStickyStyle, textAlign: "right" }} />
              {admin && <th style={{ ...theadStickyStyle, textAlign: "left" }}>Usuário</th>}
              <th style={theadStickyStyle}></th>
            </tr></thead>
            <tbody>
              {pagNotas.linhasPagina.map((r) => {
                const produtos = (r.itens || []).map((it) => it.produto).filter(Boolean).join(", ");
                const ativa = r.id === notaId;
                return (
                  <tr key={r.id} className="row-clickable" title="Clique para selecionar esta nota" style={{ background: ativa ? "rgba(94,26,46,0.35)" : undefined }} onClick={() => selecionar(r)}>
                    <td style={{ fontSize: "0.78rem" }}>
                      <strong>{r.numero_documento || r.numero_lancamento || "—"}</strong>
                      {r.numero_documento && r.numero_lancamento && <span style={{ color: "var(--text-muted)" }}> · {r.numero_lancamento}</span>}
                      <br /><span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{r.descricao}</span>
                    </td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", maxWidth: "220px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{produtos || "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600, color: r.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{formatBRL(r.valor)}</td>
                    {admin && <td>{r.usuario_nome ?? "—"}</td>}
                    <td>{ativa ? <CheckCircle2 size={14} style={{ color: "var(--dourado-light)" }} /> : <Circle size={14} style={{ color: "var(--text-muted)", opacity: 0.4 }} />}</td>
                  </tr>
                );
              })}
              {!filtradas.length && <tr><td colSpan={admin ? 7 : 6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma nota em aberto no filtro.</td></tr>}
            </tbody>
          </table>
        </div>
        {filtradas.length > 0 && (
          <div style={{ padding: "0 0.9rem 0.6rem" }}>
            <Paginacao pagina={pagNotas.pagina} totalPaginas={pagNotas.totalPaginas} totalLinhas={pagNotas.totalLinhas}
              tamanhoPagina={pagNotas.tamanhoPagina} onMudarPagina={pagNotas.setPagina} onMudarTamanho={pagNotas.setTamanhoPagina} />
          </div>
        )}
      </div>
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {notaSelecionada ? (
        <div className="card">
          <div className="card-header mb-3">
            Tratar {tipo === "receita" ? "recebimento" : "pagamento"} — {notaSelecionada.descricao} · {formatBRL(notaSelecionada.valor)}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><label style={labelStyleLote}>Data de {tipo === "receita" ? "recebimento" : "pagamento"}</label>
              <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Valor {tipo === "receita" ? "recebido" : "pago"} (R$)</label>
              <CampoMoeda style={selStyleLote} value={Number(valorPago) || 0} onChange={(v) => setValorPago(v ? String(v) : "")} /></div>
            <div><label style={labelStyleLote}>Conta corrente</label>
              <select style={selStyleLote} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                <option value="">Selecione…</option>{contasBancarias.map((c) => <option key={c}>{c}</option>)}
              </select></div>
            <div><label style={labelStyleLote}>Forma</label>
              <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
                <option value="">Selecione…</option>{Object.entries(LABEL_FORMA_PAGAMENTO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            {formaPagamento === "credito" ? (
              <div><label style={labelStyleLote}>Vencimento do cartão</label>
                <input type="date" style={selStyleLote} value={dataVencimentoCartao} onChange={(e) => setDataVencimentoCartao(e.target.value)} /></div>
            ) : (
              <div><label style={labelStyleLote}>Nº do comprovante</label>
                <input style={selStyleLote} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
            )}
            {formaPagamento === "credito" && (
              <div><label style={labelStyleLote}>Nº do comprovante</label>
                <input style={selStyleLote} value={numeroDocPagamento} onChange={(e) => setNumeroDocPagamento(e.target.value)} /></div>
            )}
          </div>
          {diferenca !== 0 && (
            <div style={{ marginTop: "0.7rem", padding: "0.7rem 0.8rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
              <p style={{ fontSize: "0.78rem", margin: "0 0 0.5rem", color: diferenca < 0 ? "var(--green-light)" : "var(--amber)" }}>
                {diferenca < 0 ? `Desconto de ${formatBRL(Math.abs(diferenca))}` : `Acréscimo de ${formatBRL(diferenca)}`} em relação ao valor do lançamento. O que fazer com a diferença?
              </p>
              <div className="flex items-center gap-4" style={{ flexWrap: "wrap" }}>
                <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                  <input type="radio" checked={modoDiferenca === "desconto"} onChange={() => setModoDiferenca("desconto")} />
                  Lançar {diferenca < 0 ? "desconto" : "acréscimo"}
                </label>
                <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                  <input type="radio" checked={modoDiferenca === "parcelar"} onChange={() => setModoDiferenca("parcelar")} />
                  Parcelar a diferença de {formatBRL(Math.abs(diferenca))}
                </label>
              </div>
              {modoDiferenca === "parcelar" && (
                <div style={{ marginTop: "0.7rem" }}>
                  <div className="flex items-center gap-2 mb-2">
                    <label style={labelStyleLote}>Em quantas parcelas?</label>
                    <input type="number" min={1} max={36} style={{ ...selStyleLote, width: "5rem" }}
                      value={qtdParcelasDiferenca} onChange={(e) => setQtdParcelasDiferenca(Math.max(1, Number(e.target.value) || 1))} />
                  </div>
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor (R$)</th></tr></thead>
                    <tbody>
                      {parcelasDiferenca.map((p, i) => (
                        <tr key={i}>
                          <td><input type="date" style={selStyleLote} value={p.data_vencimento}
                            onChange={(e) => setParcelasDiferenca((arr) => arr.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} /></td>
                          <td><CampoMoeda style={{ ...selStyleLote, textAlign: "right" }} value={Number(p.valor) || 0}
                            onChange={(v) => setParcelasDiferenca((arr) => arr.map((x, j) => j === i ? { ...x, valor: v ? String(v) : "" } : x))} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p style={{ fontSize: "0.74rem", marginTop: "0.4rem", color: parcelasDiferencaBatem ? "var(--text-muted)" : "var(--red)" }}>
                    Soma das parcelas: {formatBRL(somaParcelasDiferenca)} {parcelasDiferencaBatem ? "" : `(precisa bater com ${formatBRL(Math.abs(diferenca))})`}
                  </p>
                </div>
              )}
            </div>
          )}

          <div style={{ marginTop: "0.9rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
            <label style={labelStyleLote}>Comprovante de pagamento (opcional)</label>
            <Dropzone
              compact
              accept="application/pdf,image/jpeg,image/png"
              disabled={enviandoAnexoPagamento}
              label={enviandoAnexoPagamento ? "Enviando…" : "Arraste o comprovante aqui, ou"}
              onFiles={(files) => enviarAnexoPagamento(files[0])}
            />
            {/* Documentos já anexados a ESTE lançamento (boleto, nota fiscal,
                orçamento...), não só comprovantes de pagamento — clicáveis,
                pra abrir o boleto e ler código de barras/QR code sem precisar
                lembrar onde ele foi guardado, com o lançamento ainda aberto
                aqui na tela enquanto paga. */}
            {anexosPagamento && anexosPagamento.length > 0 && (
              <ul style={{ listStyle: "none", padding: 0, margin: "0.5rem 0 0" }}>
                {anexosPagamento.map((a) => (
                  <li key={a.id} className="flex items-center justify-between" style={{ fontSize: "0.78rem", padding: "0.2rem 0" }}>
                    <a href={urlAnexoLancamento(a.id)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)" }}>
                      {a.nome_arquivo}{a.categoria ? ` (${a.categoria}${a.numero_documento ? ` ${a.numero_documento}` : ""})` : ""}
                    </a>
                    <button className="btn-ghost" title="Remover anexo" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => removerAnexoPagamento(a.id)}>
                      <Trash2 size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Sucesso vai pro aviso persistente no topo (AvisoSalvo) — este
              painel inteiro some no mesmo clique que confirma (setNotaId(null)
              zera notaSelecionada), então um sucesso mostrado aqui dentro
              nunca chegaria a ser visto. */}
          {msg?.tipo === "erro" && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: "0.6rem" }}>{msg.texto}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary" title="Registrar a baixa desta nota" onClick={confirmar}
              disabled={salvando || (diferenca !== 0 && modoDiferenca === "parcelar" && !parcelasDiferencaBatem)}>
              <Check size={14} /> {salvando ? "Salvando…" : "Confirmar baixa"}
            </button>
            <button className="btn-ghost" title="Cancelar e voltar à seleção de nota" onClick={() => setNotaId(null)}>Cancelar</button>
          </div>
        </div>
      ) : (
        <div className="card" style={{ textAlign: "center", padding: "2.4rem 1rem" }}>
          <Circle size={22} style={{ color: "var(--text-muted)", margin: "0 auto 0.6rem" }} />
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione uma nota à esquerda para tratar {tipo === "receita" ? "o recebimento" : "o pagamento"}.</p>
        </div>
      )}
      </div>
      </div>
    </div>
  );
}

/*
 * RMCA (Receita Menos Custo com Alimentação) — duas versões lado a lado, por
 * decisão explícita do usuário: "gerencial" (contas do plano de contas
 * marcadas em Configurações > Parâmetros financeiros) e "físico" (consumo
 * real registrado pela Alimentação × valor unitário do Estoque).
 */
type ItemFisicoRmca = { ingrediente: string; quantidade: number; valor_unitario: number; custo: number };
type RmcaResp = {
  periodo: { inicio: string; fim: string };
  configurado: boolean;
  contas_receita: string[];
  contas_custo: string[];
  gerencial: { receita_leite: number; custo_alimentacao: number; rmca: number };
  fisico: { receita_leite: number; custo_alimentacao: number; rmca: number; itens: ItemFisicoRmca[] };
  meta_rmca: number;
};

function primeiroDiaDoMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
}

/* ───────────────────────── Roteiro do RMCA (modal em tela, mesmo padrão do manual de colostro/sangue) ───────────────────────── */
const ROTEIRO_RMCA = [
  { t: "1. O que é o RMCA", d: "Receita Menos Custo com Alimentação: quanto sobra da receita do leite depois de descontar o gasto com ração/alimentação no mesmo período. Duas versões lado a lado — gerencial e físico — para conferência cruzada." },
  { t: "2. Versão gerencial — marque as contas", d: "Vá em Configurações → Parâmetros financeiros → Conta gerencial. Marque a(s) conta(s) de receita que representam a venda do leite (ex.: \"Leite indústria\") e a(s) conta(s) de despesa que representam alimentação (ex.: \"Ração\", \"Silagem\", \"Sal mineral\"). O RMCA gerencial soma os lançamentos financeiros dessas contas no período." },
  { t: "3. Versão física — indique os produtos", d: "Vá em Configurações → Cadastro → Estoque → Itens de Estoque. Na coluna RMCA, marque quais produtos são ração/alimento e devem entrar no custo físico. Desmarque produtos que não são alimentação (medicamentos, materiais etc.), mesmo que também tenham baixa de \"Saída de ajuste\"." },
  { t: "4. Como o custo físico é calculado", d: "Para cada produto marcado, o sistema soma a quantidade baixada como \"Saída de ajuste\" pela Alimentação no período e multiplica pelo valor unitário cadastrado no Estoque. O card \"RMCA físico\" mostra o detalhamento produto a produto." },
  { t: "5. Por que duas versões", d: "A gerencial reflete o que foi de fato lançado no financeiro (pode incluir sobras de estoque, compras antecipadas). A física reflete o consumo real no período, ainda que o pagamento tenha sido em outro mês. Comparar as duas ajuda a identificar diferenças de timing." },
];

function RoteiroRmcaModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "560px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Roteiro — Como indicar os produtos do RMCA</div>
          <button onClick={onClose} title="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {ROTEIRO_RMCA.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--dourado-light)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RmcaView() {
  const [dataInicio, setDataInicio] = useState(() => primeiroDiaDoMes());
  const [dataFim, setDataFim] = useState(() => new Date().toISOString().slice(0, 10));
  const [dados, setDados] = useState<RmcaResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [roteiroAberto, setRoteiroAberto] = useState(false);

  useEffect(() => { fetchRmca(dataInicio, dataFim).then(setDados).catch((e) => setErro(e.message)); }, [dataInicio, dataFim]);

  return (
    <div>
      {roteiroAberto && <RoteiroRmcaModal onClose={() => setRoteiroAberto(false)} />}

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center justify-between">
          <span className="flex items-center gap-2"><Filter size={14} /> Período</span>
          <button className="btn-ghost" title="Abrir o passo a passo de configuração do RMCA" style={{ fontSize: "0.75rem" }} onClick={() => setRoteiroAberto(true)}>
            <BookOpen size={13} /> Roteiro — como indicar os produtos do RMCA
          </button>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Início</label><input type="date" style={selStyleLote} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Fim</label><input type="date" style={selStyleLote} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {!dados.configurado && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Nenhuma conta gerencial está marcada como receita do leite ou custo de alimentação — a versão gerencial fica zerada até a configuração ser feita.
                Marque em <strong>Configurações → Parâmetros financeiros → Conta gerencial</strong>.
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-header mb-3">RMCA gerencial</div>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                A partir dos lançamentos financeiros, pelas contas marcadas como receita do leite / custo de alimentação.
              </p>
              <div className="grid grid-cols-1 gap-3 mb-3">
                <KPI v={formatBRL(dados.gerencial.receita_leite)} l="Receita do leite" c="var(--green-light)" />
                <KPI v={formatBRL(dados.gerencial.custo_alimentacao)} l="Custo de alimentação" c="var(--red)" />
                <KPI v={formatBRL(dados.gerencial.rmca)} l="RMCA" c={dados.gerencial.rmca >= dados.meta_rmca ? "var(--green-light)" : "var(--amber)"} />
              </div>
              {dados.contas_receita.length > 0 && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Receita: {dados.contas_receita.join(", ")}</p>}
              {dados.contas_custo.length > 0 && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Custo: {dados.contas_custo.join(", ")}</p>}
            </div>
            <div className="card">
              <div className="card-header mb-3">RMCA físico</div>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Mesma receita do leite, mas custo a partir do consumo real registrado pela Alimentação × valor unitário do Estoque.
              </p>
              <div className="grid grid-cols-1 gap-3 mb-3">
                <KPI v={formatBRL(dados.fisico.receita_leite)} l="Receita do leite" c="var(--green-light)" />
                <KPI v={formatBRL(dados.fisico.custo_alimentacao)} l="Custo de alimentação (físico)" c="var(--red)" />
                <KPI v={formatBRL(dados.fisico.rmca)} l="RMCA" c={dados.fisico.rmca >= dados.meta_rmca ? "var(--green-light)" : "var(--amber)"} />
              </div>
              {dados.fisico.itens.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th>Ingrediente</th><th style={{ textAlign: "right" }}>Consumo</th><th style={{ textAlign: "right" }}>Vlr. unit.</th><th style={{ textAlign: "right" }}>Custo</th></tr></thead>
                    <tbody>
                      {dados.fisico.itens.map((it) => (
                        <tr key={it.ingrediente}>
                          <td style={{ fontSize: "0.78rem" }}>{it.ingrediente}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{it.quantidade}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(it.valor_unitario)}</td>
                          <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(it.custo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {!dados.fisico.itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem consumo registrado pela Alimentação no período.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

type CustoLitroLeiteResp = {
  periodo: { inicio: string; fim: string }; configurado: boolean; tem_entrega: boolean;
  contas_custo: string[]; litros: number; custo_total: number; custo_por_litro: number | null;
};

function CustoLitroLeiteView() {
  const [dataInicio, setDataInicio] = useState(() => primeiroDiaDoMes());
  const [dataFim, setDataFim] = useState(() => new Date().toISOString().slice(0, 10));
  const [dados, setDados] = useState<CustoLitroLeiteResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchCustoLitroLeite(dataInicio, dataFim).then(setDados).catch((e) => setErro(e.message)); }, [dataInicio, dataFim]);

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Período</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Início</label><input type="date" style={selStyleLote} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Fim</label><input type="date" style={selStyleLote} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {!dados.configurado && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Nenhuma conta gerencial está marcada como custo de alimentação — o custo fica zerado até a configuração ser feita.
                Marque em <strong>Configurações → Parâmetros financeiros → Conta gerencial</strong>.
              </p>
            </div>
          )}
          {!dados.tem_entrega && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Nenhuma entrega mensal de leite cadastrada — sem litros no período, o custo por litro fica indefinido.
                Lance em <strong>Lançamentos → Produção → Venda mensal do leite</strong>.
              </p>
            </div>
          )}
          <div className="card">
            <div className="card-header mb-3">Custo por litro de leite</div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Custo de alimentação do período (mesmas contas marcadas para o RMCA) dividido pelos litros de leite entregues
              no período (Venda mensal do leite), projetados proporcionalmente por dia quando o período não cobre o mês inteiro.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <KPI v={formatBRL(dados.custo_total)} l="Custo de alimentação" c="var(--red)" />
              <KPI v={`${dados.litros.toLocaleString("pt-BR")} L`} l="Litros entregues" c="var(--dourado-light)" />
              <KPI v={dados.custo_por_litro != null ? formatBRL(dados.custo_por_litro) : "—"} l="Custo por litro" c="var(--green-light)" />
            </div>
            {dados.contas_custo.length > 0 && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Custo: {dados.contas_custo.join(", ")}</p>}
          </div>
        </>
      )}
    </div>
  );
}

type CustoHectareResp = {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; area_configurada: boolean;
  area_hectares: number | null; despesas_total: number; custo_por_hectare: number | null;
};

function CustoHectareView() {
  const [dataInicio, setDataInicio] = useState(() => primeiroDiaDoMes());
  const [dataFim, setDataFim] = useState(() => new Date().toISOString().slice(0, 10));
  const [centroCusto, setCentroCusto] = useState("");
  const [centros, setCentros] = useState<string[]>([]);
  const [dados, setDados] = useState<CustoHectareResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchCentrosCusto().then((d) => setCentros(d.filter((c: any) => c.ativo).map((c: any) => c.nome))).catch(() => {}); }, []);
  useEffect(() => {
    fetchCustoHectare(dataInicio, dataFim, centroCusto || undefined).then(setDados).catch((e) => setErro(e.message));
  }, [dataInicio, dataFim, centroCusto]);

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Período</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Início</label><input type="date" style={selStyleLote} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Fim</label><input type="date" style={selStyleLote} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}
            </select></div>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {!dados.area_configurada && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Área total da fazenda ainda não foi cadastrada — o custo por hectare fica indefinido até a configuração ser feita.
                Cadastre em <strong>Configurações → Parâmetros → Estrutura da fazenda</strong>.
              </p>
            </div>
          )}
          <div className="card">
            <div className="card-header mb-3">Custo por hectare</div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Despesas do período (ContaGerencial, por competência{dados.centro_custo ? `, centro de custo "${dados.centro_custo}"` : ""})
              dividido pela área total da fazenda em hectares.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <KPI v={formatBRL(dados.despesas_total)} l="Despesas do período" c="var(--red)" />
              <KPI v={dados.area_hectares != null ? `${dados.area_hectares.toLocaleString("pt-BR")} ha` : "—"} l="Área total" c="var(--dourado-light)" />
              <KPI v={dados.custo_por_hectare != null ? formatBRL(dados.custo_por_hectare) : "—"} l="Custo por hectare" c="var(--green-light)" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

type CustoVacaLoteResp = {
  periodo: { inicio: string; fim: string }; centro_custo: string | null; tem_vacas_no_periodo: boolean;
  num_vacas: number; despesas_total: number; custo_por_vaca: number | null;
  por_lote: { lote: string; num_vacas: number; custo_alocado: number; custo_por_vaca: number }[];
};

function CustoVacaLoteView() {
  const [dataInicio, setDataInicio] = useState(() => primeiroDiaDoMes());
  const [dataFim, setDataFim] = useState(() => new Date().toISOString().slice(0, 10));
  const [centroCusto, setCentroCusto] = useState("");
  const [centros, setCentros] = useState<string[]>([]);
  const [dados, setDados] = useState<CustoVacaLoteResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchCentrosCusto().then((d) => setCentros(d.filter((c: any) => c.ativo).map((c: any) => c.nome))).catch(() => {}); }, []);
  useEffect(() => {
    fetchCustoVacaLote(dataInicio, dataFim, centroCusto || undefined).then(setDados).catch((e) => setErro(e.message));
  }, [dataInicio, dataFim, centroCusto]);

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Período</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Início</label><input type="date" style={selStyleLote} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Fim</label><input type="date" style={selStyleLote} value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}
            </select></div>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {!dados.tem_vacas_no_periodo && (
            <div className="card mb-4" style={{ borderColor: "var(--amber)" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--amber)" }}>
                Nenhuma vaca com Controle leiteiro lançado no período — o custo por vaca fica indefinido.
                Lance em <strong>Lançamentos → Produção → Controle leiteiro</strong>.
              </p>
            </div>
          )}
          <div className="card mb-4">
            <div className="card-header mb-3">Custo por vaca</div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Despesas do período (ContaGerencial, por competência{dados.centro_custo ? `, centro de custo "${dados.centro_custo}"` : ""})
              dividido pelo número de vacas com ao menos um Controle leiteiro lançado no período.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <KPI v={formatBRL(dados.despesas_total)} l="Despesas do período" c="var(--red)" />
              <KPI v={String(dados.num_vacas)} l="Vacas em lactação" c="var(--dourado-light)" />
              <KPI v={dados.custo_por_vaca != null ? formatBRL(dados.custo_por_vaca) : "—"} l="Custo por vaca" c="var(--green-light)" />
            </div>
          </div>
          {dados.por_lote.length > 0 && (
            <div className="card">
              <div className="card-header mb-3">Custo por lote</div>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Rateio proporcional ao número de vacas de cada lote sobre o total — não há vínculo direto
                entre lançamento financeiro e lote/animal, então cada lote recebe sua fatia do custo total
                pelo peso de cabeças.
              </p>
              <table className="w-full" style={{ fontSize: "0.82rem" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                    <th style={{ padding: "0.3rem 0.5rem" }}>Lote</th>
                    <th style={{ padding: "0.3rem 0.5rem" }}>Vacas</th>
                    <th style={{ padding: "0.3rem 0.5rem" }}>Custo alocado</th>
                    <th style={{ padding: "0.3rem 0.5rem" }}>Custo por vaca</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_lote.map((l) => (
                    <tr key={l.lote} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "0.3rem 0.5rem" }}>{l.lote}</td>
                      <td style={{ padding: "0.3rem 0.5rem" }}>{l.num_vacas}</td>
                      <td style={{ padding: "0.3rem 0.5rem" }}>{formatBRL(l.custo_alocado)}</td>
                      <td style={{ padding: "0.3rem 0.5rem" }}>{formatBRL(l.custo_por_vaca)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

type SafraOpcao = { id: number; nome: string; centro_custo: string; hectares: number; toneladas_produzidas: number; ativo: boolean };
type CustoSafraResp = {
  safra: SafraOpcao & { data_inicio: string; data_fim: string; observacao: string | null };
  por_categoria: { codigo: string; descricao: string; valor: number }[];
  despesas_total: number; hectares: number | null; toneladas_produzidas: number | null;
  custo_por_hectare: number | null; custo_por_tonelada: number | null;
};

// Opção A do plano de custo agrícola (silagem): em vez de período/centro de
// custo livres como os relatórios acima, aqui o usuário escolhe a Safra já
// cadastrada (Configurações > Cadastro > Safra) — ela já traz o centro de
// custo e o período embutidos.
function CustoSafraView() {
  const [safras, setSafras] = useState<SafraOpcao[]>([]);
  const [safraId, setSafraId] = useState<number | "">("");
  const [dados, setDados] = useState<CustoSafraResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchSafras().then((lista: SafraOpcao[]) => {
      setSafras(lista);
      const primeira = lista.find((s) => s.ativo) ?? lista[0];
      if (primeira) setSafraId(primeira.id);
    }).catch((e) => setErro(e.message));
  }, []);

  useEffect(() => {
    if (safraId === "") return;
    setDados(null);
    fetchCustoSafra(Number(safraId)).then(setDados).catch((e) => setErro(e.message));
  }, [safraId]);

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Safra</div>
        {!safras.length && !erro && (
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            Nenhuma safra cadastrada ainda. Cadastre em <strong>Configurações → Cadastro → Safra</strong>
            (nome, centro de custo, período, hectares e toneladas produzidas).
          </p>
        )}
        {!!safras.length && (
          <select style={selStyleLote} value={safraId} onChange={(e) => setSafraId(Number(e.target.value))}>
            {safras.map((s) => <option key={s.id} value={s.id}>{s.nome}{!s.ativo ? " (inativa)" : ""}</option>)}
          </select>
        )}
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}

      {dados && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3">Custo por safra — {dados.safra.nome}</div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Despesas lançadas no centro de custo "{dados.safra.centro_custo}" entre{" "}
              {dados.safra.data_inicio.split("-").reverse().join("/")} e {dados.safra.data_fim.split("-").reverse().join("/")},
              divididas pelos {dados.hectares?.toLocaleString("pt-BR")} ha e {dados.toneladas_produzidas?.toLocaleString("pt-BR")} ton cadastrados na safra.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
              <KPI v={formatBRL(dados.despesas_total)} l="Despesas do período" c="var(--red)" />
              <KPI v={dados.hectares != null ? `${dados.hectares.toLocaleString("pt-BR")} ha` : "—"} l="Hectares" c="var(--dourado-light)" />
              <KPI v={dados.custo_por_hectare != null ? formatBRL(dados.custo_por_hectare) : "—"} l="Custo por hectare" c="var(--green-light)" />
              <KPI v={dados.custo_por_tonelada != null ? formatBRL(dados.custo_por_tonelada) : "—"} l="Custo por tonelada" c="var(--green-light)" />
            </div>
          </div>

          {dados.por_categoria.length > 0 && (
            <div className="card">
              <div className="card-header mb-3">Quebra por categoria</div>
              <div className="overflow-x-auto">
                <table className="w-full" style={{ fontSize: "0.82rem" }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                      <th style={{ padding: "0.3rem 0.5rem" }}>Categoria</th>
                      <th style={{ padding: "0.3rem 0.5rem", textAlign: "right" }}>Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dados.por_categoria.map((cat) => (
                      <tr key={cat.codigo} style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "0.3rem 0.5rem" }}>{cat.codigo} — {cat.descricao || "Sem descrição"}</td>
                        <td style={{ padding: "0.3rem 0.5rem", textAlign: "right" }}>{formatBRL(cat.valor)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Planejamento > Orçamento
// ─────────────────────────────────────────────────────────────────────────
type OrcamentoItemRow = OrcamentoItemPayload & { id: number; nome_conta_gerencial: string };
type ComparativoLinha = { codigo_conta_gerencial: string; nome_conta_gerencial: string; tipo: string; orcado: number; realizado: number; desvio: number; desvio_pct: number | null };

const MESES_NOMES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

function OrcamentoView({ planoContas, fornecedores }: { planoContas: ContaPlano[]; fornecedores: string[] }) {
  const anoAtual = new Date().getFullYear();
  const [ano, setAno] = useState(anoAtual);
  const [centros, setCentros] = useState<string[]>([]);
  const [itens, setItens] = useState<OrcamentoItemRow[] | null>(null);
  const [comparativo, setComparativo] = useState<{ linhas: ComparativoLinha[]; total_orcado: number; total_realizado: number } | null>(null);
  const [mesInicio, setMesInicio] = useState(1);
  const [mesFim, setMesFim] = useState(12);
  const [centroFiltro, setCentroFiltro] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState<OrcamentoItemRow | "novo" | null>(null);
  const [importando, setImportando] = useState<OrcamentoItemRow | null>(null);

  const recarregar = () => fetchOrcamento(ano).then(setItens).catch((e) => setErro(e.message));
  useEffect(() => { recarregar(); }, [ano]);
  useEffect(() => { fetchCentrosCusto().then((d) => setCentros(d.filter((c: any) => c.ativo).map((c: any) => c.nome))).catch(() => {}); }, []);
  useEffect(() => {
    fetchComparativoOrcado({ ano, mes_inicio: mesInicio, mes_fim: mesFim, centro_custo: centroFiltro || undefined })
      .then(setComparativo).catch((e) => setErro(e.message));
  }, [ano, mesInicio, mesFim, centroFiltro, itens]);

  async function excluir(id: number) {
    if (!confirm("Excluir este item de orçamento?")) return;
    await excluirItemOrcamento(id);
    recarregar();
  }

  const { ordenados: comparativoOrdenado, sortKey: sortKeyComparativo, sortDir: sortDirComparativo, ordenar: ordenarComparativo } = useOrdenacao(comparativo?.linhas ?? [], {
    conta: (l) => (l.nome_conta_gerencial || "").toLowerCase(),
    tipo: (l) => l.tipo,
    orcado: (l) => l.orcado,
    realizado: (l) => l.realizado,
    desvio: (l) => l.desvio,
    desvioPct: (l) => l.desvio_pct ?? 0,
  });
  const { ordenados: itensOrdenados, sortKey: sortKeyItensOrc, sortDir: sortDirItensOrc, ordenar: ordenarItensOrc } = useOrdenacao(itens ?? [], {
    mes: (i) => i.mes,
    conta: (i) => (i.nome_conta_gerencial || "").toLowerCase(),
    centro_custo: (i) => (i.centro_custo || "").toLowerCase(),
    tipo: (i) => i.tipo,
    valor_orcado: (i) => i.valor_orcado,
  });

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Target size={14} /> Orçamento — {ano}</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Planilha orçamentária por conta gerencial/centro de custo/mês (mesmo padrão de ERPs como TOTVS Protheus),
          comparada automaticamente ao realizado lançado em Financeiro.
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <div><label style={labelStyleLote}>Ano</label>
            <input type="number" style={{ ...selStyleLote, width: "6rem" }} value={ano} onChange={(e) => setAno(Number(e.target.value) || anoAtual)} /></div>
          <div><label style={labelStyleLote}>Mês inicial</label>
            <select style={selStyleLote} value={mesInicio} onChange={(e) => setMesInicio(Number(e.target.value))}>
              {MESES_NOMES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Mês final</label>
            <select style={selStyleLote} value={mesFim} onChange={(e) => setMesFim(Number(e.target.value))}>
              {MESES_NOMES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Centro de custo</label>
            <select style={selStyleLote} value={centroFiltro} onChange={(e) => setCentroFiltro(e.target.value)}>
              <option value="">Todos</option>{centros.map((c) => <option key={c}>{c}</option>)}
            </select></div>
          <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem" }} onClick={() => setEditando("novo")}>
            <Plus size={14} /> Novo item de orçamento
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}

      {comparativo && (
        <div className="card mb-4">
          <div className="card-header mb-3">Orçado × Realizado</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <KPI v={formatBRL(comparativo.total_orcado)} l="Total orçado" c="var(--dourado-light)" />
            <KPI v={formatBRL(comparativo.total_realizado)} l="Total realizado" />
            <KPI v={formatBRL(comparativo.total_realizado - comparativo.total_orcado)} l="Desvio" c={comparativo.total_realizado - comparativo.total_orcado <= 0 ? "var(--green-light)" : "var(--red)"} />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr>
                <ThOrd rotulo="Conta gerencial" chave="conta" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} />
                <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} />
                <ThOrd rotulo="Orçado" chave="orcado" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Realizado" chave="realizado" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Desvio" chave="desvio" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} style={{ textAlign: "right" }} />
                <ThOrd rotulo="Desvio %" chave="desvioPct" sortKey={sortKeyComparativo} sortDir={sortDirComparativo} onSort={ordenarComparativo} style={{ textAlign: "right" }} />
              </tr></thead>
              <tbody>
                {comparativoOrdenado.map((l) => (
                  <tr key={l.codigo_conta_gerencial}>
                    <td style={{ fontSize: "0.82rem" }}>{l.nome_conta_gerencial}</td>
                    <td style={{ fontSize: "0.78rem", color: l.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{l.tipo === "receita" ? "Receita" : "Despesa"}</td>
                    <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{formatBRL(l.orcado)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{formatBRL(l.realizado)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.82rem", color: (l.tipo === "despesa" ? l.desvio > 0 : l.desvio < 0) ? "var(--red)" : "var(--green-light)" }}>{formatBRL(l.desvio)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.desvio_pct != null ? `${l.desvio_pct}%` : "—"}</td>
                  </tr>
                ))}
                {!comparativoOrdenado.length && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhum item de orçamento cadastrado neste período.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header mb-3">Itens de orçamento — {ano}</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrd rotulo="Mês" chave="mes" sortKey={sortKeyItensOrc} sortDir={sortDirItensOrc} onSort={ordenarItensOrc} />
              <ThOrd rotulo="Conta gerencial" chave="conta" sortKey={sortKeyItensOrc} sortDir={sortDirItensOrc} onSort={ordenarItensOrc} />
              <ThOrd rotulo="Centro de custo" chave="centro_custo" sortKey={sortKeyItensOrc} sortDir={sortDirItensOrc} onSort={ordenarItensOrc} />
              <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeyItensOrc} sortDir={sortDirItensOrc} onSort={ordenarItensOrc} />
              <ThOrd rotulo="Valor orçado" chave="valor_orcado" sortKey={sortKeyItensOrc} sortDir={sortDirItensOrc} onSort={ordenarItensOrc} style={{ textAlign: "right" }} />
              <th></th>
            </tr></thead>
            <tbody>
              {itensOrdenados.map((i) => (
                <tr key={i.id}>
                  <td style={{ fontSize: "0.82rem" }}>{MESES_NOMES[i.mes - 1]}</td>
                  <td style={{ fontSize: "0.82rem" }}>{i.nome_conta_gerencial}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{i.centro_custo || "—"}</td>
                  <td style={{ fontSize: "0.78rem", color: i.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{i.tipo === "receita" ? "Receita" : "Despesa"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.82rem", fontWeight: 600 }}>{formatBRL(i.valor_orcado)}</td>
                  <td style={{ display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                    <button title="Importar para Pedido" onClick={() => setImportando(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--dourado-light)" }}><ShoppingCart size={15} /></button>
                    <button title="Editar" onClick={() => setEditando(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><Pencil size={14} /></button>
                    <button title="Excluir" onClick={() => excluir(i.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              ))}
              {itens && !itens.length && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhum item de orçamento cadastrado em {ano}.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {editando && (
        <Modal onClose={() => setEditando(null)} title={editando === "novo" ? "Novo item de orçamento" : "Editar item de orçamento"}>
          <FormItemOrcamento planoContas={planoContas} centros={centros} anoDefault={ano}
            item={editando === "novo" ? null : editando}
            onSalvo={() => { setEditando(null); recarregar(); }} onCancelar={() => setEditando(null)} />
        </Modal>
      )}
      {importando && (
        <Modal onClose={() => setImportando(null)} title="Importar para Pedido">
          <FormImportarPedido origemTipo="orcamento" origemItemId={importando.id}
            valorEstimado={importando.valor_orcado} nomeItem={importando.nome_conta_gerencial}
            fornecedores={fornecedores}
            onSalvo={() => setImportando(null)} onCancelar={() => setImportando(null)} />
        </Modal>
      )}
    </div>
  );
}

function FormItemOrcamento({ planoContas, centros, anoDefault, item, onSalvo, onCancelar }: {
  planoContas: ContaPlano[]; centros: string[]; anoDefault: number; item: OrcamentoItemRow | null;
  onSalvo: () => void; onCancelar: () => void;
}) {
  const [ano, setAno] = useState(item?.ano ?? anoDefault);
  const [mes, setMes] = useState(item?.mes ?? new Date().getMonth() + 1);
  const [tipo, setTipo] = useState<"receita" | "despesa">((item?.tipo as any) ?? "despesa");
  const [codigo, setCodigo] = useState(item?.codigo_conta_gerencial ?? "");
  const [nome, setNome] = useState(item?.nome_conta_gerencial ?? "");
  const [centro, setCentro] = useState(item?.centro_custo ?? "");
  const [valor, setValor] = useState(item?.valor_orcado ?? 0);
  const [observacao, setObservacao] = useState(item?.observacao ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    if (!codigo || !valor) { setErro("Informe a conta gerencial e o valor orçado."); return; }
    setSalvando(true); setErro(null);
    const dados: OrcamentoItemPayload = { ano, mes, codigo_conta_gerencial: codigo, centro_custo: centro || null, tipo, valor_orcado: valor, observacao: observacao || null };
    try {
      if (item) await atualizarItemOrcamento(item.id, dados); else await criarItemOrcamento(dados);
      onSalvo();
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyleLote}>Ano</label><input type="number" style={{ ...selStyleLote, width: "6rem" }} value={ano} onChange={(e) => setAno(Number(e.target.value))} /></div>
        <div><label style={labelStyleLote}>Mês</label>
          <select style={selStyleLote} value={mes} onChange={(e) => setMes(Number(e.target.value))}>
            {MESES_NOMES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Tipo</label>
          <select style={selStyleLote} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setCodigo(""); setNome(""); }}>
            <option value="despesa">Despesa</option><option value="receita">Receita</option>
          </select></div>
      </div>
      <div>
        <label style={labelStyleLote}>Conta gerencial</label>
        <SeletorContaGerencial contas={planoContas} tipo={tipo} codigo={codigo} nome={nome} onSelect={(c, n) => { setCodigo(c); setNome(n); }} />
      </div>
      <div>
        <label style={labelStyleLote}>Centro de custo (opcional)</label>
        <select style={{ ...selStyleLote, width: "100%" }} value={centro} onChange={(e) => setCentro(e.target.value)}>
          <option value="">— Nenhum —</option>{centros.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div><label style={labelStyleLote}>Valor orçado</label><CampoMoeda style={{ ...selStyleLote, width: "100%" }} value={valor} onChange={setValor} /></div>
      <div><label style={labelStyleLote}>Observação (opcional)</label><input style={{ ...selStyleLote, width: "100%" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </div>
  );
}

// Formulário compartilhado (Orçamento e Planejamento financeiro) para criar um
// Pedido-rascunho a partir de uma linha — só copia dados, não lança nada em
// Estoque/Financeiro; o pedido em si fica pendente até ser vinculado depois.
function FormImportarPedido({ origemTipo, origemItemId, valorEstimado, nomeItem, fornecedores, onSalvo, onCancelar }: {
  origemTipo: "orcamento" | "planejamento_financeiro"; origemItemId: number; valorEstimado: number; nomeItem: string;
  fornecedores: string[]; onSalvo: () => void; onCancelar: () => void;
}) {
  const [tipoPedido, setTipoPedido] = useState<"compra" | "venda">("compra");
  const [fornecedorCliente, setFornecedorCliente] = useState("");
  const [dataPedido, setDataPedido] = useState(() => new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{ numero_pedido: string } | null>(null);
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  const tipoContaPedido = tipoPedido === "venda" ? "receita" : "despesa";
  const fornecedoresDisponiveis = useMemo(
    () => Array.from(new Set([...(fornecedorCliente ? [fornecedorCliente] : []), ...fornecedores])).sort(),
    [fornecedores, fornecedorCliente]
  );

  async function salvar() {
    setSalvando(true); setErro(null);
    try {
      const r = await importarParaPedido({ origem_tipo: origemTipo, origem_item_id: origemItemId, tipo_pedido: tipoPedido, fornecedor_cliente: fornecedorCliente || null, data_pedido: dataPedido });
      setResultado(r);
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  if (resultado) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <p style={{ fontSize: "0.85rem" }}>Pedido <strong>{resultado.numero_pedido}</strong> criado a partir de <strong>{nomeItem}</strong> ({formatBRL(valorEstimado)}).</p>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Ele fica em Pedidos como rascunho — só reflete em Estoque/Financeiro quando uma nota fiscal/recibo ou uma entrada de estoque for vinculada a ele.</p>
        <div className="flex gap-2 justify-end">
          <a href="/pedidos" className="btn-primary" style={{ textDecoration: "none" }}>Ver em Pedidos</a>
          <button className="btn-secondary" onClick={onSalvo}>Fechar</button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
        Cria um pedido-rascunho a partir de <strong>{nomeItem}</strong> ({formatBRL(valorEstimado)}). Não lança nada em Estoque/Financeiro agora.
      </p>
      <div><label style={labelStyleLote}>Tipo do pedido</label>
        <select style={{ ...selStyleLote, width: "100%" }} value={tipoPedido} onChange={(e) => setTipoPedido(e.target.value as any)}>
          <option value="compra">Compra</option><option value="venda">Venda</option>
        </select></div>
      <div><label style={labelStyleLote}>Fornecedor/Cliente (opcional)</label>
        <div className="flex items-center gap-2">
          <select style={{ ...selStyleLote, width: "100%" }} value={fornecedorCliente} onChange={(e) => setFornecedorCliente(e.target.value)}>
            <option value="">Selecione…</option>
            {fornecedoresDisponiveis.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <button type="button" className="btn-ghost" title={`Cadastrar novo ${tipoContaPedido === "receita" ? "cliente" : "fornecedor"}`} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoFornecedor(true)}>
            <Plus size={13} /> Novo
          </button>
        </div>
      </div>
      <div><label style={labelStyleLote}>Data do pedido</label><input type="date" style={{ ...selStyleLote, width: "100%" }} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></div>
      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Criando…" : "Criar pedido"}</button>
      </div>
      {abrirNovoFornecedor && (
        <Modal title={`Novo ${tipoContaPedido === "receita" ? "cliente" : "fornecedor"}`} onClose={() => setAbrirNovoFornecedor(false)} width="480px">
          <NovoFornecedorRapido
            tipoSugerido={tipoContaPedido}
            onCriado={(f) => { if (f?.nome) setFornecedorCliente(f.nome); setAbrirNovoFornecedor(false); }}
            onCancelar={() => setAbrirNovoFornecedor(false)}
          />
        </Modal>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Planejamento > Planejamento financeiro (cenários)
// ─────────────────────────────────────────────────────────────────────────
type CenarioRow = CenarioPayload & { id: number; ativo: boolean; criado_em: string };
type PlanejamentoItemRow = PlanejamentoItemPayload & { id: number; nome_conta_gerencial: string };
const TIPOS_CENARIO = [
  { id: "otimista", label: "Otimista", cor: "var(--green-light)" },
  { id: "realista", label: "Realista", cor: "var(--dourado-light)" },
  { id: "pessimista", label: "Pessimista", cor: "var(--red)" },
  { id: "personalizado", label: "Personalizado", cor: "var(--text-muted)" },
] as const;

function PlanejamentoFinanceiroView({ planoContas, fornecedores }: { planoContas: ContaPlano[]; fornecedores: string[] }) {
  const [cenarios, setCenarios] = useState<CenarioRow[] | null>(null);
  const [centros, setCentros] = useState<string[]>([]);
  const [cenarioAtivo, setCenarioAtivo] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [editandoCenario, setEditandoCenario] = useState<CenarioRow | "novo" | null>(null);

  const recarregarCenarios = () => fetchCenarios().then((d) => {
    setCenarios(d);
    if (!cenarioAtivo && d.length) setCenarioAtivo(d[0].id);
  }).catch((e) => setErro(e.message));
  useEffect(() => { recarregarCenarios(); }, []);
  useEffect(() => { fetchCentrosCusto().then((d) => setCentros(d.filter((c: any) => c.ativo).map((c: any) => c.nome))).catch(() => {}); }, []);

  async function excluirCenarioAtual(id: number) {
    if (!confirm("Excluir este cenário e todas as suas linhas?")) return;
    await excluirCenario(id);
    if (cenarioAtivo === id) setCenarioAtivo(null);
    recarregarCenarios();
  }

  return (
    <div>
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><TrendingUp size={14} /> Planejamento financeiro — cenários</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Simule situações "e se" — cenários otimista/realista/pessimista com receitas e despesas previstas mês a mês,
          projetando um fluxo de caixa futuro (rolling forecast), sem afetar Financeiro/Estoque.
        </p>
        <div className="flex flex-wrap gap-2 items-center">
          {(cenarios ?? []).map((c) => {
            const t = TIPOS_CENARIO.find((x) => x.id === c.tipo);
            return (
              <button key={c.id} onClick={() => setCenarioAtivo(c.id)}
                style={{
                  display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem",
                  padding: "0.35rem 0.7rem", borderRadius: "999px", border: "1px solid var(--border)", cursor: "pointer",
                  background: cenarioAtivo === c.id ? "var(--pill-active-bg)" : "var(--surface-2)",
                  color: cenarioAtivo === c.id ? "var(--pill-active-fg)" : "var(--text)",
                }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: t?.cor || "var(--text-muted)" }} />
                {c.nome}
              </button>
            );
          })}
          <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem" }} onClick={() => setEditandoCenario("novo")}>
            <Plus size={14} /> Novo cenário
          </button>
        </div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}
      {cenarios && !cenarios.length && <div className="card" style={{ textAlign: "center", padding: "2rem" }}><p style={{ color: "var(--text-muted)" }}>Nenhum cenário cadastrado ainda.</p></div>}

      {cenarioAtivo && (
        <CenarioDetalheView
          cenario={(cenarios ?? []).find((c) => c.id === cenarioAtivo)!}
          planoContas={planoContas} centros={centros} fornecedores={fornecedores}
          onEditarCenario={() => setEditandoCenario((cenarios ?? []).find((c) => c.id === cenarioAtivo)!)}
          onExcluirCenario={() => excluirCenarioAtual(cenarioAtivo)}
        />
      )}

      {editandoCenario && (
        <Modal onClose={() => setEditandoCenario(null)} title={editandoCenario === "novo" ? "Novo cenário" : "Editar cenário"}>
          <FormCenario item={editandoCenario === "novo" ? null : editandoCenario}
            onSalvo={(id) => { setEditandoCenario(null); recarregarCenarios(); if (id) setCenarioAtivo(id); }}
            onCancelar={() => setEditandoCenario(null)} />
        </Modal>
      )}
    </div>
  );
}

function FormCenario({ item, onSalvo, onCancelar }: { item: CenarioRow | null; onSalvo: (id?: number) => void; onCancelar: () => void }) {
  const [nome, setNome] = useState(item?.nome ?? "");
  const [tipo, setTipo] = useState<CenarioPayload["tipo"]>(item?.tipo ?? "realista");
  const [observacao, setObservacao] = useState(item?.observacao ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    if (!nome.trim()) { setErro("Informe o nome do cenário."); return; }
    setSalvando(true); setErro(null);
    try {
      const dados: CenarioPayload = { nome, tipo, observacao: observacao || null };
      const r = item ? await atualizarCenario(item.id, dados) : await criarCenario(dados);
      onSalvo(r.id);
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div><label style={labelStyleLote}>Nome do cenário</label><input style={{ ...selStyleLote, width: "100%" }} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Expansão do rebanho 2027" /></div>
      <div><label style={labelStyleLote}>Tipo</label>
        <select style={{ ...selStyleLote, width: "100%" }} value={tipo} onChange={(e) => setTipo(e.target.value as any)}>
          {TIPOS_CENARIO.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select></div>
      <div><label style={labelStyleLote}>Observação (opcional)</label><input style={{ ...selStyleLote, width: "100%" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </div>
  );
}

function CenarioDetalheView({ cenario, planoContas, centros, fornecedores, onEditarCenario, onExcluirCenario }: {
  cenario: CenarioRow; planoContas: ContaPlano[]; centros: string[]; fornecedores: string[]; onEditarCenario: () => void; onExcluirCenario: () => void;
}) {
  const [itens, setItens] = useState<PlanejamentoItemRow[] | null>(null);
  const [projecao, setProjecao] = useState<{ meses: { mes: string; receitas: number; despesas: number; saldo: number; acumulado: number }[] } | null>(null);
  const [editando, setEditando] = useState<PlanejamentoItemRow | "novo" | null>(null);
  const [importando, setImportando] = useState<PlanejamentoItemRow | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const recarregar = () => {
    fetchItensCenario(cenario.id).then(setItens).catch((e) => setErro(e.message));
    fetchProjecaoCenario(cenario.id).then(setProjecao).catch(() => {});
  };
  useEffect(() => { recarregar(); }, [cenario.id]);

  async function excluir(id: number) {
    if (!confirm("Excluir esta linha do cenário?")) return;
    await excluirItemCenario(id);
    recarregar();
  }

  // "Mês" ordena pelo próprio mes_competencia ("AAAA-MM") — já é uma string
  // que ordena cronologicamente sozinha, sem precisar de índice à parte.
  const { ordenados: itensCenarioOrdenados, sortKey: sortKeyItensCen, sortDir: sortDirItensCen, ordenar: ordenarItensCen } = useOrdenacao(itens ?? [], {
    mes: (i) => i.mes_competencia || "",
    conta: (i) => (i.nome_conta_gerencial || "").toLowerCase(),
    centro_custo: (i) => (i.centro_custo || "").toLowerCase(),
    tipo: (i) => i.tipo,
    valor_previsto: (i) => i.valor_previsto,
  });

  return (
    <>
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{cenario.nome}</div>
          <div className="flex gap-2">
            <button title="Editar cenário" onClick={onEditarCenario} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><Pencil size={14} /></button>
            <button title="Excluir cenário" onClick={onExcluirCenario} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={14} /></button>
          </div>
        </div>
        {cenario.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>{cenario.observacao}</p>}

        {projecao && projecao.meses.length > 0 && (
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={projecao.meses}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="mes" tickFormatter={mesCompLabel} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={48} />
              <Tooltip formatter={(v: any) => formatBRL(Number(v))} labelFormatter={(m: any) => mesCompLabel(m as string)} contentStyle={tip} />
              <Legend wrapperStyle={{ fontSize: "0.75rem" }} />
              <Bar dataKey="receitas" name="Receitas previstas" fill="var(--green-light)" radius={[2, 2, 0, 0]} />
              <Bar dataKey="despesas" name="Despesas previstas" fill="var(--red)" radius={[2, 2, 0, 0]} />
              <Line type="monotone" dataKey="acumulado" name="Saldo acumulado" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        {projecao && !projecao.meses.length && <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhuma linha prevista neste cenário ainda.</p>}
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Linhas previstas</div>
          <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem" }} onClick={() => setEditando("novo")}>
            <Plus size={14} /> Nova linha
          </button>
        </div>
        {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrd rotulo="Mês" chave="mes" sortKey={sortKeyItensCen} sortDir={sortDirItensCen} onSort={ordenarItensCen} />
              <ThOrd rotulo="Conta gerencial" chave="conta" sortKey={sortKeyItensCen} sortDir={sortDirItensCen} onSort={ordenarItensCen} />
              <ThOrd rotulo="Centro de custo" chave="centro_custo" sortKey={sortKeyItensCen} sortDir={sortDirItensCen} onSort={ordenarItensCen} />
              <ThOrd rotulo="Tipo" chave="tipo" sortKey={sortKeyItensCen} sortDir={sortDirItensCen} onSort={ordenarItensCen} />
              <ThOrd rotulo="Valor previsto" chave="valor_previsto" sortKey={sortKeyItensCen} sortDir={sortDirItensCen} onSort={ordenarItensCen} style={{ textAlign: "right" }} />
              <th></th>
            </tr></thead>
            <tbody>
              {itensCenarioOrdenados.map((i) => (
                <tr key={i.id}>
                  <td style={{ fontSize: "0.82rem" }}>{mesCompLabel(i.mes_competencia)}</td>
                  <td style={{ fontSize: "0.82rem" }}>{i.nome_conta_gerencial}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{i.centro_custo || "—"}</td>
                  <td style={{ fontSize: "0.78rem", color: i.tipo === "receita" ? "var(--green-light)" : "var(--red)" }}>{i.tipo === "receita" ? "Receita" : "Despesa"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.82rem", fontWeight: 600 }}>{formatBRL(i.valor_previsto)}</td>
                  <td style={{ display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                    <button title="Importar para Pedido" onClick={() => setImportando(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--dourado-light)" }}><ShoppingCart size={15} /></button>
                    <button title="Editar" onClick={() => setEditando(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><Pencil size={14} /></button>
                    <button title="Excluir" onClick={() => excluir(i.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              ))}
              {itens && !itens.length && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma linha prevista neste cenário.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {editando && (
        <Modal onClose={() => setEditando(null)} title={editando === "novo" ? "Nova linha prevista" : "Editar linha prevista"}>
          <FormItemCenario planoContas={planoContas} centros={centros} cenarioId={cenario.id}
            item={editando === "novo" ? null : editando}
            onSalvo={() => { setEditando(null); recarregar(); }} onCancelar={() => setEditando(null)} />
        </Modal>
      )}
      {importando && (
        <Modal onClose={() => setImportando(null)} title="Importar para Pedido">
          <FormImportarPedido origemTipo="planejamento_financeiro" origemItemId={importando.id}
            valorEstimado={importando.valor_previsto} nomeItem={importando.nome_conta_gerencial}
            fornecedores={fornecedores}
            onSalvo={() => setImportando(null)} onCancelar={() => setImportando(null)} />
        </Modal>
      )}
    </>
  );
}

function FormItemCenario({ planoContas, centros, cenarioId, item, onSalvo, onCancelar }: {
  planoContas: ContaPlano[]; centros: string[]; cenarioId: number; item: PlanejamentoItemRow | null;
  onSalvo: () => void; onCancelar: () => void;
}) {
  const [mesCompetencia, setMesCompetencia] = useState(item?.mes_competencia ?? new Date().toISOString().slice(0, 7));
  const [tipo, setTipo] = useState<"receita" | "despesa">((item?.tipo as any) ?? "despesa");
  const [codigo, setCodigo] = useState(item?.codigo_conta_gerencial ?? "");
  const [nome, setNome] = useState(item?.nome_conta_gerencial ?? "");
  const [centro, setCentro] = useState(item?.centro_custo ?? "");
  const [valor, setValor] = useState(item?.valor_previsto ?? 0);
  const [observacao, setObservacao] = useState(item?.observacao ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    if (!codigo || !valor) { setErro("Informe a conta gerencial e o valor previsto."); return; }
    setSalvando(true); setErro(null);
    const dados: PlanejamentoItemPayload = { mes_competencia: mesCompetencia, codigo_conta_gerencial: codigo, centro_custo: centro || null, tipo, valor_previsto: valor, observacao: observacao || null };
    try {
      if (item) await atualizarItemCenario(item.id, dados); else await criarItemCenario(cenarioId, dados);
      onSalvo();
    } catch (e: any) { setErro(e.message); } finally { setSalvando(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyleLote}>Mês de competência</label><input type="month" style={selStyleLote} value={mesCompetencia} onChange={(e) => setMesCompetencia(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Tipo</label>
          <select style={selStyleLote} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setCodigo(""); setNome(""); }}>
            <option value="despesa">Despesa</option><option value="receita">Receita</option>
          </select></div>
      </div>
      <div>
        <label style={labelStyleLote}>Conta gerencial</label>
        <SeletorContaGerencial contas={planoContas} tipo={tipo} codigo={codigo} nome={nome} onSelect={(c, n) => { setCodigo(c); setNome(n); }} />
      </div>
      <div>
        <label style={labelStyleLote}>Centro de custo (opcional)</label>
        <select style={{ ...selStyleLote, width: "100%" }} value={centro} onChange={(e) => setCentro(e.target.value)}>
          <option value="">— Nenhum —</option>{centros.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div><label style={labelStyleLote}>Valor previsto</label><CampoMoeda style={{ ...selStyleLote, width: "100%" }} value={valor} onChange={setValor} /></div>
      <div><label style={labelStyleLote}>Observação (opcional)</label><input style={{ ...selStyleLote, width: "100%" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </div>
  );
}
