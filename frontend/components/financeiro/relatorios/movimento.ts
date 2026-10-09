"use client";
// Movimento de CONTINUIDADE dos Relatórios (Fase C, tese em MOVIMENTO.md §2):
// ao trocar período, comparação, regime ou centro, barras/degraus/segmentos
// "morfam" do estado antigo para o novo e linhas trocam o `d` do caminho, em vez
// de piscar. Técnica FLIP com Web Animations, só `transform`, `opacity` e `d`:
//   - cada elemento animável leva `data-m="<chave estável>"`;
//   - depois de cada render medimos a caixa NOVA (getBBox/offset, que ignoram
//     transform) e animamos da caixa ANTIGA até ela;
//   - interrupção: antes de medir, toda animação em curso é cancelada — a
//     geometria do DOM já é o alvo novo, então o próximo morph parte sempre do
//     ALVO anterior, nunca de um valor intermediário (nada fica errado);
//   - primeira montagem: nada (a entrada rotineira de ≤ 300 ms é do CSS);
//   - elemento novo entra com opacidade em 200 ms; o que sai some na hora;
//   - prefers-reduced-motion: troca direta, sem morph.
import { useLayoutEffect, useRef, type RefObject } from "react";

type Caixa = { x: number; y: number; w: number; h: number; d?: string };
export const EASE_CHEGADA = "cubic-bezier(.16,1,.3,1)";

function medir(el: Element): Caixa {
  if (el instanceof SVGGraphicsElement) {
    const b = el.getBBox();
    return { x: b.x, y: b.y, w: b.width, h: b.height, d: el instanceof SVGPathElement ? el.getAttribute("d") || undefined : undefined };
  }
  const h = el as HTMLElement;
  return { x: h.offsetLeft, y: h.offsetTop, w: h.offsetWidth, h: h.offsetHeight };
}

const comandos = (d: string) => (d.match(/[a-zA-Z]/g) || []).join("");
let suportaD: boolean | null = null;
function podeMorfarD(a: string, b: string): boolean {
  if (suportaD === null) suportaD = typeof CSS !== "undefined" && CSS.supports?.("d", 'path("M0 0")') === true;
  return suportaD && comandos(a) === comandos(b);
}

export function movimentoReduzidoAgora(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Morph dos elementos `[data-m]` dentro de `ref` sempre que `gatilho` muda. */
export function useMorph(ref: RefObject<Element | null>, gatilho: unknown, duracao = 280) {
  const antes = useRef<Map<string, Caixa>>(new Map());
  const ultimo = useRef<unknown>(gatilho);
  const montado = useRef(false);
  useLayoutEffect(() => {
    const raiz = ref.current;
    if (!raiz) return;
    const mudou = montado.current && ultimo.current !== gatilho;
    ultimo.current = gatilho;
    montado.current = true;
    const reduz = movimentoReduzidoAgora();
    const novo = new Map<string, Caixa>();
    raiz.querySelectorAll<Element>("[data-m]").forEach((el) => {
      const chave = el.getAttribute("data-m")!;
      if (mudou) el.getAnimations().forEach((a) => { if (a instanceof CSSAnimation) return; a.cancel(); });
      const c = medir(el);
      novo.set(chave, c);
      if (!mudou || reduz) return;
      const v = antes.current.get(chave);
      if (!v) {
        el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: EASE_CHEGADA });
        return;
      }
      if (c.d !== undefined && v.d !== undefined) {
        if (v.d !== c.d && podeMorfarD(v.d, c.d)) {
          el.animate([{ d: `path("${v.d}")` }, { d: `path("${c.d}")` }] as Keyframe[], { duration: Math.max(duracao, 360), easing: EASE_CHEGADA });
        }
        return;
      }
      const dx = v.x - c.x, dy = v.y - c.y;
      const sx = c.w > 0.5 ? v.w / c.w : 1, sy = c.h > 0.5 ? v.h / c.h : 1;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 && Math.abs(sx - 1) < 0.005 && Math.abs(sy - 1) < 0.005) return;
      const st = (el as HTMLElement | SVGElement).style;
      if (el instanceof SVGElement) st.transformBox = "fill-box";
      st.transformOrigin = "0 0";
      st.willChange = "transform";
      const a = el.animate(
        [{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` }, { transform: "translate(0px, 0px) scale(1, 1)" }],
        { duration: duracao, easing: EASE_CHEGADA },
      );
      const limpar = () => { st.willChange = ""; };
      a.onfinish = limpar;
      a.oncancel = limpar;
    });
    antes.current = novo;
  });
}
