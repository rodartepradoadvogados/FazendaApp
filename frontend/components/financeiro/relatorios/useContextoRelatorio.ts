"use client";
// Estado da barra de contexto dos Relatórios — inteiro na URL (?per=&cmp=&cmpp=&reg=&cc=).
// Cada mudança é uma entrada nova no histórico (pushState): o link é
// compartilhável e o Voltar do navegador volta ao contexto anterior. O mesmo
// contexto vale para todos os relatórios (trocar de relatório preserva os
// parâmetros). Lê com window.location em vez de useSearchParams para não
// exigir <Suspense> na página do Financeiro (mesmo motivo de SubNavContext).
// O Next integra pushState/replaceState nativos ao roteador (ver
// node_modules/next/dist/docs/01-app/01-getting-started/04-linking-and-navigating.md).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  comparacaoDe, escreverContexto, lerContexto, periodoDe, type Comparacao, type EstadoContexto, type Periodo,
} from "@/lib/relatorioContexto";

/** Trava do relatório: o que ele NÃO deixa mudar e por quê (ex.: regras antigas = DRE da fazenda inteira).
 *  `per`/`cmp` (Fase C): o relatório fixa o período (código) ou a comparação — a URL guarda o que a
 *  pessoa escolheu nos outros relatórios; aqui vale a trava. */
export type TravasContexto = { cc?: string; reg?: EstadoContexto["reg"]; cmpOrcado?: boolean; per?: string; cmp?: EstadoContexto["cmp"]; porque?: string };

export function useContextoRelatorio(padrao: EstadoContexto, travas: TravasContexto = {}) {
  const padraoRef = useRef(padrao);
  useEffect(() => { padraoRef.current = padrao; }, [padrao]);
  const [estado, setEstado] = useState<EstadoContexto>(() =>
    typeof window === "undefined" ? padrao : lerContexto(window.location.search, padrao));
  const estadoRef = useRef(estado);
  useEffect(() => { estadoRef.current = estado; }, [estado]);

  // Primeira visita sem parâmetros: grava o padrão na URL (sem entrada nova no
  // histórico) para o link copiado já trazer o contexto completo.
  useEffect(() => {
    const busca = escreverContexto(window.location.search, estado);
    if (`?${busca}` !== window.location.search) {
      window.history.replaceState(window.history.state, "", `${window.location.pathname}?${busca}${window.location.hash}`);
    }
    // só na montagem
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Voltar/Avançar do navegador: relê a URL.
  useEffect(() => {
    const aoVoltar = () => setEstado(lerContexto(window.location.search, padraoRef.current));
    window.addEventListener("popstate", aoVoltar);
    return () => window.removeEventListener("popstate", aoVoltar);
  }, []);

  const mudar = useCallback((parcial: Partial<EstadoContexto>) => {
    const novo = { ...estadoRef.current, ...parcial };
    if (novo.cmp !== "outro") novo.cmpp = "";
    estadoRef.current = novo;
    const busca = escreverContexto(window.location.search, novo);
    window.history.pushState(window.history.state, "", `${window.location.pathname}?${busca}${window.location.hash}`);
    setEstado(novo);
  }, []);

  // O que vale de fato na tela (com as travas do relatório aplicadas).
  const efetivo: EstadoContexto = useMemo(() => ({
    ...estado,
    ...(travas.cc ? { cc: travas.cc } : {}),
    ...(travas.reg ? { reg: travas.reg } : {}),
    ...(travas.per ? { per: travas.per } : {}),
    ...(travas.cmp ? { cmp: travas.cmp, cmpp: "" } : {}),
  }), [estado, travas.cc, travas.reg, travas.per, travas.cmp]);
  const periodo: Periodo = useMemo(() => periodoDe(efetivo.per) ?? periodoDe(padrao.per)!, [efetivo.per, padrao.per]);
  const comparacao: Comparacao | null = useMemo(() => comparacaoDe(periodo, efetivo.cmp, efetivo.cmpp), [periodo, efetivo.cmp, efetivo.cmpp]);

  return { estado, efetivo, periodo, comparacao, mudar, travas };
}

export type ContextoRelatorio = ReturnType<typeof useContextoRelatorio>;

/** Drill dentro do relatório (?det=…), também no histórico: Voltar sobe um nível. */
export function useDetalheNaUrl(chave = "det") {
  const ler = () => (typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get(chave) || "");
  const [det, setDet] = useState<string>(ler);
  useEffect(() => {
    const aoVoltar = () => setDet(new URLSearchParams(window.location.search).get(chave) || "");
    window.addEventListener("popstate", aoVoltar);
    return () => window.removeEventListener("popstate", aoVoltar);
  }, [chave]);
  const abrir = useCallback((valor: string) => {
    const q = new URLSearchParams(window.location.search);
    if (valor) q.set(chave, valor); else q.delete(chave);
    window.history.pushState(window.history.state, "", `${window.location.pathname}?${q.toString()}${window.location.hash}`);
    setDet(valor);
  }, [chave]);
  return [det, abrir] as const;
}
