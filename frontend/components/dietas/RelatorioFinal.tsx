"use client";
// Etapa 10 — relatório final: cabeçalho, grade, balanço completo, avisos e as
// duas ações (Salvar / Aplicar). Exportação reaproveita lib/export.ts (mesmo
// padrão de exportarExcel/exportarPDF usado no resto do site).
import { useState } from "react";
import { FileSpreadsheet, FileText } from "lucide-react";
import { exportarExcel, exportarPDF } from "@/lib/export";
import { ItemGrade, Resultado, SimulacaoCabecalho } from "@/lib/dietas";

const COR_SITUACAO: Record<string, string> = { adequado: "var(--green-light)", deficit: "var(--red)", excesso: "var(--amber)" };
const ROTULO_SITUACAO: Record<string, string> = { adequado: "Adequado", deficit: "Déficit", excesso: "Excesso" };

function fmt(v: number | null | undefined, casas = 2): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function RelatorioFinal({
  cabecalho, itens, resultado, onAbrirAplicar, onSalvar, salvando,
}: {
  cabecalho: SimulacaoCabecalho; itens: ItemGrade[]; resultado: Resultado | null;
  onAbrirAplicar: () => void; onSalvar: () => void; salvando: boolean;
}) {
  const [exportando, setExportando] = useState<"excel" | "pdf" | null>(null);

  async function exportar(formato: "excel" | "pdf") {
    if (!resultado) return;
    setExportando(formato);
    const colunas = [
      { header: "Nutriente", key: "nutriente" }, { header: "Unidade", key: "unidade" },
      { header: "Exigência", key: "exigencia" }, { header: "Fornecido", key: "fornecido" },
      { header: "Balanço", key: "balanco" }, { header: "Situação", key: "situacao" },
    ];
    const linhas = resultado.balanco.map((l) => ({ ...l, situacao: ROTULO_SITUACAO[l.situacao] || l.situacao }));
    try {
      if (formato === "excel") await exportarExcel(`Balanço nutricional — ${cabecalho.nome}`, colunas, linhas, `dieta-${cabecalho.id}-balanco`);
      else await exportarPDF(`Balanço nutricional — ${cabecalho.nome}`, colunas, linhas, `dieta-${cabecalho.id}-balanco`);
    } finally {
      setExportando(null);
    }
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: "0.9rem", display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "0.8rem" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "var(--text)" }}>{cabecalho.nome}</h3>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Lote {cabecalho.lote ?? "—"} · {cabecalho.estado_fisiologico} · {cabecalho.raca} · {itens.length} ingrediente(s)
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" className="btn-secondary" disabled={!resultado || exportando !== null} onClick={() => exportar("excel")}>
            <FileSpreadsheet size={14} /> Excel
          </button>
          <button type="button" className="btn-secondary" disabled={!resultado || exportando !== null} onClick={() => exportar("pdf")}>
            <FileText size={14} /> PDF
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, marginBottom: "0.9rem", overflowX: "auto" }}>
        <div className="card-header">Grade de ingredientes</div>
        <table className="fazenda-table">
          <thead><tr><th>Ingrediente</th><th>Categoria</th><th>Prop. MS %</th><th>kg MS/d</th><th>kg MN/d</th><th>R$/d</th></tr></thead>
          <tbody>
            {(resultado?.ingredientes || itens.map((i) => ({ nome: i.nome, categoria_nasem: i.categoria_nasem, proporcao_ms_pct: i.proporcao_ms_pct, kg_materia_seca_dia: null as any, kg_materia_natural_dia: null as any, custo_dia: null as any }))).map((ing, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 600 }}>{ing.nome}</td>
                <td>{ing.categoria_nasem}</td>
                <td>{fmt(ing.proporcao_ms_pct, 1)}</td>
                <td>{fmt(ing.kg_materia_seca_dia)}</td>
                <td>{fmt(ing.kg_materia_natural_dia)}</td>
                <td>{fmt(ing.custo_dia)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ padding: 0, marginBottom: "0.9rem", overflowX: "auto" }}>
        <div className="card-header">Balanço nutricional completo</div>
        <table className="fazenda-table">
          <thead><tr><th>Nutriente</th><th>Exigência</th><th>Fornecido</th><th>Balanço</th><th>Situação</th></tr></thead>
          <tbody>
            {!resultado && <tr><td colSpan={5}><div className="empty-state">Sem cálculo ainda.</div></td></tr>}
            {resultado?.balanco.map((l) => (
              <tr key={l.nutriente}>
                <td style={{ fontWeight: 600 }}>{l.nutriente}</td>
                <td>{fmt(l.exigencia)} {l.unidade}</td>
                <td>{fmt(l.fornecido)} {l.unidade}</td>
                <td style={{ color: COR_SITUACAO[l.situacao], fontWeight: 700 }}>{fmt(l.balanco)}</td>
                <td style={{ color: COR_SITUACAO[l.situacao], fontWeight: 700, fontSize: "0.78rem" }}>{ROTULO_SITUACAO[l.situacao] || l.situacao}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {resultado && resultado.avisos.length > 0 && (
        <div className="card" style={{ marginBottom: "0.9rem" }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--gold-deep)", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Avisos</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {resultado.avisos.map((a, i) => (
              <div key={i} className="alert-critico" style={{
                background: a.severidade === "bloqueante" ? "color-mix(in srgb, var(--red) 16%, transparent)" : a.severidade === "atencao" ? "color-mix(in srgb, var(--amber) 16%, transparent)" : "var(--surface-2)",
                borderColor: a.severidade === "bloqueante" ? "var(--red)" : a.severidade === "atencao" ? "var(--amber)" : "var(--border)",
                color: "var(--text)",
              }}>
                {a.mensagem}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end" }}>
        <button type="button" className="btn-secondary" disabled={salvando} onClick={onSalvar}>
          {salvando ? "Salvando…" : "Salvar simulação"}
        </button>
        <button type="button" className="btn-primary-gold" disabled={!resultado || itens.length === 0} onClick={onAbrirAplicar}>
          Aplicar na dieta atual
        </button>
      </div>
    </div>
  );
}
