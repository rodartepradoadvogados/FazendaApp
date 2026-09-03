"use client";
// Etapa 1, "Importar do cadastro" — lista os Alimentos já cadastrados na
// fazenda (tela normal de Alimentação) e resolve cada um escolhido em cascata
// biblioteca → análise bromatológica → template (GET /alimentos/{id}/resolver).
//
// Fase 2 (01/09/2026): uma família de Alimento (ex.: "Concentrado Protéico")
// pode ter vários produtos de Estoque vinculados, cada um com sua própria
// composição cadastrada na Tabela Nutricional — importar só a família dava
// sempre o mesmo valor genérico de template, mesmo quando o produto real
// já tinha composição própria. Por isso, ao confirmar a seleção, toda família
// com produto(s) vinculado(s) abre um segundo passo pedindo qual(is)
// produto(s) específico(s) importar; famílias sem produto vinculado
// continuam indo direto (comportamento de sempre).
import { useEffect, useState } from "react";
import { AlertTriangle, ChevronLeft, Search } from "lucide-react";
import { AlimentoCadastradoResumo, ItemGrade, itemGradeDeResolucao, listarAlimentos, resolverAlimento } from "@/lib/dietas";

export function ImportarAlimentoModal({
  onFechar, onImportar,
}: {
  onFechar: () => void; onImportar: (itens: ItemGrade[]) => void;
}) {
  const [busca, setBusca] = useState("");
  const [cadastrados, setCadastrados] = useState<AlimentoCadastradoResumo[] | null>(null);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [importando, setImportando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Passo 2 — só aparece quando alguma família selecionada tem produto(s)
  // de Estoque vinculado(s) (ver docstring acima).
  const [familiasComProduto, setFamiliasComProduto] = useState<AlimentoCadastradoResumo[] | null>(null);
  const [produtosSelecionados, setProdutosSelecionados] = useState<Set<number>>(new Set());

  useEffect(() => {
    const t = setTimeout(() => {
      listarAlimentos(busca).then((r) => setCadastrados(r.cadastrados)).catch((e) => setErro(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [busca]);

  function alternar(id: number) {
    setSelecionados((prev) => {
      const novo = new Set(prev);
      if (novo.has(id)) novo.delete(id); else novo.add(id);
      return novo;
    });
  }

  function alternarProduto(id: number) {
    setProdutosSelecionados((prev) => {
      const novo = new Set(prev);
      if (novo.has(id)) novo.delete(id); else novo.add(id);
      return novo;
    });
  }

  async function importarLista(pares: { alimentoId: number; estoqueId?: number }[]) {
    const itens: ItemGrade[] = [];
    for (const { alimentoId, estoqueId } of pares) {
      const r = await resolverAlimento(alimentoId, estoqueId);
      itens.push(itemGradeDeResolucao(alimentoId, r));
    }
    return itens;
  }

  async function confirmarPasso1() {
    if (selecionados.size === 0) return;
    const escolhidos = (cadastrados || []).filter((a) => selecionados.has(a.id));
    const comProduto = escolhidos.filter((a) => a.estoque_vinculado.length > 0);
    if (comProduto.length > 0) {
      setFamiliasComProduto(comProduto);
      return;
    }
    setImportando(true);
    setErro(null);
    try {
      const itens = await importarLista(escolhidos.map((a) => ({ alimentoId: a.id })));
      onImportar(itens);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setImportando(false);
    }
  }

  async function confirmarPasso2() {
    if (produtosSelecionados.size === 0) return;
    setImportando(true);
    setErro(null);
    try {
      const semProduto = (cadastrados || []).filter((a) => selecionados.has(a.id) && a.estoque_vinculado.length === 0);
      const pares: { alimentoId: number; estoqueId?: number }[] = semProduto.map((a) => ({ alimentoId: a.id }));
      for (const familia of familiasComProduto || []) {
        for (const produto of familia.estoque_vinculado) {
          if (produtosSelecionados.has(produto.id)) pares.push({ alimentoId: familia.id, estoqueId: produto.id });
        }
      }
      const itens = await importarLista(pares);
      onImportar(itens);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setImportando(false);
    }
  }

  if (familiasComProduto) {
    return (
      <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--overlay)" }} onClick={onFechar}>
        <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: "min(34rem, 92vw)", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.4rem" }}>
            <button type="button" className="btn-ghost" style={{ padding: "0.2rem" }} onClick={() => setFamiliasComProduto(null)} title="Voltar">
              <ChevronLeft size={16} />
            </button>
            <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>Escolha o(s) produto(s)</h3>
          </div>
          <p style={{ margin: "0 0 0.7rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Cada família abaixo tem produto(s) de estoque com composição própria cadastrada — escolha qual(is) importar.
          </p>

          <div style={{ overflowY: "auto", flex: 1 }}>
            {familiasComProduto.map((familia) => (
              <div key={familia.id} style={{ marginBottom: "0.7rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
                <div style={{ padding: "0.4rem 0.7rem", fontSize: "0.8rem", fontWeight: 700, color: "var(--text)", background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                  {familia.nome}
                </div>
                {familia.estoque_vinculado.map((produto) => (
                  <label key={produto.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)", cursor: "pointer", fontSize: "0.85rem" }}>
                    <input type="checkbox" checked={produtosSelecionados.has(produto.id)} onChange={() => alternarProduto(produto.id)} />
                    <span style={{ flex: 1, color: "var(--text)" }}>{produto.nome}</span>
                    {produto.sem_composicao && (
                      <span title="Ainda não tem composição nutricional cadastrada — usará o template da categoria" style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem", color: "var(--amber)" }}>
                        <AlertTriangle size={12} /> sem composição
                      </span>
                    )}
                  </label>
                ))}
              </div>
            ))}
          </div>

          {erro && <div className="alert-critico" style={{ marginTop: "0.6rem" }}>{erro}</div>}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.9rem" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{produtosSelecionados.size} produto(s) selecionado(s)</span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
              <button type="button" className="btn-primary-gold" disabled={produtosSelecionados.size === 0 || importando} onClick={confirmarPasso2}>
                {importando ? "Importando…" : "Importar selecionados"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--overlay)" }} onClick={onFechar}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: "min(34rem, 92vw)", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
        <h3 style={{ margin: "0 0 0.8rem", fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>Importar do cadastro</h3>

        <div style={{ position: "relative", marginBottom: "0.7rem" }}>
          <Search size={14} style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            autoFocus value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar alimento…"
            style={{ width: "100%", padding: "0.45rem 0.6rem 0.45rem 2rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}
          />
        </div>

        <div style={{ overflowY: "auto", flex: 1, border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
          {cadastrados === null && <p style={{ padding: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>}
          {cadastrados !== null && cadastrados.length === 0 && <p style={{ padding: "1rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum alimento cadastrado com esse termo.</p>}
          {cadastrados?.map((a) => (
            <label key={a.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)", cursor: "pointer", fontSize: "0.85rem" }}>
              <input type="checkbox" checked={selecionados.has(a.id)} onChange={() => alternar(a.id)} />
              <span style={{ flex: 1, color: "var(--text)" }}>{a.nome}</span>
              {a.estoque_vinculado.length > 0 && (
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{a.estoque_vinculado.length} produto(s)</span>
              )}
              {a.estoque_vinculado.length === 0 && a.sem_composicao && (
                <span title="Ainda não tem composição nutricional cadastrada — usará o template da categoria" style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem", color: "var(--amber)" }}>
                  <AlertTriangle size={12} /> sem composição
                </span>
              )}
            </label>
          ))}
        </div>

        {erro && <div className="alert-critico" style={{ marginTop: "0.6rem" }}>{erro}</div>}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.9rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{selecionados.size} selecionado(s)</span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
            <button type="button" className="btn-primary-gold" disabled={selecionados.size === 0 || importando} onClick={confirmarPasso1}>
              {importando ? "Importando…" : "Importar selecionados"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
