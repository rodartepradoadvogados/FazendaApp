"use client";
import { AlertTriangle } from "lucide-react";
import { formatBRL } from "@/lib/api";

export type Parcela = { data_vencimento: string; valor: string };

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

export function dividirParcelas(valorTotal: number, qtd: number, primeiraData: string): Parcela[] {
  if (qtd <= 0) return [];
  const base = Math.floor((valorTotal / qtd) * 100) / 100;
  const resto = Math.round((valorTotal - base * qtd) * 100) / 100;
  const inicio = primeiraData ? new Date(primeiraData + "T00:00:00") : new Date();
  return Array.from({ length: qtd }, (_, i) => {
    const d = new Date(inicio); d.setMonth(d.getMonth() + i);
    const valor = i === qtd - 1 ? base + resto : base;
    return { data_vencimento: d.toISOString().slice(0, 10), valor: valor.toFixed(2) };
  });
}

/** Bloco reutilizável de parcelamento — mesma UI usada no Financeiro, aplicada
 * também ao lançamento de compra/venda de animal e à comissão de corretagem. */
export function ParcelasEditor({
  parcelas, setParcelas, valorReferencia, tituloContaA = "pagar",
}: {
  parcelas: Parcela[];
  setParcelas: (fn: (arr: Parcela[]) => Parcela[]) => void;
  valorReferencia: number;
  tituloContaA?: "pagar" | "receber";
}) {
  const somaParcelas = parcelas.reduce((a, p) => a + (Number(p.valor) || 0), 0);
  return (
    <div>
      <table className="fazenda-table mt-2">
        <thead><tr><th>Parcela</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor (R$)</th></tr></thead>
        <tbody>
          {parcelas.map((p, i) => (
            <tr key={i}>
              <td>{i + 1}/{parcelas.length}</td>
              <td><input type="date" style={inputStyle} value={p.data_vencimento}
                onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, data_vencimento: e.target.value } : x))} /></td>
              <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }} value={p.valor}
                onChange={(e) => setParcelas((arr) => arr.map((x, j) => j === i ? { ...x, valor: e.target.value } : x))} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {Math.abs(somaParcelas - valorReferencia) > 0.01 && (
        <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.4rem" }}>
          <AlertTriangle size={12} style={{ display: "inline", marginRight: "0.2rem" }} />
          Soma das parcelas ({formatBRL(somaParcelas)}) difere do valor de referência ({formatBRL(valorReferencia)}).
        </p>
      )}
      <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
        Cada parcela nasce em aberto (conta a {tituloContaA}) — dê baixa individualmente quando for paga/recebida.
      </p>
    </div>
  );
}

export function CampoQtdParcelas({ qtd, setQtd }: { qtd: string; setQtd: (v: string) => void }) {
  return (
    <div>
      <label style={lbl}>Quantidade de parcelas</label>
      <input type="number" min={1} style={{ ...inputStyle, maxWidth: "8rem" }} value={qtd} onChange={(e) => setQtd(e.target.value)} />
    </div>
  );
}
