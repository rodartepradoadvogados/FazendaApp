"use client";
// Estado da tela de exclusão (Fase 2). Reducer simples: escolher → impacto → pronto.
// O servidor é a fonte da verdade do risco e das exigências; aqui só orquestramos.
import { useCallback, useReducer } from "react";
import type { ImpactoExclusao } from "@/lib/exclusao";

export type Etapa = "escolher" | "impacto" | "pronto";

export type Selecao = { tipo: string; id: string; titulo: string };

export type EstadoExclusao = {
  etapa: Etapa;
  selecao: Selecao | null;
  impacto: ImpactoExclusao | null;
  motivo: string;
  confirmacao: string;
  resultado: { status: string; comprovante?: string; id?: number } | null;
  erro: string | null;
  carregando: boolean;
};

type Acao =
  | { type: "escolher"; selecao: Selecao }
  | { type: "impacto"; impacto: ImpactoExclusao }
  | { type: "motivo"; valor: string }
  | { type: "confirmacao"; valor: string }
  | { type: "pronto"; resultado: EstadoExclusao["resultado"] }
  | { type: "erro"; mensagem: string }
  | { type: "carregando"; valor: boolean }
  | { type: "reiniciar" };

const inicial: EstadoExclusao = {
  etapa: "escolher", selecao: null, impacto: null, motivo: "", confirmacao: "",
  resultado: null, erro: null, carregando: false,
};

function reduzir(s: EstadoExclusao, a: Acao): EstadoExclusao {
  switch (a.type) {
    case "escolher":
      return { ...inicial, etapa: "impacto", selecao: a.selecao, carregando: true };
    case "impacto":
      return { ...s, impacto: a.impacto, carregando: false, erro: null };
    case "motivo":
      return { ...s, motivo: a.valor };
    case "confirmacao":
      return { ...s, confirmacao: a.valor };
    case "pronto":
      return { ...s, etapa: "pronto", resultado: a.resultado, carregando: false };
    case "erro":
      return { ...s, erro: a.mensagem, carregando: false };
    case "carregando":
      return { ...s, carregando: a.valor };
    case "reiniciar":
      return inicial;
  }
}

export function useExclusao() {
  const [estado, despachar] = useReducer(reduzir, inicial);

  const escolher = useCallback((selecao: Selecao) => despachar({ type: "escolher", selecao }), []);
  const setImpacto = useCallback((impacto: ImpactoExclusao) => despachar({ type: "impacto", impacto }), []);
  const setMotivo = useCallback((valor: string) => despachar({ type: "motivo", valor }), []);
  const setConfirmacao = useCallback((valor: string) => despachar({ type: "confirmacao", valor }), []);
  const pronto = useCallback((resultado: EstadoExclusao["resultado"]) => despachar({ type: "pronto", resultado }), []);
  const setErro = useCallback((mensagem: string) => despachar({ type: "erro", mensagem }), []);
  const setCarregando = useCallback((valor: boolean) => despachar({ type: "carregando", valor }), []);
  const reiniciar = useCallback(() => despachar({ type: "reiniciar" }), []);

  return { estado, escolher, setImpacto, setMotivo, setConfirmacao, pronto, setErro, setCarregando, reiniciar };
}
