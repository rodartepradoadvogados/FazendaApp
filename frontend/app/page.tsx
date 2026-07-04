// Capa — Dashboard principal (Server Component)
import { fetchAgenda, fetchAnimais, formatBRL, today, firstDayOfMonth, fetchDRE } from "@/lib/api";
import { AlertTriangle, TrendingDown, Syringe, MilkOff, Activity } from "lucide-react";

async function getData() {
  try {
    const [agenda, animais] = await Promise.all([
      fetchAgenda(today()),
      fetchAnimais(),
    ]);
    return { agenda, animais, error: null };
  } catch (e: any) {
    return { agenda: null, animais: [], error: e.message };
  }
}

export default async function Home() {
  const { agenda, animais, error } = await getData();

  const totalAnimais = animais?.length ?? "—";
  const gestantes = animais?.filter((a: any) => a.sit_rep === "Ges.").length ?? "—";
  const lactantes = animais?.filter((a: any) => ["01 - NOV. ALTA", "02 - VACAS ALTA", "03 - MÉDIA"]
    .some((g: string) => (a.grupo_primario || "").includes(g.split(" ")[0]))).length ?? "—";

  const candidatasIATF = agenda?.totais?.candidatas_iatf ?? "—";
  const bstElegiveis = agenda?.totais?.bst_elegiveis ?? "—";

  // Implante é o gargalo — verifica estoque
  const implantCheck = agenda?.hormonios_check?.find((h: any) => h.nome?.includes("Implante"));
  const implanteFalta = implantCheck && !implantCheck.suficiente;
  const implanteFaltaQtd = implantCheck ? Math.ceil(implantCheck.falta) : 0;

  return (
    <div className="p-6 animate-in">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>
          Fazenda Estreito Ponte de Pedra
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Pecuária leiteira · Girolando / Holandês ·{" "}
          {new Date().toLocaleDateString("pt-BR", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
        </p>
      </div>

      {/* Alerta implante */}
      {implanteFalta && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>
            <strong>ALERTA:</strong> Estoque de implantes insuficiente para o protocolo IATF.
            Faltam <strong>{implanteFaltaQtd}</strong> implante(s) para {candidatasIATF} candidata(s).
          </span>
        </div>
      )}

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Backend offline ou sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload dos CSV</a>.</span>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card">
          <p className="kpi-value">{totalAnimais}</p>
          <p className="kpi-label">Total de animais</p>
          <Activity size={20} style={{ color: "var(--text-muted)", marginTop: "0.5rem" }} />
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--green-light)" }}>{gestantes}</p>
          <p className="kpi-label">Gestantes</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--blue)" }}>{candidatasIATF}</p>
          <p className="kpi-label">Candidatas IATF</p>
          <Syringe size={20} style={{ color: "var(--text-muted)", marginTop: "0.5rem" }} />
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--amber)" }}>{bstElegiveis}</p>
          <p className="kpi-label">BST hoje</p>
          <MilkOff size={20} style={{ color: "var(--text-muted)", marginTop: "0.5rem" }} />
        </div>
      </div>

      {/* Bloco 2 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Próximos eventos */}
        <div className="card">
          <div className="card-header mb-3">Próximos Eventos (7 dias)</div>
          {agenda?.eventos && agenda.eventos.length > 0 ? (
            <div className="space-y-2">
              {agenda.eventos
                .filter((e: any) => {
                  const d = new Date(e.data);
                  const limite = new Date();
                  limite.setDate(limite.getDate() + 7);
                  return d <= limite;
                })
                .slice(0, 8)
                .map((ev: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 py-1">
                    <span style={{
                      fontSize: "0.7rem",
                      color: "var(--text-muted)",
                      minWidth: "4.5rem",
                      paddingTop: "0.15rem"
                    }}>
                      {new Date(ev.data + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
                    </span>
                    <span
                      className={`badge-${ev.categoria?.toLowerCase().split("/")[0] || "atividades"}`}
                      style={{ fontSize: "0.65rem", padding: "0.15rem 0.4rem", borderRadius: "4px", whiteSpace: "nowrap", flexShrink: 0 }}
                    >
                      {ev.categoria?.split("/")[0]}
                    </span>
                    <span style={{ fontSize: "0.8rem", color: "var(--text)" }}>
                      {ev.numero_animal ? <strong>{ev.numero_animal}</strong> : null}
                      {ev.numero_animal ? " · " : ""}
                      {ev.descricao}
                    </span>
                  </div>
                ))}
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              {error ? "Sem dados — faça o upload dos CSV." : "Nenhum evento nos próximos 7 dias."}
            </p>
          )}
        </div>

        {/* Checagem de hormônios */}
        <div className="card">
          <div className="card-header mb-3">Checagem de Hormônios (IATF)</div>
          {agenda?.hormonios_check && agenda.hormonios_check.length > 0 ? (
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Hormônio</th>
                  <th>Estoque</th>
                  <th>Necessário</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {agenda.hormonios_check.map((h: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontSize: "0.78rem" }}>{h.nome}</td>
                    <td style={{ fontWeight: 600 }}>
                      {h.estoque_atual?.toFixed(1)} {h.unidade}
                    </td>
                    <td>{h.necessidade?.toFixed(1)} {h.unidade}</td>
                    <td>
                      {h.suficiente ? (
                        <span style={{ color: "var(--green-light)", fontWeight: 700 }}>OK</span>
                      ) : (
                        <span style={{ color: "var(--red)", fontWeight: 700 }}>
                          FALTA {Math.ceil(h.falta)}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Sem candidatas IATF ou dados de estoque.
            </p>
          )}
        </div>
      </div>

      {/* Contas a pagar */}
      {agenda?.contas_a_pagar && agenda.contas_a_pagar.length > 0 && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2">
            <TrendingDown size={14} />
            Contas a Pagar (próximos 10 dias)
          </div>
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Vencimento</th>
                <th>Descrição</th>
                <th>Fornecedor</th>
                <th>Valor</th>
              </tr>
            </thead>
            <tbody>
              {agenda.contas_a_pagar.map((c: any, i: number) => (
                <tr key={i}>
                  <td style={{ color: "var(--red)", fontWeight: 600 }}>
                    {new Date(c.data_vencimento + "T00:00:00").toLocaleDateString("pt-BR")}
                  </td>
                  <td>{c.descricao}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{c.fornecedor_cliente}</td>
                  <td style={{ fontWeight: 700, color: "var(--amber)" }}>
                    {formatBRL(c.valor_total || 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
