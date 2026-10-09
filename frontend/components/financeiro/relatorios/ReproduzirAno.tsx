"use client";
// "Reproduzir o ano" (MOVIMENTO.md §3) — reutilizável: Resultado por litro hoje,
// Fluxo de caixa quando chegar. Play/pausa + controle de 12 meses (input range);
// o gráfico mostra o cursor no mês escolhido (o pai recebe `onIndice`) e os
// valores do mês sob o cursor são os do SERVIDOR (o pai passa os textos prontos).
//   - setas do teclado movem o controle (nativo do input range);
//   - `aria-valuetext` diz o mês e os valores; a leitura (dl) é aria-live polite
//     quando parado e "off" enquanto toca (para não falar 12 vezes seguidas);
//   - para sozinho no último mês, quando a aba fica oculta, quando a pessoa mexe
//     no controle e quando a tela sai; movimento reduzido: passo mais lento.
import { useEffect, useId, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { movimentoReduzidoAgora } from "./movimento";

// Estilo próprio: o componente vai em telas que não carregam os estilos da Fase C4.
const CSS_RA = `
.ra{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .9rem;margin-top:.7rem;padding:.65rem .75rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface-2)}
.ra .mes{font-weight:800;font-size:1rem;min-width:9.5rem;font-variant-numeric:tabular-nums}
.ra input[type=range]{flex:1 1 220px;min-width:0;accent-color:var(--text-accent);min-height:32px}
.ra dl{display:flex;flex-wrap:wrap;gap:.3rem 1.2rem;margin:0;flex-basis:100%}
.ra dt{font-size:.74rem;color:var(--text-muted)}
.ra dd{margin:0;font-weight:800;font-variant-numeric:tabular-nums}
@media print{.ra{display:none!important}}
`;

export type ItemAno = { chave: string; rotulo: string; campos: { nome: string; texto: string }[] };

export function ReproduzirAno({ itens, indice, onIndice, oque }: {
  itens: ItemAno[];
  /** Mês mostrado (índice em `itens`). */
  indice: number;
  onIndice: (i: number) => void;
  /** O que o controle escolhe, para o leitor de tela (ex.: "preço e custo por litro"). */
  oque: string;
}) {
  const uid = useId();
  const [tocando, setTocando] = useState(false);
  const atual = useRef(indice);
  useEffect(() => { atual.current = indice; }, [indice]);
  const ultimo = itens.length - 1;

  useEffect(() => {
    if (!tocando) return;
    const passo = movimentoReduzidoAgora() ? 1200 : 800;
    const t = window.setInterval(() => {
      if (document.hidden) { setTocando(false); return; }
      const prox = atual.current + 1;
      if (prox > ultimo) { setTocando(false); return; }
      onIndice(prox);
      if (prox === ultimo) setTocando(false);
    }, passo);
    const oculto = () => { if (document.hidden) setTocando(false); };
    document.addEventListener("visibilitychange", oculto);
    return () => { window.clearInterval(t); document.removeEventListener("visibilitychange", oculto); };
  }, [tocando, ultimo, onIndice]);

  if (itens.length < 2) return null;
  const it = itens[Math.max(0, Math.min(ultimo, indice))];
  const texto = (i: ItemAno) => `${i.rotulo}: ${i.campos.map((c) => `${c.nome} ${c.texto}`).join(", ")}`;
  const tocar = () => {
    if (tocando) { setTocando(false); return; }
    // Do começo quando já está no último mês; senão continua de onde está.
    if (indice >= ultimo) onIndice(0);
    setTocando(true);
  };
  return (
    <div className="ra rl-noprint" role="group" aria-label="Reproduzir o ano">
      <style>{CSS_RA}</style>
      <button type="button" className="rl-btn" aria-pressed={tocando} onClick={tocar}>
        {tocando ? <><Pause size={14} aria-hidden /> Pausar</> : <><Play size={14} aria-hidden /> Reproduzir o ano</>}
      </button>
      <span className="mes" aria-hidden>{it.rotulo}</span>
      <label className="rl-sr" htmlFor={`${uid}-r`}>Mês mostrado: {oque}</label>
      <input id={`${uid}-r`} type="range" min={0} max={ultimo} step={1} value={indice} aria-valuetext={texto(it)}
        onChange={(e) => { setTocando(false); onIndice(Number(e.target.value)); }} />
      <dl aria-live={tocando ? "off" : "polite"}>
        {it.campos.map((c) => (
          <div key={c.nome}><dt>{c.nome}</dt><dd>{c.texto}</dd></div>
        ))}
      </dl>
    </div>
  );
}
