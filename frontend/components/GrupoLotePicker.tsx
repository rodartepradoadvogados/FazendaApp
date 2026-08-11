"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown, Check } from "lucide-react";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { casaBusca } from "@/lib/busca";

/**
 * Seletor de grupo/lote em tela cheia, no mesmo estilo visual do AnimalPicker
 * (overlay fixo, tabela com linha em destaque vermelho), mas para seleção
 * MÚLTIPLA com confirmação explícita: os cliques nas caixas de marcação só
 * mexem num estado local (rascunho); o filtro de verdade (`selecionados`/
 * `onChange`) só muda quando o usuário clica em "OK". "Cancelar" (ou fechar
 * pelo X/backdrop) descarta o rascunho e mantém o filtro como estava.
 *
 * Diferente do MultiFiltro (menu suspenso que aplica a cada clique), aqui é
 * pensado para listas de lote potencialmente grandes: modal maior, com busca.
 */
export function GrupoLotePicker({ label = "Grupo / lote", opcoes, selecionados, onChange }:
  { label?: string; opcoes: string[]; selecionados: string[]; onChange: (v: string[]) => void }) {
  const [aberto, setAberto] = useState(false);
  const [rascunho, setRascunho] = useState<string[]>(selecionados);
  const [busca, setBusca] = useState("");

  // Sempre que o modal abre, o rascunho parte da seleção já aplicada — assim
  // reabrir depois de um "Cancelar" mostra de novo o filtro real, não o que
  // foi descartado.
  const abrir = () => { setRascunho(selecionados); setBusca(""); setAberto(true); };
  const cancelar = () => setAberto(false);
  const confirmar = () => { onChange(rascunho); setAberto(false); };

  const marcados = useMemo(() => new Set(rascunho), [rascunho]);
  const toggle = (o: string) => {
    const n = new Set(marcados);
    n.has(o) ? n.delete(o) : n.add(o);
    setRascunho(Array.from(n));
  };

  const filtrados = useMemo(
    () => opcoes.filter((o) => casaBusca(o, busca)),
    [opcoes, busca]
  );
  // `useOrdenacao` exige objetos (linhas com chaves) — como `opcoes` é uma
  // lista de strings soltas, embrulha cada uma em { valor } só pra reaproveitar
  // o mesmo padrão de ordenação por clique no cabeçalho.
  const linhasOrdenaveis = useMemo(() => filtrados.map((o) => ({ valor: o })), [filtrados]);
  const ord = useOrdenacao(linhasOrdenaveis);

  const todosMarcados = opcoes.length > 0 && opcoes.every((o) => marcados.has(o));
  const alternarTodos = () => setRascunho(todosMarcados ? [] : [...opcoes]);

  const resumo = selecionados.length === 0
    ? "Todos os lotes"
    : selecionados.length === 1
      ? selecionados[0]
      : `${selecionados.length} lotes selecionados`;

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: selecionados.length ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.3rem",
  };

  return (
    <div>
      <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>{label}</label>
      <button type="button" style={btn} onClick={abrir}
        title="Escolher um ou vários grupos/lotes — nenhum marcado mostra todos">
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{resumo}</span>
        <ChevronDown size={13} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "480px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>
                Escolher grupo/lote <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({rascunho.length} de {opcoes.length})</span>
              </div>
              <button onClick={cancelar} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar grupo/lote…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto", flex: 1 }}>
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <th style={{ width: 36 }}></th>
                    <ThOrdenavel label="Grupo / lote" campo="valor" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  </tr>
                </thead>
                <tbody>
                  <tr onClick={alternarTodos} style={{ cursor: "pointer" }} className="row-clickable">
                    <td>
                      <span style={{
                        width: 15, height: 15, borderRadius: 4, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
                        border: "1px solid " + (todosMarcados ? "var(--dourado)" : "var(--border)"),
                        background: todosMarcados ? "var(--dourado)" : "transparent",
                      }}>
                        {todosMarcados && <Check size={11} color="#fff" strokeWidth={3} />}
                      </span>
                    </td>
                    <td style={{ fontStyle: "italic", color: "var(--text-muted)" }}>{todosMarcados ? "Desmarcar todos" : "Marcar todos"}</td>
                  </tr>
                  {ord.linhasOrdenadas.map(({ valor: o }) => {
                    const on = marcados.has(o);
                    return (
                      <tr key={o} onClick={() => toggle(o)} style={{ cursor: "pointer", background: on ? "rgba(94,26,46,0.35)" : undefined }} className="row-clickable">
                        <td>
                          <span style={{
                            width: 15, height: 15, borderRadius: 4, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
                            border: "1px solid " + (on ? "var(--dourado)" : "var(--border)"),
                            background: on ? "var(--dourado)" : "transparent",
                          }}>
                            {on && <Check size={11} color="#fff" strokeWidth={3} />}
                          </span>
                        </td>
                        <td>{o}</td>
                      </tr>
                    );
                  })}
                  {!filtrados.length && <tr><td colSpan={2} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum grupo/lote encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-end gap-2 mt-3">
              <button onClick={cancelar} className="btn-ghost" style={{ fontSize: "0.82rem" }}>Cancelar</button>
              <button onClick={confirmar} className="btn-primary" style={{ fontSize: "0.82rem" }}>OK</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
