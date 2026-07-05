// Indicadores — painel zootécnico/reprodutivo/produtivo (Server Component)
import { fetchIndicadores } from "@/lib/api";
import { AlertTriangle, TrendingUp, HeartPulse, Milk, BarChart3 } from "lucide-react";

async function getData() {
  try {
    return { ind: await fetchIndicadores(), error: null };
  } catch (e: any) {
    return { ind: null, error: e.message };
  }
}

function pct(v: number | null) {
  return v === null || v === undefined ? "—" : `${v}%`;
}
function num(v: number | null | undefined, suf = "") {
  return v === null || v === undefined ? "—" : `${v}${suf}`;
}

export default async function IndicadoresPage() {
  const { ind, error } = await getData();

  const reb = ind?.rebanho;
  const rep = ind?.reproducao;
  const prod = ind?.producao;
  const grupos: [string, number][] = reb ? Object.entries(reb.distribuicao_grupos) : [];
  const maxGrupo = grupos.reduce((m, [, n]) => Math.max(m, n), 0) || 1;

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 size={22} style={{ color: "var(--dourado-light)" }} />
          Indicadores do Rebanho
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Composição, eficiência reprodutiva e produção — calculado sobre os dados carregados.
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload dos CSV</a>.</span>
        </div>
      )}

      {/* KPIs reprodutivos */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--green-light)" }}>{pct(rep?.taxa_prenhez_pct)}</p>
          <p className="kpi-label">Taxa de prenhez</p>
          <HeartPulse size={18} style={{ color: "var(--text-muted)", marginTop: "0.4rem" }} />
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--blue)" }}>{pct(rep?.taxa_concepcao_pct)}</p>
          <p className="kpi-label">Concepção / serviço</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--amber)" }}>{num(rep?.iep_meses, " m")}</p>
          <p className="kpi-label">IEP médio</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{pct(rep?.perc_vazias_pct)}</p>
          <p className="kpi-label">Vazias</p>
        </div>
      </div>

      {/* KPIs produção */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="kpi-card">
          <p className="kpi-value" style={{ color: "var(--green-light)" }}>{num(prod?.producao_total_dia_kg, " kg")}</p>
          <p className="kpi-label">Produção/dia (últ. controle)</p>
          <Milk size={18} style={{ color: "var(--text-muted)", marginTop: "0.4rem" }} />
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{num(prod?.producao_media_kg, " kg")}</p>
          <p className="kpi-label">Média por vaca</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{num(prod?.del_medio)}</p>
          <p className="kpi-label">DEL médio (dias)</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-value">{num(prod?.vacas_com_producao)}</p>
          <p className="kpi-label">Vacas com produção</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Situação reprodutiva */}
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2">
            <HeartPulse size={14} /> Situação Reprodutiva
          </div>
          <table className="fazenda-table">
            <tbody>
              <tr><td>Fêmeas aptas</td><td style={{ fontWeight: 700, textAlign: "right" }}>{num(rep?.aptas)}</td></tr>
              <tr><td>Prenhes</td><td style={{ fontWeight: 700, textAlign: "right", color: "var(--green-light)" }}>{num(rep?.prenhes)}</td></tr>
              <tr><td>Vazias</td><td style={{ fontWeight: 700, textAlign: "right", color: "var(--amber)" }}>{num(rep?.vazias)}</td></tr>
              <tr><td>Inseminadas (aguard. diagnóstico)</td><td style={{ fontWeight: 700, textAlign: "right", color: "var(--blue)" }}>{num(rep?.inseminadas)}</td></tr>
            </tbody>
          </table>
          <div className="card-header mt-4 mb-2 flex items-center gap-2">
            <TrendingUp size={14} /> Partos previstos
          </div>
          <table className="fazenda-table">
            <tbody>
              <tr><td>Próximos 30 dias</td><td style={{ fontWeight: 700, textAlign: "right" }}>{num(rep?.partos_previstos?.em_30_dias)}</td></tr>
              <tr><td>Próximos 60 dias</td><td style={{ fontWeight: 700, textAlign: "right" }}>{num(rep?.partos_previstos?.em_60_dias)}</td></tr>
              <tr><td>Próximos 90 dias</td><td style={{ fontWeight: 700, textAlign: "right" }}>{num(rep?.partos_previstos?.em_90_dias)}</td></tr>
            </tbody>
          </table>
        </div>

        {/* Composição do rebanho */}
        <div className="card">
          <div className="card-header mb-3">
            Composição do Rebanho ({num(reb?.total)} animais)
          </div>
          <div className="space-y-1.5">
            {grupos.map(([grupo, n]) => (
              <div key={grupo} className="flex items-center gap-2">
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", minWidth: "11rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {grupo}
                </span>
                <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "14px", overflow: "hidden" }}>
                  <div style={{ width: `${(n / maxGrupo) * 100}%`, height: "100%", background: "var(--vinho-light, #8B3A56)", minWidth: "2px" }} />
                </div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, minWidth: "1.6rem", textAlign: "right" }}>{n}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
