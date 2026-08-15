"use client";
import { useMemo, useState } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { casaBusca } from "@/lib/busca";

export type ServicoPickerItem = { nome: string };

/**
 * Seletor de serviço em janela suspensa — irmão do EstoquePicker, para o
 * outro lado do toggle "Produto × Serviço" do lançamento financeiro
 * (FormFinanceiro.tsx e o formulário de edição em app/financeiro/page.tsx).
 *
 * O produto já tinha janela suspensa nos dois lugares; o serviço continuava
 * num <select> nativo, sem busca — em cadastro de serviço grande, achar o
 * item virava rolagem no escuro. Como serviço não tem categoria nem saldo, a
 * tabela aqui é de uma coluna só, e por isso este componente não reusa o
 * EstoquePicker (que mostraria "Categoria"/"Estoque atual" sempre vazias e
 * diria "Escolher produto" no título).
 */
export function ServicoPicker({ servicos, value, onChange, placeholder = "Selecionar serviço…", disabled = false }:
  { servicos: ServicoPickerItem[]; value: string; onChange: (v: string) => void; placeholder?: string; disabled?: boolean }) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");

  const disponiveis = useMemo(() => {
    const nomes = servicos.map((s) => s.nome);
    // Lançamento antigo pode apontar para um serviço que saiu do cadastro (ou
    // foi desativado): sem isto, abrir a edição apagaria silenciosamente o
    // valor salvo. Mesmo cuidado que o <select> anterior tinha com a opção
    // extra do valor atual.
    if (value && !nomes.includes(value)) nomes.unshift(value);
    return nomes.sort((a, b) => (a === value ? -1 : b === value ? 1 : a.localeCompare(b, "pt-BR")));
  }, [servicos, value]);

  const filtrados = useMemo(
    () => disponiveis.filter((n) => casaBusca(n, busca)),
    [disponiveis, busca]
  );

  const btn: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: value ? "var(--text)" : "var(--text-muted)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
    textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
  };

  return (
    <>
      <button type="button" style={{ ...btn, opacity: disabled ? 0.6 : 1, cursor: disabled ? "not-allowed" : "pointer" }} disabled={disabled}
        onClick={() => { setAberto(true); setBusca(""); }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value || placeholder}</span>
        <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
      </button>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "520px", maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>Escolher serviço <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({filtrados.length})</span></div>
              <button onClick={() => setAberto(false)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div style={{ position: "relative", marginBottom: "0.6rem" }}>
              <Search size={14} style={{ position: "absolute", left: 9, top: 10, color: "var(--text-muted)" }} />
              <input autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar serviço…"
                style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem 0.45rem 2rem", fontSize: "0.85rem" }} />
            </div>
            <div style={{ overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th>Serviço</th></tr></thead>
                <tbody>
                  {filtrados.map((n) => (
                    <tr key={n} onClick={() => { onChange(n); setAberto(false); }} style={{ cursor: "pointer", background: n === value ? "rgba(94,26,46,0.35)" : undefined }} className="row-clickable">
                      <td style={{ fontWeight: 700 }}>{n}</td>
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td style={{ color: "var(--text-muted)", padding: "1rem" }}>Nenhum serviço encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
