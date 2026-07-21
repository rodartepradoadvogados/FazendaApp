import type { LucideIcon } from "lucide-react";

export type Destaque = { icon: LucideIcon; titulo: string; texto: string };

// Grade de destaques reaproveitada em todas as páginas /sobre/* — cada
// página só fornece os dados (ícone/título/texto), o layout é sempre igual.
export function DestaquesGrid({ itens }: { itens: Destaque[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px,1fr))", gap: "1rem" }}>
      {itens.map((item) => (
        <div key={item.titulo} className="card" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <div style={{
            width: "2.6rem", height: "2.6rem", borderRadius: "50%", background: "var(--surface-2)",
            border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <item.icon size={20} color="var(--dourado-light)" />
          </div>
          <div style={{ fontWeight: 700, color: "var(--text)", fontSize: "0.95rem" }}>{item.titulo}</div>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.84rem", lineHeight: 1.5 }}>{item.texto}</p>
        </div>
      ))}
    </div>
  );
}

// Faixa de números/estatísticas curtas (ex.: "4 protocolos IATF", "12 sub-abas")
// para dar volume visual sem depender de fotos.
export function FaixaNumeros({ itens }: { itens: { valor: string; rotulo: string }[] }) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: `repeat(${Math.min(itens.length, 4)}, 1fr)`, gap: "1rem",
      padding: "1.4rem", borderRadius: "14px", background: "var(--surface-2)", border: "1px solid var(--border)",
    }} className="destaques-faixa-numeros">
      {itens.map((it) => (
        <div key={it.rotulo} style={{ textAlign: "center" }}>
          <div style={{ fontSize: "1.7rem", fontWeight: 800, color: "var(--dourado-light)" }}>{it.valor}</div>
          <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{it.rotulo}</div>
        </div>
      ))}
      <style>{`
        @media (max-width: 700px) {
          .destaques-faixa-numeros { grid-template-columns: repeat(2, 1fr) !important; }
        }
      `}</style>
    </div>
  );
}

export function SecaoConteudo({ titulo, children }: { titulo?: string; children: React.ReactNode }) {
  return (
    <section style={{ padding: "0 1.5rem 3rem" }}>
      <div style={{ maxWidth: "1000px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {titulo && <h2 style={{ fontSize: "1.3rem", fontWeight: 800, color: "#fff", margin: 0, textAlign: "center" }}>{titulo}</h2>}
        {children}
      </div>
    </section>
  );
}
