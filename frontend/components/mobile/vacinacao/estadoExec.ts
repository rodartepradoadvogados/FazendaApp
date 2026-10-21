"use client";
// Estado da execução de um dia no aparelho (preparação, quem aplica, modo,
// animais incluídos no curral, o que já foi registrado AQUI, "não aplicar",
// trocas de produto e decisões de carência). Fica no localStorage por fazenda
// e dia: fechar o app no meio do curral não perde nada. Os registros em si
// vão para a fila do aparelho (lib/filaSanitario.ts).
import { useCallback, useState } from "react";
import { getFazendaAtual } from "@/lib/api";
import type { CarenciaDecisaoIn, ProdutoIn } from "@/lib/sanitarioTipos";
import type { ExtraDia, FeitoLocal } from "@/lib/sanitarioCampo";
import type { Aplicador } from "./comum";

export type FeitoExec = FeitoLocal & { grupo: string; caixa: string };
export type CarenciaExec = CarenciaDecisaoIn & { enviar: boolean };
export type ExecDia = {
  preparacao: { marcados: string[]; ciencia: { nome: string; em: string; itens: string[] } | null; concluida: boolean };
  aplicador: Aplicador | null;
  modo: "tronco" | "grupo" | null;
  extras: ExtraDia[];
  feitos: FeitoExec[];
  naoAplicar: Record<string, { numero: string; motivo: string | null; em: string }>;
  trocas: Record<string, ProdutoIn>;
  carencia: Record<string, CarenciaExec>;
};

export function execVazio(): ExecDia {
  return { preparacao: { marcados: [], ciencia: null, concluida: false }, aplicador: null, modo: null, extras: [], feitos: [],
    naoAplicar: {}, trocas: {}, carencia: {} };
}

function chave(diaId: number): string {
  return `san_exec_${getFazendaAtual()?.id ?? "sem"}_${diaId}`;
}
function ler(diaId: number): ExecDia {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(chave(diaId)) : null;
    return raw ? { ...execVazio(), ...(JSON.parse(raw) as Partial<ExecDia>) } : execVazio();
  } catch {
    return execVazio();
  }
}

export function useExecDia(diaId: number): [ExecDia, (fn: (e: ExecDia) => ExecDia) => void] {
  const [estado, setEstado] = useState<ExecDia>(() => ler(diaId));
  const atualizar = useCallback((fn: (e: ExecDia) => ExecDia) => {
    setEstado((atual) => {
      const novo = fn(atual);
      try { window.localStorage.setItem(chave(diaId), JSON.stringify(novo)); } catch { /* cheio: segue em memória */ }
      return novo;
    });
  }, [diaId]);
  return [estado, atualizar];
}
