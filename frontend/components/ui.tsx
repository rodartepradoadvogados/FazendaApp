"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronRight, Check, Cog, HeartPulse, Milk, Wallet, Syringe, BarChart3 } from "lucide-react";

/**
 * Indicador — cartão de KPI com um círculo de ícone colorido por categoria,
 * ecoando os ícones circulares já usados no Menu do app. Cores de categoria
 * fixas da marca CowData (--cat-*), iguais em Agenda, menu do app e landing.
 * "Produção" não é uma das 8 categorias fixas da marca; mantém azul (sem
 * mudança). "Geral" continua dourado (não é uma categoria de módulo).
 */
export type CategoriaIndicador = "geral" | "reprodutivo" | "producao" | "financeiro" | "sanidade";

const CATEGORIA_COR: Record<CategoriaIndicador, string> = {
  geral: "var(--dourado)",
  reprodutivo: "var(--cat-reproducao)",
  producao: "var(--blue)",
  financeiro: "var(--cat-financeiro)",
  sanidade: "var(--cat-sanidade)",
};
const CATEGORIA_ICONE: Record<CategoriaIndicador, any> = {
  geral: Cog,
  reprodutivo: HeartPulse,
  producao: Milk,
  financeiro: Wallet,
  sanidade: Syringe,
};

export function Indicador({
  valor, rotulo, categoria = "geral", icon, cor, onClick, podeClicar, extra, title, corLabel, borda,
}: {
  valor: React.ReactNode;
  rotulo: React.ReactNode;
  categoria?: CategoriaIndicador;
  icon?: any;
  /** Sobrescreve a cor da categoria quando o indicador precisa de destaque próprio (ex.: alerta). */
  cor?: string;
  onClick?: () => void;
  podeClicar?: boolean;
  extra?: React.ReactNode;
  /** Sobrescreve o tooltip padrão ("Clique para ver os detalhes") quando clicável; se
   * informado, aparece mesmo quando o cartão não está clicável (ex.: explicação fixa). */
  title?: string;
  /** Cor do rótulo — usado junto com `cor` quando o indicador é um alerta (ex.: pendências). */
  corLabel?: string;
  /** Contorno do cartão — mesmo destaque de alerta, quando uma borda simples não basta. */
  borda?: string;
}) {
  const clicavel = !!onClick && (podeClicar ?? true);
  // O círculo do ícone é sempre a cor da categoria (identidade fixa da área);
  // `cor` só sobrescreve o texto do valor, para destaque semântico (positivo/
  // negativo, alerta) — sem isso, o círculo mudava de cor a cada indicador.
  const corCategoria = CATEGORIA_COR[categoria];
  const corValor = cor || corCategoria;
  const Icon = icon || CATEGORIA_ICONE[categoria];
  return (
    <div
      className={clicavel ? "kpi-card row-clickable" : "kpi-card"}
      onClick={clicavel ? onClick : undefined}
      title={title || (clicavel ? "Clique para ver os detalhes" : undefined)}
      style={{ ["--kpi-c" as any]: corCategoria, cursor: clicavel ? "pointer" : undefined, border: borda ? `1px solid ${borda}` : undefined }}
    >
      <div className="kpi-chip"><Icon size={15} /></div>
      <p className="kpi-value" style={{ fontSize: "1.4rem", color: corValor }}>{valor}</p>
      <p className="kpi-label flex items-center gap-1 flex-wrap" style={corLabel ? { color: corLabel } : undefined}>{rotulo}{extra}</p>
    </div>
  );
}

/** Estado vazio com ícone — substitui o texto solto usado hoje quando um
 * gráfico ou lista não tem dados, deixando claro que a tela está correta. */
export function EstadoVazio({ icon, children }: { icon?: any; children: React.ReactNode }) {
  const Icon = icon || BarChart3;
  return (
    <div className="empty-state">
      <Icon size={22} />
      <div>{children}</div>
    </div>
  );
}

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
  permitirNovo,
  onAdicionarNovo,
  placeholderNovo,
}: {
  label: string;
  opcoes: string[];
  selecionados: string[];
  onChange: (v: string[]) => void;
  formatar?: (v: string) => string;
  // Quando true, mostra um campo "+ novo" dentro do próprio painel — corrige o
  // caso de opções que não vêm de um cadastro fixo (ex.: categoria-alvo livre
  // do calendário sanitário): sem isso, depois de adicionar a 1ª opção por um
  // campo externo, reabrir o painel para escolher a 2ª só mostrava o que já
  // tinha sido marcado, sem nada novo para selecionar.
  permitirNovo?: boolean;
  onAdicionarNovo?: (valor: string) => void;
  placeholderNovo?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [novoValor, setNovoValor] = useState("");
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
          borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
          textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.3rem",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: selecionados.length ? "var(--text)" : "var(--text-muted)" }}>{resumo}</span>
        <ChevronDown size={13} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>
      {aberto && posicao && typeof document !== "undefined" && createPortal(
        <div ref={painelRef} style={{
          position: "fixed", zIndex: 1000, top: posicao.top, left: posicao.left, width: posicao.width,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
          boxShadow: "0 8px 24px rgba(0,0,0,0.18)", maxHeight: "260px", overflowY: "auto", padding: "0.25rem",
        }}>
          {permitirNovo && (
            <div style={{ display: "flex", gap: "0.3rem", padding: "0.3rem 0.5rem" }}>
              <input
                value={novoValor} onChange={(e) => setNovoValor(e.target.value)}
                placeholder={placeholderNovo || "+ novo…"} autoFocus
                style={{ flex: 1, minWidth: 0, fontSize: "0.75rem", padding: "0.25rem 0.4rem", border: "1px solid var(--border)", borderRadius: 5, background: "var(--surface-2)", color: "var(--text)" }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" || !novoValor.trim()) return;
                  e.preventDefault();
                  onAdicionarNovo?.(novoValor.trim());
                  setNovoValor("");
                }}
              />
              <button type="button"
                onClick={() => { if (!novoValor.trim()) return; onAdicionarNovo?.(novoValor.trim()); setNovoValor(""); }}
                style={{ fontSize: "0.72rem", padding: "0.25rem 0.5rem", border: "1px solid var(--border)", borderRadius: 5, background: "var(--surface-2)", color: "var(--text)", cursor: "pointer", whiteSpace: "nowrap" }}>
                Adicionar
              </button>
            </div>
          )}
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
                  borderRadius: "var(--r-sm)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
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
              transition: "background 0.15s ease, border-color 0.15s ease, color 0.15s ease",
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
 * Que METADE de uma tela de categoria (empreita, contrato, diária, férias/13º,
 * rescisão) deve aparecer.
 *
 * A tela de Fechamento da folha passou a ter três cards no topo — Consultar ·
 * Lançar · Resolver antes de fechar — e cada tela de categoria tem as duas
 * coisas dentro: o formulário/assistente ("lançar") e a listagem do que já foi
 * lançado, com as ações sobre cada item ("listar"). Sem este corte, escolher
 * "Lançar" continuaria mostrando a listagem inteira embaixo e o card não
 * significaria nada. "tudo" é o comportamento antigo, para quem monta a tela
 * fora desse contexto.
 */
export type ModoSecaoCategoria = "tudo" | "lancar" | "listar";

/**
 * SecaoRecolhivel — cartão com cabeçalho clicável que expande/recolhe o conteúdo.
 * Útil para agrupar blocos densos e deixar a tela mais limpa por padrão.
 */
export function SecaoRecolhivel({
  titulo,
  icon: Icon,
  defaultAberta = false,
  aberta: abertaControlada,
  onAlternar,
  badge,
  descricao,
  children,
}: {
  titulo: string;
  icon?: any;
  defaultAberta?: boolean;
  /** Modo CONTROLADO: quem chama manda o estado e recebe o clique. Existe
   *  porque o painel de exceções da folha precisa ABRIR o card certo antes de
   *  rolar até a linha — com o estado só aqui dentro, "Ver a folha" rolava
   *  para um elemento que ainda não estava montado e não achava nada. */
  aberta?: boolean;
  onAlternar?: () => void;
  badge?: React.ReactNode;
  descricao?: string;
  children: React.ReactNode;
}) {
  const [abertaLocal, setAbertaLocal] = useState(defaultAberta);
  const aberta = abertaControlada ?? abertaLocal;

  return (
    <div className="card mb-4">
      <button
        onClick={() => (onAlternar ? onAlternar() : setAbertaLocal((a) => !a))}
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
