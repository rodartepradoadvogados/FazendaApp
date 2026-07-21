import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";

// Cabeçalho de topo compartilhado pelas páginas /sobre/* — reaproveita o
// mesmo fundo temático (baixa opacidade, escala de cinza) já usado nas
// páginas internas por seção (ver components/SectionBackground.tsx), então
// não depende de fotos novas para ficar ilustrado.
export function InstitucionalHero({
  icon: Icon, eyebrow, titulo, subtitulo, imagem,
}: {
  icon: LucideIcon; eyebrow: string; titulo: string; subtitulo: string; imagem: string;
}) {
  return (
    <section style={{ position: "relative", overflow: "hidden", padding: "2.5rem 1.5rem 3rem" }}>
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imagem} alt="" style={{
          position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 50%",
          opacity: 0.14, filter: "grayscale(1) contrast(1.08) brightness(0.95)", mixBlendMode: "luminosity",
        }} />
      </div>
      <div style={{ position: "relative", zIndex: 1, maxWidth: "760px", margin: "0 auto", textAlign: "center" }}>
        <Link href="/login" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", color: "var(--text-muted)", textDecoration: "none", fontSize: "0.8rem", marginBottom: "1.4rem" }}>
          <ArrowLeft size={14} /> Voltar para a página inicial
        </Link>
        <div style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center", width: "3.4rem", height: "3.4rem",
          borderRadius: "999px", background: "rgba(212,160,23,0.14)", border: "1px solid rgba(212,160,23,0.3)", marginBottom: "1.1rem",
        }}>
          <Icon size={26} style={{ color: "var(--dourado-light)" }} />
        </div>
        <div>
          <span style={{
            display: "inline-block", padding: "0.3rem 0.75rem", borderRadius: "999px", fontSize: "0.72rem", fontWeight: 700,
            letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dourado-light)",
            background: "rgba(212,160,23,0.14)", border: "1px solid rgba(212,160,23,0.3)", marginBottom: "0.9rem",
          }}>
            {eyebrow}
          </span>
        </div>
        <h1 style={{ fontSize: "clamp(1.6rem, 3.2vw, 2.4rem)", fontWeight: 800, lineHeight: 1.18, margin: "0 0 0.8rem", color: "#fff" }}>{titulo}</h1>
        <p style={{ fontSize: "1rem", color: "rgba(245,238,241,0.78)", margin: 0, lineHeight: 1.55 }}>{subtitulo}</p>
      </div>
    </section>
  );
}
