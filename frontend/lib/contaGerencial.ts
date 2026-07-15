// Utilidades do plano de contas gerenciais — hierarquia por código
// ("3", "3.01", "3.01.01", "3.01.01.01"...), estilo por nível e detecção de
// conta-folha. Usado no seletor do lançamento financeiro e na árvore de
// Configurações, para que a MESMA aparência hierárquica apareça em todo lugar.
import type { CSSProperties } from "react";

export type ContaPlano = {
  id?: number;
  codigo: string;
  nome: string;
  ativa?: boolean;
  tipo_fixo_variavel?: string | null;
  rmca_receita_leite?: boolean | null;
  rmca_custo_alimentacao?: boolean | null;
  natureza?: string | null; // "servico" | "produto" | "ambos"
};

/** Nível na hierarquia: "3" = 1, "3.01" = 2, "3.01.01" = 3, "3.01.01.01" = 4. */
export function nivelDaConta(codigo: string): number {
  return codigo.split(".").length;
}

/**
 * Estilo tipográfico por nível, conforme padrão pedido:
 *  - nível 1: negrito
 *  - nível 2: normal (sem negrito)
 *  - nível 3: itálico + transparência
 *  - nível 4+: itálico + transparência + sublinhado
 */
export function estiloNivel(nivel: number): CSSProperties {
  if (nivel <= 1) return { fontWeight: 700 };
  if (nivel === 2) return { fontWeight: 400 };
  if (nivel === 3) return { fontStyle: "italic", opacity: 0.72 };
  return { fontStyle: "italic", opacity: 0.72, textDecoration: "underline" };
}

/** Uma conta é FOLHA quando nenhuma outra usa o código dela como prefixo "X.". */
export function ehFolha(codigo: string, todosCodigos: Iterable<string>): boolean {
  const prefixo = codigo + ".";
  for (const outro of todosCodigos) {
    if (outro !== codigo && outro.startsWith(prefixo)) return false;
  }
  return true;
}

/** Prefixo raiz do tipo de lançamento: receita = "2", despesa = "3". */
export function prefixoDoTipo(tipo: "receita" | "despesa"): string {
  return tipo === "receita" ? "2" : "3";
}

/** Filhos DIRETOS de um código (um nível abaixo). Se pai === "", devolve as raízes. */
export function filhosDiretos(pai: string, contas: ContaPlano[]): ContaPlano[] {
  const nivelPai = pai ? nivelDaConta(pai) : 0;
  return contas
    .filter((c) => {
      if (pai === "") return nivelDaConta(c.codigo) === 1;
      return c.codigo.startsWith(pai + ".") && nivelDaConta(c.codigo) === nivelPai + 1;
    })
    .sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true }));
}

/** Normaliza texto para busca (minúsculas, sem acento). */
export function normalizar(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}
