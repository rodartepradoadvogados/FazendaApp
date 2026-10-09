"use client";
import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useOverlay } from "@/components/useOverlay";
import { LARGURA_GAVETA_PADRAO } from "@/lib/janelas";

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
 *
 * 09/10/2026 — também é a "janela travada" do Financeiro (Dar baixa): `largura`
 * muda a largura e `fecharComEsc={false}` deixa só o X fechando. O Esc passa pela
 * pilha de overlays (useOverlay): um Modal aberto aqui dentro fecha sozinho, sem
 * levar a gaveta junto. Foco: vai para a gaveta ao abrir, fica preso nela (Tab) e
 * volta a quem abriu ao fechar.
 */
export function GavetaLancamento({
  aberto, onFechar, titulo, icone: Icone, aviso,
  mensagemSalva, onSalvarProximo, onConcluir,
  largura = LARGURA_GAVETA_PADRAO, fecharComEsc = true,
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
  /** Largura CSS da gaveta (padrão: min(80vw, 1320px), a de Lançamentos). */
  largura?: string;
  /** Padrão true. false = janela travada: Esc não fecha, só o X (e o clique fora nunca fecha). */
  fecharComEsc?: boolean;
  children: React.ReactNode;
}) {
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);
  // Uma gaveta montada já aberta (ex.: só existe enquanto há uma baixa) precisa de
  // um quadro "fechada" antes de deslizar — senão nasceria parada, sem animação.
  const [pronto, setPronto] = useState(false);
  useEffect(() => {
    if (!montado) return;
    const id = requestAnimationFrame(() => setPronto(true));
    return () => cancelAnimationFrame(id);
  }, [montado]);
  const visivel = aberto && pronto;
  const painelRef = useRef<HTMLElement>(null);

  // Trava o scroll do fundo enquanto a gaveta está aberta — mesmo cuidado que
  // um modal de tela cheia teria, senão a página por trás rola junto no celular.
  useEffect(() => {
    if (!aberto) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [aberto]);

  // Esc — pela pilha de overlays: só o da frente reage, e só se `fecharComEsc`.
  const { ehTopo } = useOverlay({ ativo: aberto, fecharComEsc, aoEsc: onFechar });

  // Foco: entra na gaveta ao abrir (sem roubar o de um campo que já tenha autoFocus),
  // fica preso nela com Tab/Shift+Tab e volta a quem abriu ao fechar. O ouvinte é
  // nativo no <aside> de propósito: o React propaga eventos de portais pela árvore
  // de componentes, e o Tab de um Modal aberto aqui dentro não pode cair neste laço.
  useEffect(() => {
    if (!aberto || !montado) return;
    const painel = painelRef.current;
    if (!painel) return;
    const gatilho = document.activeElement as HTMLElement | null;
    const seletorFocavel = 'a[href], button:not([disabled]), textarea, input:not([type="hidden"]), select, [tabindex]:not([tabindex="-1"])';
    if (!painel.contains(document.activeElement)) painel.focus({ preventScroll: true });
    function aoTeclar(e: KeyboardEvent) {
      if (e.key !== "Tab" || !painel || !ehTopo()) return;
      const focaveis = Array.from(painel.querySelectorAll<HTMLElement>(seletorFocavel)).filter((el) => el.offsetParent !== null);
      if (!focaveis.length) { e.preventDefault(); painel.focus(); return; }
      const [primeiro, ultimo] = [focaveis[0], focaveis[focaveis.length - 1]];
      const ativo = document.activeElement;
      if (e.shiftKey && (ativo === primeiro || ativo === painel)) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && ativo === ultimo) { e.preventDefault(); primeiro.focus(); }
      else if (!painel.contains(ativo)) { e.preventDefault(); primeiro.focus(); }
    }
    painel.addEventListener("keydown", aoTeclar);
    return () => {
      painel.removeEventListener("keydown", aoTeclar);
      if (gatilho && gatilho.isConnected) gatilho.focus?.({ preventScroll: true });
    };
  }, [aberto, montado, ehTopo]);

  if (!montado) return null;

  return createPortal(
    <>
      {/* Scrim clicável de propósito NENHUM — só escurece o fundo e bloqueia
          interação com ele. Clicar fora NÃO fecha a gaveta (pedido explícito
          do usuário): só o X do cabeçalho ou Esc fecham, para não perder um
          lançamento em andamento por um clique sem querer ao lado. */}
      <div
        aria-hidden={true}
        className="gaveta-lancamento-scrim"
        style={{
          position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 65,
          background: "var(--overlay)",
          opacity: visivel ? 1 : 0,
          pointerEvents: aberto ? "auto" : "none",
          transition: "opacity 0.2s ease",
        }}
      />
      <aside
        ref={painelRef} tabIndex={-1}
        role="dialog" aria-modal="true" aria-label={titulo}
        // Fechada, a gaveta fica fora da tela mas montada: `inert` tira o conteúdo
        // dela do Tab e do leitor de tela.
        aria-hidden={!aberto} inert={!aberto}
        onClick={(e) => e.stopPropagation()}
        className="gaveta-lancamento-painel"
        style={{
          // 65–75% da tela (nunca os ~330px de antes) para caber campos lado
          // a lado — os grids responsivos dos formulários (md:/lg:grid-cols-N)
          // reagem à largura da JANELA, não à da gaveta, então precisam de
          // espaço de verdade para não ficar cramped (ver comentário em
          // globals.css sobre a força de 1 coluna que existia antes disto).
          position: "fixed", bottom: 0, right: visivel ? 0 : "-100vw",
          width: largura, minWidth: "min(330px, 100vw)", maxWidth: "100vw", zIndex: 65, outline: "none",
          background: "var(--surface)", borderLeft: "1px solid var(--border)",
          boxShadow: "-6px 0 20px rgba(20,30,45,0.18)",
          display: "flex", flexDirection: "column",
          // Desliza entrando da direita pra esquerda (abrir) e saindo da
          // esquerda pra direita (fechar) — mesma curva do scrim.
          transition: "right 0.28s cubic-bezier(0.4, 0, 0.2, 1)",
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
