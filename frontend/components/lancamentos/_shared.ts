"use client";
import { useEffect, useState } from "react";
import { AnimalPicker } from "@/components/AnimalPicker";
import type { AnimalRow } from "@/components/AnimalModal";
import { fetchParametros } from "@/lib/api";

/* ───────────────────────── Utilitários e constantes compartilhados por
   vários formulários de Lançamentos — extraídos de app/lancamentos/page.tsx
   quando usados por mais de um Form* ao mesmo tempo (para não duplicar a
   mesma lógica em arquivos diferentes). ───────────────────────── */

/**
 * Idade mínima de aptidão a serviço, em meses.
 *
 * ATENÇÃO: isto é só o valor de partida enquanto a API não responde. O valor
 * QUE VALE é o parâmetro `idade_apta_min_meses` da fazenda (Configurações >
 * Parâmetros > Aptidão da novilha) — use `useIdadeMinServico()` abaixo.
 *
 * Aqui havia um `13` CRAVADO, e ele era a única trava de aptidão do sistema
 * inteiro: divergia do parâmetro real da fazenda (15 meses), só escondia as
 * inaptas da lista em vez de explicar por quê, e o app de campo, o bot do
 * Telegram e qualquer chamada direta à API passavam por baixo dele. A trava
 * de verdade agora é do backend (ver `backend/fazenda/rules/aptidao.py`), que
 * devolve 409 com o motivo; esta tela apenas ANTECIPA o que o backend vai
 * dizer, para o usuário não descobrir só depois de preencher tudo.
 *
 * O padrão aqui é 15 para bater com o padrão do backend
 * (`rules/parametros.py::idade_apta_min_meses`).
 */
export const IDADE_MIN_SERVICO_PADRAO = 15;

/**
 * Lê `idade_apta_min_meses` dos parâmetros da fazenda. Devolve o padrão
 * enquanto a chamada não volta (ou se ela falhar) — a tela nunca fica sem
 * um número, e nunca inventa um diferente do que o backend usaria.
 */
export function useIdadeMinServico(): number {
  const [meses, setMeses] = useState<number>(IDADE_MIN_SERVICO_PADRAO);
  useEffect(() => {
    let cancelado = false;
    fetchParametros()
      .then((d: any) => {
        const itens: any[] = d?.grupos?.aptidao_novilha?.itens ?? [];
        const valor = Number(itens.find((i) => i.chave === "idade_apta_min_meses")?.valor);
        if (!cancelado && Number.isFinite(valor) && valor > 0) setMeses(valor);
      })
      .catch(() => {});
    return () => { cancelado = true; };
  }, []);
  return meses;
}

/** Um impedimento de aptidão a serviço, do jeito que a tela precisa mostrar. */
export type InaptidaoServico = {
  /** Código estável, espelha `backend/fazenda/rules/aptidao.py`. */
  motivo: "sexo" | "inativo" | "a_descartar" | "idade";
  /** Texto curto, mostrado ao lado do animal na lista. */
  rotulo: string;
  /** True quando o backend aceitaria um "confirmar mesmo assim" (`forcar`). */
  confirmavel: boolean;
};

/**
 * Antecipa, com o que a tela já tem em mãos, os bloqueios DUROS de aptidão do
 * backend. Peso e "já gestante" não entram aqui de propósito: dependem de
 * pesagem e do serviço vigente, que a listagem de animais não carrega — esses
 * casos chegam como 409 confirmável na hora de salvar, com a mensagem certa.
 *
 * Devolve `null` para quem está apta (ou para quem não dá para afirmar nada,
 * como um animal sem idade cadastrada — não se reprova por dado ausente).
 */
export function inaptidaoServico(a: AnimalRow, idadeMinMeses: number): InaptidaoServico | null {
  if ((a.sexo || "").toUpperCase() === "M") {
    return { motivo: "sexo", rotulo: "macho — não recebe serviço", confirmavel: false };
  }
  if (a.ativo === false) {
    return { motivo: "inativo", rotulo: "baixado(a) do rebanho", confirmavel: false };
  }
  if (a.a_descartar) {
    return { motivo: "a_descartar", rotulo: "marcado(a) como a descartar", confirmavel: false };
  }
  const idade = idadeMeses(a);
  if (idade != null && idade < idadeMinMeses) {
    return {
      motivo: "idade",
      rotulo: `${idade.toFixed(1)} meses — mínimo ${idadeMinMeses}`,
      confirmavel: false,
    };
  }
  return null;
}

/** Idade em meses: da data de nascimento quando existe, senão do campo do cadastro. */
function idadeMeses(a: AnimalRow): number | null {
  if (a.data_nasc) {
    const nasc = new Date(a.data_nasc + "T00:00:00").getTime();
    if (!Number.isNaN(nasc)) return (Date.now() - nasc) / 86400000 / 30.44;
  }
  return a.idade_meses ?? null;
}

export const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];

export function addDias(iso: string, n: number): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Seleção de animal via tabela clara (Nº · Grupo · Categoria · Sit. Rep. · DEL).
export const SelectAnimal = AnimalPicker;

// Categorias prontas de animais para o lançamento em massa do protocolo sanitário
// — reaproveita o mesmo motor de critérios cumulativos de Configurações > Lotes
// (POST /lotes/preview), sem precisar criar um lote de verdade.
export const CATEGORIAS_ANIMAIS = [
  { id: "novilhas_inseminadas", label: "Novilhas inseminadas", criterios: { novilhas_inseminadas: true } },
  { id: "novilhas_gestantes", label: "Novilhas gestantes", criterios: { novilhas_gestantes: true } },
  { id: "lactacao", label: "Vacas em lactação", criterios: { status_lactacao: "lactacao" } },
  { id: "secas", label: "Vacas secas", criterios: { status_lactacao: "seca" } },
  { id: "pre_parto_15", label: "Pré-parto (próximos 15 dias)", criterios: { dias_para_parto_min: 0, dias_para_parto_max: 15 } },
  { id: "em_tratamento", label: "Em tratamento", criterios: { em_tratamento: true } },
] as const;

export const FREQUENCIA_UNIDADES = [
  { v: "dias", l: "dia(s)" }, { v: "meses", l: "mês(es)" }, { v: "anos", l: "ano(s)" },
];

// ─────────────────────── Preventivo — aplicação (vacina/exame) ───────────────────────
export type ExameDef = { id: number; nome: string; tipo_resultado: "diagnostico" | "numerico"; faixa_min: number | null; faixa_max: number | null; acao_abaixo: string | null; acao_dentro: string | null; acao_acima: string | null };
