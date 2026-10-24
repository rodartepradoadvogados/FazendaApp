"use client";
import { useEffect } from "react";

/**
 * Liga cada `<label>` solto ao campo logo depois dele.
 *
 * Auditoria de 24/10/2026: dezenas de telas escrevem `<label>De</label><input
 * type="date" />` sem `htmlFor`/`id`, então leitor de tela anuncia "campo de
 * edição" sem nome e clicar no rótulo não foca o campo. Em vez de editar cada
 * uma das ~100 telas, este componente (montado uma vez no layout raiz) cria o
 * vínculo no DOM: `label` sem `for` e sem controle dentro, cujo irmão seguinte
 * é um input/select/textarea sem `id` ganha um `id` gerado e o `htmlFor`.
 * Nunca mexe em rótulo já associado nem em campo que já tem nome.
 */
const CONTROLES = "INPUT,SELECT,TEXTAREA";
let contador = 0;

export function associarRotulos(raiz: ParentNode): number {
  let feitos = 0;
  for (const rotulo of Array.from(raiz.querySelectorAll("label"))) {
    if (rotulo.htmlFor || rotulo.querySelector("input,select,textarea")) continue;
    const campo = rotulo.nextElementSibling;
    if (!campo || !CONTROLES.includes(campo.tagName)) continue;
    if ((campo as HTMLInputElement).type === "hidden") continue;
    if (campo.getAttribute("aria-label") || campo.getAttribute("aria-labelledby")) continue;
    if ((campo as HTMLInputElement).labels && (campo as HTMLInputElement).labels!.length > 0) continue;
    if (!campo.id) campo.id = `campo-auto-${++contador}`;
    rotulo.htmlFor = campo.id;
    feitos++;
  }
  return feitos;
}

export function AssociarRotulos() {
  useEffect(() => {
    let quadro = 0;
    const rodar = () => { quadro = 0; associarRotulos(document); };
    const agendar = () => { if (!quadro) quadro = window.requestAnimationFrame(rodar); };
    rodar();
    const obs = new MutationObserver(agendar);
    obs.observe(document.body, { childList: true, subtree: true });
    return () => { obs.disconnect(); if (quadro) window.cancelAnimationFrame(quadro); };
  }, []);
  return null;
}
