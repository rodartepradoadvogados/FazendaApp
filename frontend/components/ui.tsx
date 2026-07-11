"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

/**
 * TabBar — barra de abas em formato de "pílula", usada em várias telas do app.
 * Cada pílula mostra o `title` (ou o próprio label) ao passar o mouse, para
 * quem não conhece o sistema entender o que cada aba faz.
 */
export function TabBar<T extends string>({
  abas,
  ativa,
  onChange,
}: {
  abas: readonly { id: T; label: string; icon?: any; title?: string }[];
  ativa: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
      {abas.map((aba) => {
        const Icon = aba.icon;
        const ativo = aba.id === ativa;
        return (
          <button
            key={aba.id}
            onClick={() => onChange(aba.id)}
            title={aba.title || aba.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              fontSize: "0.8rem",
              padding: "0.4rem 0.9rem",
              borderRadius: "999px",
              cursor: "pointer",
              border: "1px solid " + (ativo ? "var(--pill-active-border)" : "var(--border)"),
              background: ativo ? "var(--pill-active-bg)" : "transparent",
              color: ativo ? "var(--pill-active-fg)" : "var(--text-muted)",
              fontWeight: ativo ? 700 : 500,
            }}
          >
            {Icon && <Icon size={14} />} {aba.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * SecaoRecolhivel — cartão com cabeçalho clicável que expande/recolhe o conteúdo.
 * Útil para agrupar blocos densos e deixar a tela mais limpa por padrão.
 */
export function SecaoRecolhivel({
  titulo,
  icon: Icon,
  defaultAberta = false,
  badge,
  descricao,
  children,
}: {
  titulo: string;
  icon?: any;
  defaultAberta?: boolean;
  badge?: React.ReactNode;
  descricao?: string;
  children: React.ReactNode;
}) {
  const [aberta, setAberta] = useState(defaultAberta);

  return (
    <div className="card mb-4">
      <button
        onClick={() => setAberta((a) => !a)}
        title={descricao || (aberta ? "Clique para recolher" : "Clique para expandir")}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          textAlign: "left",
        }}
      >
        <div className="flex items-center gap-2">
          {aberta ? (
            <ChevronDown size={15} style={{ color: "var(--accent-icon)" }} />
          ) : (
            <ChevronRight size={15} style={{ color: "var(--accent-icon)" }} />
          )}
          {Icon && <Icon size={14} />}
          <span className="card-header" style={{ margin: 0 }}>
            {titulo}
          </span>
          {badge != null && <span style={{ marginLeft: "auto" }}>{badge}</span>}
        </div>
      </button>
      {aberta && <div className="mt-3">{children}</div>}
    </div>
  );
}
