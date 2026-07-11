"use client";
import { useEffect, useMemo, useRef, useState } from "react";
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
  contas, tipo, codigo, nome, onSelect, placeholder,
}: {
  contas: ContaPlano[];
  tipo: "receita" | "despesa";
  codigo: string;
  nome: string;
  onSelect: (codigo: string, nome: string) => void;
  placeholder?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [termo, setTermo] = useState("");
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  // Só as contas do tipo certo (receita "2" / despesa "3") e ativas.
  const disponiveis = useMemo(() => {
    const pref = prefixoDoTipo(tipo);
    return contas.filter(
      (c) => (c.ativa ?? true) && (c.codigo === pref || c.codigo.startsWith(pref + "."))
    );
  }, [contas, tipo]);

  const todosCodigos = useMemo(() => disponiveis.map((c) => c.codigo), [disponiveis]);
  const raizes = useMemo(() => filhosDiretos("", disponiveis), [disponiveis]);

  // Abre as raízes do tipo por padrão (mostra os grandes grupos de cara).
  useEffect(() => {
    setExpandidos(new Set(raizes.map((r) => r.codigo)));
  }, [raizes]);

  // Fecha ao clicar fora.
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setAberto(false); };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
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

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
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

      {aberto && (
        <div
          style={{
            position: "absolute", zIndex: 40, top: "calc(100% + 4px)", left: 0, right: 0,
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px",
            boxShadow: "0 8px 28px rgba(0,0,0,0.28)", padding: "0.5rem", maxHeight: "22rem", overflowY: "auto",
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
        </div>
      )}
    </div>
  );
}
