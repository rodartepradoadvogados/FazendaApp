// Alimentação — plano de dieta por lote e consumo diário (Server Component)
import { fetchAlimentacao } from "@/lib/api";
import { AlertTriangle, Wheat } from "lucide-react";

async function getData() {
  try {
    return { a: await fetchAlimentacao(), error: null };
  } catch (e: any) {
    return { a: null, error: e.message };
  }
}

export default async function AlimentacaoPage() {
  const { a, error } = await getData();
  const total: any[] = a?.consumo_total ?? [];
  const porLote: any[] = a?.por_lote ?? [];
  const maxTotal = total.reduce((m, x) => Math.max(m, x.consumo_dia), 0) || 1;

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Wheat size={22} style={{ color: "var(--dourado-light)" }} />
          Alimentação
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Plano de dieta por lote cruzado com o efetivo atual → consumo diário estimado.
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do DIETA.csv</a>.</span>
        </div>
      )}

      {/* Consumo total por ingrediente */}
      <div className="card mb-4">
        <div className="card-header mb-3">Consumo Diário do Rebanho (por ingrediente)</div>
        <div className="space-y-2">
          {total.map((x) => (
            <div key={x.ingrediente} className="flex items-center gap-3">
              <span style={{ fontSize: "0.8rem", minWidth: "9rem" }}>{x.ingrediente}</span>
              <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "18px", overflow: "hidden" }}>
                <div style={{ width: `${(x.consumo_dia / maxTotal) * 100}%`, height: "100%", background: "var(--dourado)", minWidth: "2px" }} />
              </div>
              <span style={{ fontSize: "0.8rem", fontWeight: 700, minWidth: "7rem", textAlign: "right" }}>
                {x.consumo_dia.toLocaleString("pt-BR")} {x.unidade}
              </span>
            </div>
          ))}
          {total.length === 0 && !error && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Sem dieta carregada.</p>
          )}
        </div>
      </div>

      {/* Plano por lote */}
      <div className="card">
        <div className="card-header mb-3">Plano por Lote</div>
        <table className="fazenda-table">
          <thead>
            <tr><th>Lote</th><th>Categoria</th><th>Efetivo</th><th>Dieta (por cabeça/dia)</th></tr>
          </thead>
          <tbody>
            {porLote.map((l) => (
              <tr key={l.lote}>
                <td style={{ fontWeight: 700 }}>{l.lote}</td>
                <td>{l.categoria}</td>
                <td style={{ fontWeight: 600, color: l.efetivo === 0 ? "var(--text-muted)" : "var(--text)" }}>{l.efetivo}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  {l.itens.map((i: any) => `${i.ingrediente} ${i.por_cabeca}${i.unidade}`).join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
