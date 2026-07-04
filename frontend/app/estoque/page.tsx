// Página de Estoque (Server Component)
import { Package, AlertTriangle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getEstoque() {
  try {
    const res = await fetch(`${API}/agenda/`, { cache: "no-store" });
    const agenda = await res.json();
    // Estoque vem indiretamente via agenda; buscar diretamente do banco
    // Por ora usamos o hormonios_check da agenda
    return { agenda, error: null };
  } catch (e: any) {
    return { agenda: null, error: e.message };
  }
}

// Lista de hormônios IATF para destaque
const HORMONIOS_IATF = ["sincrogest", "cidr", "sincrodiol", "sincroforte", "estron", "sincrocp", "lactotropin"];

export default async function EstoquePage() {
  const { agenda, error } = await getEstoque();
  const hormCheck = agenda?.hormonios_check || [];

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Package size={22} style={{ color: "var(--dourado)" }} />
          Estoque
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Monitoramento de insumos — foco em hormônios do protocolo IATF
        </p>
      </div>

      {error && <div className="alert-critico mb-4">{error} — <a href="/upload" style={{ color: "var(--dourado-light)" }}>Upload CSV</a></div>}

      {/* Hormônios IATF */}
      {hormCheck.length > 0 && (
        <div className="card mb-6">
          <div className="card-header mb-3 flex items-center gap-2">
            <AlertTriangle size={14} />
            Hormônios IATF — Necessidade vs. Estoque
            {agenda?.candidatas_iatf?.length > 0 && (
              <span style={{ fontWeight: 400, fontSize: "0.75rem", color: "var(--text-muted)" }}>
                (para {agenda.candidatas_iatf.length} candidata{agenda.candidatas_iatf.length !== 1 ? "s" : ""})
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {hormCheck.map((h: any, i: number) => (
              <div
                key={i}
                className="p-3 rounded-lg"
                style={{
                  background: h.suficiente ? "rgba(46,125,82,0.1)" : "rgba(192,57,43,0.15)",
                  border: `1px solid ${h.suficiente ? "var(--green)" : "var(--red)"}`,
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{h.nome}</span>
                  <span style={{
                    color: h.suficiente ? "var(--green-light)" : "var(--red)",
                    fontWeight: 800,
                    fontSize: "0.8rem"
                  }}>
                    {h.suficiente ? "OK" : `FALTA ${Math.ceil(h.falta)} ${h.unidade}`}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "1.5rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  <span>Estoque: <strong style={{ color: "var(--text)" }}>{h.estoque_atual?.toFixed(2)} {h.unidade}</strong></span>
                  <span>Necessário: <strong style={{ color: "var(--text)" }}>{h.necessidade?.toFixed(1)} {h.unidade}</strong></span>
                </div>
                {/* Barra de progresso */}
                <div style={{ marginTop: "0.5rem", height: "4px", background: "var(--border)", borderRadius: "2px" }}>
                  <div style={{
                    height: "100%",
                    borderRadius: "2px",
                    width: `${Math.min(100, (h.estoque_atual / (h.necessidade || 1)) * 100)}%`,
                    background: h.suficiente ? "var(--green)" : "var(--red)",
                    transition: "width 0.5s",
                  }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Instrução upload */}
      {hormCheck.length === 0 && !error && (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <Package size={40} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-muted)" }}>
            Faça o upload do <strong>ESTOQUE.csv</strong> e do <strong>GERAL.csv</strong> para ver a checagem de hormônios.
          </p>
          <a href="/upload" className="btn-primary" style={{ display: "inline-flex", marginTop: "1rem" }}>
            Upload CSV
          </a>
        </div>
      )}
    </div>
  );
}
