"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { desempilhar, ehTopo, empilhar, idParaFecharComEsc, type EntradaPilha } from "@/lib/janelas";

/**
 * Pilha global de overlays (Modal, GavetaLancamento…). Um ÚNICO ouvinte de Esc
 * serve a todos: só o overlay do topo reage, e só se permitir (`fecharComEsc`).
 * Sem isso, um Modal aberto dentro de uma gaveta fechava os dois com um Esc só
 * (cada um tinha seu próprio ouvinte). A lógica pura está em lib/janelas.ts.
 */
let pilha: EntradaPilha[] = [];
const aoEscPorId = new Map<number, () => void>();
let proximoId = 1;
let ouvindo = false;

function aoTeclar(e: KeyboardEvent) {
  if (e.key !== "Escape") return;
  const id = idParaFecharComEsc(pilha);
  if (id == null) return; // pilha vazia, ou topo travado: Esc não faz nada
  e.preventDefault();
  aoEscPorId.get(id)?.();
}

function sincronizarOuvinte() {
  if (pilha.length && !ouvindo) { document.addEventListener("keydown", aoTeclar); ouvindo = true; }
  else if (!pilha.length && ouvindo) { document.removeEventListener("keydown", aoTeclar); ouvindo = false; }
}

/**
 * Registra o overlay na pilha enquanto `ativo`. `aoEsc` roda quando Esc chega ao
 * topo e `fecharComEsc` é true. Devolve `ehTopo()` para quem precisa saber se
 * ainda é a janela da frente (ex.: prender o Tab só no topo).
 */
export function useOverlay({ ativo, fecharComEsc = true, aoEsc }: { ativo: boolean; fecharComEsc?: boolean; aoEsc: () => void }) {
  const [id] = useState(() => proximoId++);
  const aoEscRef = useRef(aoEsc);
  const fecharComEscRef = useRef(fecharComEsc);
  // Últimos valores, para o ouvinte global nunca chamar um `aoEsc` velho. Roda antes dos efeitos abaixo.
  useEffect(() => { aoEscRef.current = aoEsc; fecharComEscRef.current = fecharComEsc; });

  // Entra na pilha ao ativar, sai ao desativar/desmontar (a ordem de entrada é a ordem de empilhamento).
  useEffect(() => {
    if (!ativo) return;
    aoEscPorId.set(id, () => aoEscRef.current());
    pilha = empilhar(pilha, { id, fecharComEsc: fecharComEscRef.current });
    sincronizarOuvinte();
    return () => {
      pilha = desempilhar(pilha, id);
      aoEscPorId.delete(id);
      sincronizarOuvinte();
    };
  }, [ativo, id]);

  // Trocar `fecharComEsc` com a janela aberta atualiza a flag sem mudar a posição na pilha.
  useEffect(() => {
    if (ativo && pilha.some((e) => e.id === id)) pilha = empilhar(pilha, { id, fecharComEsc });
  }, [ativo, fecharComEsc, id]);

  return { ehTopo: useCallback(() => ehTopo(pilha, id), [id]) };
}
