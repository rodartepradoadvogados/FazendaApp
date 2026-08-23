"use client";
import { useEffect, useMemo, useState } from "react";
import { Search, X, ChevronDown, UserPlus } from "lucide-react";
import { AnimalRow } from "./AnimalModal";
import { Modal } from "./Modal";
import NovoAnimalRapido from "./NovoAnimalRapido";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { casaBusca } from "@/lib/busca";

/**
 * Padrão único de seleção de VÁRIOS animais no site: um botão mostra quantos
 * já foram escolhidos e, ao tocar, abre uma tela suspensa com busca + tabela
 * marcável — em vez de uma lista de checkbox sempre aberta ocupando a página
 * (como era em Inseminação/Diagnóstico) ou de overlays reimplementados a cada
 * tela. Mesmo visual do `AnimalPicker` (seleção única), com checkboxes.
 */
export function AnimalPickerModal({ animais, selecionados, onToggle, colunas, placeholder = "Selecionar animais…", titulo = "Escolher animais", permitirNovoAnimal = false, abrirAoMudar, motivosInaptidao, ocultarFiltroLote = false }: {
  animais: AnimalRow[];
  selecionados: Set<string>;
  onToggle: (numero: string) => void;
  colunas: { header: string; render: (a: AnimalRow) => React.ReactNode }[];
  placeholder?: string;
  titulo?: string;
  // Quando true, mostra "+ Cadastrar novo animal" dentro do seletor — usado
  // no fluxo de Comprar animal, onde o animal recém-adquirido pode ainda não
  // estar no cadastro. Os animais criados aqui somam-se localmente à lista
  // recebida por prop (persistem até a tela ser recarregada/recém-buscada).
  permitirNovoAnimal?: boolean;
  // Abre o seletor sozinho sempre que este valor mudar (ex.: a assinatura do(s)
  // lote(s) escolhido(s) num picker de lote acima) — em vez de depender do
  // usuário notar e clicar o botão pra revisar quem entrou na seleção. Usado
  // quando a lista de `animais` vem de uma escolha em lote e o usuário precisa
  // confirmar explicitamente se quer todos, nenhum ou só alguns.
  abrirAoMudar?: string | number;
  // numero -> motivo de inaptidão. Marca o animal EM CINZA, com o motivo ao
  // lado do número, em vez de escondê-lo da lista (era o que Lançamentos
  // fazia com as fêmeas abaixo da idade mínima — e ninguém entendia por que a
  // vaca "sumiu"). Continua selecionável de propósito: a decisão final é do
  // backend, que aceita uma confirmação explícita nos casos limítrofes.
  motivosInaptidao?: Map<string, string>;
  // Esconde o select "Todos os lotes" de dentro do modal — usado por telas que
  // já têm um filtro de Lote próprio no topo (ex.: Histórico > Reprodução,
  // Serviços/IAS unificado) para não duplicar o mesmo filtro em dois lugares.
  ocultarFiltroLote?: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const [filtroLote, setFiltroLote] = useState("");
  const [novoAnimalAberto, setNovoAnimalAberto] = useState(false);
  const [extras, setExtras] = useState<AnimalRow[]>([]);
  const { rotuloDe } = useEstadosReprodutivos();

  useEffect(() => {
    if (abrirAoMudar === undefined) return;
    setAberto(true); setBusca(""); setFiltroLote("");
  }, [abrirAoMudar]); // eslint-disable-line react-hooks/exhaustive-deps

  const animaisComExtras = useMemo(() => {
    if (!extras.length) return animais;
    const numeros = new Set(animais.map((a) => a.numero));
    return [...animais, ...extras.filter((e) => !numeros.has(e.numero))];
  }, [animais, extras]);

  const lotes = useMemo(
    () => Array.from(new Set(animaisComExtras.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort(),
    [animaisComExtras]
  );

  const filtrados = useMemo(() => {
    return animaisComExtras.filter((a) => {
      if (filtroLote && (a.grupo_primario || "") !== filtroLote) return false;
      return casaBusca(`${a.numero} ${a.grupo_primario || ""} ${a.categoria_abrev || a.categoria_completa || ""} ${rotuloDe(a.numero)}`, busca);
    });
  }, [animaisComExtras, busca, filtroLote, rotuloDe]);

  const todosFiltradosSelecionados = filtrados.length > 0 && filtrados.every((a) => selecionados.has(a.numero));
  function alternarFiltrados() {
    filtrados.forEach((a) => {
      const selecionado = selecionados.has(a.numero);
      if (todosFiltradosSelecionados ? selecionado : !selecionado) onToggle(a.numero);
    });
  }

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: selecionados.size ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={btn} onClick={() => { setAberto(true); setBusca(""); setFiltroLote(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {selecionados.size ? `${selecionados.size} animal(is) selecionado(s)` : placeholder}
        </span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {/* Chips de conferência — quais números exatos foram marcados, sem
          precisar reabrir o modal. Clicável pra desmarcar um de cada vez,
          mesmo padrão visual usado em FormInducaoCio.tsx. */}
      {selecionados.size > 0 && (
        <div className="mt-2" style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
          {Array.from(selecionados).sort().map((n) => (
            <span key={n} onClick={() => onToggle(n)} title="Clique para remover da seleção" style={{
              fontSize: "0.74rem", background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "999px", padding: "0.12rem 0.55rem", fontWeight: 600, cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "0.25rem",
            }}>
              {n} <X size={10} style={{ opacity: 0.6 }} />
            </span>
          ))}
        </div>
      )}

      {aberto && (
        // Sem fechar ao clicar fora — clique perdido no fundo enquanto se
        // marca vários animais fechava a janela e derrubava a seleção em
        // andamento. Só fecha pelo X ou "Concluir" abaixo.
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" style={{ width: "720px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>
                {titulo} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({selecionados.size}/{animaisComExtras.length})</span>
              </div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div className="flex gap-2 mb-2" style={{ flexWrap: "wrap" }}>
              <div style={{ position: "relative", flex: "1 1 220px" }}>
                <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
                <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por número, grupo, categoria…"
                  style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
              </div>
              {!ocultarFiltroLote && lotes.length > 1 && (
                <select value={filtroLote} onChange={(e) => setFiltroLote(e.target.value)} title="Filtrar por lote"
                  style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem" }}>
                  <option value="">Todos os lotes</option>
                  {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              )}
              {permitirNovoAnimal && (
                <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                  onClick={() => setNovoAnimalAberto(true)}>
                  <UserPlus size={14} /> Cadastrar novo animal
                </button>
              )}
            </div>
            <div className="flex items-center justify-between mb-2">
              <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={alternarFiltrados} disabled={!filtrados.length}>
                {todosFiltradosSelecionados ? "Limpar seleção" : "Selecionar todos"}{busca.trim() || filtroLote ? " (filtrados)" : ""}
              </button>
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th></th>{colunas.map((c) => <th key={c.header}>{c.header}</th>)}{motivosInaptidao ? <th>Aptidão</th> : null}</tr></thead>
                <tbody>
                  {filtrados.map((a) => {
                    const inapto = motivosInaptidao?.get(a.numero);
                    return (
                    <tr key={a.numero} onClick={() => onToggle(a.numero)} title={inapto || undefined}
                      style={{ cursor: "pointer", opacity: inapto ? 0.55 : undefined }} className="row-clickable">
                      <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => onToggle(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                      {colunas.map((c) => <td key={c.header} style={{ fontSize: "0.8rem", color: inapto ? "var(--text-muted)" : undefined }}>{c.render(a)}</td>)}
                      {motivosInaptidao ? (
                        <td style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: inapto ? "italic" : undefined }}>
                          {inapto || "—"}
                        </td>
                      ) : null}
                    </tr>
                    );
                  })}
                  {!filtrados.length && <tr><td colSpan={colunas.length + (motivosInaptidao ? 2 : 1)} style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-end mt-3">
              <button type="button" className="btn-primary" onClick={() => setAberto(false)}>Concluir</button>
            </div>
          </div>
        </div>
      )}

      {novoAnimalAberto && (
        <Modal title="Cadastrar novo animal" onClose={() => setNovoAnimalAberto(false)} width="560px" zIndex={80}>
          <NovoAnimalRapido
            onCriado={(novo) => {
              setExtras((prev) => [...prev, novo]);
              if (!selecionados.has(novo.numero)) onToggle(novo.numero);
              setNovoAnimalAberto(false);
            }}
            onCancelar={() => setNovoAnimalAberto(false)}
          />
        </Modal>
      )}
    </>
  );
}
