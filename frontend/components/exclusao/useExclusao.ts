"use client";
// Estado da tela "Excluir lançamento" (3 passos): tipos → registros → confirmar. Reducer simples; o servidor é a fonte da
// verdade do risco e das exigências, aqui só orquestramos. Depois de apagar a tela VOLTA ao passo 2 (a lista recarrega,
// `recarga` sobe) e o retorno aparece na barra.
import { useCallback, useReducer } from "react";
import type { ImpactoExclusao } from "@/lib/exclusao";
import type { RegistroBusca, Retorno, TipoApi } from "@/lib/exclusaoTela";

export type Etapa = "tipos" | "registros" | "confirmar";

/** O que está em confirmação: um registro ou um lote (itens[]). `registros` = o que a lista mostrava, para a faixa "Você vai…". */
export type Alvo = {
  lote: boolean;
  itens: { tipo: string; id: string }[];
  registros: RegistroBusca[];
  /** Tipo da lista de onde veio (em "Todos os lançamentos" cada item tem o seu `tipo_real`). */
  tipoLista: string;
};

export type EstadoExclusao = {
  etapa: Etapa;
  tipo: TipoApi | null;
  alvo: Alvo | null;
  impacto: ImpactoExclusao | null;
  motivo: string;
  confirmacao: string;
  retorno: Retorno | null;
  erro: string | null;
  carregando: boolean;
  /** Sobe a cada exclusão concluída: a lista do passo 2 recarrega. */
  recarga: number;
};

type Acao =
  | { type: "tipo"; tipo: TipoApi }
  | { type: "carregando"; valor: boolean }
  | { type: "impacto"; alvo: Alvo; impacto: ImpactoExclusao }
  | { type: "motivo"; valor: string }
  | { type: "confirmacao"; valor: string }
  | { type: "concluido"; retorno: Retorno }
  | { type: "erro"; mensagem: string }
  | { type: "limparRetorno" }
  | { type: "voltarRegistros" }
  | { type: "voltarTipos" };

const inicial: EstadoExclusao = {
  etapa: "tipos", tipo: null, alvo: null, impacto: null, motivo: "", confirmacao: "",
  retorno: null, erro: null, carregando: false, recarga: 0,
};

function reduzir(s: EstadoExclusao, a: Acao): EstadoExclusao {
  switch (a.type) {
    case "tipo":
      return { ...inicial, etapa: "registros", tipo: a.tipo, recarga: s.recarga };
    case "carregando":
      return { ...s, carregando: a.valor, erro: a.valor ? null : s.erro };
    case "impacto":
      return { ...s, etapa: "confirmar", alvo: a.alvo, impacto: a.impacto, motivo: "", confirmacao: "", erro: null, carregando: false, retorno: null };
    case "motivo":
      return { ...s, motivo: a.valor };
    case "confirmacao":
      return { ...s, confirmacao: a.valor };
    case "concluido":
      return { ...s, etapa: "registros", alvo: null, impacto: null, motivo: "", confirmacao: "", retorno: a.retorno, erro: null, carregando: false, recarga: s.recarga + 1 };
    case "erro":
      return { ...s, erro: a.mensagem, carregando: false };
    case "limparRetorno":
      return { ...s, retorno: null };
    case "voltarRegistros":
      return { ...s, etapa: "registros", alvo: null, impacto: null, motivo: "", confirmacao: "", erro: null, carregando: false };
    case "voltarTipos":
      return { ...inicial, recarga: s.recarga };
  }
}

export function useExclusao() {
  const [estado, despachar] = useReducer(reduzir, inicial);

  const escolherTipo = useCallback((tipo: TipoApi) => despachar({ type: "tipo", tipo }), []);
  const setCarregando = useCallback((valor: boolean) => despachar({ type: "carregando", valor }), []);
  const setImpacto = useCallback((alvo: Alvo, impacto: ImpactoExclusao) => despachar({ type: "impacto", alvo, impacto }), []);
  const setMotivo = useCallback((valor: string) => despachar({ type: "motivo", valor }), []);
  const setConfirmacao = useCallback((valor: string) => despachar({ type: "confirmacao", valor }), []);
  const concluido = useCallback((retorno: Retorno) => despachar({ type: "concluido", retorno }), []);
  const setErro = useCallback((mensagem: string) => despachar({ type: "erro", mensagem }), []);
  const limparRetorno = useCallback(() => despachar({ type: "limparRetorno" }), []);
  const voltarRegistros = useCallback(() => despachar({ type: "voltarRegistros" }), []);
  const voltarTipos = useCallback(() => despachar({ type: "voltarTipos" }), []);

  return {
    estado, escolherTipo, setCarregando, setImpacto, setMotivo, setConfirmacao, concluido, setErro, limparRetorno,
    voltarRegistros, voltarTipos,
  };
}

export type Exclusao = ReturnType<typeof useExclusao>;
