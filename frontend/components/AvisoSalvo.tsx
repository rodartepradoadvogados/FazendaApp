"use client";
import { useEffect, useRef } from "react";
import { Check, Sparkles } from "lucide-react";

/**
 * Confirmação de salvamento persistente — fica no topo da tela (não some no
 * mesmo clique que limpa a seleção/formulário) e rola a página até ela, com
 * uma segunda linha avisando que já dá pra lançar o próximo. Usado em Contas
 * a pagar/receber, baixa individual, pagamento em lote e folha de pagamento.
 */
export function AvisoSalvo({ texto, aviso2 = "Pronto para um novo lançamento." }: { texto: string | null; aviso2?: string | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!texto) return;
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [texto]);
  if (!texto) return null;
  return (
    <div ref={ref} className="mb-3" style={{ background: "rgba(45,138,86,0.15)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 1rem" }}>
      <div className="flex items-center gap-2" style={{ color: "var(--green-light)", fontSize: "0.85rem", fontWeight: 600 }}>
        <Check size={16} /> {texto}
      </div>
      {aviso2 && (
        <div className="flex items-center gap-2 mt-1" style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
          <Sparkles size={13} /> {aviso2}
        </div>
      )}
    </div>
  );
}
