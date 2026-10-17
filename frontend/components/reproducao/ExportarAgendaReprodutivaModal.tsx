"use client";
// Pop-up "Exportar agenda reprodutiva": escolhe quais listas entram (cards configurados e "Outras pendências"), se o
// arquivo respeita o filtro de situação da tela, e gera PDF (A4 paisagem) ou Excel (uma aba por lista).
// Quem monta as seções é lib/exportAgendaReprodutiva.ts; quem desenha o arquivo é lib/export.ts.
import { useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { Modal } from "@/components/Modal";
import type { LinhaDoModal } from "@/lib/exportAgendaReprodutiva";

export function ExportarAgendaReprodutivaModal({ linhasPara, filtroAtivo, rotuloFiltro, onClose, onExportar }: {
  /** Listas com o total e quantos entram no arquivo, para cada escolha de "aplicar o filtro da tela". */
  linhasPara: (aplicarFiltro: boolean) => LinhaDoModal[];
  filtroAtivo: boolean;
  /** Ex.: "A tocar + A reconfirmar". */
  rotuloFiltro: string;
  onClose: () => void;
  /** Gera e entrega o arquivo; rejeita com a mensagem de erro para o pop-up mostrar. */
  onExportar: (formato: "pdf" | "excel", ids: Set<string>, aplicarFiltro: boolean) => Promise<void>;
}) {
  const [aplicar, setAplicar] = useState(true);
  const linhas = linhasPara(filtroAtivo && aplicar);
  const [desmarcadas, setDesmarcadas] = useState<Set<string>>(new Set());
  const [gerando, setGerando] = useState<"pdf" | "excel" | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const efetivas = linhas.filter((l) => !l.semAnimais && !desmarcadas.has(l.id));
  const animais = efetivas.reduce((s, l) => s + l.n, 0);
  const marcavel = linhas.filter((l) => !l.semAnimais);
  const alternar = (id: string) => setDesmarcadas((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function exportar(formato: "pdf" | "excel") {
    setGerando(formato); setErro(null);
    try {
      await onExportar(formato, new Set(efetivas.map((l) => l.id)), filtroAtivo && aplicar);
      onClose();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gerar o arquivo.");
    } finally {
      setGerando(null);
    }
  }

  const grupo = (g: "card" | "outra", titulo: string) => {
    const itens = linhas.filter((l) => l.grupo === g);
    if (itens.length === 0) return null;
    return (
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.5rem", padding: 0 }}>{titulo}</legend>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "0.5rem" }}>
          {itens.map((l) => {
            const marcada = !l.semAnimais && !desmarcadas.has(l.id);
            return (
              <label key={l.id} style={{ display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.55rem 0.75rem", border: `1px ${l.semAnimais ? "dashed" : "solid"} var(--border)`,
                borderRadius: "var(--r-sm)", background: "var(--surface)", cursor: l.semAnimais ? "default" : "pointer", opacity: l.semAnimais ? 0.5 : 1 }}>
                <input type="checkbox" checked={marcada} disabled={l.semAnimais} onChange={() => alternar(l.id)} style={{ width: 18, height: 18, accentColor: "var(--dourado)" }} />
                <span style={{ flex: 1, minWidth: 0, fontSize: "0.88rem" }}>
                  {l.titulo}<br /><span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.nota}</span>
                </span>
                <span style={{ fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{l.n}</span>
              </label>
            );
          })}
        </div>
      </fieldset>
    );
  };

  return (
    <Modal title="Exportar agenda reprodutiva" onClose={onClose} width="820px">
      <div style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}>
        {filtroAtivo && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.88rem", cursor: "pointer" }}>
              <input type="checkbox" checked={aplicar} onChange={() => setAplicar((v) => !v)} style={{ width: 18, height: 18, accentColor: "var(--dourado)" }} />
              Aplicar o filtro que está na tela
            </label>
            <span className="ft-st ft-st-a_tocar" style={{ color: "var(--ft-ouro-txt)" }}>Situação · {rotuloFiltro}</span>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Desmarque para exportar todos os animais de cada lista.</span>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginBottom: "-0.6rem" }}>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", padding: "0.2rem 0.6rem" }} onClick={() => setDesmarcadas(new Set())}>Selecionar todas</button>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", padding: "0.2rem 0.6rem" }} onClick={() => setDesmarcadas(new Set(marcavel.map((l) => l.id)))}>Nenhuma</button>
        </div>
        {grupo("card", "Cards configurados")}
        {grupo("outra", "Outras pendências")}

        <p style={{ margin: 0, padding: "0.7rem 0.85rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", fontSize: "0.78rem", lineHeight: 1.6, color: "var(--text-muted)" }}>
          <strong style={{ color: "var(--text)" }}>O que sai no arquivo.</strong> PDF em A4 paisagem: capa com a data de referência, o filtro e a próxima visita reprodutiva,
          totais por situação, uma seção por lista (Matriz, Categoria, Lote, DEL, Dias da IA, Toque, Retoque e Situação) e a legenda P, V e I.
          Excel: uma aba por lista, com todas as colunas, cabeçalho congelado e filtros.
        </p>

        {erro && <p role="alert" style={{ margin: 0, color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}

        {/* Rodapé fixo na base da janela: com muitas listas o conteúdo rola, mas os botões de exportar nunca saem da tela. */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", position: "sticky", bottom: 0, background: "var(--surface)", padding: "0.8rem 0 0.2rem", borderTop: "1px solid var(--border)" }}>
          <span aria-live="polite" style={{ fontSize: "0.85rem", fontVariantNumeric: "tabular-nums" }}>
            <strong>{efetivas.length} {efetivas.length === 1 ? "lista" : "listas"}</strong> · <strong>{animais} animais</strong>
          </span>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn-secondary" disabled={efetivas.length === 0 || gerando !== null} onClick={() => exportar("excel")} style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            <FileSpreadsheet size={15} aria-hidden="true" />{gerando === "excel" ? "Gerando…" : "Exportar Excel"}
          </button>
          <button type="button" className="btn-primary-gold" disabled={efetivas.length === 0 || gerando !== null} onClick={() => exportar("pdf")} style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            <Download size={15} aria-hidden="true" />{gerando === "pdf" ? "Gerando…" : "Exportar PDF"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
