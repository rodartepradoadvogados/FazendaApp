"use client";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle, CalendarClock, CheckCircle2, Clock, Circle, CreditCard, Layers, Pencil, Receipt, Plus, Repeat, Search, X, Filter, ChevronUp, ChevronDown, MoreHorizontal, Wallet, Undo2,
} from "lucide-react";
import { formatBRL, formatDate, ehAdmin, estornarPagamentoLancamento, fetchCartoesCredito, fetchFaturasCartao, type FaturaCartao } from "@/lib/api";
import type { Lanc } from "@/lib/financeiroTipos";
import { FAIXAS, diasAte, faixaDe, hojeLocal, situacaoDe, somaDias, somaValores, type FaixaId, type Situacao } from "@/lib/financeiroSituacao";
import type { ContaPlano } from "@/lib/contaGerencial";
import { casaBusca } from "@/lib/busca";
import { useRegrasV2 } from "@/lib/useRegrasV2";
import { LARGURA_GAVETA_BAIXA, MSG_SAIR_SEM_SALVAR } from "@/lib/janelas";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { FiltrosSalvos } from "@/components/FiltrosSalvos";
import { casaContaGerencial, FiltroContaGerencial } from "@/components/financeiro/filtroContaGerencial";

type Props = {
  tipo: "despesa" | "receita";
  regs: Lanc[];
  planoContas: ContaPlano[];
  contasBancarias: string[];
  centros: string[];
  fornecedores: string[];
  produtos: string[];
  /** Formulário de baixa (a gaveta "Dar baixa" só o hospeda). */
  renderBaixa: (nota: Lanc, fechar: (feito?: boolean) => void) => ReactNode;
  /** Depois de "Desfazer" (estorno da baixa): a página recarrega os lançamentos. */
  onDesfeito: () => void;
  onEditar: (l: Lanc) => void;
  onRecibo: (l: Lanc) => void;
  onInserirEmFatura: (l: Lanc) => void;
  onAbrirFatura: (l: Lanc) => void;
  onNovoLancamento: () => void;
  onRecorrentes: () => void;
  onBaixarSelecionadas: (ids: number[]) => void;
  /** Nº de lançamento/documento vindo de link (Agenda, sino, busca): abre a lista já filtrada por ele. */
  documentoInicial?: string | null;
  /** Vindo do Resumo: vencimento de/até já aplicado, com o rótulo que aparece no chip. */
  filtroInicial?: { de?: string; ate?: string; rotulo?: string } | null;
  /** Abre a aba Cartão de crédito (fatura de cartão fechada se paga inteira, não por aqui). */
  onAbrirCartao?: () => void;
};

const ORIGENS: { id: string; label: string; docs: string[] }[] = [
  { id: "folha", label: "Fechamento da folha (todos)", docs: ["Folha de pagamento", "Empreitada", "Contrato", "Acerto de diária", "Diária", "Vale avulso", "Férias", "13º salário", "Rescisão"] },
  { id: "contrato", label: "Contrato", docs: ["Contrato"] },
  { id: "empreita", label: "Empreita", docs: ["Empreitada"] },
  { id: "diaria", label: "Diária", docs: ["Acerto de diária", "Diária"] },
  { id: "clt", label: "Folha CLT", docs: ["Folha de pagamento"] },
  { id: "ferias", label: "Férias / 13º", docs: ["Férias", "13º salário"] },
  { id: "rescisao", label: "Rescisão", docs: ["Rescisão"] },
];

const ICONE_SITUACAO: Record<Situacao["id"], ReactNode> = {
  vencida: <AlertTriangle size={13} aria-hidden />,
  hoje: <Clock size={13} aria-hidden />,
  logo: <Clock size={13} aria-hidden />,
  aberto: <Circle size={13} aria-hidden />,
  fatura: <Layers size={13} aria-hidden />,
  parcial: <Circle size={13} aria-hidden />,
  paga: <CheckCircle2 size={13} aria-hidden />,
  agendada: <CalendarClock size={13} aria-hidden />,
};

export function PilulaSituacao({ s }: { s: Situacao }) {
  return <span className={`st-pill ${s.classe}`}>{ICONE_SITUACAO[s.id]}{s.rotulo}</span>;
}

const camp: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.5rem", fontSize: "0.82rem", width: "100%", minHeight: 36 };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: 2, fontWeight: 600 };

type Ord = { chave: "numero" | "venc" | "desc" | "forn" | "valor"; dir: "asc" | "desc" } | null;

export default function ContasListaView(p: Props) {
  const admin = ehAdmin();
  const regrasV2 = useRegrasV2();
  const receber = p.tipo === "receita";
  const hoje = hojeLocal();
  const nomeLista = receber ? "Contas a receber" : "Contas a pagar";
  const telaSalva = receber ? "financeiro_a_receber" : "financeiro_a_pagar";

  // ── filtros ─────────────────────────────────────────────────────────
  const [campoPeriodo, setCampoPeriodo] = useState<"emissao" | "vencimento">("vencimento");
  const [de, setDe] = useState(p.filtroInicial?.de || "");
  const [ate, setAte] = useState(p.filtroInicial?.ate || "");
  const [centro, setCentro] = useState("");
  const [banco, setBanco] = useState("");
  const [documento, setDocumento] = useState(p.documentoInicial || "");
  const [produto, setProduto] = useState("");
  const [forn, setForn] = useState("");
  const [conta, setConta] = useState("");
  const [contaNome, setContaNome] = useState("");
  const [origem, setOrigem] = useState("");
  const [faixa, setFaixa] = useState<FaixaId | null>(null);
  const [agrupar, setAgrupar] = useState<"venc" | "forn">("venc");
  const [diasAdiante, setDiasAdiante] = useState(7);
  const [ord, setOrd] = useState<Ord>(null);
  // No celular os filtros começam recolhidos (a lista é o que importa); no computador, abertos acima dos cards.
  const [filtrosAbertos, setFiltrosAbertos] = useState(() => (typeof window === "undefined" ? true : window.matchMedia("(min-width: 721px)").matches));
  const [origemChip, setOrigemChip] = useState<string | null>(p.filtroInicial?.rotulo ?? null);
  // Faturas de cartão já fechadas: aparecem como referência (fora do total) — são pagas inteiras, em Cartão de crédito.
  const [cartoes, setCartoes] = useState<{ rotulo: string; venc: string; valor: number }[]>([]);
  useEffect(() => {
    if (receber) return;
    let vivo = true;
    (async () => {
      try {
        const cs = await fetchCartoesCredito();
        const fs = await Promise.all(cs.filter((c) => c.ativo).map(async (c) => (await fetchFaturasCartao(c.id)).map((f: FaturaCartao) => ({ f, c }))));
        if (vivo) setCartoes(fs.flat().filter(({ f }) => f.status === "fechada" && (f.valor_total || 0) > 0).map(({ f, c }) => ({ rotulo: c.apelido, venc: f.data_vencimento, valor: f.valor_total || 0 })));
      } catch { /* sem cartões: nada a mostrar */ }
    })();
    return () => { vivo = false; };
  }, [receber]);

  const filtrosAtuais = () => ({ campoPeriodoContas: campoPeriodo, inicio: de, fim: ate, centro, contaBanco: banco, fornecedor: forn, documento, produto, conta, contaNome, origem });
  function aplicarSalvos(f: Record<string, string | undefined>) {
    setCampoPeriodo(f.campoPeriodoContas === "emissao" ? "emissao" : "vencimento");
    setDe(f.inicio || ""); setAte(f.fim || ""); setCentro(f.centro || ""); setBanco(f.contaBanco || "");
    setForn(f.fornecedor || ""); setDocumento(f.documento || ""); setProduto(f.produto || "");
    setConta(f.conta || ""); setContaNome(f.contaNome || ""); setOrigem(f.origem || ""); setFaixa(null); setOrigemChip(null);
  }

  const abertas = useMemo(() => p.regs.filter((r) => r.tipo === p.tipo && !r.data_pagamento), [p.regs, p.tipo]);

  const base = useMemo(() => abertas.filter((r) => {
    const d = campoPeriodo === "emissao" ? (r.data_emissao || r.data_competencia) : r.data_vencimento;
    if ((de || ate) && !d) return false;
    if (de && d! < de) return false;
    if (ate && d! > ate) return false;
    if (centro && r.centro_custo !== centro) return false;
    if (banco && r.conta_bancaria !== banco) return false;
    if (forn && r.fornecedor !== forn) return false;
    if (produto && !(r.itens || []).some((it) => it.produto === produto)) return false;
    if (documento && !casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""} ${r.numero_boleto || ""}`, documento)) return false;
    if (!casaContaGerencial(r, conta)) return false;
    if (origem && !(ORIGENS.find((o) => o.id === origem)?.docs || []).includes(r.tipo_documento || "")) return false;
    return true;
  }), [abertas, campoPeriodo, de, ate, centro, banco, forn, produto, documento, conta, origem]);

  const vis = useMemo(() => (faixa ? base.filter((r) => faixaDe(r, hoje) === faixa) : base), [base, faixa, hoje]);

  const venc = useMemo(() => base.filter((r) => r.data_vencimento && diasAte(r.data_vencimento, hoje) < 0), [base, hoje]);
  const noHorizonte = useMemo(() => base.filter((r) => r.data_vencimento && (() => { const d = diasAte(r.data_vencimento!, hoje); return d >= 0 && d <= diasAdiante; })()), [base, hoje, diasAdiante]);

  const nFiltros = [de, ate, centro, banco, forn, produto, documento, conta, origem].filter(Boolean).length;
  const filtrando = nFiltros > 0 || !!faixa;

  function limpar() {
    setDe(""); setAte(""); setCentro(""); setBanco(""); setForn(""); setProduto(""); setDocumento(""); setConta(""); setContaNome(""); setOrigem(""); setFaixa(null); setOrigemChip(null);
  }

  // ── ordenação + agrupamento + paginação ────────────────────────────
  const ordenadas = useMemo(() => {
    const v = (r: Lanc) => {
      switch (ord?.chave) {
        case "numero": return (r.numero_lancamento || "").toLowerCase();
        case "desc": return (r.descricao || "").toLowerCase();
        case "forn": return (r.fornecedor || "").toLowerCase();
        case "valor": return r.valor;
        default: return r.data_vencimento || "9999-12-31";
      }
    };
    const arr = [...vis];
    if (ord) {
      arr.sort((a, b) => {
        const va = v(a), vb = v(b);
        const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), "pt-BR", { numeric: true });
        return ord.dir === "asc" ? c : -c;
      });
    } else if (agrupar === "venc") {
      const idx = (r: Lanc) => FAIXAS.findIndex((f) => f.id === faixaDe(r, hoje));
      arr.sort((a, b) => idx(a) - idx(b) || (a.data_vencimento || "9999").localeCompare(b.data_vencimento || "9999"));
    } else {
      const tot = new Map<string, number>();
      vis.forEach((r) => tot.set(r.fornecedor || "—", (tot.get(r.fornecedor || "—") || 0) + r.valor));
      arr.sort((a, b) => (tot.get(b.fornecedor || "—")! - tot.get(a.fornecedor || "—")!) || (a.fornecedor || "").localeCompare(b.fornecedor || "") || (a.data_vencimento || "9999").localeCompare(b.data_vencimento || "9999"));
    }
    return arr;
  }, [vis, ord, agrupar, hoje]);
  const pag = usePaginacao(ordenadas);

  const chaveGrupo = (r: Lanc) => (agrupar === "venc" ? faixaDe(r, hoje) : r.fornecedor || "—");
  const nomeGrupo = (r: Lanc) => (agrupar === "venc" ? FAIXAS.find((f) => f.id === faixaDe(r, hoje))!.nome : r.fornecedor || "Sem fornecedor");
  const subtotal = useMemo(() => {
    const m = new Map<string, { n: number; v: number }>();
    vis.forEach((r) => { const k = chaveGrupo(r); const g = m.get(k) || { n: 0, v: 0 }; g.n += 1; g.v += r.valor; m.set(k, g); });
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vis, agrupar, hoje]);

  // ── seleção em lote ─────────────────────────────────────────────────
  const [sel, setSel] = useState<Set<number>>(new Set());
  // Nota de fatura de fornecedor ou de compra no cartão (PR 5): só se paga pela fatura.
  const selecionaveis = (r: Lanc) => !r.fatura_id && !r.fatura_cartao_id;
  const selecionadas = ordenadas.filter((r) => sel.has(r.id));
  const alternar = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const paginaSel = pag.linhasPagina.filter(selecionaveis);
  const todasDaPagina = paginaSel.length > 0 && paginaSel.every((r) => sel.has(r.id));
  useEffect(() => { setSel((s) => new Set([...s].filter((id) => p.regs.some((r) => r.id === id && !r.data_pagamento)))); }, [p.regs]);

  // ── gaveta de baixa ─────────────────────────────────────────────────
  const [baixa, setBaixa] = useState<Lanc | null>(null);
  // Janela TRAVADA: não fecha por clique fora nem por Esc, só pelo X. Se o usuário já
  // mexeu em algum campo, o X pergunta antes (mesmo texto de Lançamentos). Detectado
  // pelos eventos de change/input que sobem do formulário, sem tocar nele.
  const [baixaSuja, setBaixaSuja] = useState(false);
  useEffect(() => { setBaixaSuja(false); }, [baixa?.id]);
  function fecharBaixaPeloX() {
    if (baixaSuja && !window.confirm(MSG_SAIR_SEM_SALVAR)) return;
    setBaixa(null);
  }
  // "Desfazer" logo após a baixa (= estorno): some sozinho em 12 s.
  const [desfazer, setDesfazer] = useState<{ id: number; rotulo: string; erro?: string } | null>(null);
  useEffect(() => {
    if (!desfazer || desfazer.erro) return;
    const t = setTimeout(() => setDesfazer(null), 12000);
    return () => clearTimeout(t);
  }, [desfazer]);
  async function desfazerBaixa() {
    if (!desfazer) return;
    try {
      await estornarPagamentoLancamento(desfazer.id, { confirmar_parcelas_diferenca: true });
      setDesfazer(null);
      p.onDesfeito();
    } catch (e) {
      setDesfazer({ ...desfazer, erro: e instanceof Error ? e.message : "Não foi possível desfazer." });
    }
  }
  useEffect(() => { if (baixa && !abertas.some((r) => r.id === baixa.id)) setBaixa(null); }, [abertas, baixa]);
  // Chegou por link (Agenda, sino, busca) com um nº de nota: se só uma conta casa, já abre a baixa dela.
  const abriuAlvo = useRef(false);
  useEffect(() => {
    if (abriuAlvo.current || !p.documentoInicial) return;
    const achadas = abertas.filter((r) => casaBusca(`${r.numero_documento || ""} ${r.numero_lancamento || ""} ${r.numero_os_orcamento || ""} ${r.numero_boleto || ""}`, p.documentoInicial!));
    abriuAlvo.current = true;
    if (achadas.length === 1 && selecionaveis(achadas[0])) setBaixa(achadas[0]);
  }, [abertas, p.documentoInicial]);

  const ordenar = (chave: NonNullable<Ord>["chave"]) => setOrd((o) => (o?.chave === chave ? (o.dir === "asc" ? { chave, dir: "desc" } : null) : { chave, dir: "asc" }));
  const ariaSort = (chave: NonNullable<Ord>["chave"]): "ascending" | "descending" | "none" => (ord?.chave === chave ? (ord.dir === "asc" ? "ascending" : "descending") : "none");
  const th = (chave: NonNullable<Ord>["chave"], rotulo: string, direita?: boolean) => (
    <th key={chave} aria-sort={ariaSort(chave)} style={{ textAlign: direita ? "right" : "left", whiteSpace: "nowrap" }}>
      <button type="button" onClick={() => ordenar(chave)} style={{ background: "none", border: 0, color: "inherit", font: "inherit", cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 3 }}>
        {rotulo}{ord?.chave === chave ? (ord.dir === "asc" ? <ChevronUp size={12} aria-hidden /> : <ChevronDown size={12} aria-hidden />) : null}
      </button>
    </th>
  );

  const opcoesForn = useMemo(() => Array.from(new Set(abertas.map((r) => r.fornecedor).filter(Boolean))).sort((a, b) => a.localeCompare(b, "pt-BR")), [abertas]);
  const opcoesProd = useMemo(() => {
    const s = new Set<string>();
    abertas.forEach((r) => (r.itens || []).forEach((it) => { if (it.produto) s.add(it.produto); }));
    return Array.from(s).sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [abertas]);
  const opcoesCentros = useMemo(() => Array.from(new Set(abertas.map((r) => r.centro_custo).filter(Boolean))).sort(), [abertas]);

  const totalGeral = somaValores(abertas);
  const semNada = abertas.length === 0;
  const faturasAbertas = new Set(abertas.filter((r) => r.fatura_id).map((r) => r.fatura_id)).size;
  const colunas = admin ? 9 : 8;

  return (
    <div>
      <style>{`
        @media (max-width: 720px) {
          .cl-tab, .cl-tab tbody { display: block; }
          .cl-tab thead { display: none; }
          .cl-tab tr { display: grid; grid-template-columns: auto 1fr auto; gap: .3rem .65rem; padding: .75rem .8rem; border-bottom: 1px solid var(--border); align-items: center; }
          .cl-tab td { display: block; padding: 0 !important; border: 0 !important; background: transparent; min-width: 0; }
          .cl-tab td.c-grp { grid-column: 1 / -1; background: var(--surface-2) !important; padding: .4rem .8rem !important; margin: 0 -.8rem; }
          .cl-tab tr:has(td.c-grp) { padding: 0; display: block; }
          .cl-tab td.c-chk { grid-column: 1; grid-row: 1; }
          .cl-tab td.c-sit { grid-column: 2; grid-row: 1; }
          .cl-tab td.c-val { grid-column: 3; grid-row: 1; font-size: 1rem; }
          .cl-tab td.c-desc { grid-column: 1 / -1; }
          .cl-tab td.c-venc { grid-column: 1 / 3; }
          .cl-tab td.c-forn { grid-column: 1 / -1; }
          .cl-tab td.c-usr { grid-column: 1 / -1; }
          .cl-tab td.c-act { grid-column: 1 / 3; text-align: left !important; }
          .cl-tab td.c-menu { grid-column: 3; justify-self: end; }
          .cl-tab .btn-ghost, .cl-tab .btn-primary { min-height: 44px; }
          .cl-tab input[type=checkbox] { width: 22px; height: 22px; }
          .cl-tab tr.st-row-venc, .cl-tab tr.st-row-sel { background: var(--st-venc-row); }
          .cl-tab tr.st-row-sel { background: var(--sel-row); }
        }
      `}</style>
      {/* cabeçalho + ações */}
      <div className="flex items-start justify-between gap-3 mb-3" style={{ flexWrap: "wrap" }}>
        <div>
          <h2 style={{ fontFamily: "var(--font-heading)", fontSize: "1.35rem", fontWeight: 700 }}>{nomeLista}</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
            {receber ? "Tudo que ainda não foi recebido" : "Tudo que ainda não foi pago"}, do mais urgente ao mais distante. Filtre, confira os totais e dê baixa sem sair da lista.
          </p>
        </div>
        <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
          <button className="btn-primary" onClick={p.onNovoLancamento} title="Lançar uma conta nova (com leitura automática de nota fiscal, boleto ou recibo)"><Plus size={14} /> Novo lançamento</button>
          {!receber && <button className="btn-ghost" onClick={p.onRecorrentes} title="Contas que se repetem todo mês: gerar só com o valor do período"><Repeat size={14} /> Recorrentes</button>}
          <ExportarBotoes titulo={nomeLista} nomeArquivoBase={telaSalva}
            colunas={[{ header: "Nº lanç.", key: "numero_lancamento" }, { header: "Vencimento", key: "data" }, { header: "Situação", key: "situacao" }, { header: "Descrição", key: "descricao" }, { header: receber ? "Cliente" : "Fornecedor", key: "fornecedor" }, { header: "Centro custo", key: "centro_custo" }, { header: "Valor", key: "valor" }]}
            linhas={ordenadas.map((r) => ({ ...r, data: formatDate(r.data_vencimento || ""), situacao: situacaoDe(r, hoje).rotulo }))} />
        </div>
      </div>

      {/* filtros ficam ACIMA dos cards (definem o que os cards somam) */}
      <div className="card mb-3" style={{ padding: "0.75rem 0.9rem" }}>
        <div className="flex items-center justify-between gap-2" style={{ flexWrap: "wrap" }}>
          <button type="button" onClick={() => setFiltrosAbertos((v) => !v)} aria-expanded={filtrosAbertos}
            style={{ background: "none", border: 0, color: "var(--text)", font: "inherit", fontWeight: 700, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Filter size={14} aria-hidden /> Filtros{nFiltros ? ` (${nFiltros})` : ""} {filtrosAbertos ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
          </button>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            <div role="group" aria-label="Agrupar por" className="flex">
              {([["venc", "Por vencimento"], ["forn", receber ? "Por cliente" : "Por fornecedor"]] as const).map(([id, rot]) => (
                <button key={id} type="button" aria-pressed={agrupar === id && !ord} onClick={() => { setAgrupar(id); setOrd(null); }}
                  className="btn-ghost" style={{ fontSize: "0.76rem", borderColor: agrupar === id && !ord ? "var(--text-accent)" : undefined, fontWeight: agrupar === id && !ord ? 700 : 500 }}>{rot}</button>
              ))}
            </div>
            {filtrando && <button type="button" className="btn-ghost" onClick={limpar} style={{ fontSize: "0.76rem" }}><X size={12} /> Limpar filtros</button>}
          </div>
        </div>
        {filtrosAbertos && (
          <div style={{ marginTop: "0.7rem" }}>
            <div className="mb-3"><FiltrosSalvos tela={telaSalva} valor={filtrosAtuais()} aoAplicar={aplicarSalvos} /></div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><label style={lbl} htmlFor="cl-per">Período por</label>
                <select id="cl-per" style={camp} value={campoPeriodo} onChange={(e) => setCampoPeriodo(e.target.value as "emissao" | "vencimento")}>
                  <option value="vencimento">Vencimento</option><option value="emissao">Emissão</option>
                </select></div>
              <div><label style={lbl} htmlFor="cl-de">De</label><input id="cl-de" type="date" style={camp} value={de} onChange={(e) => setDe(e.target.value)} /></div>
              <div><label style={lbl} htmlFor="cl-ate">Até</label><input id="cl-ate" type="date" style={camp} value={ate} onChange={(e) => setAte(e.target.value)} /></div>
              <div><label style={lbl} htmlFor="cl-cc">Centro de custo</label>
                <select id="cl-cc" style={camp} value={centro} onChange={(e) => setCentro(e.target.value)}><option value="">Todos</option>{opcoesCentros.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label style={lbl} htmlFor="cl-forn">{receber ? "Cliente" : "Fornecedor"}</label>
                <select id="cl-forn" style={camp} value={forn} onChange={(e) => setForn(e.target.value)}><option value="">Todos</option>{opcoesForn.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label style={lbl} htmlFor="cl-doc">Nº do documento</label>
                <div style={{ position: "relative" }}><Search size={13} aria-hidden style={{ position: "absolute", left: 8, top: 11, color: "var(--text-muted)" }} />
                  <input id="cl-doc" style={{ ...camp, paddingLeft: "1.6rem" }} value={documento} onChange={(e) => setDocumento(e.target.value)} placeholder="ex.: 4521 ou LC-2026-00012" /></div></div>
              <div><label style={lbl} htmlFor="cl-prod">Produto / serviço</label>
                <select id="cl-prod" style={camp} value={produto} onChange={(e) => setProduto(e.target.value)}><option value="">Todos</option>{Array.from(new Set([...p.produtos, ...opcoesProd])).sort((a, b) => a.localeCompare(b, "pt-BR")).map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label style={lbl} htmlFor="cl-bco">Conta bancária</label>
                <select id="cl-bco" style={camp} value={banco} onChange={(e) => setBanco(e.target.value)}><option value="">Todas</option>{p.contasBancarias.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div className="md:col-span-2"><span style={lbl}>Conta gerencial</span>
                <FiltroContaGerencial contas={p.planoContas} tipos={[p.tipo]} codigo={conta} nome={contaNome} onChange={(c, n) => { setConta(c); setContaNome(n); }} /></div>
              {!receber && (
                <div><label style={lbl} htmlFor="cl-org">Origem</label>
                  <select id="cl-org" style={camp} value={origem} onChange={(e) => setOrigem(e.target.value)}><option value="">Todas as origens</option>{ORIGENS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* cards: mudam com o filtro */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3" role="group" aria-label="Resumo do que está filtrado">
        <div className="st-kpi">
          <div className="l">Total em aberto</div>
          <div className="v">{formatBRL(totalGeral)}</div>
          <div className="s">{abertas.length} no geral, sem filtros</div>
        </div>
        <button type="button" className={`st-kpi venc${venc.length ? "" : " zero"}`} aria-pressed={faixa === "venc"} onClick={() => setFaixa((f) => (f === "venc" ? null : "venc"))}
          title="Listar só as vencidas">
          <div className="l"><AlertTriangle size={13} aria-hidden /> Vencidas</div>
          <div className="v">{venc.length ? formatBRL(somaValores(venc)) : "—"}</div>
          <div className="s">{venc.length ? `${venc.length} · clique para listar` : "nenhuma vencida"}</div>
        </button>
        <div className={`st-kpi logo${noHorizonte.length ? "" : " zero"}`}>
          <div className="l"><Clock size={13} aria-hidden /><label htmlFor="cl-dias">Vencem em</label>
            <input id="cl-dias" type="number" min={1} max={365} inputMode="numeric" value={diasAdiante}
              onChange={(e) => { const n = Math.round(Number(e.target.value)); if (n >= 1 && n <= 365) setDiasAdiante(n); }}
              style={{ width: 52, textAlign: "right", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 4px", fontSize: "0.78rem" }} /> dias</div>
          <div className="v">{noHorizonte.length ? formatBRL(somaValores(noHorizonte)) : "—"}</div>
          <div className="s">{noHorizonte.length} · <button type="button" onClick={() => { const h = hojeLocal(); setCampoPeriodo("vencimento"); setDe(h); setAte(somaDias(h, diasAdiante)); setFaixa(null); setOrigemChip(`Vencem em até ${diasAdiante} dias`); }}
            style={{ background: "none", border: 0, color: "var(--text-accent)", textDecoration: "underline", cursor: "pointer", padding: 0, font: "inherit" }}>listar</button></div>
        </div>
        <div className="st-kpi">
          <div className="l">Lançamentos</div>
          <div className="v">{vis.length}</div>
          <div className="s">{filtrando ? `de ${abertas.length} no geral` : "todos em aberto"}</div>
        </div>
        <div className="st-kpi aberto" style={filtrando ? undefined : { opacity: 0.85 }}>
          <div className="l">{filtrando ? "Valor filtrado" : "Valor em aberto"}</div>
          <div className="v">{formatBRL(somaValores(vis))}</div>
          <div className="s">{filtrando ? (totalGeral > 0 ? `${Math.round((somaValores(vis) / totalGeral) * 100)}% do total · ficaram de fora ${formatBRL(Math.max(totalGeral - somaValores(vis), 0))}` : "") : (faturasAbertas ? `${faturasAbertas} fatura${faturasAbertas > 1 ? "s" : ""} aberta${faturasAbertas > 1 ? "s" : ""} já incluída${faturasAbertas > 1 ? "s" : ""}` : "sem filtro aplicado")}</div>
        </div>
      </div>

      {cartoes.length > 0 && !regrasV2 && (
        <div className="card mb-2" style={{ padding: "0.5rem 0.8rem", display: "flex", alignItems: "center", gap: "0.7rem", flexWrap: "wrap", fontSize: "0.8rem" }}>
          <span className="st-pill fat"><Layers size={13} aria-hidden /> Cartão de crédito</span>
          <span>{cartoes.map((c) => `${c.rotulo}: ${formatBRL(c.valor)} (vence ${formatDate(c.venc)})`).join(" · ")}</span>
          <span style={{ color: "var(--text-muted)" }}>Fatura fechada, paga inteira como uma conta só; <strong>fora do total acima</strong>.</span>
          {p.onAbrirCartao && <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={p.onAbrirCartao}>Pagar pelo cartão →</button>}
        </div>
      )}
      <div className="flex items-center justify-between gap-2 mb-2" style={{ flexWrap: "wrap", fontSize: "0.8rem", color: "var(--text-muted)" }}>
        <span className="flex gap-2" style={{ flexWrap: "wrap" }}>
          <span className="st-chip">Status: não {receber ? "recebido" : "pago"}</span>
          {(de || ate) && <span className="st-chip">{campoPeriodo === "emissao" ? "Emissão" : "Vencimento"}{de ? ` de ${formatDate(de)}` : ""}{ate ? ` até ${formatDate(ate)}` : ""}</span>}
          {faixa && <span className="st-chip">Faixa: {FAIXAS.find((f) => f.id === faixa)!.nome}</span>}
          {origemChip && <span className="st-chip">{origemChip}</span>}
        </span>
        <span>Mostrando <strong style={{ color: "var(--text)" }}>{vis.length}</strong> de {abertas.length} · <strong style={{ color: "var(--text)" }}>{formatBRL(somaValores(vis))}</strong></span>
      </div>

      {/* lista */}
      <div className="card" style={{ padding: 0 }}>
        <div className="overflow-x-auto" style={{ maxHeight: "calc(100vh - 360px)", minHeight: 240 }}>
          <table className="fazenda-table cl-tab" style={{ margin: 0 }}>
            <thead style={{ position: "sticky", top: 0, zIndex: 1, background: "var(--thead-bg)" }}>
              <tr>
                <th style={{ width: 34 }}>
                  <input type="checkbox" aria-label="Selecionar todas desta página" checked={todasDaPagina}
                    onChange={() => setSel((s) => { const n = new Set(s); paginaSel.forEach((r) => (todasDaPagina ? n.delete(r.id) : n.add(r.id))); return n; })} />
                </th>
                <th>Situação</th>
                {th("venc", "Vencimento")}
                {th("desc", "Descrição")}
                {th("forn", receber ? "Cliente" : "Fornecedor")}
                {th("valor", "Valor", true)}
                {admin && <th>Usuário</th>}
                <th style={{ textAlign: "right" }}>Ações</th>
                <th aria-label="Mais" style={{ width: 36 }} />
              </tr>
            </thead>
            <tbody>
              {pag.linhasPagina.map((r, i) => {
                const s = situacaoDe(r, hoje);
                const anterior = pag.linhasPagina[i - 1];
                const mostraGrupo = !ord && (!anterior || chaveGrupo(anterior) !== chaveGrupo(r));
                const g = subtotal.get(chaveGrupo(r));
                const fat = !!r.fatura_id;
                const fatCartao = !!r.fatura_cartao_id;
                return (
                  <RowFragment key={r.id}>
                    {mostraGrupo && g && (
                      <tr>
                        <td className="c-grp" colSpan={colunas + 1} style={{ background: "var(--surface-2)", fontSize: "0.78rem", fontWeight: 700, padding: "0.35rem 0.7rem" }}>
                          {nomeGrupo(r)} <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>· {g.n} {g.n === 1 ? "lançamento" : "lançamentos"}</span>
                          <span style={{ float: "right", fontVariantNumeric: "tabular-nums" }}>{formatBRL(g.v)}</span>
                        </td>
                      </tr>
                    )}
                    <tr className={`${s.id === "vencida" ? "st-row-venc" : ""} ${sel.has(r.id) ? "st-row-sel" : ""}`}>
                      <td className="c-chk">{selecionaveis(r)
                        ? <input type="checkbox" aria-label={`Selecionar ${r.numero_lancamento || r.descricao}`} checked={sel.has(r.id)} onChange={() => alternar(r.id)} />
                        : <input type="checkbox" disabled title="Nota de fatura só se paga pela parcela da fatura" aria-label="Nota de fatura: pague pela fatura" />}</td>
                      <td className="c-sit"><PilulaSituacao s={s} /></td>
                      <td className="c-venc" style={{ whiteSpace: "nowrap", fontSize: "0.8rem", fontVariantNumeric: "tabular-nums" }}>{r.data_vencimento ? formatDate(r.data_vencimento) : "—"}</td>
                      <td className="c-desc" style={{ fontSize: "0.8rem" }}>
                        <div>{r.descricao || "—"}</div>
                        <div className="flex" style={{ flexWrap: "wrap", gap: "0.3rem", marginTop: 3, fontSize: "0.7rem", color: "var(--text-muted)" }}>
                          <span>{r.numero_lancamento}{r.parcela_total && r.parcela_total > 1 ? ` · parcela ${r.parcela_num}/${r.parcela_total}` : ""}</span>
                          {r.centro_custo && <span className="st-chip" style={{ fontSize: "0.68rem", padding: "0 8px" }}>{r.centro_custo}</span>}
                          {(r.tipo_documento || r.numero_documento) && <span className="st-chip" style={{ fontSize: "0.68rem", padding: "0 8px" }}>{r.tipo_documento ? `${r.tipo_documento} ` : ""}{r.numero_documento || ""}</span>}
                          {fat && <button type="button" onClick={() => p.onAbrirFatura(r)} className="st-pill fat" style={{ cursor: "pointer" }} title="Abrir a fatura desta nota"><Layers size={11} aria-hidden /> fatura</button>}
                          {fatCartao && <button type="button" onClick={p.onAbrirCartao} className="st-pill fat" style={{ cursor: "pointer" }} title="Compra no cartão: abrir Cartão de crédito"><CreditCard size={11} aria-hidden /> cartão</button>}
                          {r.origem_preventivo && <a href="/protocolos?aba=acompanhamento" className="st-chip" style={{ fontSize: "0.68rem", padding: "0 8px", textDecoration: "none" }} title={`Nasceu do agendamento de ${r.origem_preventivo.protocolo}`}>Protocolo preventivo · {r.origem_preventivo.protocolo}</a>}
                          {(r.itens || []).some((it) => it.eh_vale) && <span className="st-chip" style={{ fontSize: "0.68rem", padding: "0 8px" }} title="Item lançado como vale — fora dos relatórios gerenciais">vale</span>}
                        </div>
                      </td>
                      <td className="c-forn" style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.fornecedor || "—"}</td>
                      <td className="c-val" style={{ textAlign: "right", fontWeight: 700, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{formatBRL(r.valor)}</td>
                      {admin && <td className="c-usr" style={{ fontSize: "0.75rem" }}>{r.usuario_nome ?? "—"}</td>}
                      <td className="c-act" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {fatCartao
                          ? <button className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={p.onAbrirCartao} title="Compra no cartão: só se paga pela fatura do cartão"><CreditCard size={12} /> Pagar pela fatura do cartão →</button>
                          : fat
                          ? <button className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => p.onAbrirFatura(r)} title="Nota de fatura só se paga pela parcela da fatura"><Layers size={12} /> Pagar pela fatura →</button>
                          : <button className={s.id === "vencida" ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.74rem", minHeight: 32 }} onClick={() => setBaixa(r)}
                              title={`Registrar ${receber ? "o recebimento" : "o pagamento"} desta conta (data, conta, forma, comprovante)`}><Wallet size={12} /> Dar baixa</button>}
                      </td>
                      <td className="c-menu"><MenuLinha r={r} onEditar={p.onEditar} onRecibo={p.onRecibo} onInserirEmFatura={p.onInserirEmFatura} podeInserir={!receber && !!r.fornecedor && !fat && !fatCartao} /></td>
                    </tr>
                  </RowFragment>
                );
              })}
              {!ordenadas.length && (
                <tr><td colSpan={colunas + 1} style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-muted)" }}>
                  <CheckCircle2 size={26} aria-hidden style={{ margin: "0 auto 0.5rem", color: "var(--st-pago-fg)" }} />
                  {semNada
                    ? <strong style={{ color: "var(--text)" }}>Tudo em dia: nenhuma conta em aberto.</strong>
                    : <><strong style={{ color: "var(--text)", display: "block" }}>{faixa === "venc" ? "Nenhuma conta vencida neste filtro." : "Nada neste filtro."}</strong>
                        <button className="btn-ghost" style={{ marginTop: 8 }} onClick={limpar}>Limpar filtros</button></>}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        {ordenadas.length > 0 && (
          <div style={{ padding: "0 0.9rem 0.6rem" }}>
            <Paginacao pagina={pag.pagina} totalPaginas={pag.totalPaginas} totalLinhas={pag.totalLinhas} tamanhoPagina={pag.tamanhoPagina} onMudarPagina={pag.setPagina} onMudarTamanho={pag.setTamanhoPagina} />
          </div>
        )}
      </div>

      {selecionadas.length > 0 && (
        <div role="region" aria-label="Seleção" style={{ position: "sticky", bottom: 12, zIndex: 5, marginTop: 12, background: "var(--text-accent)", color: "var(--bg)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem", display: "flex", alignItems: "center", gap: "0.8rem", flexWrap: "wrap", boxShadow: "0 4px 14px rgba(0,0,0,0.25)" }}>
          <strong>{selecionadas.length} selecionada{selecionadas.length > 1 ? "s" : ""}</strong>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatBRL(somaValores(selecionadas))}</span>
          <span style={{ flex: 1 }} />
          <button className="btn-ghost" style={{ background: "var(--surface)", color: "var(--text)" }} onClick={() => p.onBaixarSelecionadas(selecionadas.map((r) => r.id))}>Baixar selecionadas</button>
          <button className="btn-ghost" style={{ color: "inherit" }} onClick={() => setSel(new Set())}>Limpar</button>
        </div>
      )}

      {baixa && (
        <GavetaLancamento aberto onFechar={fecharBaixaPeloX} titulo={`Dar baixa · ${baixa.fornecedor || baixa.descricao}`} icone={Wallet}
          largura={LARGURA_GAVETA_BAIXA} fecharComEsc={false}>
          <div onChange={() => setBaixaSuja(true)} onInput={() => setBaixaSuja(true)}>
            <ResumoNota r={baixa} hoje={hoje} />
            {p.renderBaixa(baixa, (feito) => { setBaixa(null); if (feito) setDesfazer({ id: baixa.id, rotulo: `${receber ? "Recebimento" : "Pagamento"} de ${baixa.fornecedor || baixa.descricao} registrado` }); })}
          </div>
        </GavetaLancamento>
      )}

      {desfazer && (
        <div role="status" aria-live="polite" style={{ position: "fixed", left: "50%", transform: "translateX(-50%)", bottom: 18, zIndex: 95, background: "var(--text-accent)", color: "var(--bg)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem", display: "flex", alignItems: "center", gap: "0.8rem", boxShadow: "0 6px 20px rgba(0,0,0,0.3)", maxWidth: "92vw" }}>
          <CheckCircle2 size={16} aria-hidden />
          <span style={{ fontSize: "0.85rem" }}>{desfazer.erro ? desfazer.erro : desfazer.rotulo}</span>
          {!desfazer.erro && <button className="btn-ghost" style={{ background: "var(--surface)", color: "var(--text)", minHeight: 32 }} onClick={desfazerBaixa}><Undo2 size={13} /> Desfazer</button>}
          <button className="btn-ghost" aria-label="Fechar aviso" style={{ color: "inherit", minHeight: 32 }} onClick={() => setDesfazer(null)}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

function RowFragment({ children }: { children: ReactNode }) { return <>{children}</>; }

function ResumoNota({ r, hoje }: { r: Lanc; hoje: string }) {
  const s = situacaoDe(r, hoje);
  return (
    <div className="flex items-center justify-between gap-2" style={{ marginBottom: 10, flexWrap: "wrap" }}>
      <PilulaSituacao s={s} />
      <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.numero_lancamento}{r.data_vencimento ? ` · vence ${formatDate(r.data_vencimento)}` : ""}</span>
    </div>
  );
}

function MenuLinha({ r, onEditar, onRecibo, onInserirEmFatura, podeInserir }: { r: Lanc; onEditar: (l: Lanc) => void; onRecibo: (l: Lanc) => void; onInserirEmFatura: (l: Lanc) => void; podeInserir: boolean }) {
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);
  const item: React.CSSProperties = { display: "flex", alignItems: "center", gap: 6, width: "100%", textAlign: "left", padding: "0.45rem 0.7rem", background: "none", border: 0, color: "var(--text)", font: "inherit", fontSize: "0.8rem", cursor: "pointer" };
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" className="btn-ghost" aria-label="Mais ações" aria-haspopup="menu" aria-expanded={aberto} onClick={() => setAberto((v) => !v)} style={{ padding: "0.2rem 0.35rem", minHeight: 32 }}><MoreHorizontal size={16} /></button>
      {aberto && (
        <div role="menu" style={{ position: "absolute", right: 0, top: "100%", zIndex: 20, minWidth: 190, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", boxShadow: "0 6px 20px rgba(0,0,0,0.25)" }}>
          <button role="menuitem" style={item} onClick={() => { setAberto(false); onEditar(r); }}><Pencil size={13} /> Editar lançamento</button>
          {podeInserir && <button role="menuitem" style={item} onClick={() => { setAberto(false); onInserirEmFatura(r); }}><Layers size={13} /> Inserir em fatura…</button>}
          <button role="menuitem" style={item} onClick={() => { setAberto(false); onRecibo(r); }}><Receipt size={13} /> Recibo</button>
        </div>
      )}
    </div>
  );
}
