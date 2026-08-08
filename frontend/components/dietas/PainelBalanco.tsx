"use client";
// Etapa 4 — grade reduzida e editável à esquerda, balanço nutricional ao vivo
// à direita. O cálculo em si (debounce 400ms + AbortController) roda no
// wizard pai (app/dietas/[id]/page.tsx) porque a Etapa 3 e os domínios 5-7
// também precisam do mesmo `resultado` — evita recalcular a mesma dieta em
// paralelo para cada etapa que o usuário visita.
import { Loader2 } from "lucide-react";
import { ItemGrade, Resultado } from "@/lib/dietas";

function fmt(v: number | null | undefined, casas = 2): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

const COR_SITUACAO: Record<string, string> = {
  adequado: "var(--green-light)", deficit: "var(--red)", excesso: "var(--amber)",
};
const ROTULO_SITUACAO: Record<string, string> = { adequado: "Adequado", deficit: "Déficit", excesso: "Excesso" };

export function PainelBalanco({
  itens, onChangeItens, resultado, calculando, onAbrirAplicar,
}: {
  itens: ItemGrade[]; onChangeItens: (itens: ItemGrade[]) => void; resultado: Resultado | null; calculando: boolean;
  onAbrirAplicar: () => void;
}) {
  function atualizar(idx: number, patch: Partial<ItemGrade>) {
    onChangeItens(itens.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  const porNome = new Map((resultado?.ingredientes || []).map((r) => [r.nome, r]));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.8rem" }}>
        <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "var(--text)" }}>Balanço ao vivo</h3>
        {calculando && (
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: "var(--text-muted)" }}>
            <Loader2 size={13} className="animate-spin" /> calculando…
          </span>
        )}
        <button type="button" className="btn-primary-gold" style={{ marginLeft: "auto" }} onClick={onAbrirAplicar} disabled={!resultado || itens.length === 0}>
          Aplicar na dieta atual
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(20rem, 1.1fr) minmax(22rem, 1fr)", gap: "1rem", alignItems: "start" }}>
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="fazenda-table">
            <thead><tr><th>Ingrediente</th><th>Prop. MS %</th><th>kg MS/d</th><th>kg MN/d</th><th>R$/d</th></tr></thead>
            <tbody>
              {itens.length === 0 && <tr><td colSpan={5}><div className="empty-state">Volte à Etapa 1 para montar a grade.</div></td></tr>}
              {itens.map((it, idx) => {
                const r = porNome.get(it.nome);
                return (
                  <tr key={idx}>
                    <td>
                      <input
                        value={it.nome} onChange={(e) => atualizar(idx, { nome: e.target.value })}
                        style={{ width: "100%", padding: "0.3rem 0.4rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.8rem" }}
                      />
                    </td>
                    <td>
                      <input
                        type="number" step="0.1" value={it.proporcao_ms_pct}
                        onChange={(e) => atualizar(idx, { proporcao_ms_pct: Number(e.target.value) })}
                        style={{ width: "5rem", padding: "0.3rem 0.4rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.8rem" }}
                      />
                    </td>
                    <td>{fmt(r?.kg_materia_seca_dia)}</td>
                    <td>{fmt(r?.kg_materia_natural_dia)}</td>
                    <td>{fmt(r?.custo_dia)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="fazenda-table">
            <thead><tr><th>Nutriente</th><th>Exigência</th><th>Fornecido</th><th>Balanço</th><th>Situação</th></tr></thead>
            <tbody>
              {!resultado && <tr><td colSpan={5}><div className="empty-state">Sem cálculo ainda.</div></td></tr>}
              {resultado?.balanco.map((linha) => (
                <tr key={linha.nutriente}>
                  <td style={{ fontWeight: 600 }}>{linha.nutriente}</td>
                  <td>{fmt(linha.exigencia)} {linha.unidade}</td>
                  <td>{fmt(linha.fornecido)} {linha.unidade}</td>
                  <td style={{ color: COR_SITUACAO[linha.situacao], fontWeight: 700 }}>{fmt(linha.balanco)}</td>
                  <td>
                    <span style={{ color: COR_SITUACAO[linha.situacao], fontWeight: 700, fontSize: "0.78rem" }}>{ROTULO_SITUACAO[linha.situacao] || linha.situacao}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {resultado && resultado.avisos.length > 0 && (
        <div style={{ marginTop: "0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
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
      )}
    </div>
  );
}
