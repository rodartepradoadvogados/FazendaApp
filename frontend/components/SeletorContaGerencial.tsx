"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronRight, Search, Check } from "lucide-react";
import {
  ContaPlano, nivelDaConta, estiloNivel, ehFolha, prefixoDoTipo, filhosDiretos, normalizar,
} from "@/lib/contaGerencial";

/**
 * Seletor de conta gerencial em ÁRVORE — mostra a hierarquia (nível 1 negrito,
 * 2 normal, 3 itálico+transparente, 4 itálico+transparente+sublinhado) e só
 * permite escolher a conta-FOLHA (o galho mais baixo). Com busca por nome/código.
 */
export function SeletorContaGerencial({
  contas, tipo, natureza, prefixosPermitidos, codigo, nome, onSelect, placeholder,
}: {
  contas: ContaPlano[];
  tipo: "receita" | "despesa";
  // Quando informado ("servico" | "produto"), só mostra/permite escolher
  // contas-folha marcadas com essa natureza ou "ambos" — contas de grupo
  // (não-folha) continuam aparecendo para navegação da árvore.
  natureza?: "servico" | "produto";
  // Restringe a árvore a só estes ramos (e seus descendentes) — ex.: compra
  // de animal só pode lançar em 3.10.06/3.10.07. Os próprios códigos listados
  // viram as raízes visíveis (não mostra os ancestrais deles).
  prefixosPermitidos?: string[];
  codigo: string;
  nome: string;
  onSelect: (codigo: string, nome: string) => void;
  placeholder?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [termo, setTermo] = useState("");
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);
  const botaoRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  // A lista abre num Portal (renderizada em document.body, position: fixed)
  // em vez de position: absolute dentro deste componente — isso evita que ela
  // seja cortada quando um ancestral tem overflow não-visível (ex.: `.card`
  // tem `overflow-x: auto`, que por spec do CSS também vira `overflow-y: auto`
  // quando o outro eixo não é "visible", recortando qualquer filho que
  // ultrapasse a altura do card — como este seletor costuma fazer dentro de
  // um item de nota ou de um modal).
  const [pos, setPos] = useState<{ top: number; left: number; width: number; maxHeight: number } | null>(null);

  // Só as contas do tipo certo (receita "2" / despesa "3"), ativas, e —
  // quando `natureza` for informado — restritas às folhas compatíveis.
  const disponiveis = useMemo(() => {
    let doTipo: ContaPlano[];
    if (prefixosPermitidos?.length) {
      doTipo = contas.filter((c) => (c.ativa ?? true) &&
        prefixosPermitidos.some((p) => c.codigo === p || c.codigo.startsWith(p + ".")));
    } else {
      const pref = prefixoDoTipo(tipo);
      doTipo = contas.filter(
        (c) => (c.ativa ?? true) && (c.codigo === pref || c.codigo.startsWith(pref + "."))
      );
    }
    if (!natureza) return doTipo;
    const codigosDoTipo = doTipo.map((c) => c.codigo);
    return doTipo.filter((c) => {
      if (!ehFolha(c.codigo, codigosDoTipo)) return true;
      const nat = c.natureza || "ambos";
      return nat === "ambos" || nat === natureza;
    });
  }, [contas, tipo, natureza, prefixosPermitidos]);

  const todosCodigos = useMemo(() => disponiveis.map((c) => c.codigo), [disponiveis]);
  const raizes = useMemo(() => {
    if (prefixosPermitidos?.length) {
      return disponiveis
        .filter((c) => prefixosPermitidos.includes(c.codigo))
        .sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true }));
    }
    return filhosDiretos("", disponiveis);
  }, [disponiveis, prefixosPermitidos]);

  // Abre as raízes do tipo por padrão (mostra os grandes grupos de cara).
  useEffect(() => {
    setExpandidos(new Set(raizes.map((r) => r.codigo)));
  }, [raizes]);

  // Fecha ao clicar fora (do botão OU da lista — que agora mora num Portal,
  // fora da árvore DOM deste componente).
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      const alvo = e.target as Node;
      if (ref.current?.contains(alvo)) return;
      if (popupRef.current?.contains(alvo)) return;
      setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);

  // Recalcula a posição/tamanho da lista (ancorada no botão) sempre que abrir,
  // e ao rolar/redimensionar — inclusive rolagem de um container ancestral
  // (ex.: o conteúdo interno de um Modal), por isso o listener de scroll usa
  // `capture: true`.
  useLayoutEffect(() => {
    if (!aberto) return;
    function calcular() {
      const el = botaoRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const espacoAbaixo = window.innerHeight - r.bottom - 8;
      const espacoAcima = r.top - 8;
      const abrirParaCima = espacoAbaixo < 160 && espacoAcima > espacoAbaixo;
      const maxHeight = Math.max(160, Math.min(352, abrirParaCima ? espacoAcima : espacoAbaixo));
      setPos({
        top: abrirParaCima ? r.top - maxHeight - 4 : r.bottom + 4,
        left: r.left,
        width: r.width,
        maxHeight,
      });
    }
    calcular();
    window.addEventListener("resize", calcular);
    window.addEventListener("scroll", calcular, true);
    return () => {
      window.removeEventListener("resize", calcular);
      window.removeEventListener("scroll", calcular, true);
    };
  }, [aberto]);

  function toggle(cod: string) {
    setExpandidos((prev) => {
      const novo = new Set(prev);
      if (novo.has(cod)) novo.delete(cod); else novo.add(cod);
      return novo;
    });
  }
  function escolher(c: ContaPlano) {
    onSelect(c.codigo, c.nome);
    setAberto(false);
    setTermo("");
  }

  // Resultado da busca: apenas folhas cujo código/nome batem com o termo.
  const resultadosBusca = useMemo(() => {
    const t = normalizar(termo.trim());
    if (!t) return [];
    return disponiveis
      .filter((c) => ehFolha(c.codigo, todosCodigos))
      .filter((c) => normalizar(c.codigo).includes(t) || normalizar(c.nome).includes(t))
      .sort((a, b) => a.codigo.localeCompare(b.codigo, undefined, { numeric: true }))
      .slice(0, 60);
  }, [termo, disponiveis, todosCodigos]);

  const rowBase: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: "0.4rem", width: "100%",
    padding: "0.35rem 0.5rem", background: "none", border: "none", cursor: "pointer",
    textAlign: "left", fontSize: "0.82rem", color: "var(--text)", borderRadius: "6px",
  };

  function Linha({ c }: { c: ContaPlano }) {
    const nivel = nivelDaConta(c.codigo);
    const folha = ehFolha(c.codigo, todosCodigos);
    const aberta = expandidos.has(c.codigo);
    const selecionada = c.codigo === codigo;
    return (
      <>
        <button
          type="button"
          onClick={() => (folha ? escolher(c) : toggle(c.codigo))}
          title={folha ? "Selecionar esta conta" : aberta ? "Recolher" : "Expandir"}
          className="row-clickable"
          style={{ ...rowBase, paddingLeft: `${0.4 + (nivel - 1) * 0.9}rem`,
            background: selecionada ? "var(--pill-active-bg)" : undefined,
            color: selecionada ? "var(--pill-active-fg)" : "var(--text)" }}
        >
          <span style={{ width: 14, display: "inline-flex", flexShrink: 0, color: "var(--accent-icon)" }}>
            {!folha && (aberta ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", flexShrink: 0 }}>{c.codigo}</span>
          <span style={estiloNivel(nivel)}>{c.nome}</span>
          {selecionada && <Check size={13} style={{ marginLeft: "auto", flexShrink: 0 }} />}
        </button>
        {!folha && aberta && filhosDiretos(c.codigo, disponiveis).map((f) => <Linha key={f.codigo} c={f} />)}
      </>
    );
  }

  const rotulo = codigo ? `${codigo} — ${nome}` : nome || "";

  const lista = aberto && pos && typeof document !== "undefined" ? createPortal(
    <div
      ref={popupRef}
      style={{
        position: "fixed", zIndex: 1000, top: pos.top, left: pos.left, width: pos.width,
        background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px",
        boxShadow: "0 8px 28px rgba(0,0,0,0.28)", padding: "0.5rem", maxHeight: pos.maxHeight, overflowY: "auto",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.15rem 0.35rem 0.5rem" }}>
        <Search size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
        <input
          autoFocus value={termo} onChange={(e) => setTermo(e.target.value)}
          placeholder="Buscar conta por nome ou código…"
          style={{ width: "100%", background: "transparent", border: "none", outline: "none",
            color: "var(--text)", fontSize: "0.82rem" }}
        />
      </div>
      {termo.trim() ? (
        resultadosBusca.length ? (
          resultadosBusca.map((c) => {
            const selecionada = c.codigo === codigo;
            return (
              <button key={c.codigo} type="button" onClick={() => escolher(c)} className="row-clickable"
                style={{ ...rowBase, background: selecionada ? "var(--pill-active-bg)" : undefined,
                  color: selecionada ? "var(--pill-active-fg)" : "var(--text)" }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", flexShrink: 0 }}>{c.codigo}</span>
                <span style={estiloNivel(nivelDaConta(c.codigo))}>{c.nome}</span>
                {selecionada && <Check size={13} style={{ marginLeft: "auto", flexShrink: 0 }} />}
              </button>
            );
          })
        ) : (
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", padding: "0.4rem 0.5rem" }}>
            Nenhuma conta encontrada para “{termo}”.
          </p>
        )
      ) : raizes.length ? (
        raizes.map((r) => <Linha key={r.codigo} c={r} />)
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", padding: "0.4rem 0.5rem" }}>
          Nenhuma conta gerencial de {tipo === "receita" ? "receita" : "despesa"} cadastrada.
        </p>
      )}
    </div>,
    document.body,
  ) : null;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        ref={botaoRef}
        type="button"
        onClick={() => setAberto((v) => !v)}
        title="Escolher a conta gerencial (só o galho mais baixo é selecionável)"
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.4rem",
          background: "var(--surface-2)", color: rotulo ? "var(--text)" : "var(--text-muted)",
          border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem",
          fontSize: "0.85rem", cursor: "pointer", textAlign: "left",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {rotulo || placeholder || "Selecione a conta gerencial…"}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {lista}
    </div>
  );
}
