import { HeartPulse, Milk, Syringe, Landmark, Wheat, BarChart3 } from "lucide-react";

type Feature = {
  icon: React.ComponentType<{ size?: number; color?: string }>;
  titulo: string;
  descricao: string;
};

const FEATURES: Feature[] = [
  {
    icon: HeartPulse,
    titulo: "Reprodução",
    descricao: "Protocolos IATF, inseminação, diagnóstico de gestação e histórico por matriz.",
  },
  {
    icon: Milk,
    titulo: "Produção",
    descricao: "Controle leiteiro, qualidade do leite (CCS/CPP), secagem e indicadores de produtividade.",
  },
  {
    icon: Syringe,
    titulo: "Sanidade",
    descricao: "Calendário sanitário preventivo, protocolos de tratamento e histórico clínico do rebanho.",
  },
  {
    icon: Landmark,
    titulo: "Financeiro",
    descricao: "Contas a pagar/receber, fluxo de caixa, DRE e folha de pagamento em um só lugar.",
  },
  {
    icon: Wheat,
    titulo: "Estoque & Alimentação",
    descricao: "Controle de insumos, dietas por lote e necessidade mensal de ração.",
  },
  {
    icon: BarChart3,
    titulo: "Relatórios & Indicadores",
    descricao: "Painéis gerenciais e exportação em Excel/PDF para decisão rápida.",
  },
];

export default function FeatureShowcase() {
  return (
    <div>
      <div
        className="feature-showcase-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "1rem",
        }}
      >
        {FEATURES.map(({ icon: Icon, titulo, descricao }) => (
          <div
            key={titulo}
            className="feature-showcase-card"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              padding: "1.1rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.6rem",
            }}
          >
            <div
              style={{
                width: "2.6rem",
                height: "2.6rem",
                borderRadius: "50%",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Icon size={20} color="var(--dourado-light)" />
            </div>
            <div style={{ fontWeight: 700, color: "var(--text)", fontSize: "0.95rem" }}>{titulo}</div>
            <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.82rem", lineHeight: 1.4 }}>
              {descricao}
            </p>
          </div>
        ))}
      </div>
      <style>{`
        .feature-showcase-card {
          transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }
        .feature-showcase-card:hover {
          transform: translateY(-3px);
          border-color: var(--dourado);
          box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
        }
        @media (prefers-reduced-motion: reduce) {
          .feature-showcase-card {
            transition: none;
          }
          .feature-showcase-card:hover {
            transform: none;
          }
        }
      `}</style>
    </div>
  );
}
