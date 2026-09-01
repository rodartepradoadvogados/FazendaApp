"use client";
// Tabela nutricional dos alimentos (referência do veterinário) — abre num modal
// suspenso, com uma calculadora ao lado que aceita o teclado numérico do
// computador. Botão reutilizável: <TabelaNutricionalBotao />.
import { useEffect, useMemo, useRef, useState } from "react";
import { X, Table2, Search, Plus, Trash2, Pencil, Download, Upload, Save } from "lucide-react";
import {
  fetchTabelaNutricional, criarProdutoTabelaNutricional, renomearProdutoTabelaNutricional,
  excluirProdutoTabelaNutricional, salvarValoresTabelaNutricional, baixarModeloTabelaNutricional, importarTabelaNutricional,
  fetchEstoque,
} from "@/lib/api";
import { casaBusca } from "@/lib/busca";

type Dados = { alimentos: string[]; linhas: string[][] };
type DadosEditavel = { alimentos: string[]; produto_ids: number[]; estoque_ids: (number | null)[]; linhas: string[][] };
type ItemEstoqueSimples = { id: number; nome: string; finalidade?: string | null; ativo?: boolean };

// ── Calculadora simples (aceita teclado numérico físico) ──
function Calculadora() {
  const [expr, setExpr] = useState("");
  const [res, setRes] = useState<string | null>(null);

  function press(ch: string) {
    setRes(null);
    if (ch === "C") { setExpr(""); return; }
    if (ch === "←") { setExpr((e) => e.slice(0, -1)); return; }
    if (ch === "=") { calcular(); return; }
    setExpr((e) => e + ch);
  }
  function calcular() {
    try {
      const limpo = expr.replace(/,/g, ".").replace(/[^0-9+\-*/.() ]/g, "");
      if (!limpo.trim()) return;
      // Avaliação restrita a uma expressão aritmética já filtrada.
      // eslint-disable-next-line no-new-func
      const v = Function(`"use strict"; return (${limpo})`)();
      setRes(typeof v === "number" && isFinite(v) ? String(Math.round(v * 10000) / 10000) : "erro");
    } catch { setRes("erro"); }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key;
      if (/[0-9]/.test(k) || ["+", "-", "*", "/", ".", "(", ")"].includes(k)) { press(k); e.preventDefault(); }
      else if (k === "," ) { press("."); e.preventDefault(); }
      else if (k === "Enter" || k === "=") { press("="); e.preventDefault(); }
      else if (k === "Backspace") { press("←"); e.preventDefault(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expr]);

  const btn: React.CSSProperties = { padding: "0.7rem 0", fontSize: "1.05rem", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", cursor: "pointer", fontWeight: 600 };
  const teclas = ["7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "0", ".", "=", "+"];

  return (
    <div style={{ width: 220, flexShrink: 0 }}>
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Calculadora (use o teclado numérico)</div>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem", minHeight: "3.2rem", marginBottom: "0.5rem", textAlign: "right" }}>
        <div style={{ fontSize: "0.9rem", color: "var(--text-muted)", wordBreak: "break-all" }}>{expr || "0"}</div>
        {res != null && <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--dourado-light)" }}>= {res}</div>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem" }}>
        <button style={{ ...btn, gridColumn: "span 2", color: "var(--red)" }} onClick={() => press("C")}>C</button>
        <button style={btn} onClick={() => press("←")}>←</button>
        <button style={btn} onClick={() => press("(")}>(</button>
        {teclas.map((t) => (
          <button key={t} style={t === "=" ? { ...btn, background: "var(--dourado)", color: "#1a1205", fontWeight: 800 } : btn} onClick={() => press(t)}>{t}</button>
        ))}
        <button style={{ ...btn, gridColumn: "span 4" }} onClick={() => press(")")}>)</button>
      </div>
    </div>
  );
}

export function TabelaNutricionalBotao({ estilo }: { estilo?: React.CSSProperties }) {
  const [aberto, setAberto] = useState(false);
  const [dados, setDados] = useState<Dados | null>(null);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    if (aberto && !dados) fetchTabelaNutricional().then(setDados).catch(() => setDados({ alimentos: [], linhas: [] }));
  }, [aberto, dados]);

  const linhasFiltradas = useMemo(() => {
    if (!dados) return [];
    return dados.linhas.filter((l) => casaBusca(l[0], busca));
  }, [dados, busca]);

  return (
    <>
      <button className="btn-ghost" style={{ fontSize: "0.8rem", display: "inline-flex", alignItems: "center", gap: "0.4rem", ...estilo }} onClick={() => setAberto(true)}>
        <Table2 size={15} /> Tabela nutricional
      </button>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: "1100px", width: "100%", maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div className="card-header flex items-center justify-between" style={{ marginBottom: "0.6rem" }}>
              <span className="flex items-center gap-2"><Table2 size={16} /> Tabela nutricional dos alimentos</span>
              <button className="btn-ghost" onClick={() => setAberto(false)}><X size={16} /></button>
            </div>
            <div className="flex gap-4" style={{ minHeight: 0, flex: 1 }}>
              <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                <div style={{ position: "relative", marginBottom: "0.5rem", maxWidth: 320 }}>
                  <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                  <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar nutriente…"
                    style={{ width: "100%", padding: "0.4rem 0.5rem 0.4rem 1.8rem", borderRadius: 6, fontSize: "0.82rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }} />
                </div>
                <div style={{ overflow: "auto", flex: 1 }}>
                  {!dados ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
                    <table className="fazenda-table" style={{ fontSize: "0.76rem" }}>
                      <thead><tr>
                        <th style={{ position: "sticky", top: 0, background: "var(--surface-2)" }}>Nutriente</th>
                        {dados.alimentos.map((a) => <th key={a} style={{ position: "sticky", top: 0, background: "var(--surface-2)" }}>{a}</th>)}
                      </tr></thead>
                      <tbody>
                        {linhasFiltradas.map((l, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 700 }}>{l[0]}</td>
                            {l.slice(1).map((c, j) => <td key={j}>{c || "—"}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
              <Calculadora />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── Cadastro/edição da tabela nutricional (grade nutriente × produto) ──
// Conteúdo inline (sem botão/modal) — usado como aba própria em Configurações
// › Cadastro › Alimentação, ao lado de "Matéria seca".
export function TabelaNutricionalCadastroInline() {
  const [dados, setDados] = useState<DadosEditavel | null>(null);
  const [grade, setGrade] = useState<Record<string, string>>({});
  const [novoProduto, setNovoProduto] = useState("");
  const [estoqueEscolhidoId, setEstoqueEscolhidoId] = useState("");
  const [textoLivre, setTextoLivre] = useState(false);
  const [estoqueItens, setEstoqueItens] = useState<ItemEstoqueSimples[]>([]);
  const [novoNutriente, setNovoNutriente] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [importando, setImportando] = useState(false);
  const [msg, setMsg] = useState<{ texto: string; erro?: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const chave = (produtoId: number, nutriente: string) => `${produtoId}::${nutriente}`;

  function carregar() {
    fetchTabelaNutricional().then((d) => {
      setDados(d);
      const g: Record<string, string> = {};
      d.linhas.forEach((linha) => {
        const nutriente = linha[0];
        d.produto_ids.forEach((pid, idx) => { g[chave(pid, nutriente)] = linha[idx + 1] || ""; });
      });
      setGrade(g);
    }).catch(() => setDados({ alimentos: [], produto_ids: [], estoque_ids: [], linhas: [] }));
  }

  useEffect(() => { if (!dados) carregar(); }, [dados]);
  useEffect(() => { fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => {}); }, []);

  // Cadastro fechado de produtos de alimentação (mesmo critério de
  // "finalidade indica alimento" usado em CadastroAlimentacao.tsx), menos os
  // que já estão na tabela nutricional — "Nome do novo produto" deixa de ser
  // texto livre por padrão; a flag abaixo permite voltar a digitar (produto
  // fora do cadastro de Estoque, ex.: referência genérica de tabela).
  const produtosDisponiveis = useMemo(() => {
    const termosNutricao = ["aliment", "nutri", "racao"];
    const jaNaTabela = new Set((dados?.estoque_ids || []).filter((id): id is number => id != null));
    return estoqueItens
      .filter((it) => it.ativo !== false)
      .filter((it) => it.finalidade == null || termosNutricao.some((t) => casaBusca(it.finalidade!, t)))
      .filter((it) => !jaNaTabela.has(it.id));
  }, [estoqueItens, dados]);

  const nutrientes = useMemo(() => (dados?.linhas || []).map((l) => l[0]), [dados]);

  async function salvar() {
    if (!dados) return;
    setSalvando(true); setMsg(null);
    try {
      const itens = nutrientes.flatMap((nutriente) =>
        dados.produto_ids.map((pid) => ({ produto_id: pid, nutriente, valor: grade[chave(pid, nutriente)] || "" }))
      );
      await salvarValoresTabelaNutricional(itens);
      setMsg({ texto: "Tabela nutricional salva." });
    } catch (e: any) { setMsg({ texto: e.message, erro: true }); }
    finally { setSalvando(false); }
  }

  async function adicionarProduto() {
    try {
      if (textoLivre) {
        const nome = novoProduto.trim();
        if (!nome) return;
        await criarProdutoTabelaNutricional({ nome });
        setNovoProduto("");
      } else {
        if (!estoqueEscolhidoId) return;
        await criarProdutoTabelaNutricional({ estoque_id: Number(estoqueEscolhidoId) });
        setEstoqueEscolhidoId("");
      }
      carregar();
    } catch (e: any) { setMsg({ texto: e.message, erro: true }); }
  }

  async function renomear(id: number, nomeAtual: string) {
    const nome = window.prompt("Novo nome do produto:", nomeAtual);
    if (!nome || !nome.trim() || nome.trim() === nomeAtual) return;
    try { await renomearProdutoTabelaNutricional(id, nome.trim()); carregar(); }
    catch (e: any) { setMsg({ texto: e.message, erro: true }); }
  }

  async function excluir(id: number, nome: string) {
    if (!window.confirm(`Excluir o produto "${nome}" da tabela nutricional? Os valores cadastrados dele serão perdidos.`)) return;
    try { await excluirProdutoTabelaNutricional(id); carregar(); }
    catch (e: any) { setMsg({ texto: e.message, erro: true }); }
  }

  function adicionarNutriente() {
    const nome = novoNutriente.trim();
    if (!nome || !dados) return;
    if (nutrientes.includes(nome)) { setNovoNutriente(""); return; }
    setDados({ ...dados, linhas: [...dados.linhas, [nome, ...dados.produto_ids.map(() => "")]] });
    setNovoNutriente("");
  }

  async function onImportar(file: File) {
    setImportando(true); setMsg(null);
    try {
      const r = await importarTabelaNutricional(file);
      setMsg({ texto: `Importado: ${r.produtos} produto(s), ${r.nutrientes} nutriente(s).` });
      setDados(null); // força recarregar do zero
      carregar();
    } catch (e: any) { setMsg({ texto: e.message, erro: true }); }
    finally { setImportando(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  const cellInput: React.CSSProperties = { width: "100%", minWidth: "7rem", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "0.2rem 0.4rem", fontSize: "0.74rem", color: "var(--text)" };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => baixarModeloTabelaNutricional().catch((e) => setMsg({ texto: e.message, erro: true }))}>
          <Download size={13} /> Baixar planilha (Excel)
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.76rem" }} disabled={importando} onClick={() => fileRef.current?.click()}>
          <Upload size={13} /> {importando ? "Importando…" : "Importar planilha"}
        </button>
        <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) onImportar(f); }} />
        <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>1ª coluna = nutriente, demais colunas = um produto cada (mesmo formato do modelo baixado).</span>
      </div>

      {msg && <p style={{ fontSize: "0.78rem", color: msg.erro ? "var(--red)" : "var(--green-light)", marginBottom: "0.5rem" }}>{msg.texto}</p>}

      {!dados ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <>
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.76rem" }}>
              <thead><tr>
                <th style={{ position: "sticky", top: 0, background: "var(--surface-2)", minWidth: "10rem" }}>Nutriente</th>
                {dados.alimentos.map((nome, idx) => (
                  <th key={dados.produto_ids[idx]} style={{ position: "sticky", top: 0, background: "var(--surface-2)", minWidth: "9rem" }}>
                    <div className="flex items-center gap-1">
                      <span style={{ flex: 1 }}>{nome}</span>
                      <button className="btn-ghost" title="Renomear produto" style={{ padding: "0.1rem" }} onClick={() => renomear(dados.produto_ids[idx], nome)}><Pencil size={11} /></button>
                      <button className="btn-ghost" title="Excluir produto" style={{ padding: "0.1rem", color: "var(--red)" }} onClick={() => excluir(dados.produto_ids[idx], nome)}><Trash2 size={11} /></button>
                    </div>
                  </th>
                ))}
              </tr></thead>
              <tbody>
                {nutrientes.map((nutriente) => (
                  <tr key={nutriente}>
                    <td style={{ fontWeight: 700 }}>{nutriente}</td>
                    {dados.produto_ids.map((pid) => (
                      <td key={pid}>
                        <input style={cellInput} value={grade[chave(pid, nutriente)] || ""}
                          onChange={(e) => setGrade((g) => ({ ...g, [chave(pid, nutriente)]: e.target.value }))} placeholder="—" />
                      </td>
                    ))}
                  </tr>
                ))}
                {!nutrientes.length && <tr><td colSpan={dados.alimentos.length + 1} style={{ color: "var(--text-muted)", textAlign: "center", padding: "1rem" }}>Nenhum nutriente cadastrado ainda.</td></tr>}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-2 mt-3" style={{ flexWrap: "wrap" }}>
            {textoLivre ? (
              <input value={novoProduto} onChange={(e) => setNovoProduto(e.target.value)} placeholder="Nome do novo produto…"
                style={{ ...cellInput, width: "auto", flex: "1 1 200px" }} onKeyDown={(e) => e.key === "Enter" && adicionarProduto()} />
            ) : (
              <select value={estoqueEscolhidoId} onChange={(e) => setEstoqueEscolhidoId(e.target.value)}
                style={{ ...cellInput, width: "auto", flex: "1 1 200px" }}>
                <option value="">Selecione um produto de alimentação…</option>
                {produtosDisponiveis.map((it) => <option key={it.id} value={it.id}>{it.nome}</option>)}
              </select>
            )}
            <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={adicionarProduto}><Plus size={13} /> Novo produto</button>
            <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", color: "var(--text-muted)" }}>
              <input type="checkbox" checked={textoLivre} onChange={(e) => { setTextoLivre(e.target.checked); setNovoProduto(""); setEstoqueEscolhidoId(""); }} />
              Produto fora do cadastro (texto livre)
            </label>
            <input value={novoNutriente} onChange={(e) => setNovoNutriente(e.target.value)} placeholder="Nome do novo nutriente…"
              style={{ ...cellInput, width: "auto", flex: "1 1 200px" }} onKeyDown={(e) => e.key === "Enter" && adicionarNutriente()} />
            <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={adicionarNutriente}><Plus size={13} /> Novo nutriente</button>
          </div>

          <div className="flex items-center gap-2 mt-3">
            <button className="btn-primary" style={{ fontSize: "0.8rem" }} disabled={salvando} onClick={salvar}>
              <Save size={14} /> {salvando ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
