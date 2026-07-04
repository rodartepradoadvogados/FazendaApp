// Página de Rebanho (Server Component)
import { fetchAnimais } from "@/lib/api";
import { Beef } from "lucide-react";

const SIT_REP_CORES: Record<string, string> = {
  "Ges.":      "var(--green-light)",
  "Vaz. apt.": "var(--blue)",
  "Vaz. atr.": "var(--red)",
  "Vaz. pev":  "var(--amber)",
  "Ins.":      "var(--dourado-light)",
};

export default async function RebanhoPage() {
  let animais: any[] = [];
  let error = "";
  try {
    animais = await fetchAnimais();
  } catch (e: any) {
    error = e.message;
  }

  // Agrupa por grupo primário
  const grupos: Record<string, any[]> = {};
  for (const a of animais) {
    const g = a.grupo_primario || "(Sem grupo)";
    if (!grupos[g]) grupos[g] = [];
    grupos[g].push(a);
  }

  const sitRepDist: Record<string, number> = {};
  for (const a of animais) {
    const s = a.sit_rep || "—";
    sitRepDist[s] = (sitRepDist[s] || 0) + 1;
  }

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Beef size={22} style={{ color: "var(--dourado)" }} />
          Rebanho
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          {animais.length} animais ativos — distribuição por grupos e situação reprodutiva
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">{error} — <a href="/upload" style={{ color: "var(--dourado-light)" }}>Upload CSV</a></div>
      )}

      {/* KPIs por sit. rep. */}
      <div className="grid grid-cols-3 md:grid-cols-5 gap-3 mb-6">
        {Object.entries(sitRepDist).map(([s, n]) => (
          <div key={s} className="kpi-card" style={{ padding: "0.9rem" }}>
            <p className="kpi-value" style={{ fontSize: "1.6rem", color: SIT_REP_CORES[s] || "var(--text)" }}>{n}</p>
            <p className="kpi-label">{s}</p>
          </div>
        ))}
      </div>

      {/* Tabela por grupo */}
      {Object.entries(grupos)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([grupo, lista]) => (
        <div key={grupo} className="card mb-4">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>{grupo}</span>
            <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>
              {lista.length} animal{lista.length !== 1 ? "is" : ""}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Nº Animal</th>
                  <th>Categoria</th>
                  <th>Raça</th>
                  <th>Sit. Rep.</th>
                  <th>DEL</th>
                  <th>Últ. CL (kg)</th>
                  <th>Diagnóstico</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((a: any) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.raca || "—"}</td>
                    <td>
                      <span style={{
                        color: SIT_REP_CORES[a.sit_rep] || "var(--text-muted)",
                        fontWeight: 600,
                        fontSize: "0.8rem"
                      }}>
                        {a.sit_rep || "—"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>
                      {a.ult_cl_kg ? `${a.ult_cl_kg.toFixed(1)}` : "—"}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: a.diagnostico === "Positivo" ? "var(--green-light)" : a.diagnostico === "Negativo" ? "var(--red)" : "var(--text-muted)" }}>
                      {a.diagnostico || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
