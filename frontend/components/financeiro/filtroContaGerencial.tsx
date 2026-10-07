"use client";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import type { ContaPlano } from "@/lib/contaGerencial";
import type { Lanc } from "@/lib/financeiroTipos";

// Código da conta gerencial de um lançamento (folha, ou o resumo por nível 1).
export const contaDoLanc = (r: Lanc) => r.conta_completa || r.codigo_conta || "";
// Uma conta selecionada casa com o próprio código e com todos os descendentes
// ("3.01" casa "3.01", "3.01.02"…) — filtro por conta e toda a subárvore.
export const casaContaGerencial = (r: Lanc, sel: string) => {
  if (!sel) return true;
  const c = contaDoLanc(r);
  return c === sel || c.startsWith(sel + ".");
};

/**
 * Filtro por CONTA GERENCIAL em árvore — reusa o mesmo SeletorContaGerencial
 * dos Lançamentos (árvore, só folha selecionável, estilo por nível). Quando o
 * contexto mistura receita e despesa (extrato, DRE, fluxo), mostra as duas
 * árvores; quando é só um tipo, mostra uma. "Limpar" volta para "Todas".
 */
export function FiltroContaGerencial({ contas, tipos, codigo, nome, onChange }: {
  contas: ContaPlano[]; tipos: ("despesa" | "receita")[];
  codigo: string; nome: string; onChange: (codigo: string, nome: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", minWidth: "220px" }}>
      {tipos.map((t) => (
        <SeletorContaGerencial
          key={t}
          contas={contas}
          tipo={t}
          codigo={codigo}
          nome={nome}
          onSelect={onChange}
          placeholder={tipos.length > 1 ? `Conta de ${t === "receita" ? "receita" : "despesa"}…` : "Todas as contas…"}
        />
      ))}
      {codigo && (
        <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem", alignSelf: "flex-start" }}
          title="Voltar a considerar todas as contas gerenciais" onClick={() => onChange("", "")}>
          Limpar conta
        </button>
      )}
    </div>
  );
}

