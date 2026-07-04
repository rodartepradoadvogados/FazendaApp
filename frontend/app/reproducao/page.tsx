// Página de Reprodução (Server Component)
import { Heart } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getServicos() {
  try {
    // Busca todos os serviços com ult_ocorrencia=1 via animais
    const res = await fetch(`${API}/animais/?ativo=true`, { cache: "no-store" });
    const animais = await res.json();
    return { animais, error: null };
  } catch (e: any) {
    return { animais: [], error: e.message };
  }
}

const SIT_CORES: Record<string, string> = {
  "Ges.":      "var(--green-light)",
  "Vaz. apt.": "var(--blue)",
  "Vaz. atr.": "var(--red)",
  "Vaz. pev":  "var(--amber)",
  "Ins.":      "var(--dourado-light)",
};

export default async function ReproducaoPage() {
  const { animais, error } = await getServicos();

  const gestantes = animais.filter((a: any) => a.sit_rep === "Ges.");
  const candidatas = animais.filter((a: any) => ["Vaz. apt.", "Vaz. atr."].includes(a.sit_rep));
  const inseminadas = animais.filter((a: any) => a.sit_rep === "Ins.");
  const pev = animais.filter((a: any) => a.sit_rep === "Vaz. pev");

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Heart size={22} style={{ color: "var(--dourado)" }} />
          Reprodução
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Situação reprodutiva por animal — atualizado a cada importação do GERAL.csv
        </p>
      </div>

      {error && <div className="alert-critico mb-4">{error}</div>}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Gestantes", value: gestantes.length, color: "var(--green-light)" },
          { label: "Candidatas IATF", value: candidatas.length, color: "var(--blue)" },
          { label: "Inseminadas", value: inseminadas.length, color: "var(--dourado-light)" },
          { label: "Em PEV", value: pev.length, color: "var(--amber)" },
        ].map(k => (
          <div key={k.label} className="kpi-card">
            <p className="kpi-value" style={{ color: k.color }}>{k.value}</p>
            <p className="kpi-label">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Tabela completa */}
      {[
        { titulo: `Gestantes (${gestantes.length})`, lista: gestantes },
        { titulo: `Candidatas IATF — Vazia Apta/Atraso (${candidatas.length})`, lista: candidatas },
        { titulo: `Inseminadas — Aguardando Diagnóstico (${inseminadas.length})`, lista: inseminadas },
        { titulo: `Em PEV (${pev.length})`, lista: pev },
      ].filter(s => s.lista.length > 0).map(secao => (
        <div key={secao.titulo} className="card mb-4">
          <div className="card-header mb-3">{secao.titulo}</div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Nº Animal</th>
                  <th>Raça</th>
                  <th>Categoria</th>
                  <th>Sit. Rep.</th>
                  <th>DEL</th>
                  <th>Diag. anterior</th>
                  <th>Últ. diagnóstico</th>
                  <th>Grupo</th>
                </tr>
              </thead>
              <tbody>
                {secao.lista.map((a: any) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.raca || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{a.categoria_abrev || "—"}</td>
                    <td style={{ color: SIT_CORES[a.sit_rep] || "var(--text)", fontWeight: 600, fontSize: "0.82rem" }}>
                      {a.sit_rep || "—"}
                    </td>
                    <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {a.data_ult_diag
                        ? new Date(a.data_ult_diag + "T00:00:00").toLocaleDateString("pt-BR")
                        : "—"}
                    </td>
                    <td style={{ fontSize: "0.8rem", color: a.diagnostico === "Positivo" ? "var(--green-light)" : a.diagnostico === "Negativo" ? "var(--red)" : "var(--text-muted)", fontWeight: a.diagnostico ? 600 : 400 }}>
                      {a.diagnostico || "—"}
                    </td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {a.grupo_primario || "—"}
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
