"use client";
// Financeiro › Resumo — a tela de entrada do módulo: o que vence (gráfico com
// período escolhido), o que pede ação, saldos por conta, a posição do dia e as
// faturas. Tudo clicável leva à tela que resolve (Contas a pagar já filtrada,
// livro caixa da conta em Consultas, Gestão de faturas, Cartão de crédito).
//
// O período (7/14/30/60/90 ou "Outro", 1 a 180 dias) é UM estado só: o gráfico
// e a Posição andam juntos. Contas puras em resumoCalculo.ts (com testes).
//
// Layout desktop (≥981px de largura e ≥600px de altura): duas colunas que
// ocupam a altura que sobra na janela, alinhadas na base, cada painel rolando
// por dentro (a página não rola). No celular, tudo empilhado.
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock, CreditCard, FileText, Info, Landmark, Layers, Lock, Wallet,
} from "lucide-react";
import {
  ehAdmin, fetchCartoesCredito, fetchContasCorrentes, fetchFaturas, fetchFaturasCartao, fetchOpcoesRetencaoPagamento,
  fetchPendenciasCaixa, formatBRL, formatDate,
  type CartaoCredito, type ContaCorrenteCadastro, type FaturaCartao, type FaturaResumo,
} from "@/lib/api";
import type { Lanc } from "@/lib/financeiroTipos";
import { diasAte, hojeLocal } from "@/lib/financeiroSituacao";
import { useRegrasV2 } from "@/lib/useRegrasV2";
import {
  PERIODOS, abertasPagar, abreviar, colunasGrafico, dataPorExtenso, diasValidos, drill, faturaFechandoEmBreve,
  ordenarFaturas, plural, posicao, proximaParcelaContrato, quandoVence, r2, topoEixo, vencidaMaisAntiga,
  type Coluna, type DrillContas, type Faixa,
} from "./resumoCalculo";

export type { DrillContas } from "./resumoCalculo";

type Props = {
  regs: Lanc[];                               // todos os lançamentos já carregados
  onDrill: (d: DrillContas) => void;          // abre Contas a pagar já filtrada (vencimento de/até, status não pago)
  onAbrirLivro: (conta: string) => void;      // abre Consultas no modo Livro caixa daquela conta (rótulo da conta)
  onAbrirFaturas: () => void;                 // Gestão de faturas
  onAbrirCartao: () => void;                  // aba Cartão de crédito
  onBaixar: (l: Lanc) => void;                // abre Contas a pagar com a baixa daquela conta
  onIrParaContas: () => void;                 // botão "Ver contas a pagar"
};

type Carga<T> = { estado: "carregando" } | { estado: "erro" } | { estado: "ok"; dados: T };
type CartaoFaturas = { cartao: CartaoCredito; faturas: FaturaCartao[] };

const CHAVE_DIAS = "financeiro_resumo_dias";
const MEDIA_DESKTOP = "(min-width: 981px) and (min-height: 600px)";

// Estilos locais com prefixo "rs-" — tudo em var(--…), funciona nos temas
// claro, escuro e misto. Dourado nunca vira texto (usa --text-accent).
const CSS = `
.rs{display:flex;flex-direction:column;gap:.75rem;min-width:0}
.rs-head{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:.6rem 1rem;flex:none}
.rs-head h2{font-size:1.35rem;font-weight:700;letter-spacing:-.01em;color:var(--text);margin:0}
.rs-saud{font-size:.86rem;color:var(--text);margin:.2rem 0 0;max-width:86ch}
.rs-saud b{font-weight:700}
.rs-grid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:.75rem;min-width:0}
.rs-col{display:flex;flex-direction:column;gap:.75rem;min-width:0;min-height:0}
.rs-pan{border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);box-shadow:var(--shadow-sm);padding:.75rem .9rem;min-width:0}
.rs-pan-topo{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.5rem .75rem;margin-bottom:.55rem}
.rs-tit{font-size:.75rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-accent);margin:0}
.rs-nota{display:flex;align-items:flex-start;gap:.35rem;font-size:.76rem;color:var(--text-muted);margin:.5rem 0 0}
.rs-nota svg{flex-shrink:0;margin-top:2px}
.rs-nota b{color:var(--text);font-variant-numeric:tabular-nums}
.rs-num{font-variant-numeric:tabular-nums;white-space:nowrap}
.rs-seg{display:inline-flex;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);flex-wrap:wrap;max-width:100%;background:var(--surface)}
.rs-seg button{border:0;background:transparent;color:var(--text-muted);font:inherit;font-size:.78rem;font-weight:600;padding:0 .6rem;min-height:32px;cursor:pointer;white-space:nowrap}
.rs-seg button+button{border-left:1px solid var(--border-strong,var(--border))}
.rs-seg button:hover{color:var(--text);background:var(--surface-2)}
.rs-seg button[aria-pressed="true"]{background:var(--pill-active-bg);color:var(--pill-active-fg);box-shadow:inset 0 0 0 1px var(--pill-active-border)}
.rs-per{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem .5rem}
.rs-outro{display:inline-flex;align-items:center;gap:.35rem;font-size:.76rem;font-weight:600;color:var(--text-muted)}
.rs-outro input{width:64px;background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:var(--r-sm);padding:0 .45rem;min-height:32px;font:inherit;font-size:.8rem;text-align:right}
.rs-outro input[aria-invalid="true"]{border-color:var(--st-venc-line)}
.rs-graf{width:100%;min-width:0}
.rs-graf svg{display:block;width:100%;height:auto;overflow:visible}
.rs-graf text{font-family:inherit;font-size:11px;fill:var(--text-muted)}
.rs-graf .rs-gl{stroke:var(--border);stroke-width:1}
.rs-graf .rs-val{fill:var(--text);font-weight:700}
.rs-graf .rs-hj{fill:var(--text);font-weight:700}
.rs-graf .rs-hit{fill:transparent}
.rs-graf g.rs-c:hover .rs-hit{fill:var(--surface-2)}
.rs-b-venc{fill:var(--st-venc-fg)}.rs-b-logo{fill:var(--st-logo-fg)}.rs-b-aberto{fill:var(--st-aberto-fg)}
.rs-leg{display:flex;flex-wrap:wrap;align-items:center;gap:.3rem .9rem;font-size:.75rem;color:var(--text-muted);margin-top:.35rem}
.rs-leg>span{display:inline-flex;align-items:center;gap:.35rem}
.rs-leg .rs-depois{margin-left:auto}
.rs-dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0;background:var(--st-neutro-line)}
.rs-dot.venc{background:var(--st-venc-fg)}.rs-dot.logo{background:var(--st-logo-fg)}.rs-dot.aberto{background:var(--st-aberto-fg)}.rs-dot.pago{background:var(--st-pago-fg)}
.rs-lk{background:none;border:0;padding:0;font:inherit;color:inherit;cursor:pointer;text-align:inherit;text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px}
.rs-lk:hover{color:var(--text)}
.rs-lk b{color:var(--text)}
.rs-fila{list-style:none;margin:0;padding:0}
.rs-fila li{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:.65rem;align-items:center;padding:.6rem 0;border-bottom:1px solid var(--border)}
.rs-fila li:last-child{border-bottom:0}
.rs-fila b{display:block;font-size:.88rem;color:var(--text);overflow-wrap:anywhere}
.rs-fila small{display:block;font-size:.76rem;color:var(--text-muted);margin-top:1px}
.rs-ic{display:inline-flex}.rs-ic.venc{color:var(--st-venc-fg)}.rs-ic.logo{color:var(--st-logo-fg)}.rs-ic.aberto{color:var(--st-aberto-fg)}.rs-ic.fat{color:var(--st-fat-fg)}.rs-ic.pago{color:var(--st-pago-fg)}
.rs-acao{font-size:.78rem;padding:.35rem .8rem;white-space:nowrap;text-decoration:none;display:inline-flex;align-items:center;gap:.35rem}
.rs-saldo{display:flex;align-items:center;gap:.7rem;width:100%;padding:.45rem .7rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);cursor:pointer;font:inherit;color:var(--text);text-align:left;margin-bottom:.4rem}
.rs-saldo:hover{background:var(--surface-2)}
.rs-saldo>svg:first-child{color:var(--text-muted);flex-shrink:0}
.rs-saldo .rs-nome{flex:1 1 auto;min-width:0}
.rs-saldo .rs-nome b{display:block;font-size:.88rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-saldo .rs-nome small{display:block;font-size:.74rem;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-saldo .rs-v{font-weight:700;font-size:.95rem}
.rs-neg{color:var(--st-venc-fg)}
.rs-pos-l{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.rs-lin{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.15rem .8rem;align-items:baseline;width:100%;padding:.32rem .35rem;margin:0 -.35rem;border:0;border-radius:var(--r-sm);background:transparent;font:inherit;font-size:.85rem;color:var(--text-muted);text-align:left;box-sizing:content-box}
button.rs-lin{cursor:pointer}
button.rs-lin:hover{background:var(--surface-2);color:var(--text)}
button.rs-lin:hover .rs-rot{text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px}
.rs-lin .rs-rot{display:inline-flex;align-items:center;gap:.45rem;min-width:0}
.rs-lin .rs-qt{font-size:.72rem;color:var(--text-muted);font-weight:400}
.rs-lin .rs-v{font-weight:700;color:var(--text);text-align:right}
.rs-lin.forte{color:var(--text);font-weight:600}
.rs-sep{border-top:1px solid var(--border);margin:.3rem 0}
.rs-final{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.35rem .8rem;margin-top:.35rem;padding:.5rem .6rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface-2)}
.rs-final .rs-rot{font-size:.85rem;font-weight:600;color:var(--text)}
.rs-final .rs-v{font-weight:800;font-size:1.05rem}
.rs-final .rs-v.ok{color:var(--st-pago-fg)}
.rs-fat-l{list-style:none;margin:0;padding:0}
.rs-fat{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.15rem .8rem;align-items:center;width:100%;padding:.45rem .35rem;margin:0 -.35rem;border:0;border-bottom:1px solid var(--border);background:transparent;font:inherit;color:var(--text);text-align:left;cursor:pointer;box-sizing:content-box}
.rs-fat-l li:last-child .rs-fat{border-bottom:0}
.rs-fat:hover{background:var(--surface-2)}
.rs-fat .rs-q{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem .5rem;min-width:0}
.rs-fat .rs-q b{font-size:.86rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;max-width:100%}
.rs-fat small{grid-column:1/-1;font-size:.74rem;color:var(--text-muted)}
.rs-fat .rs-v{font-weight:700;text-align:right}
.rs-vazio{display:flex;flex-direction:column;align-items:center;gap:.4rem;text-align:center;padding:1.4rem 1rem;color:var(--text-muted);border:1px dashed var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);font-size:.82rem}
.rs-vazio b{color:var(--text);font-size:.92rem}
.rs-vazio svg{color:var(--st-pago-fg)}
.rs-msg{font-size:.8rem;color:var(--text-muted);margin:.25rem 0}
.rs-msg button{margin-left:.35rem}
.rs-lk:focus-visible,.rs-lin:focus-visible,.rs-fat:focus-visible,.rs-saldo:focus-visible,.rs-seg button:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
@media (max-width:980px){.rs-grid{grid-template-columns:minmax(0,1fr)}}
@media ${MEDIA_DESKTOP}{
  .rs.rs-fit .rs-grid{flex:1 1 auto;min-height:0}
  .rs.rs-fit .rs-pan{min-height:0;overflow:auto;overscroll-behavior:contain}
  .rs.rs-fit .rs-pan.nat{flex:0 0 auto}
  .rs.rs-fit .rs-pan.enc{flex:0 1 auto;min-height:96px}
  .rs.rs-fit .rs-pan.cresce{flex:1 1 0;min-height:120px}
}
@media (max-width:767px){
  .rs-seg button,.rs-outro input,.rs-acao,.rs .btn-primary,.rs .btn-ghost{min-height:44px}
  .rs-outro input{font-size:16px}
  .rs-lin{align-items:center}
  button.rs-lin{min-height:40px}
  .rs-fat,.rs-saldo{min-height:44px}
  .rs-saldo .rs-nome b,.rs-saldo .rs-nome small{white-space:normal}
  .rs-leg .rs-depois{margin-left:0;width:100%}
}
@media (max-width:480px){
  .rs-per{width:100%}
  .rs-per .rs-seg{display:flex;width:100%}.rs-per .rs-seg button{flex:1 1 0;padding:0 .3rem}
  .rs-fila li{grid-template-columns:22px minmax(0,1fr)}
  .rs-fila li>:last-child{grid-column:2;justify-self:start}
}
`;

const PILULA_FATURA: Record<"aberta" | "fechada" | "paga", ReactNode> = {
  aberta: <span className="st-pill fat"><Layers size={12} aria-hidden />Aberta</span>,
  fechada: <span className="st-pill aberto"><Lock size={12} aria-hidden />Fechada</span>,
  paga: <span className="st-pill pago"><CheckCircle2 size={12} aria-hidden />Paga</span>,
};

const dm = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : "—");
const competenciaTxt = (c: string) => (/^\d{4}-\d{2}$/.test(c) ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : c);
const ehDinheiro = (banco: string) => /caixa da fazenda|dinheiro|esp[eé]cie|cofre/i.test(banco);
const subConta = (c: ContaCorrenteCadastro) =>
  [c.agencia ? `Ag. ${c.agencia}` : "", c.numero_conta ? `C/C ${c.numero_conta}` : ""].filter(Boolean).join(" · ") || (ehDinheiro(c.banco) ? "Dinheiro em espécie" : "");
const contasTxt = (n: number) => plural(n, "conta", "contas");

function lerDiasSalvos(): number {
  if (typeof window === "undefined") return 14;
  try { return diasValidos(window.localStorage.getItem(CHAVE_DIAS) || "") ?? 14; } catch { return 14; }
}

/** Altura do bloco = o que sobra no contêiner que rola (o <main>) — a página não rola no desktop. */
function useAlturaDaJanela(ref: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mq = window.matchMedia(MEDIA_DESKTOP);
    const ajustar = () => {
      if (!mq.matches) { el.style.height = ""; el.classList.remove("rs-fit"); return; }
      const rolador = el.closest("main") as HTMLElement | null;
      const r = el.getBoundingClientRect();
      const topo = rolador ? r.top - rolador.getBoundingClientRect().top + rolador.scrollTop : r.top + window.scrollY;
      const visivel = rolador ? rolador.clientHeight : window.innerHeight;
      const respiro = 24; // padding de baixo da página (p-6)
      el.style.height = `${Math.max(560, Math.floor(visivel - topo - respiro))}px`;
      el.classList.add("rs-fit");
    };
    ajustar();
    const t = window.setTimeout(ajustar, 250); // faixas do topo (offline, suporte) podem aparecer depois
    window.addEventListener("resize", ajustar);
    mq.addEventListener("change", ajustar);
    return () => { window.clearTimeout(t); window.removeEventListener("resize", ajustar); mq.removeEventListener("change", ajustar); };
  }, [ref]);
}

/** Largura real do gráfico em px (o SVG desenha 1:1, o texto não encolhe no celular). */
function useLargura(ref: React.RefObject<HTMLDivElement | null>, inicial: number) {
  const [w, setW] = useState(inicial);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => { const x = Math.round(es[0].contentRect.width); if (x > 0) setW(Math.max(260, x)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

/** Janela baixa no desktop (notebook 768px): gráfico mais baixo para sobrar espaço aos outros painéis. */
const MEDIA_BAIXA = "(min-width: 981px) and (max-height: 820px)";
function useJanelaBaixa() {
  return useSyncExternalStore(
    (cb) => { const mq = window.matchMedia(MEDIA_BAIXA); mq.addEventListener("change", cb); return () => mq.removeEventListener("change", cb); },
    () => window.matchMedia(MEDIA_BAIXA).matches,
    () => false,
  );
}

const rotEixo = (v: number) => (v === 0 ? "0" : v >= 1e6 ? `${(v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi` : `${(v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`);

function Grafico({ cols, largura, semanal, dias, baixo }: { cols: Coluna[]; largura: number; semanal: boolean; dias: number; baixo: boolean }) {
  const W = largura, T = 18, H = baixo ? 112 : 150, B = 44, L = 44, R = 4;
  const top = topoEixo(Math.max(0, ...cols.map((c) => c.valor)));
  // A coluna "Vencidas" é 1,6× mais larga (o rótulo é maior que um dia do mês).
  const PV = 1.6, bw = (W - L - R) / (cols.length - 1 + PV);
  const x0 = (i: number) => L + (i === 0 ? 0 : (PV + i - 1) * bw), larg = (i: number) => (i === 0 ? PV * bw : bw);
  const gap = Math.max(1, Math.min(6, bw * 0.18));
  const mostraSub = bw >= 19, pulo = bw < 15 ? 2 : 1;
  const resumo = `Valor a pagar ${semanal ? "por semana" : "por dia"} de hoje até daqui a ${dias} dias, mais o vencido acumulado. `
    + cols.filter((c) => c.valor > 0).map((c) => `${c.chave === "venc" ? "Vencidas" : c.dica}: ${formatBRL(c.valor)}`).join("; ");
  return (
    <svg viewBox={`0 0 ${W} ${T + H + B}`} role="img" aria-label={resumo.trim() || "Nada a pagar no período"}>
      {[0, 0.5, 1].map((f) => {
        const y = T + (1 - f) * H;
        return <g key={f}><line className="rs-gl" x1={L} x2={W - R} y1={y} y2={y} /><text x={L - 6} y={y + 4} textAnchor="end">{rotEixo(top * f)}</text></g>;
      })}
      {cols.map((c, i) => {
        const x = x0(i) + gap, w = Math.max(1, larg(i) - gap * 2);
        const h = c.valor > 0 ? Math.max(2, (c.valor / top) * H) : 0, y = T + H - h;
        const rotulo = i === 0 || i % pulo === 1 || pulo === 1;
        return (
          <g key={c.chave} className="rs-c">
            <title>{`${c.dica}:${formatBRL(c.valor)}${c.n ? ` em ${plural(c.n, "conta", "contas")}` : ""}`}</title>
            <rect className="rs-hit" x={x0(i)} y={T - 14} width={larg(i)} height={H + 14 + B} />
            {h > 0 && <rect className={`rs-b-${c.st}`} x={x} y={y} width={w} height={h} rx={2} />}
            {h > 0 && larg(i) >= 28 && <text className="rs-val" x={x + w / 2} y={y - 5} textAnchor="middle">{abreviar(c.valor)}</text>}
            {rotulo && <text className={c.hoje ? "rs-hj" : undefined} x={x + w / 2} y={T + H + 16} textAnchor="middle" style={semanal || (i === 0 && PV * bw < 60) ? { fontSize: 10 } : undefined}>{i === 0 && PV * bw < 60 ? "Venc." : c.rotulo}</text>}
            {rotulo && mostraSub && c.sub && <text x={x + w / 2} y={T + H + 30} textAnchor="middle" style={{ fontSize: 10 }}>{c.sub}</text>}
          </g>
        );
      })}
    </svg>
  );
}

/** Linha da Posição: botão (abre Contas a pagar filtrada) ou só leitura. */
function Linha({ rotulo, faixa, valor, cor, forte, onClick, titulo }: {
  rotulo: string; faixa?: Faixa; valor?: ReactNode; cor?: string; forte?: boolean; onClick?: () => void; titulo?: string;
}) {
  const miolo = (
    <>
      <span className="rs-rot">{cor && <i className={`rs-dot ${cor}`} aria-hidden />}<span>{rotulo}{faixa && faixa.n > 0 && <span className="rs-qt"> · {contasTxt(faixa.n)}</span>}</span></span>
      <span className="rs-v rs-num">{valor ?? (faixa ? formatBRL(faixa.valor) : "")}</span>
    </>
  );
  return (
    <li>
      {onClick
        ? <button type="button" className={`rs-lin${forte ? " forte" : ""}`} onClick={onClick} title={titulo}>{miolo}</button>
        : <div className={`rs-lin${forte ? " forte" : ""}`}>{miolo}</div>}
    </li>
  );
}

type ItemFila = { chave: string; icone: ReactNode; st: string; titulo: string; sub: string; botao: string; primario?: boolean; onClick?: () => void; href?: string };

export default function ResumoView(p: Props) {
  const hoje = hojeLocal();
  const admin = ehAdmin();
  const idOutro = useId();
  const raiz = useRef<HTMLDivElement>(null);
  const caixaGraf = useRef<HTMLDivElement>(null);
  useAlturaDaJanela(raiz);
  const largura = useLargura(caixaGraf, 640);
  const janelaBaixa = useJanelaBaixa();

  // ── período (um estado só para gráfico e Posição) ──────────────────────
  const [dias, setDiasEstado] = useState<number>(lerDiasSalvos);
  const [outroTxt, setOutroTxt] = useState(() => ((PERIODOS as readonly number[]).includes(dias) ? "" : String(dias)));
  const setDias = (n: number) => {
    setDiasEstado(n);
    try { window.localStorage.setItem(CHAVE_DIAS, String(n)); } catch { /* sem armazenamento: só não lembra */ }
  };
  const outroInvalido = outroTxt.trim() !== "" && diasValidos(outroTxt) == null;

  // ── dados de fora dos lançamentos ───────────────────────────────────────
  const [contas, setContas] = useState<Carga<ContaCorrenteCadastro[]>>({ estado: "carregando" });
  const [faturas, setFaturas] = useState<Carga<FaturaResumo[]>>({ estado: "carregando" });
  const [cartoes, setCartoes] = useState<Carga<CartaoFaturas[]>>({ estado: "carregando" });
  const [termos, setTermos] = useState<{ pessoa_id: number; nome: string }[]>([]);
  const [tentativa, setTentativa] = useState(0);
  const [ftipo, setFtipo] = useState<"forn" | "cartao">("forn");

  useEffect(() => {
    let vivo = true;
    fetchContasCorrentes(hojeLocal())
      .then((d) => { if (vivo) setContas({ estado: "ok", dados: d }); })
      .catch(() => { if (vivo) setContas({ estado: "erro" }); });
    fetchFaturas()
      .then((d) => { if (vivo) setFaturas({ estado: "ok", dados: d }); })
      .catch(() => { if (vivo) setFaturas({ estado: "erro" }); });
    fetchCartoesCredito()
      .then((cs) => Promise.all(cs.filter((c) => c.ativo).map((c) => fetchFaturasCartao(c.id).then((f) => ({ cartao: c, faturas: f })).catch(() => ({ cartao: c, faturas: [] as FaturaCartao[] })))))
      .then((d) => { if (vivo) setCartoes({ estado: "ok", dados: d }); })
      .catch(() => { if (vivo) setCartoes({ estado: "erro" }); });
    if (ehAdmin()) fetchPendenciasCaixa().then((d) => { if (vivo) setTermos(d.termos_pendentes); }).catch(() => {});
    return () => { vivo = false; };
  }, [tentativa]);
  const recarregar = () => {
    setContas({ estado: "carregando" }); setFaturas({ estado: "carregando" }); setCartoes({ estado: "carregando" });
    setTentativa((t) => t + 1);
  };

  // ── contas ──────────────────────────────────────────────────────────────
  const abertas = useMemo(() => abertasPagar(p.regs), [p.regs]);
  const contasVisiveis = useMemo(
    () => (contas.estado === "ok" ? contas.dados.filter((c) => c.ativo || Math.abs(c.saldo) >= 0.005) : []),
    [contas],
  );
  const saldoContas = contas.estado === "ok" ? r2(contasVisiveis.reduce((a, c) => a + c.saldo, 0)) : null;
  const pos = useMemo(() => posicao(p.regs, hoje, dias, saldoContas), [p.regs, hoje, dias, saldoContas]);
  const semana = useMemo(() => posicao(p.regs, hoje, 7, null).sem, [p.regs, hoje]);
  const cols = useMemo(() => colunasGrafico(abertas, hoje, dias), [abertas, hoje, dias]);
  const semanal = cols.length > 1 && cols[1].sub.startsWith("sem.");

  // Cartão: fatura só vira lançamento quando é paga — não entra em "A pagar".
  const cartaoEmCurso = useMemo(() => (cartoes.estado === "ok"
    ? cartoes.dados.flatMap((c) => c.faturas.filter((f) => f.status !== "paga" && (f.valor_total ?? 0) > 0).map((f) => ({ ...f, apelido: c.cartao.apelido })))
    : []), [cartoes]);
  const totalCartao = r2(cartaoEmCurso.reduce((a, f) => a + (f.valor_total ?? 0), 0));
  // Regras v2 (Fase A, PR 5 — decisão do dono): cada compra no cartão é uma nota em
  // aberto até a fatura ser paga, então a fatura JÁ ENTRA em "A pagar".
  const regrasV2 = useRegrasV2();
  const cartaoNasContas = useMemo(() => r2(abertas.filter((l) => l.fatura_cartao_id).reduce((a, l) => a + l.valor, 0)), [abertas]);

  // ── o que pede ação ─────────────────────────────────────────────────────
  const v0 = useMemo(() => vencidaMaisAntiga(abertas, hoje), [abertas, hoje]);
  const ct = useMemo(() => proximaParcelaContrato(abertas, hoje), [abertas, hoje]);
  const [retencao, setRetencao] = useState<{ id: number; disponivel: boolean } | null>(null);
  useEffect(() => {
    if (!ct || !ehAdmin()) return;
    let vivo = true;
    fetchOpcoesRetencaoPagamento({ lancamentoId: ct.id, valor: ct.valor })
      .then((o) => { if (vivo) setRetencao({ id: ct.id, disponivel: !!o.disponivel }); })
      .catch(() => {});
    return () => { vivo = false; };
  }, [ct]);

  const fila = useMemo<ItemFila[]>(() => {
    const xs: ItemFila[] = [];
    if (v0) {
      const outras = pos.vencido.n - 1;
      xs.push({
        chave: "venc", icone: <AlertTriangle size={18} aria-hidden />, st: "venc",
        titulo: `${v0.fornecedor || v0.descricao || "Conta"} · ${formatBRL(v0.valor)}`,
        sub: `Venceu em ${dm(v0.data_vencimento)}, há ${plural(-diasAte(v0.data_vencimento!, hoje), "dia", "dias")}${v0.fatura_id ? " · está numa fatura" : ""}${outras > 0 ? ` · mais ${plural(outras, "vencida", "vencidas")}` : ""}`,
        botao: v0.fatura_id ? "Abrir fatura" : "Dar baixa", primario: true,
        onClick: v0.fatura_id ? p.onAbrirFaturas : () => p.onBaixar(v0),
      });
    }
    if (ct && ct.id !== v0?.id) {
      const empreita = ct.tipo_documento === "Empreitada";
      const parc = ct.parcela_total && ct.parcela_total > 1 ? `parcela ${ct.parcela_num ?? "?"}/${ct.parcela_total} ` : "";
      const ret = admin && retencao?.id === ct.id && retencao.disponivel ? " · retenção do caixa disponível" : "";
      xs.push({
        chave: "contrato", icone: <Clock size={18} aria-hidden />, st: "logo",
        titulo: `${ct.fornecedor || "Colaborador"} · ${parc ? `${parc}${empreita ? "da empreita" : "do contrato"}` : empreita ? "empreita" : "contrato"}`,
        sub: `${quandoVence(ct.data_vencimento!, hoje)} · ${formatBRL(ct.valor)}${ret}`,
        botao: "Dar baixa", onClick: () => p.onBaixar(ct),
      });
    }
    if (faturas.estado === "ok") {
      const ab = faturaFechandoEmBreve(faturas.dados, hoje);
      if (ab) {
        const d = diasAte(ab.data_fechamento_prevista!, hoje);
        xs.push({
          chave: "fat-ab", icone: <Layers size={18} aria-hidden />, st: "fat",
          titulo: `Fatura ${ab.rotulo} · ${ab.fornecedor}`,
          sub: `Aberta, ${d < 0 ? `devia ter fechado em ${dm(ab.data_fechamento_prevista)}` : d === 0 ? "fecha hoje" : `fecha em ${plural(d, "dia", "dias")}`} · ${plural(ab.notas, "nota", "notas")} · ${formatBRL(ab.valor_total)}`,
          botao: "Abrir", onClick: p.onAbrirFaturas,
        });
      }
      const fc = faturas.dados.filter((f) => f.status === "fechada" && f.data_vencimento && diasAte(f.data_vencimento, hoje) <= 7)
        .sort((a, b) => a.data_vencimento!.localeCompare(b.data_vencimento!))[0];
      if (fc) {
        xs.push({
          chave: "fat-fc", icone: <Layers size={18} aria-hidden />, st: diasAte(fc.data_vencimento!, hoje) < 0 ? "venc" : "logo",
          titulo: `Fatura ${fc.rotulo} · ${fc.fornecedor}`,
          sub: `Fechada · ${quandoVence(fc.data_vencimento!, hoje).toLowerCase()} · ${formatBRL(fc.valor_total)}`,
          botao: "Pagar", onClick: p.onAbrirFaturas,
        });
      }
    }
    const cc = cartaoEmCurso.filter((f) => f.status === "fechada").sort((a, b) => a.data_vencimento.localeCompare(b.data_vencimento))[0];
    if (cc && diasAte(cc.data_vencimento, hoje) <= 10) {
      xs.push({
        chave: "cartao", icone: <CreditCard size={18} aria-hidden />, st: diasAte(cc.data_vencimento, hoje) < 0 ? "venc" : "logo",
        titulo: `Fatura do cartão ${cc.apelido} · ${formatBRL(cc.valor_total ?? 0)}`,
        sub: `Fechada · ${quandoVence(cc.data_vencimento, hoje).toLowerCase()} · paga como uma conta só`,
        botao: "Pagar", onClick: p.onAbrirCartao,
      });
    }
    if (admin && termos.length) {
      xs.push({
        chave: "termos", icone: <FileText size={18} aria-hidden />, st: "aberto",
        titulo: plural(termos.length, "termo de retenção pendente", "termos de retenção pendentes"),
        sub: `Retenção do caixa sem o termo anexado: ${termos.map((t) => t.nome).join(", ")}`,
        botao: "Ver", href: "/financeiro?ir=caixa_funcionarios",
      });
    }
    return xs;
  }, [v0, ct, pos.vencido.n, hoje, faturas, cartaoEmCurso, admin, termos, retencao, p]);

  // ── textos ──────────────────────────────────────────────────────────────
  const hojeExtenso = dataPorExtenso(hoje);
  const saudacao: ReactNode = pos.aPagar.n === 0
    ? <>{hojeExtenso}. <b>Nenhuma conta a pagar em aberto.</b></>
    : pos.vencido.n > 0
      ? <>{hojeExtenso}. <b>{plural(pos.vencido.n, "conta vencida", "contas vencidas")}</b> (<span className="rs-num">{formatBRL(pos.vencido.valor)}</span>){semana.n > 0
        ? <> e <b>{semana.n} {semana.n === 1 ? "vence" : "vencem"} esta semana</b> (<span className="rs-num">{formatBRL(semana.valor)}</span>).</>
        : <>. Nada mais vence esta semana.</>}</>
      : <>{hojeExtenso}. <b>Nada vencido.</b> {semana.n > 0
        ? <>{semana.n} {semana.n === 1 ? "conta vence" : "contas vencem"} esta semana (<span className="rs-num">{formatBRL(semana.valor)}</span>).</>
        : <>Nada vence esta semana.</>}</>;

  const ir = (t: DrillContas["tipo"]) => p.onDrill(drill(t, hoje, dias));
  const valorSaldo = (v: number | null) => (contas.estado === "carregando" ? "…" : v == null ? "indisponível" : formatBRL(v));

  return (
    <div className="rs" ref={raiz}>
      <style>{CSS}</style>

      <div className="rs-head">
        <div>
          <h2>Resumo do financeiro</h2>
          <p className="rs-saud">{saudacao}</p>
        </div>
        <button type="button" className="btn-primary" onClick={p.onIrParaContas}>Ver contas a pagar</button>
      </div>

      <div className="rs-grid">
        {/* ── coluna esquerda: gráfico + fila ── */}
        <div className="rs-col">
          <section className="rs-pan nat" aria-labelledby="rs-h-venc">
            <div className="rs-pan-topo">
              <h3 id="rs-h-venc" className="rs-tit">Vencimentos dos próximos {dias} dias</h3>
              <div className="rs-per">
                <div className="rs-seg" role="group" aria-label="Período do gráfico e da posição">
                  {PERIODOS.map((n) => (
                    <button key={n} type="button" aria-pressed={dias === n} onClick={() => { setDias(n); setOutroTxt(""); }}>{n} dias</button>
                  ))}
                </div>
                <label className="rs-outro" htmlFor={idOutro}>Outro
                  <input id={idOutro} type="number" min={1} max={180} step={1} inputMode="numeric" placeholder="dias"
                    value={outroTxt} aria-invalid={outroInvalido} aria-describedby={outroInvalido ? `${idOutro}-erro` : undefined}
                    onChange={(e) => { setOutroTxt(e.target.value); const n = diasValidos(e.target.value); if (n != null) setDias(n); }} />
                </label>
                {outroInvalido && <span id={`${idOutro}-erro`} className="rs-msg" role="alert">De 1 a 180 dias.</span>}
              </div>
            </div>

            {pos.aPagar.n === 0 ? (
              <div className="rs-vazio">
                <CheckCircle2 size={22} aria-hidden />
                <b>Nenhuma conta a pagar em aberto</b>
                <span>Quando uma conta for lançada, os vencimentos aparecem aqui, dia a dia.</span>
              </div>
            ) : (
              <>
                <div className="rs-graf" ref={caixaGraf}>
                  <Grafico cols={cols} largura={largura} semanal={semanal} dias={dias} baixo={janelaBaixa} />
                  <div className="sr-only"><table>
                    <caption>Valor a pagar por {semanal ? "semana" : "dia"}, de hoje até daqui a {dias} dias, mais o vencido</caption>
                    <thead><tr><th scope="col">Quando</th><th scope="col">Valor</th><th scope="col">Contas</th></tr></thead>
                    <tbody>{cols.map((c) => <tr key={c.chave}><th scope="row">{c.dica}</th><td>{formatBRL(c.valor)}</td><td>{c.n}</td></tr>)}</tbody>
                  </table></div>
                </div>
                <div className="rs-leg">
                  <span><i className="rs-dot venc" aria-hidden />Vencidas (acumulado)</span>
                  <span><i className="rs-dot logo" aria-hidden />Até 7 dias</span>
                  {dias > 7 && <span><i className="rs-dot aberto" aria-hidden />A partir do 8º dia</span>}
                  {semanal && <span>Cada barra soma uma semana</span>}
                  <span className="rs-depois">
                    {pos.alem.n
                      ? <button type="button" className="rs-lk" onClick={() => ir("alem")}>Depois deste período: <b className="rs-num">{formatBRL(pos.alem.valor)}</b> em {plural(pos.alem.n, "parcela", "parcelas")}</button>
                      : "Nada vence depois deste período"}
                  </span>
                </div>
              </>
            )}
          </section>

          <section className="rs-pan cresce" aria-labelledby="rs-h-acao">
            <div className="rs-pan-topo"><h3 id="rs-h-acao" className="rs-tit">O que pede ação</h3></div>
            {fila.length === 0 ? (
              <p className="rs-nota" style={{ marginTop: 0 }}><CheckCircle2 size={14} aria-hidden style={{ color: "var(--st-pago-fg)" }} /><span><b>Nada pede ação agora.</b> Sem conta vencida, parcela de contrato ou fatura para fechar.</span></p>
            ) : (
              <ul className="rs-fila">
                {fila.map((it) => (
                  <li key={it.chave}>
                    <span className={`rs-ic ${it.st}`}>{it.icone}</span>
                    <div><b>{it.titulo}</b><small>{it.sub}</small></div>
                    {it.href
                      ? <a className="btn-ghost rs-acao" href={it.href}>{it.botao}</a>
                      : <button type="button" className={`${it.primario ? "btn-primary" : "btn-ghost"} rs-acao`} onClick={it.onClick}>{it.botao}</button>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* ── coluna direita: saldos, posição, faturas ── */}
        <div className="rs-col">
          <section className="rs-pan enc" aria-labelledby="rs-h-saldo">
            <div className="rs-pan-topo"><h3 id="rs-h-saldo" className="rs-tit">Saldos por conta</h3></div>
            {contas.estado === "carregando" && <p className="rs-msg" role="status">Carregando saldos…</p>}
            {contas.estado === "erro" && <p className="rs-msg" role="alert">Não foi possível carregar os saldos.<button type="button" className="rs-lk" onClick={recarregar}>Tentar de novo</button></p>}
            {contas.estado === "ok" && (contasVisiveis.length === 0 ? (
              <p className="rs-msg">Nenhuma conta corrente cadastrada. Cadastre em Configurações › Parâmetros financeiros.</p>
            ) : (
              <>
                {contasVisiveis.map((c) => (
                  <button key={c.id} type="button" className="rs-saldo" onClick={() => p.onAbrirLivro(c.rotulo)} title="Abrir o livro caixa desta conta em Consultas">
                    {ehDinheiro(c.banco) ? <Wallet size={18} aria-hidden /> : <Landmark size={18} aria-hidden />}
                    <span className="rs-nome"><b>{c.banco}</b>{subConta(c) && <small>{subConta(c)}{c.ativo ? "" : " · inativa"}</small>}</span>
                    <span className={`rs-v rs-num${c.saldo < 0 ? " rs-neg" : ""}`}>{formatBRL(c.saldo)}</span>
                    <ChevronRight size={14} aria-hidden style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                  </button>
                ))}
                <p className="rs-nota" style={{ marginTop: ".2rem" }}>
                  <span>Total <b className={saldoContas != null && saldoContas < 0 ? "rs-neg" : undefined}>{formatBRL(saldoContas ?? 0)}</b>. Clique numa conta para abrir o livro caixa dela.</span>
                </p>
              </>
            ))}
          </section>

          <section className="rs-pan enc" aria-labelledby="rs-h-pos">
            <div className="rs-pan-topo"><h3 id="rs-h-pos" className="rs-tit">Posição em {dataPorExtenso(hoje, false)}</h3></div>
            <p className="rs-nota" style={{ margin: "0 0 .4rem" }}>
              <span>Acompanha o período do gráfico: <b>próximos {dias} dias</b>. Cada linha abre Contas a pagar já filtrada.</span>
            </p>
            <ul className="rs-pos-l">
              <Linha rotulo="Vencido (até ontem)" cor="venc" faixa={pos.vencido} onClick={() => ir("venc")} titulo="Abrir Contas a pagar: vencidas até ontem" />
              <Linha rotulo={`Vence em até ${Math.min(7, dias)} ${Math.min(7, dias) === 1 ? "dia" : "dias"}`} cor="logo" faixa={pos.sem} onClick={() => ir("sem")} />
              {pos.meio && <Linha rotulo={`Vence do 8º ao ${dias}º dia`} cor="aberto" faixa={pos.meio} onClick={() => ir("meio")} />}
              <Linha rotulo="Total no período" faixa={pos.periodo} forte onClick={() => ir("ate")} titulo={`Abrir Contas a pagar: de hoje até daqui a ${dias} dias`} />
              <Linha rotulo="Depois do período" faixa={pos.alem} onClick={() => ir("alem")} />
              <li className="rs-sep" aria-hidden />
              <Linha rotulo="A pagar, total" faixa={pos.aPagar} onClick={() => ir("todas")} titulo="Abrir Contas a pagar: todas em aberto" />
              <Linha rotulo="A receber, total" cor="pago" faixa={pos.aReceber} />
              <Linha rotulo="Saldo nas contas" valor={<span className={saldoContas != null && saldoContas < 0 ? "rs-neg" : undefined}>{valorSaldo(saldoContas)}</span>} />
            </ul>
            <div className="rs-final">
              <span className="rs-rot">Saldo após pagar o período (+ vencido)</span>
              {pos.saldoAposPagar == null
                ? <span className="rs-v rs-num" style={{ color: "var(--text-muted)", fontWeight: 600 }}>{valorSaldo(null)}</span>
                : (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: ".5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {pos.saldoAposPagar < 0
                      ? <span className="st-pill venc"><AlertTriangle size={12} aria-hidden />Não cobre</span>
                      : <span className="st-pill pago"><CheckCircle2 size={12} aria-hidden />Cobre</span>}
                    <span className={`rs-v rs-num ${pos.saldoAposPagar < 0 ? "rs-neg" : "ok"}`}>{formatBRL(pos.saldoAposPagar)}</span>
                  </span>
                )}
            </div>
            {pos.semVencimento.n > 0 && (
              <p className="rs-nota"><Info size={13} aria-hidden /><span>{plural(pos.semVencimento.n, "conta sem vencimento", "contas sem vencimento")} (<b>{formatBRL(pos.semVencimento.valor)}</b>) {pos.semVencimento.n === 1 ? "entra" : "entram"} só no total a pagar.</span></p>
            )}
            <p className="rs-nota"><Layers size={13} aria-hidden /><span>Notas de fatura aberta já contam em A pagar.</span></p>
            {regrasV2 ? (cartaoNasContas > 0 && (
              <p className="rs-nota"><CreditCard size={13} aria-hidden /><span>Inclui <b>{formatBRL(cartaoNasContas)}</b> de faturas de cartão (cada compra é uma nota, paga pela fatura).</span></p>
            )) : totalCartao > 0 && (
              <p className="rs-nota"><CreditCard size={13} aria-hidden /><span>A fatura do cartão (<b>{formatBRL(totalCartao)}</b> em curso) não entra nestes totais: vira lançamento quando é paga.</span></p>
            )}
          </section>

          <section className="rs-pan cresce" aria-labelledby="rs-h-fat">
            <div className="rs-pan-topo">
              <h3 id="rs-h-fat" className="rs-tit">Faturas</h3>
              <div className="rs-seg" role="group" aria-label="Tipo de fatura">
                <button type="button" aria-pressed={ftipo === "forn"} onClick={() => setFtipo("forn")}>Fornecedor</button>
                <button type="button" aria-pressed={ftipo === "cartao"} onClick={() => setFtipo("cartao")}>Cartão de crédito</button>
              </div>
            </div>
            {ftipo === "forn" ? <FaturasFornecedor carga={faturas} hoje={hoje} onAbrir={p.onAbrirFaturas} onTentar={recarregar} />
              : <FaturasCartao carga={cartoes} onAbrir={p.onAbrirCartao} onTentar={recarregar} />}
          </section>
        </div>
      </div>
    </div>
  );
}

function FaturasFornecedor({ carga, hoje, onAbrir, onTentar }: { carga: Carga<FaturaResumo[]>; hoje: string; onAbrir: () => void; onTentar: () => void }) {
  if (carga.estado === "carregando") return <p className="rs-msg" role="status">Carregando faturas…</p>;
  if (carga.estado === "erro") return <p className="rs-msg" role="alert">Não foi possível carregar as faturas.<button type="button" className="rs-lk" onClick={onTentar}>Tentar de novo</button></p>;
  const ord = ordenarFaturas(carga.dados);
  const emCurso = ord.filter((f) => f.status !== "paga");
  const pagas = ord.filter((f) => f.status === "paga");
  const lista = [...emCurso, ...pagas.slice(0, Math.max(0, 3 - emCurso.length))];
  if (!lista.length) return <p className="rs-msg">Nenhuma fatura de fornecedor. Abra uma em Gestão de faturas para juntar as notas do mês.</p>;
  return (
    <>
      <ul className="rs-fat-l">
        {lista.map((f) => {
          const sub = f.status === "aberta"
            ? `${f.data_fechamento_prevista ? (diasAte(f.data_fechamento_prevista, hoje) < 0 ? `Devia ter fechado em ${dm(f.data_fechamento_prevista)}` : `Fecha em ${formatDate(f.data_fechamento_prevista)}`) : "Sem data de fechamento"} · ${plural(f.notas, "nota", "notas")}`
            : f.status === "fechada"
              ? `${f.data_vencimento ? `Vence em ${formatDate(f.data_vencimento)}` : f.parcelas_n ? `Parcelada em ${f.parcelas_n}x` : "Fechada"} · ${plural(f.notas, "nota", "notas")}`
              : `${f.paga_em ? `Paga em ${formatDate(f.paga_em)}` : "Paga"} · ${plural(f.notas, "nota", "notas")}`;
          return (
            <li key={f.id}>
              <button type="button" className="rs-fat" onClick={onAbrir} title="Abrir em Gestão de faturas">
                <span className="rs-q">{PILULA_FATURA[f.status]}<b>{f.rotulo} · {f.fornecedor}</b></span>
                <span className="rs-v rs-num">{formatBRL(f.valor_total)}</span>
                <small>{sub}</small>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="rs-nota">
        <span>{emCurso.length ? `${plural(emCurso.length, "fatura", "faturas")} em curso` : "Nenhuma fatura em curso"}{pagas.length ? ` · ${plural(pagas.length, "paga", "pagas")}` : ""}. <button type="button" className="rs-lk" onClick={onAbrir}>Abrir Gestão de faturas</button></span>
      </p>
    </>
  );
}

function FaturasCartao({ carga, onAbrir, onTentar }: { carga: Carga<CartaoFaturas[]>; onAbrir: () => void; onTentar: () => void }) {
  if (carga.estado === "carregando") return <p className="rs-msg" role="status">Carregando faturas do cartão…</p>;
  if (carga.estado === "erro") return <p className="rs-msg" role="alert">Não foi possível carregar os cartões.<button type="button" className="rs-lk" onClick={onTentar}>Tentar de novo</button></p>;
  const linhas = carga.dados.flatMap(({ cartao, faturas }) => {
    const emCurso = faturas.filter((f) => f.status !== "paga");
    const ultimaPaga = faturas.filter((f) => f.status === "paga").sort((a, b) => b.competencia.localeCompare(a.competencia))[0];
    return [...emCurso, ...(ultimaPaga ? [ultimaPaga] : [])].map((f) => ({ f, apelido: cartao.apelido }));
  }).sort((a, b) => (a.f.status === "paga" ? 1 : 0) - (b.f.status === "paga" ? 1 : 0) || a.f.data_vencimento.localeCompare(b.f.data_vencimento));
  return (
    <>
      {carga.dados.length === 0 ? (
        <p className="rs-msg">Nenhum cartão de crédito ativo.</p>
      ) : linhas.length === 0 ? (
        <p className="rs-msg">Nenhuma fatura de cartão ainda.</p>
      ) : (
        <ul className="rs-fat-l">
          {linhas.map(({ f, apelido }) => (
            <li key={f.id}>
              <button type="button" className="rs-fat" onClick={onAbrir} title="Abrir Cartão de crédito">
                <span className="rs-q">{PILULA_FATURA[f.status]}<b>{apelido} · {competenciaTxt(f.competencia)}</b></span>
                <span className="rs-v rs-num">{formatBRL(f.valor_total ?? 0)}</span>
                <small>{f.status === "aberta" ? `Fecha em ${formatDate(f.data_fechamento)} · vence em ${formatDate(f.data_vencimento)}` : f.status === "fechada" ? `Vence em ${formatDate(f.data_vencimento)}` : "Paga"}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="rs-nota"><CreditCard size={13} aria-hidden /><span>A fatura do cartão é paga inteira, como uma conta só. Não tem notas dentro. <button type="button" className="rs-lk" onClick={onAbrir}>Abrir Cartão de crédito</button></span></p>
    </>
  );
}
