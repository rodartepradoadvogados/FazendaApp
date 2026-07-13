"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronRight, Check } from "lucide-react";

/**
 * MultiFiltro — filtro de seleção múltipla em formato de menu suspenso com
 * caixas de marcação. Simples para o usuário leigo: o botão mostra quantos
 * itens estão marcados; nenhum marcado = "Todos" (sem filtro). Marcar mais de
 * um item filtra por qualquer um deles (OU).
 */
export function MultiFiltro({
  label,
  opcoes,
  selecionados,
  onChange,
  formatar,
}: {
  label: string;
  opcoes: string[];
  selecionados: string[];
  onChange: (v: string[]) => void;
  formatar?: (v: string) => string;
}) {
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const painelRef = useRef<HTMLDivElement>(null);
  const [posicao, setPosicao] = useState<{ top: number; left: number; width: number } | null>(null);

  const atualizarPosicao = () => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setPosicao({ top: r.bottom + 4, left: r.left, width: r.width });
  };

  useEffect(() => {
    if (!aberto) return;
    atualizarPosicao();
    const onDoc = (e: MouseEvent) => {
      const alvo = e.target as Node;
      const dentroTrigger = ref.current && ref.current.contains(alvo);
      const dentroPainel = painelRef.current && painelRef.current.contains(alvo);
      if (!dentroTrigger && !dentroPainel) setAberto(false);
    };
    const onScrollOuResize = () => atualizarPosicao();
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("resize", onScrollOuResize);
    window.addEventListener("scroll", onScrollOuResize, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("resize", onScrollOuResize);
      window.removeEventListener("scroll", onScrollOuResize, true);
    };
  }, [aberto]);

  const marcados = new Set(selecionados);
  const toggle = (o: string) => {
    const n = new Set(marcados);
    n.has(o) ? n.delete(o) : n.add(o);
    onChange(Array.from(n));
  };
  const resumo = selecionados.length === 0
    ? "Todos"
    : selecionados.length === 1
      ? (formatar ? formatar(selecionados[0]) : selecionados[0])
      : `${selecionados.length} selecionados`;

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>{label}</label>
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        title={`Filtrar por ${label.toLowerCase()} — marque um ou vários; nenhum marcado mostra todos`}
        style={{
          background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
          borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
          textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.3rem",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: selecionados.length ? "var(--text)" : "var(--text-muted)" }}>{resumo}</span>
        <ChevronDown size={13} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>
      {aberto && posicao && typeof document !== "undefined" && createPortal(
        <div ref={painelRef} style={{
          position: "fixed", zIndex: 1000, top: posicao.top, left: posicao.left, width: posicao.width,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px",
          boxShadow: "0 8px 24px rgba(0,0,0,0.18)", maxHeight: "260px", overflowY: "auto", padding: "0.25rem",
        }}>
          {selecionados.length > 0 && (
            <button type="button" onClick={() => onChange([])}
              style={{ width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer",
                fontSize: "0.72rem", color: "var(--text-muted)", padding: "0.3rem 0.5rem" }}>
              Limpar seleção
            </button>
          )}
          {opcoes.length === 0 && (
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", padding: "0.4rem 0.5rem" }}>Sem opções.</div>
          )}
          {opcoes.map((o) => {
            const on = marcados.has(o);
            return (
              <button type="button" key={o} onClick={() => toggle(o)}
                style={{ width: "100%", textAlign: "left", background: on ? "var(--surface-2)" : "none", border: "none",
                  cursor: "pointer", fontSize: "0.8rem", color: "var(--text)", padding: "0.35rem 0.5rem",
                  borderRadius: "5px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ width: 15, height: 15, borderRadius: 4, flexShrink: 0,
                  border: "1px solid " + (on ? "var(--dourado)" : "var(--border)"),
                  background: on ? "var(--dourado)" : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {on && <Check size={11} color="#fff" strokeWidth={3} />}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{formatar ? formatar(o) : o}</span>
              </button>
            );
          })}
        </div>,
        document.body
      )}
    </div>
  );
}

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
