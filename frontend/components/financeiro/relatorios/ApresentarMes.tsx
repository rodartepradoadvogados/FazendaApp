"use client";
// "Apresentar o mês" — o ÚNICO momento autoral e lento dos Relatórios
// (MOVIMENTO.md §1). Diálogo em tela cheia com 5 cenas sobre os MESMOS números
// do Painel do dono (DRE, Resultado por litro e Caixa real do servidor):
//   1 Receita que conta até o valor · 2 Custos em degraus · 3 O litro (margem entre
//   preço e custo) · 4 O caixa (linha do saldo + "abaixo da reserva") · 5 A decisão.
// Controles: Espaço/→/PageDown avança, ←/PageUp volta, Home/End, Esc sai (o foco
// volta ao botão). Progresso com 5 rótulos de texto (aria-current="step"),
// Reproduzir/Pausar (autoavanço de 8 s, começa pausado, para na última cena e
// quando a aba fica oculta). Celular: uma cena por tela, deslize para os lados.
// Troca de cena: sai em 120 ms e entra em 260 ms (opacidade + 12 px). Movimento
// reduzido: fade de 120 ms, sem deslocamento, sem contagem e sem autoavanço.
// Cada cena tem título e frase escritos (região aria-live) — legível sem animação.
import { useCallback, useEffect, useRef, useState, type PointerEvent as PE } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Clock, FileText, Info, Pause, Play, X } from "lucide-react";
import { brl, litros, mesCurto, mesLongo } from "@/lib/relatorioContexto";
import { degrausCascata, valorLinha, type LinhaVis } from "@/lib/relatorioDre";
import { serieLitro, temResultadoPorLitro, type RespostaLitro } from "@/lib/relatorioLitro";
import type { CaixaLite, Decisao, RespostaCaixa } from "@/lib/painelDono";
import { NumeroAnimado } from "./RelatorioShell";
import { CascataDegraus, GraficoPrecoCusto, LegendaCascata, LegendaPrecoCusto } from "./graficos";
import { GraficoSaldo, LegendaSaldo } from "./GraficoSaldo";
import { movimentoReduzidoAgora } from "./movimento";

const ROTULOS = ["Receita", "Custos", "Litro", "Caixa", "Decisão"];
const AUTO_MS = 8000;
type Cena = { titulo: string; frase: string; corpo: React.ReactNode };
const dm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const ICONE: Record<Decisao["tipo"], [typeof Info, string]> = { alerta: [AlertTriangle, "ruim"], prazo: [Clock, "aten"], contador: [FileText, ""], info: [Info, ""] };

export function ApresentarMes(p: {
  periodoLabel: string; contexto: string; linhas: LinhaVis[]; rotuloCmp: string | null;
  litro: RespostaLitro | null; caixa: CaixaLite | null; cx: RespostaCaixa | null; decisoes: Decisao[];
  onFechar: () => void; onIr: (id: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cenaRef = useRef<HTMLDivElement>(null);
  const tituloRef = useRef<HTMLHeadingElement>(null);
  const saida = useRef<Animation | null>(null);
  const toque = useRef<[number, number] | null>(null);
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(false);
  const [reduz] = useState(movimentoReduzidoAgora);

  const cenas = montarCenas(p);
  const ultimo = cenas.length - 1;

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    tituloRef.current?.focus();
  }, []);

  const ir = useCallback((k: number) => {
    const alvo = Math.max(0, Math.min(ultimo, k));
    if (saida.current) { saida.current.cancel(); saida.current = null; }
    if (alvo === i) return;
    const el = cenaRef.current;
    if (!el) { setI(alvo); return; }
    // Saída mais rápida que a entrada (120 ms); em movimento reduzido também é um fade curto.
    const a = el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, easing: "cubic-bezier(.4,0,1,1)", fill: "forwards" });
    saida.current = a;
    a.onfinish = () => { saida.current = null; setI(alvo); requestAnimationFrame(() => a.cancel()); };
  }, [i, ultimo]);

  // Autoavanço: começa pausado, 8 s por cena, para na última e com a aba oculta.
  const tocando = auto && i < ultimo && !reduz;
  useEffect(() => {
    if (!tocando) return;
    const t = window.setTimeout(() => { if (document.hidden) setAuto(false); else ir(i + 1); }, AUTO_MS);
    const oculto = () => { if (document.hidden) setAuto(false); };
    document.addEventListener("visibilitychange", oculto);
    return () => { window.clearTimeout(t); document.removeEventListener("visibilitychange", oculto); };
  }, [tocando, i, ir]);

  // O teclado vale no documento inteiro enquanto a apresentação está aberta: a cena
  // que sai leva o foco junto (o elemento some), e o atalho não pode depender dele.
  const tecla = (e: KeyboardEvent) => {
    const emControle = (e.target as HTMLElement | null)?.closest?.("button,a,input,select,textarea,summary");
    if (e.key === "ArrowRight" || e.key === "PageDown" || (e.key === " " && !emControle)) { e.preventDefault(); setAuto(false); ir(i + 1); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); setAuto(false); ir(i - 1); }
    else if (e.key === "Home") { e.preventDefault(); setAuto(false); ir(0); }
    else if (e.key === "End") { e.preventDefault(); setAuto(false); ir(ultimo); }
  };
  const inicioToque = (e: PE) => { toque.current = [e.clientX, e.clientY]; };
  const fimToque = (e: PE) => {
    const t = toque.current; toque.current = null;
    if (!t) return;
    const dx = e.clientX - t[0], dy = e.clientY - t[1];
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) { setAuto(false); ir(i + (dx < 0 ? 1 : -1)); }
  };
  const sair = () => { setAuto(false); ref.current?.close(); };
  const teclaRef = useRef(tecla);
  useEffect(() => { teclaRef.current = tecla; });
  useEffect(() => {
    const ouvir = (e: KeyboardEvent) => teclaRef.current(e);
    document.addEventListener("keydown", ouvir);
    return () => document.removeEventListener("keydown", ouvir);
  }, []);
  // Cena nova: se o foco caiu fora do diálogo (a cena antiga saiu do DOM), vai para o título novo.
  useEffect(() => {
    const d = ref.current;
    if (d && !d.contains(document.activeElement)) tituloRef.current?.focus({ preventScroll: true });
  }, [i]);
  const c = cenas[i];

  return (
    <dialog ref={ref} className="ap" aria-labelledby="ap-t" aria-describedby="ap-f"
      onClose={() => p.onFechar()}>
      <div className="ap-topo">
        <div className="lin">
          <span className="tit">Apresentar o mês · {p.periodoLabel}</span>
          <div className="acts">
            <button type="button" onClick={() => { setAuto(false); ir(i - 1); }} disabled={i === 0} aria-label="Cena anterior"><ChevronLeft size={15} aria-hidden /><span className="so-largo">Anterior</span></button>
            <button type="button" aria-pressed={tocando} disabled={reduz} title={reduz ? "Autoavanço desligado: movimento reduzido" : undefined}
              onClick={() => { if (tocando) setAuto(false); else { if (i >= ultimo) ir(0); setAuto(true); } }}>{tocando ? <><Pause size={15} aria-hidden /> Pausar</> : <><Play size={15} aria-hidden /> Reproduzir</>}</button>
            <button type="button" onClick={() => { setAuto(false); ir(i + 1); }} disabled={i === ultimo} aria-label="Próxima cena"><span className="so-largo">Próxima</span><ChevronRight size={15} aria-hidden /></button>
            <button type="button" onClick={sair}><X size={15} aria-hidden /> Sair (Esc)</button>
          </div>
        </div>
        <ol className="ap-prog" aria-label="Cenas da apresentação">
          {ROTULOS.map((r, k) => (
            <li key={r}>
              <button type="button" className={k < i ? "feita" : undefined} aria-current={k === i ? "step" : undefined}
                aria-label={`${r}${k === i ? " (cena atual)" : k < i ? " (vista)" : ""}`} onClick={() => { setAuto(false); ir(k); }}>{r}</button>
            </li>
          ))}
        </ol>
      </div>
      <div className="ap-palco" onPointerDown={inicioToque} onPointerUp={fimToque} onPointerCancel={() => { toque.current = null; }}>
        <div className="ap-cena ap-entra" key={i} ref={cenaRef}>
          <h2 id="ap-t" ref={tituloRef} tabIndex={-1}>{c.titulo}</h2>
          <p className="ap-frase" id="ap-f">{c.frase}</p>
          {c.corpo}
          <p className="ap-nota">Cena {i + 1} de {cenas.length} · números do mesmo servidor dos relatórios ({p.contexto}).</p>
        </div>
      </div>
      <p className="rl-sr" aria-live="polite">{`Cena ${i + 1} de ${cenas.length}: ${c.titulo}. ${c.frase}`}</p>
    </dialog>
  );

  function montarCenas(o: typeof p): Cena[] {
    const L = (k: string) => valorLinha(o.linhas, k);
    const rb = L("RECEITA_VENDAS"), rl = L("RECEITA_LIQUIDA"), ger = L("EBITDA"), res = L("RESULTADO_LIQUIDO"), alim = L("CUSTO_VARIAVEL");
    const cmp = (l: LinhaVis | null) => (o.rotuloCmp && l && l.b != null ? ` (${l.a - l.b >= 0 ? "+" : "−"}${brl(Math.abs(l.a - l.b), 0)} em relação a ${o.rotuloCmp})` : "");
    const a = o.litro?.atual ?? null, okL = temResultadoPorLitro(a);
    const pontos = serieLitro(o.litro).filter((x) => x.preco != null && x.custo != null);
    const degraus = degrausCascata(o.linhas);
    const cx = o.cx;
    const dur = reduz ? 0 : 1200;
    return [
      {
        titulo: "Entrou a receita",
        frase: `Em ${o.periodoLabel} entraram ${brl(rb?.a ?? 0, 0)} de receita bruta${cmp(rb)}${okL ? `: ${brl(a!.receita_leite_bruta, 0)} da venda de leite (${litros(a!.litros)})` : ""}. Depois do Funrural, do Senar e dos descontos, ficaram ${brl(rl?.a ?? 0, 0)}.`,
        corpo: (<>
          <div className="ap-grande">{rb ? <NumeroAnimado valor={rb.a} formato="brl0" duracao={dur || undefined} /> : "—"}</div>
          <div className="ap-tiles">
            <div><small>Venda de leite</small><b>{okL ? brl(a!.receita_leite_bruta, 0) : "—"}</b></div>
            <div><small>Receita líquida</small><b>{rl ? brl(rl.a, 0) : "—"}</b></div>
            <div><small>Litros entregues</small><b>{okL ? litros(a!.litros) : "—"}</b></div>
            <div><small>Preço líquido do leite</small><b>{okL ? `${brl(a!.preco_liquido_l!)}/L` : "—"}</b></div>
          </div>
        </>),
      },
      {
        titulo: "Os custos descem em degraus",
        frase: `Da receita líquida de ${brl(rl?.a ?? 0, 0)} saíram a comida e os outros custos variáveis${alim ? ` (${brl(Math.abs(alim.a), 0)})` : ""}, o pessoal e as despesas operacionais: a atividade gerou ${brl(ger?.a ?? 0, 0)} de caixa. Depois do desgaste dos bens e dos juros, o resultado foi ${brl(res?.a ?? 0, 0)}${cmp(res)}.`,
        corpo: (
          <section className="rl-painel rl-graf" aria-label="Cascata da DRE">
            <CascataDegraus degraus={degraus} descricao={`Cascata da DRE de ${o.periodoLabel}: receita bruta ${brl(rb?.a ?? 0, 0)} até o resultado ${brl(res?.a ?? 0, 0)}.`} />
            <div className="rl-leg"><LegendaCascata /></div>
          </section>
        ),
      },
      {
        titulo: "O litro",
        frase: okL
          ? `Cada litro foi vendido por ${brl(a!.preco_liquido_l!)} líquido e custou ${brl(a!.coe_l!)} de custeio: ${a!.margem_l! >= 0 ? "sobraram" : "faltaram"} ${brl(Math.abs(a!.margem_l!))} por litro. A faixa entre as linhas é a margem de cada mês.`
          : "Neste período não há litros entregues com receita do leite: não há resultado por litro.",
        corpo: okL ? (<>
          <div className="ap-grande">{a!.margem_l! < 0 ? "−" : ""}<NumeroAnimado valor={Math.abs(a!.margem_l!)} formato="brlL" duracao={dur || undefined} /><small>/L de {a!.margem_l! >= 0 ? "sobra" : "falta"}</small></div>
          {pontos.length >= 2 && (
            <section className="rl-painel rl-graf" aria-label="Preço × custo por litro">
              <GraficoPrecoCusto pontos={serieLitro(o.litro)} altura={300} duracao={reduz ? 0 : 1100}
                descricao={`Preço líquido e custo de custeio por litro, ${mesCurto(pontos[0].comp)} a ${mesCurto(pontos[pontos.length - 1].comp)}.`} />
              <div className="rl-leg"><LegendaPrecoCusto /></div>
              <details className="rl-astab"><summary>Ver os dados do gráfico em tabela</summary>
                <div className="rl-tw"><table className="fazenda-table rl-tab"><caption className="rl-sr">Preço e custo por litro</caption>
                  <thead><tr><th scope="col">Mês</th><th scope="col" className="r">Preço líquido</th><th scope="col" className="r">Custo de custeio</th></tr></thead>
                  <tbody>{pontos.map((x) => <tr key={x.comp}><th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>{mesLongo(x.comp)}</th><td className="r">{brl(x.preco!)}</td><td className="r">{brl(x.custo!)}</td></tr>)}</tbody>
                </table></div>
              </details>
            </section>
          )}
        </>) : null,
      },
      {
        titulo: "O caixa",
        frase: cx
          ? `Hoje o caixa tem ${brl(cx.saldoHoje, 0)}. ${cx.abaixoReservaEm ? `Fica abaixo da reserva de ${brl(cx.reserva, 0)} em ${dm(cx.abaixoReservaEm)}` : "Fica acima da reserva nos próximos 60 dias"}${cx.negativoEm ? ` e abaixo de zero em ${dm(cx.negativoEm)}` : ""}${cx.menor ? `; o ponto mais baixo é ${brl(cx.menor.saldo, 0)} em ${dm(cx.menor.data)}` : ""}.`
          : "O Caixa real só aparece para o administrador da fazenda.",
        corpo: cx && o.caixa ? (
          <section className="rl-painel rl-graf" aria-label="Saldo projetado">
            <GraficoSaldo serie={o.caixa.serie} reserva={cx.reserva} abaixoReservaEm={cx.abaixoReservaEm} negativoEm={cx.negativoEm} menor={cx.menor}
              lento altura={typeof window !== "undefined" && window.innerWidth <= 640 ? 240 : 320}
              descricao={`Saldo projetado: hoje ${brl(cx.saldoHoje, 0)}${cx.menor ? `, menor ${brl(cx.menor.saldo, 0)} em ${dm(cx.menor.data)}` : ""}.`} />
            <LegendaSaldo temNegativo={!!cx.menor && cx.menor.saldo < 0} />
          </section>
        ) : null,
      },
      {
        titulo: "A decisão do mês",
        frase: o.decisoes.length
          ? `${o.decisoes.length} ${o.decisoes.length === 1 ? "ponto pede" : "pontos pedem"} decisão ou ação. Cada um leva ao relatório que mostra o detalhe.`
          : "Nada pede decisão urgente neste mês: caixa acima da reserva, litro com sobra e nada sem classificação.",
        corpo: o.decisoes.length ? (
          <ul className="ap-dec">
            {o.decisoes.map((d) => {
              const [Ic, cls] = ICONE[d.tipo];
              return (
                <li key={d.chave}>
                  <span className={`ic ${cls}`}><Ic size={20} aria-hidden /></span>
                  <div><b>{d.titulo}</b><small>{d.texto}</small></div>
                  <button type="button" className="rl-btn" onClick={() => { ref.current?.close(); o.onIr(d.relatorio); }}>{d.rotulo}</button>
                </li>
              );
            })}
          </ul>
        ) : null,
      },
    ];
  }
}
