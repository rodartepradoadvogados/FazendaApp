"use client";
import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * Container único de lançamento (redesign "Cooperativa", mockup 1e) — gaveta
 * lateral de ~330px que envolve TODOS os formulários de components/lancamentos/*
 * (reprodutivo, produção, sanidade, alimentação, estoque), abrindo tanto a
 * partir da tela de Lançamentos quanto de uma linha da Agenda. Financeiro fica
 * de fora (T4, duas colunas, feito em paralelo) e Protocolos/wizard também
 * (T5) — nenhum dos dois usa este componente.
 *
 * Por que `right` e não `transform: translateX(...)` para a animação de
 * entrada: os pickers/popups internos (AnimalPickerModal, Modal, LotePicker,
 * PopupVinculoFinanceiro...) são todos `position: fixed; inset: 0` — e um
 * elemento fixed só cobre a tela INTEIRA enquanto nenhum ancestral seu tiver
 * transform/filter/perspective (isso cria um novo bloco de posicionamento, e
 * "fixed" passa a valer só dentro dele). Se a gaveta deslizasse via
 * transform, qualquer picker aberto dentro dela ficaria espremido nos 330px
 * de largura da gaveta em vez de cobrir a tela — exatamente o bug que este
 * ticket pede pra evitar. Animar `right` (posição, não transform) não cria
 * esse bloco, então os popups continuam centralizados na tela toda.
 */
export function GavetaLancamento({
  aberto, onFechar, titulo, icone: Icone, aviso,
  mensagemSalva, onSalvarProximo, onConcluir,
  children,
}: {
  aberto: boolean;
  onFechar: () => void;
  titulo: string;
  icone: React.ComponentType<{ size?: number | string; style?: React.CSSProperties }>;
  /** Faixa informativa opcional (equivalente ao banner "já grava de verdade" da tela de Lançamentos). */
  aviso?: React.ReactNode;
  /** Mensagem transitória de sucesso — quando presente, mostra o rodapé com
   * "Salvar e próximo" (lançamento sequencial: mantém a gaveta aberta e pede
   * pro formulário reiniciar) e "Concluir" (fecha a gaveta). */
  mensagemSalva?: string | null;
  onSalvarProximo?: () => void;
  onConcluir?: () => void;
  children: React.ReactNode;
}) {
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);

  // Trava o scroll do fundo enquanto a gaveta está aberta — mesmo cuidado que
  // um modal de tela cheia teria, senão a página por trás rola junto no celular.
  useEffect(() => {
    if (!aberto) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [aberto]);

  // Esc fecha — mesma convenção dos demais overlays do site.
  useEffect(() => {
    if (!aberto) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onFechar(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [aberto, onFechar]);

  if (!montado) return null;

  return createPortal(
    <>
      {/* Scrim clicável de propósito NENHUM — só escurece o fundo e bloqueia
          interação com ele. Clicar fora NÃO fecha a gaveta (pedido explícito
          do usuário): só o X do cabeçalho ou Esc fecham, para não perder um
          lançamento em andamento por um clique sem querer ao lado. */}
      <div
        aria-hidden={!aberto}
        className="gaveta-lancamento-scrim"
        style={{
          position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 65,
          background: "var(--overlay)",
          opacity: aberto ? 1 : 0,
          pointerEvents: aberto ? "auto" : "none",
          transition: "opacity 0.2s ease",
        }}
      />
      <aside
        role="dialog" aria-modal="true" aria-label={titulo}
        onClick={(e) => e.stopPropagation()}
        className="gaveta-lancamento-painel"
        style={{
          // 65–75% da tela (nunca os ~330px de antes) para caber campos lado
          // a lado — os grids responsivos dos formulários (md:/lg:grid-cols-N)
          // reagem à largura da JANELA, não à da gaveta, então precisam de
          // espaço de verdade para não ficar cramped (ver comentário em
          // globals.css sobre a força de 1 coluna que existia antes disto).
          position: "fixed", bottom: 0, right: aberto ? 0 : "-100vw",
          width: "min(72vw, 1180px)", minWidth: "min(330px, 100vw)", zIndex: 65,
          background: "var(--surface)", borderLeft: "1px solid var(--border)",
          boxShadow: "-6px 0 20px rgba(20,30,45,0.18)",
          display: "flex", flexDirection: "column",
        }}
      >
        <header style={{
          background: "var(--card-header-bg)", color: "var(--card-header-fg)",
          padding: "0.75rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: "0.5rem", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <Icone size={15} style={{ flexShrink: 0 }} />
            <span style={{
              fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", fontSize: "0.78rem",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {titulo}
            </span>
          </div>
          <button type="button" onClick={onFechar} aria-label="Fechar" className="btn-ghost"
            style={{ padding: "0.3rem", border: "none", background: "transparent", color: "inherit", flexShrink: 0 }}>
            <X size={16} />
          </button>
        </header>

        {aviso && (
          <div style={{
            padding: "0.6rem 0.9rem", background: "rgba(184,134,11,0.10)",
            borderBottom: "1px solid var(--border)", fontSize: "0.74rem", color: "var(--text-muted)", flexShrink: 0,
          }}>
            {aviso}
          </div>
        )}

        <div className="gaveta-lancamento-corpo" style={{ padding: "0.9rem", overflowY: "auto", overflowX: "auto", flex: 1, minHeight: 0 }}>
          {children}
        </div>

        {mensagemSalva != null && (
          <div style={{ padding: "0.75rem 0.9rem", borderTop: "1px solid var(--border)", background: "rgba(46,125,82,0.12)", flexShrink: 0 }}>
            <p style={{ fontSize: "0.8rem", color: "var(--text)", margin: "0 0 0.5rem" }}>✓ {mensagemSalva}</p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" className="btn-primary-gold" style={{ fontSize: "0.8rem" }} onClick={onSalvarProximo}
                title="Mantém a gaveta aberta, pronta para lançar o próximo">
                Salvar e próximo
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={onConcluir}>
                Concluir
              </button>
            </div>
          </div>
        )}
      </aside>
    </>,
    document.body
  );
}
