import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BANNERS } from "./banners";

// Todos os temas do banco de banners, sempre navegáveis — os 4 que não
// estiverem girando no carrossel do topo hoje ficam disponíveis aqui.
export default function BannerGrid() {
  return (
    <div>
      <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "#fff", textAlign: "center", margin: "2.4rem 0 1.2rem" }}>
        Todos os temas do sistema
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px,1fr))", gap: "0.9rem" }}>
        {BANNERS.map((b) => (
          <Link
            key={b.slug}
            href={b.href}
            className="banner-grid-card"
            style={{
              display: "flex", alignItems: "flex-start", gap: "0.8rem", textDecoration: "none",
              padding: "1rem", borderRadius: "12px", background: "var(--surface)", border: "1px solid var(--border)",
            }}
          >
            <div style={{
              width: "2.4rem", height: "2.4rem", borderRadius: "50%", background: "var(--surface-2)",
              border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            }}>
              <b.icon size={18} color="var(--dourado-light)" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, color: "var(--text)", fontSize: "0.88rem" }}>{b.eyebrow}</div>
              <p style={{ margin: "0.15rem 0 0", color: "var(--text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>{b.descricao}</p>
            </div>
            <ArrowRight size={15} style={{ color: "var(--text-muted)", flexShrink: 0, marginTop: "0.2rem" }} />
          </Link>
        ))}
      </div>
      <style>{`
        .banner-grid-card { transition: border-color 0.15s ease, transform 0.15s ease; }
        .banner-grid-card:hover { border-color: var(--dourado); transform: translateY(-2px); }
        @media (prefers-reduced-motion: reduce) {
          .banner-grid-card { transition: none; }
          .banner-grid-card:hover { transform: none; }
        }
      `}</style>
    </div>
  );
}
