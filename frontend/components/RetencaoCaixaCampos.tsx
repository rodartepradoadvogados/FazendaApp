"use client";
// "Reter no caixa do funcionário" dentro da janela de pagamento de quem NÃO é CLT (parcela de contrato/empreita,
// diária). O combinado da pessoa só SUGERE: dá para aceitar o percentual sugerido, digitar outro percentual
// (livre) ou um valor nominal em R$. Só aparece para administrador e quando o pagamento é de uma pessoa do caixa.
import { useEffect, useState } from "react";
import { fetchOpcoesRetencaoPagamento, formatBRL, type RetencaoCaixaIn, type RetencaoPagamentoOpcoes } from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";

type Escolha = "nao" | "sugestao" | "percentual" | "valor";

const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;
const campo = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.82rem",
} as const;

/** Quanto será retido, em R$, para a escolha atual (espelha o cálculo do servidor, que é quem vale). */
export function valorRetido(escolha: Escolha, bruto: number, op: RetencaoPagamentoOpcoes | null, pct: number, nominal: number): number {
  if (!op?.disponivel || escolha === "nao") return 0;
  if (escolha === "sugestao") return op.forma_combinada === "fixo" ? (op.valor_sugerido ?? 0) : Math.round(bruto * (op.percentual_sugerido ?? 0)) / 100;
  if (escolha === "percentual") return Math.round(bruto * (pct || 0)) / 100;
  return Math.round((nominal || 0) * 100) / 100;
}

export function RetencaoCaixaCampos({ pessoaId, lancamentoId, bruto, data, onChange }: {
  pessoaId?: number; lancamentoId?: number; bruto: number; data: string;
  /** Devolve o que enviar ao servidor (ou null se não for reter) e o texto do que será retido. */
  onChange: (r: RetencaoCaixaIn | null) => void;
}) {
  const [op, setOp] = useState<RetencaoPagamentoOpcoes | null>(null);
  const [escolha, setEscolha] = useState<Escolha>("nao");
  const [pct, setPct] = useState(0);
  const [nominal, setNominal] = useState(0);

  useEffect(() => {
    if (!(bruto > 0)) return;
    let vivo = true;
    const t = setTimeout(() => {
      fetchOpcoesRetencaoPagamento({ pessoaId, lancamentoId, valor: bruto, data }).then((o) => { if (vivo) setOp(o); }).catch(() => { if (vivo) setOp(null); });
    }, 250);
    return () => { vivo = false; clearTimeout(t); };
  }, [pessoaId, lancamentoId, bruto, data]);

  useEffect(() => {
    if (!op?.disponivel || escolha === "nao") { onChange(null); return; }
    if (escolha === "sugestao") {
      onChange(op.forma_combinada === "fixo" ? { modo: "valor", valor: op.valor_sugerido ?? 0 } : { modo: "percentual", valor: op.percentual_sugerido ?? 0 });
    } else if (escolha === "percentual") onChange(pct > 0 ? { modo: "percentual", valor: pct } : null);
    else onChange(nominal > 0 ? { modo: "valor", valor: nominal } : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op, escolha, pct, nominal]);

  if (!op || (!op.disponivel && !op.pessoa)) return null; // não é pagamento de pessoa do caixa (ou não é administrador)
  if (!op.disponivel) {
    return <p style={{ marginTop: "0.8rem", fontSize: "0.76rem", color: "var(--text-muted)" }}>Caixa do funcionário: {op.motivo}</p>;
  }
  const retido = valorRetido(escolha, bruto, op, pct, nominal);
  const acimaTeto = op.teto_restante != null && retido > op.teto_restante + 0.001;
  const opcoes: [Escolha, string][] = [
    ["nao", "Não reter"],
    ["sugestao", op.forma_combinada === "fixo"
      ? `Combinado: ${formatBRL(op.valor_sugerido ?? 0)} (${(op.percentual_sugerido ?? 0).toLocaleString("pt-BR")}% deste pagamento)`
      : `Sugestão: ${(op.percentual_sugerido ?? 0).toLocaleString("pt-BR")}% = ${formatBRL(Math.round(bruto * (op.percentual_sugerido ?? 0)) / 100)}`],
    ["percentual", "Outro percentual"],
    ["valor", "Valor nominal (R$)"],
  ];
  return (
    <div style={{ marginTop: "0.9rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
      <p id="ret-titulo" style={{ margin: "0 0 0.4rem", fontWeight: 600, fontSize: "0.82rem" }}>Reter no caixa de {op.pessoa}</p>
      <div role="radiogroup" aria-labelledby="ret-titulo" style={{ display: "grid", gap: "0.25rem" }}>
        {opcoes.map(([v, r]) => (
          <label key={v} style={{ display: "flex", gap: "0.4rem", alignItems: "center", fontSize: "0.8rem", margin: 0, cursor: "pointer", minHeight: 28 }}>
            <input type="radio" name="ret-escolha" checked={escolha === v} onChange={() => setEscolha(v)} /> {r}
          </label>
        ))}
      </div>
      {escolha === "percentual" && (
        <div style={{ maxWidth: "160px", marginTop: "0.5rem" }}>
          <label style={lbl} htmlFor="ret-pct">Percentual do valor pago (%)</label>
          <input id="ret-pct" inputMode="decimal" style={{ ...campo, textAlign: "right" }} value={pct ? String(pct).replace(".", ",") : ""}
            onChange={(e) => setPct(Math.max(0, Math.min(100, Number(e.target.value.replace(",", ".")) || 0)))} placeholder="ex.: 10" />
        </div>
      )}
      {escolha === "valor" && (
        <div style={{ maxWidth: "200px", marginTop: "0.5rem" }}>
          <label style={lbl} htmlFor="ret-nom">Valor a reter (R$)</label>
          <CampoMoeda id="ret-nom" style={{ ...campo, textAlign: "right" }} value={nominal} onChange={setNominal} />
        </div>
      )}
      {escolha !== "nao" && retido > 0 && (
        <p style={{ margin: "0.5rem 0 0", fontSize: "0.78rem" }}>
          Retido <strong>{formatBRL(retido)}</strong> · sai da conta <strong>{formatBRL(Math.max(bruto - retido, 0))}</strong> · o gasto total continua {formatBRL(bruto)}.
        </p>
      )}
      {acimaTeto && <p style={{ margin: "0.35rem 0 0", fontSize: "0.76rem", color: "var(--st-logo-fg)" }}>Passa do teto combinado (restam {formatBRL(Math.max(op.teto_restante ?? 0, 0))}). Vai pedir confirmação.</p>}
      {op.termo_pendente && <p style={{ margin: "0.35rem 0 0", fontSize: "0.74rem", color: "var(--text-muted)" }}>O termo de autorização ainda não foi anexado (pendência na Agenda).</p>}
    </div>
  );
}
