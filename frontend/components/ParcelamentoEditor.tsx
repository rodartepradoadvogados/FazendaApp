"use client";
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

export type Parcela = { data_vencimento: string; valor: string };

const FREQ_DIAS: Record<string, number> = { semanal: 7, quinzenal: 14 };

function somaDias(dataISO: string, dias: number): string {
  const d = new Date(dataISO + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}
function somaMeses(dataISO: string, meses: number): string {
  const d = new Date(dataISO + "T00:00:00");
  d.setMonth(d.getMonth() + meses);
  return d.toISOString().slice(0, 10);
}
function proximaData(dataISO: string, frequencia: string): string {
  if (frequencia === "mensal") return somaMeses(dataISO, 1);
  return somaDias(dataISO, FREQ_DIAS[frequencia] || 30);
}

function contarPeriodos(inicio: string, fim: string, frequencia: string): number {
  if (!inicio || !fim || fim <= inicio) return 1;
  let n = 1;
  let atual = inicio;
  while (atual < fim && n < 240) {
    atual = proximaData(atual, frequencia);
    n++;
  }
  return n;
}

export function dividirParcelasPorFrequencia(valorTotal: number, qtd: number, primeiraData: string, frequencia: string): Parcela[] {
  if (qtd <= 0 || !primeiraData) return [];
  const base = Math.floor((valorTotal / qtd) * 100) / 100;
  const resto = Math.round((valorTotal - base * qtd) * 100) / 100;
  const parcelas: Parcela[] = [];
  let data = primeiraData;
  for (let i = 0; i < qtd; i++) {
    const valor = i === qtd - 1 ? base + resto : base;
    parcelas.push({ data_vencimento: data, valor: valor.toFixed(2) });
    data = proximaData(data, frequencia);
  }
  return parcelas;
}

const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const inputSm: React.CSSProperties = {
  fontSize: "0.8rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem",
};

/**
 * Editor de parcelamento por frequência (mensal/semanal/quinzenal) — deriva a
 * quantidade de parcelas a partir de uma data de término estimada (apenas
 * para cálculo, sem vincular o lançamento a essa data) OU de um número de
 * parcelas informado diretamente; sem nenhuma das duas, o usuário lança
 * livremente quantas parcelas quiser. Sempre editável linha a linha depois
 * de gerado — mesmo padrão do parcelamento do lançamento financeiro.
 */
export function ParcelamentoEditor({
  valorTotal, frequencia, primeiraData, parcelas, setParcelas,
}: {
  valorTotal: number; frequencia: string; primeiraData: string;
  parcelas: Parcela[]; setParcelas: (p: Parcela[]) => void;
}) {
  const [modo, setModo] = useState<"parcelas" | "data_fim" | "livre">("parcelas");
  const [numParcelas, setNumParcelas] = useState("2");
  const [dataFim, setDataFim] = useState("");

  const gerar = () => {
    if (!primeiraData) return;
    if (modo === "livre") {
      setParcelas([{ data_vencimento: primeiraData, valor: valorTotal ? valorTotal.toFixed(2) : "" }]);
      return;
    }
    const qtd = modo === "parcelas" ? Math.max(1, parseInt(numParcelas) || 1) : contarPeriodos(primeiraData, dataFim, frequencia);
    setParcelas(dividirParcelasPorFrequencia(valorTotal, qtd, primeiraData, frequencia));
  };

  const atualizarParcela = (i: number, campo: keyof Parcela, valor: string) =>
    setParcelas(parcelas.map((p, idx) => (idx === i ? { ...p, [campo]: valor } : p)));
  const removerParcela = (i: number) => setParcelas(parcelas.filter((_, idx) => idx !== i));
  const adicionarParcela = () =>
    setParcelas([
      ...parcelas,
      { data_vencimento: parcelas.length ? proximaData(parcelas[parcelas.length - 1].data_vencimento, frequencia) : primeiraData, valor: "" },
    ]);

  const somaParcelas = parcelas.reduce((a, p) => a + (parseFloat(p.valor) || 0), 0);
  const divergente = valorTotal > 0 && parcelas.length > 0 && Math.abs(somaParcelas - valorTotal) > 0.01;

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 mb-2">
        <div>
          <label style={lbl}>Duração</label>
          <select value={modo} onChange={(e) => setModo(e.target.value as any)} style={inputSm}>
            <option value="parcelas">Número de parcelas</option>
            <option value="data_fim">Data estimada de término</option>
            <option value="livre">Lançar livremente</option>
          </select>
        </div>
        {modo === "parcelas" && (
          <div>
            <label style={lbl}>Quantas parcelas</label>
            <input type="number" min={1} value={numParcelas} onChange={(e) => setNumParcelas(e.target.value)} style={{ ...inputSm, width: "80px" }} />
          </div>
        )}
        {modo === "data_fim" && (
          <div>
            <label style={lbl}>Término estimado (só para cálculo, não vincula)</label>
            <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} style={inputSm} />
          </div>
        )}
        <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={gerar} disabled={!primeiraData}>
          Gerar parcelas
        </button>
      </div>

      {parcelas.length > 0 && (
        <div className="overflow-x-auto">
          <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
            <thead><tr><th>Vencimento</th><th>Valor (R$)</th><th></th></tr></thead>
            <tbody>
              {parcelas.map((p, i) => (
                <tr key={i}>
                  <td><input type="date" value={p.data_vencimento} onChange={(e) => atualizarParcela(i, "data_vencimento", e.target.value)} style={inputSm} /></td>
                  <td><input type="number" step="0.01" value={p.valor} onChange={(e) => atualizarParcela(i, "valor", e.target.value)} style={{ ...inputSm, width: "110px" }} /></td>
                  <td><button type="button" className="btn-ghost" onClick={() => removerParcela(i)} aria-label="Remover parcela"><Trash2 size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", marginTop: "0.3rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={adicionarParcela}>
            <Plus size={13} /> Adicionar parcela
          </button>
          {divergente && (
            <p style={{ color: "var(--amber)", fontSize: "0.75rem", marginTop: "0.3rem" }}>
              Soma das parcelas ({somaParcelas.toFixed(2)}) difere do valor total ({valorTotal.toFixed(2)}).
            </p>
          )}
        </div>
      )}
    </div>
  );
}
