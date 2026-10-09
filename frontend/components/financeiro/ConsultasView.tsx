"use client";
// Financeiro › Consultas — UMA tela, só o REALIZADO (lançamentos com
// data_pagamento): filtros em 3 blocos (O quê / Quando / Detalhe), cards que
// recalculam com os filtros e a lista (ou o Livro caixa). Nada em aberto,
// nada projetado: o que está em aberto mora em Contas.
//
// Contas puras (filtro, somas, livro, ordenação) ficam em consultasCalculo.ts,
// com testes em consultasCalculo.test.ts.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowDownLeft, ArrowUp, ArrowUpDown, ArrowUpRight, BookOpen, Eraser, Info, Landmark, Layers,
  List, Paperclip, Pencil, Receipt, Search, SplitSquareHorizontal, TrendingDown, TrendingUp, Undo2,
} from "lucide-react";
import type { Lanc } from "@/lib/financeiroTipos";
import type { ContaPlano } from "@/lib/contaGerencial";
import { caminhoAncestrais } from "@/lib/contaGerencial";
import { hojeLocal, situacaoDe, somaDias } from "@/lib/financeiroSituacao";
import {
  ehAdmin, estornarPagamentoLancamento, fetchContasCorrentes, formatBRL, formatDate, listarAnexosLancamentoPorId, urlAnexoLancamento,
  type ContaCorrenteCadastro,
} from "@/lib/api";
import { casaBusca } from "@/lib/busca";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { FiltrosSalvos } from "@/components/FiltrosSalvos";
import { Modal } from "@/components/Modal";
import { larguraDobrada } from "@/lib/janelas";
import {
  aplicarFiltroInicial, contarFiltrosAtivos, filtrarRealizados, filtrosPadrao, montarLivro, ordenarLinhas, resumir,
  type CampoPeriodo, type ChaveOrdem, type FiltroInicial, type FiltrosConsulta, type ModoConsulta, type Movimento, type Ordem,
} from "./consultasCalculo";

const TELA_FILTRO = "financeiro_consultas";

type Props = {
  regs: Lanc[];
  planoContas: ContaPlano[];
  contasBancarias: string[];
  centros: string[];
  fornecedores: string[];
  produtos: string[];
  onRecibo: (l: Lanc) => void;
  onEstornado: () => void;
  onEditar: (l: Lanc) => void;
  filtroInicial?: FiltroInicialConsultas;
};

/** Filtro vindo de fora: busca global, Resumo, Agenda — ou o drill de um relatório (Fase B), com a origem para o aviso. */
export type FiltroInicialConsultas = FiltroInicial & { modo?: "lista" | "livro"; origem?: string; chave?: string };

type ParcelaDiferenca = { id: number; parcela_num: number; parcela_total: number; data_vencimento: string; valor_total: number };
type ErroApi = { status?: number; message?: string; detail?: { mensagem?: string; parcelas?: ParcelaDiferenca[] } };

const MOVIMENTOS: { v: Movimento; rotulo: string }[] = [
  { v: "pagamento", rotulo: "Pagamento" }, { v: "recebimento", rotulo: "Recebimento" }, { v: "ambos", rotulo: "Ambos" },
];
const CAMPOS_PERIODO: { v: CampoPeriodo; rotulo: string }[] = [
  { v: "emissao", rotulo: "Emissão" }, { v: "vencimento", rotulo: "Vencimento" }, { v: "pagamento", rotulo: "Pagamento" }, { v: "competencia", rotulo: "Competência" },
];
const MODOS: { v: ModoConsulta; rotulo: string; icone: React.ReactNode }[] = [
  { v: "lista", rotulo: "Lista", icone: <List size={14} aria-hidden /> },
  { v: "livro", rotulo: "Livro caixa", icone: <BookOpen size={14} aria-hidden /> },
];
const CHAVES_FILTRO = ["movimento", "periodoPor", "de", "ate", "centro", "banco", "documento", "produto", "fornecedor", "conta", "contaNome"] as const;

const ordenarPt = (xs: Iterable<string>) => Array.from(new Set(Array.from(xs).filter(Boolean))).sort((a, b) => a.localeCompare(b, "pt-BR"));
const parcelaTxt = (l: Lanc) => (l.parcela_total && l.parcela_total > 1 ? `${l.parcela_num ?? "?"}/${l.parcela_total}` : "");
const documentoTxt = (l: Lanc) => `${l.tipo_documento ? `${l.tipo_documento} ` : ""}${l.numero_documento || ""}`.trim();

// Estilos locais com prefixo "cq-" — tudo em var(--…), funciona nos temas
// claro, escuro e misto. Nada de cor fixa em texto; dourado nunca vira texto
// (usa --text-accent). Sem filete lateral > 1px.
const CSS = `
.cq{display:flex;flex-direction:column;gap:.75rem;min-width:0}
.cq-head{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:.6rem 1rem}
.cq-head h2{font-size:1.35rem;font-weight:700;letter-spacing:-.01em;color:var(--text);margin:0}
.cq-nota{display:flex;align-items:flex-start;gap:.35rem;font-size:.8rem;color:var(--text-muted);margin:.15rem 0 0}
.cq-nota svg{flex-shrink:0;margin-top:2px}
.cq-acoes{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem}
.cq-seg{display:inline-flex;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);flex-wrap:wrap;max-width:100%;background:var(--surface)}
.cq-seg button{border:0;background:transparent;color:var(--text-muted);font:inherit;font-size:.8rem;font-weight:600;padding:0 .55rem;min-height:34px;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:.35rem}
.cq-seg button+button{border-left:1px solid var(--border-strong,var(--border))}
.cq-seg button:hover{color:var(--text);background:var(--surface-2)}
.cq-seg button[aria-pressed="true"]{background:var(--pill-active-bg);color:var(--pill-active-fg);box-shadow:inset 0 0 0 1px var(--pill-active-border)}
.cq-filtros{display:grid;grid-template-columns:minmax(230px,.8fr) minmax(300px,1.25fr) minmax(0,3fr);gap:.5rem}
.cq-bloco{display:flex;flex-wrap:wrap;align-content:flex-start;gap:.5rem .6rem;padding:.55rem .7rem .7rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);min-width:0}
.cq-bloco>h3{width:100%;margin:0;font-size:.6875rem;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--text-accent)}
.cq-campo{display:flex;flex-direction:column;gap:.2rem;min-width:0;flex:1 1 150px}
.cq-campo.cq-largo{flex-basis:100%}
.cq-campo>label,.cq-campo>.cq-rot{font-size:.7rem;font-weight:600;color:var(--text-muted)}
.cq-in{background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:var(--r-sm);padding:0 .55rem;min-height:36px;font:inherit;font-size:.82rem;width:100%;min-width:0}
.cq-busca{position:relative}
.cq-busca svg{position:absolute;left:.5rem;top:50%;transform:translateY(-50%);color:var(--text-muted);pointer-events:none}
.cq-busca .cq-in{padding-left:1.7rem}
.cq-detalhe{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:.5rem .6rem;width:100%}
.cq-barra{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .75rem;font-size:.8rem;color:var(--text-muted)}
.cq-barra .cq-cont{display:inline-flex;align-items:center;gap:.3rem;font-weight:600;color:var(--text)}
.cq-btn{display:inline-flex;align-items:center;gap:.35rem;font-size:.78rem;padding:.35rem .7rem}
.cq-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr)) minmax(0,1.6fr);gap:.5rem}
.cq-kpis .st-kpi .l{text-transform:uppercase;letter-spacing:.08em;font-size:.66rem}
.cq-kpis .st-kpi .v{font-size:1.15rem;overflow-wrap:anywhere}
.cq-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:1px 8px;font-size:.78rem;margin-top:4px;align-items:baseline}
.cq-top span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cq-top b{font-variant-numeric:tabular-nums;font-weight:700}
.cq-bar{grid-column:1/-1;height:6px;border-radius:999px;background:var(--st-neutro-bg);border:1px solid var(--st-neutro-line);overflow:hidden}
.cq-bar i{display:block;height:100%;background:var(--vinho)}
.cq-info{display:flex;align-items:flex-start;gap:.4rem;font-size:.78rem;color:var(--text-muted);margin:0}
.cq-info svg{flex-shrink:0;margin-top:2px}
.cq-info b{color:var(--text)}
.cq-card{border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);min-width:0}
.cq-card-topo{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.5rem;padding:.55rem .75rem;border-bottom:1px solid var(--border)}
.cq-card-topo .cq-tit{font-size:.75rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-accent)}
.cq-tabwrap{overflow:auto;max-height:calc(100vh - 220px);min-height:240px}
.cq-tab{margin:0}
.cq-tab thead th{position:sticky;top:0;z-index:1;background:var(--thead-bg)}
.cq-sort{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:.3rem;text-transform:inherit;letter-spacing:inherit;font:inherit;color:inherit;white-space:nowrap}
.cq-sort:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
th[aria-sort] .cq-sort{text-decoration:underline;text-underline-offset:3px}
.cq-r{text-align:right}
.cq-mudo{color:var(--text-muted);font-size:.75rem}
.cq-chips{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.25rem}
.cq-chips .st-chip,.cq-chips .st-pill{font-size:.68rem}
.cq-valor{font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.cq-valor.rec{color:var(--st-pago-fg)}
.cq-item{display:block;font-size:.68rem;font-weight:500;color:var(--text-muted);white-space:nowrap}
.cq-ac{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:.3rem}
.cq-ac .btn-ghost{display:inline-flex;align-items:center;gap:.3rem;font-size:.72rem;padding:.3rem .55rem;min-height:30px}
.cq-ac .cq-fat{display:inline-flex;align-items:center;gap:.3rem;font-size:.7rem;color:var(--text-muted);padding:0 .3rem;white-space:nowrap}
.cq-vazio{display:flex;flex-direction:column;align-items:center;gap:.4rem;text-align:center;padding:2rem 1rem;color:var(--text-muted);border:1px dashed var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);margin:.75rem}
.cq-vazio b{color:var(--text);font-size:.95rem}
.cq-vazio .cq-acoes{justify-content:center;margin-top:.4rem}
.cq-alerta{display:flex;gap:.55rem;align-items:flex-start;padding:.65rem .8rem;border:1px solid var(--st-aberto-line);background:var(--st-aberto-bg);color:var(--st-aberto-fg);border-radius:var(--r-sm);font-size:.8rem}
.cq-alerta.erro{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.cq-alerta svg{flex-shrink:0;margin-top:1px}
.cq-alerta p{margin:.15rem 0 0}
.cq-livro-res{display:flex;flex-wrap:wrap;gap:.3rem 1.1rem;padding:.55rem .75rem;border-bottom:1px solid var(--border);font-size:.8rem;color:var(--text-muted)}
.cq-livro-res b{color:var(--text);font-variant-numeric:tabular-nums}
.cq-livro-res .cq-conta{display:inline-flex;align-items:center;gap:.35rem;color:var(--text);font-weight:700}
.cq-saldo-ini td{color:var(--text-muted);font-style:italic}
.cq-neg{color:var(--st-venc-fg)}
@media (max-width:1180px){.cq-filtros{grid-template-columns:1fr 1fr}.cq-filtros .cq-bloco:last-child{grid-column:1/-1}.cq-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:767px){
  .cq-in,.cq-seg button,.cq-btn,.cq .btn-ghost,.cq .btn-primary,.cq-filtros button{min-height:44px}
  .cq-in{font-size:16px}
  .cq-ac .btn-ghost{min-height:44px;padding:.3rem .7rem}
}
@media (max-width:640px){
  .cq-filtros{grid-template-columns:minmax(0,1fr)}
  .cq-seg{display:flex;width:100%}.cq-seg button{flex:1 1 0;justify-content:center;padding:0 .4rem}
  .cq-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .cq-kpis>:last-child{grid-column:1/-1}
  .cq-tabwrap{max-height:none;min-height:0;overflow:visible}
  .cq-tab thead{display:none}
  .cq-tab,.cq-tab tbody{display:block;width:100%}
  .cq-tab tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.15rem .6rem;padding:.7rem .75rem}
  .cq-tab tbody td{display:block;padding:0!important;border:0;min-width:0}
  .cq-tab tbody td.c-data{grid-column:1;order:0;font-weight:700}
  .cq-tab tbody td.c-valor{grid-column:2;order:1;text-align:right}
  .cq-tab tbody td.c-desc{grid-column:1/-1;order:2}
  .cq-tab tbody td.c-x{grid-column:1/-1;order:3}
  .cq-tab tbody td.c-x[data-rotulo]::before{content:attr(data-rotulo) ": ";color:var(--text-muted)}
  .cq-tab tbody td.c-x:empty{display:none}
  .cq-tab tbody td.c-ac{grid-column:1/-1;order:4;margin-top:.35rem}
  .cq-ac{justify-content:flex-start}
  .cq-tab tbody tr.cq-saldo-ini{display:flex;justify-content:space-between}
}
`;

/** Botões segmentados (aria-pressed) com rótulo de grupo. */
function Segmentado<T extends string>({ idRotulo, rotulo, opcoes, valor, onChange, oculto }: {
  idRotulo: string; rotulo: string; opcoes: { v: T; rotulo: string; icone?: React.ReactNode }[];
  valor: T; onChange: (v: T) => void; oculto?: boolean;
}) {
  return (
    <div className={oculto ? undefined : "cq-campo cq-largo"}>
      <span id={idRotulo} className={oculto ? "sr-only" : "cq-rot"}>{rotulo}</span>
      <div className="cq-seg" role="group" aria-labelledby={idRotulo}>
        {opcoes.map((o) => (
          <button key={o.v} type="button" aria-pressed={valor === o.v} onClick={() => onChange(o.v)}>
            {o.icone}{o.rotulo}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * SeletorContaGerencial (compartilhado, não aceita `id`) com o botão que abre
 * a árvore ligado ao <label htmlFor> — o id é posto no botão depois de montar.
 */
function SeletorContaRotulado({ id, rotuloAria, ...props }: React.ComponentProps<typeof SeletorContaGerencial> & { id: string; rotuloAria?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const botao = ref.current?.querySelector("button");
    if (!botao) return;
    botao.id = id;
    if (rotuloAria) botao.setAttribute("aria-label", rotuloAria);
  }, [id, rotuloAria]);
  return <div ref={ref}><SeletorContaGerencial {...props} /></div>;
}

/** Cabeçalho ordenável: BOTÃO real dentro do <th>, com aria-sort só na coluna ativa. */
function ThOrd({ rotulo, chave, ordem, onOrdenar, direita }: {
  rotulo: string; chave: ChaveOrdem; ordem: Ordem; onOrdenar: (c: ChaveOrdem) => void; direita?: boolean;
}) {
  const ativo = ordem.chave === chave;
  const Icone = ativo ? (ordem.dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <th className={direita ? "cq-r" : undefined} aria-sort={ativo ? (ordem.dir === "asc" ? "ascending" : "descending") : undefined}>
      <button type="button" className="cq-sort" onClick={() => onOrdenar(chave)}
        title={`Ordenar por ${rotulo.toLowerCase()}`}>
        {rotulo}<Icone size={12} aria-hidden style={{ opacity: ativo ? 1 : 0.55 }} />
      </button>
    </th>
  );
}

export default function ConsultasView(props: Props): React.JSX.Element {
  const { regs, planoContas, contasBancarias, centros, fornecedores, produtos, onRecibo, onEstornado, onEditar, filtroInicial } = props;
  const admin = ehAdmin();
  const uid = useId();
  const idc = (s: string) => `${uid}-${s}`;

  const [hoje] = useState(hojeLocal);
  const padrao = useMemo(() => filtrosPadrao(hoje), [hoje]);
  const [f, setF] = useState<FiltrosConsulta>(() => aplicarFiltroInicial(padrao, filtroInicial));
  const [modo, setModo] = useState<ModoConsulta>(filtroInicial?.modo ?? "lista");
  const [ordem, setOrdem] = useState<Ordem>({ chave: "data", dir: "desc" });

  // Novo filtro vindo de fora depois de montado (ex.: outro link para
  // Consultas com a tela já aberta): reaplica — ajuste durante o render, sem efeito.
  const chaveInicial = `${filtroInicial?.documento ?? ""}|${filtroInicial?.banco ?? ""}|${filtroInicial?.modo ?? ""}|${filtroInicial?.chave ?? ""}`;
  const [chaveAplicada, setChaveAplicada] = useState(chaveInicial);
  if (chaveAplicada !== chaveInicial) {
    setChaveAplicada(chaveInicial);
    setF(aplicarFiltroInicial(padrao, filtroInicial));
    if (filtroInicial?.modo) setModo(filtroInicial.modo);
  }

  const muda = <K extends keyof FiltrosConsulta>(k: K, v: FiltrosConsulta[K]) => setF((p) => ({ ...p, [k]: v }));
  const mudaMovimento = (m: Movimento) => setF((p) => {
    // Fornecedor e conta gerencial dependem do tipo: troca de movimento limpa
    // o que deixou de fazer sentido (conta de despesa "3", de receita "2").
    const tipoConta = m === "pagamento" ? "3" : m === "recebimento" ? "2" : "";
    const contaOk = !p.conta || !tipoConta || p.conta === tipoConta || p.conta.startsWith(tipoConta + ".");
    return { ...p, movimento: m, fornecedor: m === p.movimento ? p.fornecedor : "", ...(contaOk ? {} : { conta: "", contaNome: "" }) };
  });
  const limpar = () => setF(padrao);

  // ── Dados ──
  const realizados = useMemo(() => regs.filter((r) => r.data_pagamento), [regs]);
  const linhas = useMemo(() => filtrarRealizados(regs, f, casaBusca), [regs, f]);
  const resumo = useMemo(() => resumir(linhas, f.movimento), [linhas, f.movimento]);
  const ordenadas = useMemo(() => ordenarLinhas(linhas, ordem), [linhas, ordem]);
  // Regras v2 (Fase A, PR 6): o livro da conta parte do saldo de abertura cadastrado nela.
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);
  useEffect(() => { fetchContasCorrentes(hojeLocal()).then(setContasCorrentes).catch(() => {}); }, []);
  const abertura = useMemo(() => {
    const c = contasCorrentes.find((x) => x.rotulo === f.banco);
    return c && c.saldo_abertura != null && c.data_saldo_abertura ? { saldo: c.saldo_abertura, data: c.data_saldo_abertura } : null;
  }, [contasCorrentes, f.banco]);
  const livro = useMemo(() => montarLivro(regs, linhas, f, abertura), [regs, linhas, f, abertura]);
  const pagLista = usePaginacao(ordenadas);
  const pagLivro = usePaginacao(livro.linhas);
  const ativos = contarFiltrosAtivos(f, padrao);

  const opcoesCentro = useMemo(() => ordenarPt([...centros, ...realizados.map((r) => r.centro_custo)]), [centros, realizados]);
  const opcoesBanco = useMemo(() => ordenarPt([...contasBancarias, ...realizados.map((r) => r.conta_bancaria || "")]), [contasBancarias, realizados]);
  const opcoesProduto = useMemo(
    () => ordenarPt([...produtos, ...realizados.flatMap((r) => (r.itens || []).map((it) => it.produto))]),
    [produtos, realizados],
  );
  const opcoesFornecedor = useMemo(() => {
    const tipo = f.movimento === "pagamento" ? "despesa" : f.movimento === "recebimento" ? "receita" : null;
    return ordenarPt([...fornecedores, ...realizados.filter((r) => !tipo || r.tipo === tipo).map((r) => r.fornecedor)]);
  }, [fornecedores, realizados, f.movimento]);
  const rotuloContraparte = f.movimento === "recebimento" ? "Cliente" : f.movimento === "pagamento" ? "Fornecedor" : "Fornecedor ou cliente";

  const nomeConta = useMemo(() => {
    const porCodigo = new Map(planoContas.map((c) => [c.codigo, c.nome]));
    return (codigo: string) => {
      if (!codigo) return "(sem conta gerencial)";
      const nome = porCodigo.get(codigo);
      if (!nome) return codigo;
      const pai = caminhoAncestrais(codigo, planoContas)[0];
      return pai ? `${pai} › ${nome}` : nome;
    };
  }, [planoContas]);

  const ordenar = (chave: ChaveOrdem) => setOrdem((o) => (o.chave === chave
    ? { chave, dir: o.dir === "asc" ? "desc" : "asc" }
    : { chave, dir: chave === "data" || chave === "valor" ? "desc" : "asc" }));

  // ── Ações por linha ──
  const [aviso, setAviso] = useState<{ tipo: "erro" | "info"; texto: string } | null>(null);
  const [abrindoComp, setAbrindoComp] = useState<number | null>(null);
  const [confirmarEstorno, setConfirmarEstorno] = useState<Lanc | null>(null);
  const [confirmarParcelas, setConfirmarParcelas] = useState<{ lanc: Lanc; mensagem: string; parcelas: ParcelaDiferenca[] } | null>(null);
  const [avisosEstorno, setAvisosEstorno] = useState<string[] | null>(null);
  const [estornando, setEstornando] = useState<number | null>(null);

  async function abrirComprovante(l: Lanc) {
    // Abre a aba já no clique (antes do await) — senão o bloqueador de pop-up barra.
    const aba = window.open("", "_blank");
    setAbrindoComp(l.id); setAviso(null);
    try {
      const anexos = await listarAnexosLancamentoPorId(l.id);
      const alvo = anexos.find((a) => /comprovante/i.test(`${a.categoria || ""} ${a.nome_arquivo || ""}`)) || anexos[0];
      if (!alvo) {
        aba?.close();
        setAviso({ tipo: "info", texto: `O lançamento ${l.numero_lancamento || ""} não tem arquivo anexado.` });
        return;
      }
      const url = urlAnexoLancamento(alvo.id);
      if (aba) { aba.opener = null; aba.location.href = url; } else window.open(url, "_blank", "noopener");
    } catch (e) {
      aba?.close();
      setAviso({ tipo: "erro", texto: (e as Error).message || "Não foi possível abrir o comprovante." });
    } finally {
      setAbrindoComp(null);
    }
  }

  // Mesma lógica do estorno de TabelaContas (app/financeiro/page.tsx): se a
  // baixa gerou parcelas de diferença, a API responde 409 com elas e pedimos
  // uma 2ª confirmação para apagá-las junto. Confirmações em Modal, não window.confirm.
  async function estornar(l: Lanc, confirmarParcelasDiferenca = false) {
    setEstornando(l.id); setAviso(null);
    try {
      const r = await estornarPagamentoLancamento(l.id, { confirmar_parcelas_diferenca: confirmarParcelasDiferenca });
      setConfirmarEstorno(null); setConfirmarParcelas(null);
      if (r.avisos?.length) setAvisosEstorno(r.avisos);
      onEstornado();
    } catch (e) {
      const err = e as ErroApi;
      setConfirmarEstorno(null);
      if (err.status === 409 && err.detail?.parcelas) {
        setConfirmarParcelas({ lanc: l, mensagem: err.detail.mensagem || "Esta baixa gerou parcelas de diferença.", parcelas: err.detail.parcelas });
      } else {
        setConfirmarParcelas(null);
        setAviso({ tipo: "erro", texto: err.message || "Erro ao estornar o pagamento." });
      }
    } finally {
      setEstornando(null);
    }
  }

  // ── Exportação ──
  const rotuloValor = f.produto ? "Valor do item" : "Valor pago";
  const exportLista = useMemo(() => ({
    colunas: [
      { header: "Data pagamento", key: "data" }, { header: "Nº lanç.", key: "numero" }, { header: "Parcela", key: "parcela" },
      { header: "Movimento", key: "movimento" }, { header: "Descrição", key: "descricao" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
      { header: "Centro de custo", key: "centro" }, { header: "Documento", key: "documento" }, { header: "Conta gerencial", key: "conta" },
      { header: "Conta bancária", key: "banco" }, { header: rotuloValor, key: "valor" },
      ...(admin ? [{ header: "Usuário", key: "usuario" }] : []),
    ],
    linhas: ordenadas.map(({ l, valor }) => ({
      data: formatDate(l.data_pagamento || ""), numero: l.numero_lancamento || "", parcela: parcelaTxt(l),
      movimento: l.tipo === "receita" ? "Recebido" : "Pago", descricao: l.descricao, fornecedor: l.fornecedor,
      centro: l.centro_custo, documento: documentoTxt(l), conta: nomeConta(l.conta_completa || l.codigo_conta || ""),
      banco: l.conta_bancaria || "", valor: formatBRL(valor), usuario: l.usuario_nome || "",
    })),
  }), [ordenadas, admin, rotuloValor, nomeConta]);
  const exportLivro = useMemo(() => ({
    colunas: [
      { header: "Data", key: "data" }, { header: "Histórico", key: "historico" }, { header: "Fornecedor/Cliente", key: "fornecedor" },
      { header: "Nº lanç.", key: "numero" }, { header: "Entrada", key: "entrada" }, { header: "Saída", key: "saida" },
      ...(livro.banco ? [{ header: "Saldo", key: "saldo" }] : []),
    ],
    linhas: [
      ...(livro.saldoAnterior != null ? [{ data: "", historico: "Saldo anterior ao período", fornecedor: "", numero: "", entrada: "", saida: "", saldo: formatBRL(livro.saldoAnterior) }] : []),
      ...livro.linhas.map(({ l, entrada, saida, saldo }) => ({
        data: formatDate(l.data_pagamento || ""), historico: l.descricao, fornecedor: l.fornecedor, numero: l.numero_lancamento || "",
        entrada: entrada ? formatBRL(entrada) : "", saida: saida ? formatBRL(saida) : "", saldo: saldo != null ? formatBRL(saldo) : "",
      })),
    ],
  }), [livro]);
  const exp = modo === "livro" ? exportLivro : exportLista;
  const tituloExport = modo === "livro" ? `Livro caixa${livro.banco ? ` — ${livro.banco}` : ""}` : "Consultas — lançamentos realizados";

  const valorFiltroSalvo = useMemo(() => ({ ...f, modo }), [f, modo]);
  function aplicarFiltroSalvo(x: Record<string, unknown>) {
    const novo: FiltrosConsulta = { ...padrao };
    for (const k of CHAVES_FILTRO) if (typeof x[k] === "string") (novo as Record<string, string>)[k] = x[k] as string;
    if (!["pagamento", "recebimento", "ambos"].includes(novo.movimento)) novo.movimento = padrao.movimento;
    if (!["emissao", "vencimento", "pagamento"].includes(novo.periodoPor)) novo.periodoPor = padrao.periodoPor;
    setF(novo);
    if (x.modo === "lista" || x.modo === "livro") setModo(x.modo);
  }

  const tiposConta: ("despesa" | "receita")[] =
    f.movimento === "pagamento" ? ["despesa"] : f.movimento === "recebimento" ? ["receita"] : ["despesa", "receita"];
  const maxTop = resumo.topContas[0]?.valor || 1;

  const vazio = (
    <div className="cq-vazio" role="status">
      <Search size={24} aria-hidden />
      <b>Nenhum lançamento realizado neste período — amplie as datas ou limpe filtros</b>
      <span>Consultas mostra só o que já foi pago ou recebido. O que está em aberto fica em Contas.</span>
      <div className="cq-acoes">
        <button type="button" className="btn-ghost cq-btn"
          onClick={() => setF((p) => ({ ...p, periodoPor: "pagamento", de: somaDias(hoje, -90), ate: hoje }))}>
          Ampliar para os últimos 90 dias
        </button>
        <button type="button" className="btn-ghost cq-btn" onClick={limpar} disabled={ativos === 0}>
          <Eraser size={14} aria-hidden /> Limpar filtros
        </button>
      </div>
    </div>
  );

  return (
    <div className="cq">
      <style>{CSS}</style>

      <header className="cq-head">
        <div>
          <h2>Consultas</h2>
          <p className="cq-nota"><Info size={14} aria-hidden />Aqui só aparece o que já foi pago ou recebido; para o que está em aberto use Contas.</p>
          {filtroInicial?.origem && (
            <p className="cq-nota" role="status"><Layers size={14} aria-hidden />
              <span>
                Aberto de <b style={{ color: "var(--text)" }}>{filtroInicial.origem}</b>, com o mesmo período, regime, centro e conta.
                {filtroInicial.periodoPor === "competencia" ? " A DRE pelo mês do gasto soma também o que ainda está em aberto — isso fica em Contas." : ""}
                {" "}Use o Voltar do navegador para retornar ao relatório.
              </span>
            </p>
          )}
        </div>
        <div className="cq-acoes">
          <Segmentado idRotulo={idc("modo")} rotulo="Modo de exibição" oculto opcoes={MODOS} valor={modo} onChange={setModo} />
          <ExportarBotoes titulo={tituloExport} nomeArquivoBase={modo === "livro" ? "financeiro_livro_caixa" : "financeiro_consultas"}
            colunas={exp.colunas} linhas={exp.linhas} />
        </div>
      </header>

      <section className="cq-filtros" role="search" aria-label="Filtros de Consultas">
        <div className="cq-bloco">
          <h3>O quê</h3>
          <Segmentado idRotulo={idc("mov")} rotulo="Movimento" opcoes={MOVIMENTOS} valor={f.movimento} onChange={mudaMovimento} />
        </div>

        <div className="cq-bloco">
          <h3>Quando</h3>
          <Segmentado idRotulo={idc("por")} rotulo="Período por" opcoes={CAMPOS_PERIODO} valor={f.periodoPor}
            onChange={(v) => muda("periodoPor", v)} />
          <div className="cq-campo" style={{ flexBasis: 130 }}>
            <label htmlFor={idc("de")}>De</label>
            <input id={idc("de")} type="date" className="cq-in" value={f.de} max={f.ate || undefined} onChange={(e) => muda("de", e.target.value)} />
          </div>
          <div className="cq-campo" style={{ flexBasis: 130 }}>
            <label htmlFor={idc("ate")}>Até</label>
            <input id={idc("ate")} type="date" className="cq-in" value={f.ate} min={f.de || undefined} onChange={(e) => muda("ate", e.target.value)} />
          </div>
        </div>

        <div className="cq-bloco">
          <h3>Detalhe</h3>
          <div className="cq-detalhe">
            <div className="cq-campo">
              <label htmlFor={idc("centro")}>Centro de custo</label>
              <select id={idc("centro")} className="cq-in" value={f.centro} onChange={(e) => muda("centro", e.target.value)}>
                <option value="">Todos</option>{opcoesCentro.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="cq-campo">
              <label htmlFor={idc("banco")}>Conta bancária</label>
              <select id={idc("banco")} className="cq-in" value={f.banco} onChange={(e) => muda("banco", e.target.value)}>
                <option value="">Todas</option>{opcoesBanco.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="cq-campo">
              <label htmlFor={idc("doc")}>Nº do documento</label>
              <div className="cq-busca">
                <Search size={14} aria-hidden />
                <input id={idc("doc")} type="search" className="cq-in" value={f.documento} placeholder="NF, lançamento ou OS"
                  onChange={(e) => muda("documento", e.target.value)} />
              </div>
            </div>
            <div className="cq-campo">
              <label htmlFor={idc("prod")}>Produto/serviço</label>
              <select id={idc("prod")} className="cq-in" value={f.produto} onChange={(e) => muda("produto", e.target.value)}>
                <option value="">Todos</option>{opcoesProduto.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="cq-campo">
              <label htmlFor={idc("forn")}>{rotuloContraparte}</label>
              <select id={idc("forn")} className="cq-in" value={f.fornecedor} onChange={(e) => muda("fornecedor", e.target.value)}>
                <option value="">Todos</option>{opcoesFornecedor.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="cq-campo">
              <label htmlFor={idc("conta-0")}>Conta gerencial</label>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {tiposConta.map((t, i) => (
                  <SeletorContaRotulado key={t} id={idc(`conta-${i}`)}
                    rotuloAria={tiposConta.length > 1 ? `Conta gerencial de ${t}` : undefined}
                    contas={planoContas} tipo={t} codigo={f.conta} nome={f.contaNome}
                    placeholder={tiposConta.length > 1 ? `Todas (${t === "receita" ? "receita" : "despesa"})…` : "Todas…"}
                    onSelect={(codigo, nome) => setF((p) => ({ ...p, conta: codigo, contaNome: nome }))} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="cq-barra">
        <span className="cq-cont" aria-live="polite">
          {ativos === 0 ? "Sem filtros além do padrão (mês corrente, por pagamento)" : `${ativos} filtro${ativos === 1 ? "" : "s"} ativo${ativos === 1 ? "" : "s"}`}
        </span>
        <button type="button" className="btn-ghost cq-btn" onClick={limpar} disabled={ativos === 0}
          title="Volta ao padrão: ambos os movimentos, período por pagamento no mês corrente">
          <Eraser size={14} aria-hidden /> Limpar filtros
        </button>
        <FiltrosSalvos tela={TELA_FILTRO} valor={valorFiltroSalvo} aoAplicar={aplicarFiltroSalvo} />
      </div>

      <div className="cq-kpis" role="group" aria-label="Resultado dos filtros">
        <div className="st-kpi">
          <div className="l"><ArrowUpRight size={13} aria-hidden /> Total pago</div>
          <div className="v">{formatBRL(resumo.totalPago)}</div>
          <div className="s">{resumo.qtdPagamentos} pagamento{resumo.qtdPagamentos === 1 ? "" : "s"}</div>
        </div>
        <div className="st-kpi pago">
          <div className="l"><ArrowDownLeft size={13} aria-hidden /> Total recebido</div>
          <div className="v">{formatBRL(resumo.totalRecebido)}</div>
          <div className="s">{resumo.qtdRecebimentos} recebimento{resumo.qtdRecebimentos === 1 ? "" : "s"}</div>
        </div>
        <div className="st-kpi" style={{ borderBottomColor: resumo.resultado >= 0 ? "var(--st-pago-line)" : "var(--st-venc-line)" }}>
          <div className="l">{resumo.resultado >= 0 ? <TrendingUp size={13} aria-hidden /> : <TrendingDown size={13} aria-hidden />} Resultado</div>
          <div className="v" style={{ color: resumo.resultado >= 0 ? "var(--st-pago-fg)" : "var(--st-venc-fg)" }}>
            {resumo.resultado < 0 ? "− " : ""}{formatBRL(Math.abs(resumo.resultado))}
          </div>
          <div className="s">{resumo.resultado >= 0 ? "positivo" : "negativo"} · recebido − pago</div>
        </div>
        <div className="st-kpi">
          <div className="l"><List size={13} aria-hidden /> Lançamentos</div>
          <div className="v">{resumo.quantidade}</div>
          <div className="s">de {realizados.length} realizados</div>
        </div>
        <div className="st-kpi logo">
          <div className="l"><SplitSquareHorizontal size={13} aria-hidden /> Desconto/acréscimo</div>
          <div className="v">{resumo.descontoAcrescimo > 0 ? "+ " : resumo.descontoAcrescimo < 0 ? "− " : ""}{formatBRL(Math.abs(resumo.descontoAcrescimo))}</div>
          <div className="s">+{formatBRL(resumo.acrescimos)} acréscimo · −{formatBRL(resumo.descontos)} desconto</div>
        </div>
        <div className="st-kpi">
          <div className="l"><Layers size={13} aria-hidden /> Top contas gerenciais · {resumo.topBase === "receita" ? "receitas" : "despesas"}</div>
          {resumo.topContas.length ? (
            <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {resumo.topContas.map((t) => {
                const nome = nomeConta(t.codigo);
                return (
                  <li key={t.codigo || "-"} className="cq-top">
                    <span title={`${t.codigo} · ${nome}`}>{nome}</span><b>{formatBRL(t.valor)}</b>
                    <div className="cq-bar" aria-hidden><i style={{ width: `${Math.max(2, (t.valor / maxTop) * 100)}%` }} /></div>
                  </li>
                );
              })}
            </ol>
          ) : <div className="s">Nada no filtro</div>}
        </div>
      </div>

      <p className="cq-info">
        <Info size={14} aria-hidden />
        <span>
          Realizado é o valor efetivamente pago ou recebido, não o valor original da nota.{" "}
          {f.produto
            ? <b>Com produto/serviço filtrado, a soma usa só o valor do item “{f.produto}”, não a nota inteira.</b>
            : "Com produto/serviço filtrado, a soma usa o valor do item, não da nota inteira."}
        </span>
      </p>

      {aviso && (
        <div className={`cq-alerta${aviso.tipo === "erro" ? " erro" : ""}`} role={aviso.tipo === "erro" ? "alert" : "status"}>
          {aviso.tipo === "erro" ? <AlertTriangle size={16} aria-hidden /> : <Info size={16} aria-hidden />}
          <span style={{ flex: 1 }}>{aviso.texto}</span>
          <button type="button" className="btn-ghost cq-btn" onClick={() => setAviso(null)}>Fechar</button>
        </div>
      )}

      {modo === "lista" ? (
        <div className="cq-card">
          <div className="cq-card-topo">
            <span className="cq-tit">Lançamentos realizados</span>
            <span className="cq-mudo">{linhas.length} no filtro</span>
          </div>
          {!linhas.length ? vazio : (
            <>
              <div className="cq-tabwrap">
                <table className="fazenda-table cq-tab" aria-label="Lançamentos realizados">
                  <thead>
                    <tr>
                      <ThOrd rotulo="Data de pagamento" chave="data" ordem={ordem} onOrdenar={ordenar} />
                      <ThOrd rotulo="Nº lançamento" chave="numero" ordem={ordem} onOrdenar={ordenar} />
                      <ThOrd rotulo="Descrição" chave="descricao" ordem={ordem} onOrdenar={ordenar} />
                      <ThOrd rotulo="Fornecedor/Cliente" chave="fornecedor" ordem={ordem} onOrdenar={ordenar} />
                      <ThOrd rotulo="Conta bancária" chave="banco" ordem={ordem} onOrdenar={ordenar} />
                      <ThOrd rotulo={rotuloValor} chave="valor" ordem={ordem} onOrdenar={ordenar} direita />
                      {admin && <th>Usuário</th>}
                      <th className="cq-r">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagLista.linhasPagina.map(({ l, valor, soItem }) => {
                      const rec = l.tipo === "receita";
                      const sit = situacaoDe(l, hoje);
                      const doc = documentoTxt(l);
                      const da = l.desconto_acrescimo ?? 0;
                      return (
                        <tr key={l.id}>
                          <td className="c-data" style={{ whiteSpace: "nowrap" }}>{formatDate(l.data_pagamento || "")}</td>
                          <td className="c-x cq-mudo" data-rotulo="Lançamento" style={{ whiteSpace: "nowrap" }}>
                            {l.numero_lancamento || "—"}{parcelaTxt(l) ? <> · parc. {parcelaTxt(l)}</> : null}
                          </td>
                          <td className="c-desc" style={{ fontSize: "0.8rem", minWidth: 200 }}>
                            {l.descricao || "—"}
                            <div className="cq-chips">
                              {l.centro_custo && <span className="st-chip">{l.centro_custo}</span>}
                              {doc && <span className="st-chip">{doc}</span>}
                              {l.numero_os_orcamento && <span className="st-chip">OS {l.numero_os_orcamento}</span>}
                              {sit.id === "parcial" && (
                                <span className="st-pill parc" title="Baixa parcial: o restante virou outra conta, em aberto em Contas">
                                  <SplitSquareHorizontal size={11} aria-hidden /> Parcial · nota {formatBRL(l.valor)}
                                </span>
                              )}
                              {da !== 0 && <span className="st-chip">{da > 0 ? "Acréscimo" : "Desconto"} {formatBRL(Math.abs(da))}</span>}
                              {l.fatura_id ? <span className="st-pill fat"><Layers size={11} aria-hidden /> Fatura</span> : null}
                            </div>
                          </td>
                          <td className="c-x" data-rotulo={rec ? "Cliente" : "Fornecedor"} style={{ fontSize: "0.8rem" }}>{l.fornecedor || "—"}</td>
                          <td className="c-x cq-mudo" data-rotulo="Conta">{l.conta_bancaria || "—"}</td>
                          <td className="c-valor cq-r">
                            <span className={`st-pill ${rec ? "pago" : ""}`} style={{ marginBottom: 3 }}>
                              {rec ? <ArrowDownLeft size={11} aria-hidden /> : <ArrowUpRight size={11} aria-hidden />}{rec ? "Recebido" : "Pago"}
                            </span>
                            <div className={`cq-valor${rec ? " rec" : ""}`}>{rec ? "+ " : "− "}{formatBRL(valor)}</div>
                            {soItem && <span className="cq-item" title={`Nota inteira: ${formatBRL(l.valor_pago ?? l.valor)}`}>valor do item · nota {formatBRL(l.valor_pago ?? l.valor)}</span>}
                          </td>
                          {admin && <td className="c-x cq-mudo" data-rotulo="Usuário">{l.usuario_nome ?? "—"}</td>}
                          <td className="c-ac">
                            <div className="cq-ac">
                              <button type="button" className="btn-ghost" onClick={() => onRecibo(l)} title="Emitir recibo deste lançamento">
                                <Receipt size={13} aria-hidden /> Recibo
                              </button>
                              {l.tem_comprovante && (
                                <button type="button" className="btn-ghost" onClick={() => abrirComprovante(l)} disabled={abrindoComp === l.id}
                                  title="Abrir o comprovante anexado">
                                  <Paperclip size={13} aria-hidden /> {abrindoComp === l.id ? "Abrindo…" : "Comprovante"}
                                </button>
                              )}
                              <button type="button" className="btn-ghost" onClick={() => onEditar(l)} title="Editar este lançamento">
                                <Pencil size={13} aria-hidden /> Editar
                              </button>
                              {admin && (l.fatura_id
                                ? <span className="cq-fat" title="Esta nota faz parte de uma fatura de fornecedor"><Layers size={12} aria-hidden /> Estorne pela fatura</span>
                                : (
                                  <button type="button" className="btn-ghost" onClick={() => setConfirmarEstorno(l)} disabled={estornando === l.id}
                                    title="Estornar a baixa — o lançamento volta para Contas a pagar/receber">
                                    <Undo2 size={13} aria-hidden /> {estornando === l.id ? "Estornando…" : "Estornar"}
                                  </button>
                                ))}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: "0 0.75rem 0.6rem" }}>
                <Paginacao pagina={pagLista.pagina} totalPaginas={pagLista.totalPaginas} totalLinhas={pagLista.totalLinhas}
                  tamanhoPagina={pagLista.tamanhoPagina} onMudarPagina={pagLista.setPagina} onMudarTamanho={pagLista.setTamanhoPagina} />
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="cq-card">
          <div className="cq-card-topo">
            <span className="cq-tit">Livro caixa</span>
            <span className="cq-mudo">Cronológico pela data de pagamento</span>
          </div>
          {!livro.banco ? (
            <div style={{ padding: "0.75rem 0.75rem 0" }}>
              <div className="cq-alerta" role="note">
                <Info size={16} aria-hidden />
                <div>
                  <b>Saldo acumulado só com uma conta bancária escolhida.</b>
                  <p>Somar o saldo de contas diferentes não fecha com extrato nenhum, então aqui aparecem só entradas e saídas. Escolha a conta no filtro Conta bancária ou aqui:</p>
                  {opcoesBanco.length > 0 && (
                    <div className="cq-acoes" style={{ marginTop: "0.4rem" }}>
                      {opcoesBanco.map((b) => (
                        <button key={b} type="button" className="btn-ghost cq-btn" onClick={() => muda("banco", b)}>
                          <Landmark size={13} aria-hidden /> {b}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="cq-livro-res">
              <span className="cq-conta"><Landmark size={14} aria-hidden /> {livro.banco}</span>
              <span>Saldo {f.de ? `antes de ${formatDate(f.de)}` : "anterior"}: <b>{formatBRL(livro.saldoAnterior ?? 0)}</b></span>
              <span>Entradas: <b>{formatBRL(livro.totalEntradas)}</b></span>
              <span>Saídas: <b>{formatBRL(livro.totalSaidas)}</b></span>
              <span>Saldo no fim: <b className={(livro.saldoFinal ?? 0) < 0 ? "cq-neg" : undefined}>{formatBRL(livro.saldoFinal ?? 0)}</b></span>
              <span style={{ flexBasis: "100%", fontSize: "0.74rem" }}>
                Com a conta escolhida, o livro usa só a conta e o De/Até pela data de pagamento — os demais filtros não se aplicam, para o saldo fechar com o extrato.
                O saldo é o do movimento realizado lançado no sistema (não inclui saldo de abertura da conta que não esteja lançado).
              </span>
            </div>
          )}
          {!livro.linhas.length && !livro.banco ? vazio : (
            <>
              <div className="cq-tabwrap">
                <table className="fazenda-table cq-tab" aria-label={livro.banco ? `Livro caixa de ${livro.banco}` : "Livro caixa, todas as contas"}>
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Histórico</th>
                      <th className="cq-r">Entrada</th>
                      <th className="cq-r">Saída</th>
                      {livro.banco && <th className="cq-r">Saldo</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {livro.banco && pagLivro.pagina === 1 && (
                      <tr className="cq-saldo-ini">
                        <td className="c-desc" colSpan={4}>Saldo anterior ao período</td>
                        <td className="c-valor cq-r"><b>{formatBRL(livro.saldoAnterior ?? 0)}</b></td>
                      </tr>
                    )}
                    {pagLivro.linhasPagina.map(({ l, entrada, saida, saldo }) => (
                      <tr key={l.id}>
                        <td className="c-data" style={{ whiteSpace: "nowrap" }}>{formatDate(l.data_pagamento || "")}</td>
                        <td className="c-desc" style={{ fontSize: "0.8rem" }}>
                          <b>{l.fornecedor || "—"}</b>
                          <div className="cq-mudo">{l.descricao || "—"} · {l.numero_lancamento || "—"}{!livro.banco && l.conta_bancaria ? ` · ${l.conta_bancaria}` : ""}</div>
                        </td>
                        <td className="c-x cq-r" data-rotulo={entrada ? "Entrada" : undefined}>
                          {entrada ? <span className="cq-valor rec">{formatBRL(entrada)}</span> : ""}
                        </td>
                        <td className="c-x cq-r" data-rotulo={saida ? "Saída" : undefined}>
                          {saida ? <span className="cq-valor">{formatBRL(saida)}</span> : ""}
                        </td>
                        {livro.banco && (
                          <td className="c-valor cq-r">
                            <b className={saldo != null && saldo < 0 ? "cq-neg" : undefined}>{saldo != null ? formatBRL(saldo) : ""}</b>
                          </td>
                        )}
                      </tr>
                    ))}
                    {!livro.linhas.length && (
                      <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.25rem" }}>
                        Sem movimento realizado nesta conta no período.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: "0 0.75rem 0.6rem" }}>
                <Paginacao pagina={pagLivro.pagina} totalPaginas={pagLivro.totalPaginas} totalLinhas={pagLivro.totalLinhas}
                  tamanhoPagina={pagLivro.tamanhoPagina} onMudarPagina={pagLivro.setPagina} onMudarTamanho={pagLivro.setTamanhoPagina} />
              </div>
            </>
          )}
        </div>
      )}

      {confirmarEstorno && (
        <Modal title="Estornar a baixa" width="480px" onClose={() => setConfirmarEstorno(null)}>
          <p style={{ fontSize: "0.88rem", marginTop: 0 }}>
            Estornar a baixa de <b>{confirmarEstorno.numero_lancamento || "este lançamento"}</b>
            {confirmarEstorno.fornecedor ? <> ({confirmarEstorno.fornecedor})</> : null}, de{" "}
            <b>{formatBRL(confirmarEstorno.valor_pago ?? confirmarEstorno.valor)}</b>?
          </p>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
            Ele sai de Consultas e volta para Contas a {confirmarEstorno.tipo === "receita" ? "receber" : "pagar"}, em aberto. O lançamento não é excluído.
          </p>
          <div className="flex justify-end gap-2" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn-ghost" onClick={() => setConfirmarEstorno(null)} disabled={estornando !== null}>Cancelar</button>
            <button type="button" className="btn-primary" onClick={() => estornar(confirmarEstorno)} disabled={estornando !== null}>
              <Undo2 size={14} aria-hidden /> {estornando !== null ? "Estornando…" : "Estornar a baixa"}
            </button>
          </div>
        </Modal>
      )}

      {confirmarParcelas && (
        <Modal title="Estornar com parcelas de diferença" width={larguraDobrada(560)} onClose={() => setConfirmarParcelas(null)}>
          <p style={{ fontSize: "0.85rem", marginTop: 0 }}>{confirmarParcelas.mensagem}</p>
          <div className="overflow-x-auto" style={{ maxHeight: "40vh", margin: "0.75rem 0" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Parcela</th><th>Vencimento</th><th className="cq-r">Valor</th></tr></thead>
              <tbody>
                {confirmarParcelas.parcelas.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontSize: "0.8rem" }}>{p.parcela_num}/{p.parcela_total}</td>
                    <td style={{ fontSize: "0.8rem" }}>{formatDate(p.data_vencimento)}</td>
                    <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{formatBRL(p.valor_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn-ghost" onClick={() => setConfirmarParcelas(null)} disabled={estornando !== null}>Cancelar</button>
            <button type="button" className="btn-primary" onClick={() => estornar(confirmarParcelas.lanc, true)} disabled={estornando !== null}>
              {estornando !== null ? "Estornando…" : "Estornar e remover as parcelas"}
            </button>
          </div>
        </Modal>
      )}

      {avisosEstorno && (
        <Modal title="Estorno feito" width="480px" onClose={() => setAvisosEstorno(null)}>
          <div className="cq-alerta" role="status" style={{ marginBottom: "0.75rem" }}>
            <Info size={16} aria-hidden />
            <ul style={{ margin: 0, paddingLeft: "1rem" }}>{avisosEstorno.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
          <div className="flex justify-end">
            <button type="button" className="btn-primary" onClick={() => setAvisosEstorno(null)}>Entendi</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
