// Produção — histórico de controle leiteiro e curva de lactação (Server Component)
import { fetchProducao } from "@/lib/api";
import { AlertTriangle, Milk, TrendingUp } from "lucide-react";

async function getData() {
  try {
    return { p: await fetchProducao(), error: null };
  } catch (e: any) {
    return { p: null, error: e.message };
  }
}

function n(v: number | null | undefined, suf = "") {
  return v === null || v === undefined ? "—" : `${v}${suf}`;
}

export default async function ProducaoPage() {
  const { p, error } = await getData();
  const t = p?.totais;
  const curva: any[] = p?.curva_lactacao ?? [];
  const serie: any[] = p?.serie_temporal ?? [];
  const ranking: any[] = p?.por_animal ?? [];
  const maxCurva = curva.reduce((m, c) => Math.max(m, c.media_kg), 0) || 1;
  const ultimasSemanas = serie.slice(-12);
  const maxSerie = ultimasSemanas.reduce((m, s) => Math.max(m, s.total_kg), 0) || 1;

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Milk size={22} style={{ color: "var(--dourado-light)" }} />
          Produção Leiteira
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Histórico de controle leiteiro, curva de lactação e ranking por vaca.
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do controle leiteiro</a>.</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--green-light)" }}>{n(t?.ultima_media_kg, " kg")}</p>
          <p className="kpi-label">Média por vaca (último controle)</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{n(t?.vacas)}</p>
          <p className="kpi-label">Vacas em controle</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{n(t?.controles)}</p>
          <p className="kpi-label">Pesagens no histórico</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ fontSize: "1.1rem" }}>{t?.ultima_data ?? "—"}</p>
          <p className="kpi-label">Data do último controle</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Curva de lactação */}
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2">
            <TrendingUp size={14} /> Curva de Lactação (média por DEL)
          </div>
          <div className="space-y-2">
            {curva.map((c) => (
              <div key={c.faixa_del} className="flex items-center gap-2">
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", minWidth: "4rem" }}>{c.faixa_del}d</span>
                <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "16px", overflow: "hidden" }}>
                  <div style={{ width: `${(c.media_kg / maxCurva) * 100}%`, height: "100%", background: "var(--green-light)", minWidth: "2px" }} />
                </div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, minWidth: "3.5rem", textAlign: "right" }}>{c.media_kg} kg</span>
              </div>
            ))}
          </div>
        </div>

        {/* Produção do rebanho por controle (últimos) */}
        <div className="card">
          <div className="card-header mb-3">Produção do Rebanho (últimos controles)</div>
          <div className="space-y-2">
            {ultimasSemanas.map((s) => (
              <div key={s.data} className="flex items-center gap-2">
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", minWidth: "5rem" }}>
                  {new Date(s.data + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
                </span>
                <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "16px", overflow: "hidden" }}>
                  <div style={{ width: `${(s.total_kg / maxSerie) * 100}%`, height: "100%", background: "var(--blue)", minWidth: "2px" }} />
                </div>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, minWidth: "6.5rem", textAlign: "right" }}>
                  {s.total_kg} kg · {s.vacas}v
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Ranking de vacas */}
      <div className="card mt-4">
        <div className="card-header mb-3">Ranking de Produção (top 20 por média)</div>
        <table className="fazenda-table">
          <thead>
            <tr><th>Vaca</th><th>Média</th><th>Pico</th><th>Última</th><th>Controles</th></tr>
          </thead>
          <tbody>
            {ranking.slice(0, 20).map((v) => (
              <tr key={v.numero_matriz}>
                <td style={{ fontWeight: 700 }}>{v.numero_matriz}</td>
                <td style={{ color: "var(--green-light)", fontWeight: 600 }}>{v.media_kg} kg</td>
                <td>{v.pico_kg} kg</td>
                <td>{v.ultima_kg} kg</td>
                <td style={{ color: "var(--text-muted)" }}>{v.controles}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
