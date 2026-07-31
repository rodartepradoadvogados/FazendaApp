"use client";
// Configurações > Cadastro > Alimentação — dados mestres de alimentação
// (o lançamento de nova dieta em si vive em Lançamentos > Alimentação, via o
// mesmo CadastrarNovaDieta exportado deste arquivo). Quatro abas:
//   • "Visualizar dietas": lista as dietas lançadas e abre a apresentação como
//     o funcionário a vê (produtos, por cabeça, total/dia, total/trato e kg no
//     vagão).
//   • "Matéria seca": % de MS de cada ingrediente padrão, usado para converter
//     entre matéria natural e matéria seca nas dietas.
//   • "Tabela Nutricional": cadastro da grade nutriente × produto (mesmos
//     dados que o botão "Tabela nutricional" exibe em modo consulta).
//   • "Análise bromatológica": laudos de laboratório de lotes/silos reais da
//     fazenda (MS, PB, FDN, FDA, NDT, EE, cinzas, Ca, P) — diferente da
//     Tabela Nutricional (referência padrão) e da Matéria seca (só %MS).
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Trash2, ClipboardList, ChevronDown, ChevronRight, Percent, Table2, FlaskConical, Tag, Wheat, Pencil, Check, X, AlertTriangle } from "lucide-react";
import {
  fetchLotes, fetchContextoDieta, fetchDietas, fetchApresentacaoDieta, fetchEstoque,
  criarDieta, fetchMateriaSeca, salvarMateriaSeca, ehAdmin,
  fetchAnaliseBromatologica, criarAnaliseBromatologica, type AnaliseBromatologica,
  type ContextoDieta, type ApresentacaoDieta,
  fetchCategoriasAlimento, criarCategoriaAlimento, atualizarCategoriaAlimento, excluirCategoriaAlimento, type CategoriaAlimento,
  fetchAlimentos, criarAlimento, atualizarAlimento, excluirAlimento, type Alimento,
} from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import { TabelaNutricionalBotao, TabelaNutricionalCadastroInline } from "./TabelaNutricional";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";
import { pedirCadastroDeEstoque, onPedidoCadastroDeAlimento, type PrefillNovoAlimento } from "@/lib/alimentoEstoqueBridge";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const NUM_TRATOS = 2;
const UNIDADES = ["kg", "g", "L", "ml", "unidade", "dose", "saca 30kg", "saca 60kg"];

type LoteRow = { codigo: string; nome?: string | null; rotulo?: string; qtd_animais?: number };
type ItemForm = { alimento: string; quantidade: string; unidade: string; base: string; ms_pct: number | null };
type LoteForm = { responsavel: string; dataAbertura: string; dataPrevista: string; baseQuantidade: string; leiteBezerros: string; leitePorBezerroLDia: string; itens: ItemForm[] };

const hoje = () => new Date().toISOString().slice(0, 10);
const itemVazio = (): ItemForm => ({ alimento: "", quantidade: "", unidade: "kg", base: "MN", ms_pct: null });
// Quantidade física (matéria natural) a oferecer — converte de MS para MN
// usando o %MS do ingrediente; só se aplica a kg/g (mesma regra do backend).
function quantidadeFisica(it: ItemForm): number {
  const q = Number(it.quantidade) || 0;
  if (it.base === "MS" && it.ms_pct && ["kg", "g"].includes(it.unidade)) return q / (it.ms_pct / 100);
  return q;
}
const formVazio = (): LoteForm => ({ responsavel: "Alexandre Scarpa (consultor)", dataAbertura: hoje(), dataPrevista: "", baseQuantidade: "total", leiteBezerros: "", leitePorBezerroLDia: "", itens: [itemVazio()] });

function num(v?: number | null, casas = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}
function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

const input: React.CSSProperties = {
  width: "100%", padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem", display: "block" };

export default function CadastroAlimentacao() {
  const [aba, setAba] = useState<"ver" | "ms" | "tabela-nutricional" | "bromatologica" | "categorias" | "alimentos">("ver");
  const [prefillAlimento, setPrefillAlimento] = useState<PrefillNovoAlimento | null>(null);

  useEffect(() => onPedidoCadastroDeAlimento((dados) => { setPrefillAlimento(dados); setAba("alimentos"); }), []);

  return (
    <div>
      <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          {([["ver", "Visualizar dietas", ClipboardList], ["ms", "% Matéria seca", Percent], ["tabela-nutricional", "Cadastro de tabela nutricional", Table2], ["bromatologica", "Análise bromatológica", FlaskConical], ["categorias", "Categorias", Tag], ["alimentos", "Alimentos", Wheat]] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setAba(id)}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.35rem 0.85rem", borderRadius: 999, cursor: "pointer",
                border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
                background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
                color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
        <TabelaNutricionalBotao />
      </div>
      {aba === "ver" && <VisualizarDietas />}
      {aba === "ms" && <MateriaSeca />}
      {aba === "tabela-nutricional" && <TabelaNutricionalCadastroInline />}
      {aba === "bromatologica" && <AnaliseBromatologicaTab />}
      {aba === "categorias" && <CategoriasAlimentoTab />}
      {aba === "alimentos" && (
        <AlimentosTab
          prefill={prefillAlimento}
          onPrefillConsumido={() => setPrefillAlimento(null)}
          onIrParaTabelaNutricional={() => setAba("tabela-nutricional")}
          onIrParaBromatologica={() => setAba("bromatologica")}
        />
      )}
    </div>
  );
}

// ─────────────────────────── Categorias de alimento ───────────────────────────
function CategoriasAlimentoTab() {
  const [itens, setItens] = useState<CategoriaAlimento[] | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchCategoriasAlimento().then(setItens).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setNome(""); setEditando("novo"); setErro(null); };
  const abrirEdicao = (c: CategoriaAlimento) => { setNome(c.nome); setEditando(c.id); setErro(null); };

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      if (editando === "novo") await criarCategoriaAlimento({ nome: nome.trim() });
      else if (typeof editando === "number") await atualizarCategoriaAlimento(editando, { nome: nome.trim() });
      setEditando(null);
      await carregar();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  const excluir = async (c: CategoriaAlimento) => {
    if (!window.confirm(`Excluir a categoria "${c.nome}"?`)) return;
    try { await excluirCategoriaAlimento(c.id); await carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center justify-between">
        <span className="flex items-center gap-2"><Tag size={16} /> Categorias de alimento</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Nova categoria
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Agrupa os alimentos cadastrados na aba "Alimentos" (ex.: Volumoso, Concentrado, Mineral) — livremente editável.
      </p>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

      {editando === "novo" && (
        <div className="flex items-center gap-2 mb-3">
          <input autoFocus style={input} placeholder="Nome da categoria" value={nome} onChange={(e) => setNome(e.target.value)} />
          <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={salvar} disabled={salvando}><Check size={14} /></button>
          <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setEditando(null)}><X size={14} /></button>
        </div>
      )}

      {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {itens && (
        <div className="space-y-2">
          {itens.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-2" style={{ padding: "0.5rem 0.7rem", borderRadius: 8, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
              {editando === c.id ? (
                <>
                  <input autoFocus style={{ ...input, flex: 1 }} value={nome} onChange={(e) => setNome(e.target.value)} />
                  <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={salvar} disabled={salvando}><Check size={13} /></button>
                  <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEditando(null)}><X size={13} /></button>
                </>
              ) : (
                <>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{c.nome}</span>
                  <div className="flex items-center gap-1">
                    <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirEdicao(c)}><Pencil size={13} /></button>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(c)}><Trash2 size={13} /></button>
                  </div>
                </>
              )}
            </div>
          ))}
          {!itens.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma categoria cadastrada ainda.</p>}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Alimentos (cadastro) ───────────────────────────
function AlimentosTab({ prefill, onPrefillConsumido, onIrParaTabelaNutricional, onIrParaBromatologica }: {
  prefill: PrefillNovoAlimento | null; onPrefillConsumido: () => void;
  onIrParaTabelaNutricional: () => void; onIrParaBromatologica: () => void;
}) {
  const [itens, setItens] = useState<Alimento[] | null>(null);
  const [categorias, setCategorias] = useState<CategoriaAlimento[]>([]);
  const [estoqueItens, setEstoqueItens] = useState<(EstoqueItemPicker & { id: number; alimento_id?: number | null })[]>([]);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [nome, setNome] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [observacao, setObservacao] = useState("");
  const [estoqueIds, setEstoqueIds] = useState<number[]>([]);
  const [buscaEstoque, setBuscaEstoque] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchAlimentos().then(setItens).catch((e: any) => setErro(e.message));
  useEffect(() => {
    carregar();
    fetchCategoriasAlimento().then(setCategorias).catch(() => {});
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => {});
  }, []);

  const abrirNovo = () => {
    setNome(prefill?.nome || ""); setCategoriaId(""); setObservacao("");
    setEstoqueIds(prefill?.estoqueId ? [prefill.estoqueId] : []);
    setEditando("novo"); setErro(null);
  };
  useEffect(() => { if (prefill) abrirNovo(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [prefill]);

  const abrirEdicao = (a: Alimento) => {
    setNome(a.nome); setCategoriaId(a.categoria_alimento_id ? String(a.categoria_alimento_id) : "");
    setObservacao(a.observacao || ""); setEstoqueIds((a.estoque_vinculado || []).map((e: any) => e.id));
    setEditando(a.id); setErro(null);
  };
  const cancelar = () => { setEditando(null); onPrefillConsumido(); };

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      const dados = {
        nome: nome.trim(), categoria_alimento_id: categoriaId ? Number(categoriaId) : null,
        observacao: observacao.trim() || null, estoque_ids: estoqueIds,
      };
      const salvo = editando === "novo" ? await criarAlimento(dados) : await atualizarAlimento(editando as number, dados);
      setEditando(null);
      onPrefillConsumido();
      await carregar();

      // Vínculo obrigatório: alimento deve estar ligado a pelo menos um
      // produto de estoque — se ainda não está, oferece criar/vincular um.
      if (!estoqueIds.length) {
        const converter = window.confirm(`"${salvo.nome}" ainda não está vinculado a nenhum item de Estoque. Deseja cadastrar o produto de estoque correspondente agora?`);
        if (converter) { pedirCadastroDeEstoque({ nome: salvo.nome, finalidade: "Ração/Alimento", alimentoId: salvo.id }); return; }
      }
      if (window.confirm(`Deseja cadastrar a tabela nutricional de "${salvo.nome}" agora?`)) { onIrParaTabelaNutricional(); return; }
      if (window.confirm(`Deseja registrar uma análise bromatológica de "${salvo.nome}" agora?`)) { onIrParaBromatologica(); return; }
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  };

  const excluir = async (a: Alimento) => {
    if (!window.confirm(`Excluir o alimento "${a.nome}"? Os itens de estoque vinculados ficam sem vínculo, sem serem apagados.`)) return;
    try { await excluirAlimento(a.id); await carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  const nomeCategoria = (id: number | null) => categorias.find((c) => c.id === id)?.nome || "—";
  const termoEstoque = buscaEstoque.trim().toLowerCase();
  // Só alimentos de verdade (rações, silagens...) — finalidade "Ração/Alimento",
  // nunca medicamento/material/equipamento. Item sem finalidade definida (legado)
  // ainda aparece, mesma regra tolerante do EstoquePicker.
  const estoqueFiltrado = estoqueItens.filter((e) =>
    (e.finalidade == null || e.finalidade === "Ração/Alimento") && (!termoEstoque || e.nome.toLowerCase().includes(termoEstoque))
  );

  // Colunas derivadas (nome da categoria/estoque vinculado) só para permitir
  // ordenar por clique no cabeçalho — mesmo padrão de CadastroPessoas.tsx.
  const linhasOrdenaveis = useMemo(() => (itens ?? []).map((a) => ({
    ...a, categoriaOrdenacao: nomeCategoria(a.categoria_alimento_id), estoqueOrdenacao: a.estoque_vinculado?.length ? a.estoque_vinculado.map((e: any) => e.nome).join(", ") : "",
  })), [itens, categorias]);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(linhasOrdenaveis);

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center justify-between">
        <span className="flex items-center gap-2"><Wheat size={16} /> Alimentos</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo alimento
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        O cadastro de alimento (ex.: "Silagem de milho") é o conceito nutricional usado nas dietas — distinto do item de
        Estoque, de onde sai a baixa física quando a dieta é lançada. Um alimento pode ter vários itens de Estoque
        vinculados; um item de Estoque só pode estar vinculado a um alimento por vez.
      </p>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

      {editando !== null && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div><label style={lbl}>Nome do alimento</label><input style={input} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
            <div><label style={lbl}>Categoria</label>
              <select style={input} value={categoriaId} onChange={(e) => setCategoriaId(e.target.value)}>
                <option value="">—</option>
                {categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
              </select>
            </div>
            <div style={{ gridColumn: "1 / -1" }}><label style={lbl}>Observação</label>
              <input style={input} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
          </div>

          <label style={lbl}>Itens de Estoque vinculados ({estoqueIds.length})</label>
          <input style={{ ...input, marginBottom: "0.4rem" }} placeholder="Buscar produto…" value={buscaEstoque} onChange={(e) => setBuscaEstoque(e.target.value)} />
          <div style={{ maxHeight: "220px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6, marginBottom: "0.8rem" }}>
            {estoqueFiltrado.map((e) => {
              const jaLinkadoOutro = e.alimento_id != null && !estoqueIds.includes(e.id);
              return (
                <label key={e.id} className="flex items-center gap-2" style={{ padding: "0.35rem 0.6rem", fontSize: "0.8rem", borderBottom: "1px solid var(--border)", cursor: "pointer" }}>
                  <input
                    type="checkbox" checked={estoqueIds.includes(e.id)}
                    onChange={(ev) => setEstoqueIds((prev) => ev.target.checked ? [...prev, e.id] : prev.filter((id) => id !== e.id))}
                  />
                  <span style={{ flex: 1 }}>{e.nome}</span>
                  {jaLinkadoOutro && <span style={{ fontSize: "0.68rem", color: "var(--amber)" }} title="Marcar aqui remove o vínculo do outro alimento">já vinculado a outro alimento</span>}
                </label>
              );
            })}
            {!estoqueFiltrado.length && <p style={{ padding: "0.6rem", color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhum item de estoque encontrado.</p>}
          </div>
          <button className="btn-ghost" style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.9rem" }}
            onClick={() => pedirCadastroDeEstoque({ nome: nome.trim(), finalidade: "Ração/Alimento", alimentoId: typeof editando === "number" ? editando : undefined })}>
            <Plus size={13} /> Cadastrar novo item de estoque vinculado
          </button>

          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
              <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
            </button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
              <X size={14} /> Cancelar
            </button>
          </div>
        </div>
      )}

      {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {itens && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <ThOrdenavel label="Alimento" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Categoria" campo="categoriaOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Estoque vinculado" campo="estoqueOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhasOrdenadas.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 700 }}>{a.nome}</td>
                  <td style={{ fontSize: "0.78rem" }}>{nomeCategoria(a.categoria_alimento_id)}</td>
                  <td style={{ fontSize: "0.78rem" }}>
                    {a.estoque_vinculado?.length
                      ? a.estoque_vinculado.map((e: any) => e.nome).join(", ")
                      : <span style={{ color: "var(--amber)", display: "flex", alignItems: "center", gap: "0.3rem" }}><AlertTriangle size={12} /> Sem produto de estoque vinculado</span>}
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", marginRight: "0.3rem" }} onClick={() => abrirEdicao(a)}><Pencil size={13} /> Editar</button>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(a)}><Trash2 size={13} /></button>
                  </td>
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum alimento cadastrado ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Matéria seca (ingredientes padrão) ───────────────
function MateriaSeca() {
  const [itens, setItens] = useState<{ nome: string; ms_pct: number | null }[]>([]);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => { fetchMateriaSeca().then(setItens).catch(() => {}); }, []);
  const patch = (nome: string, ms: string) => setItens((p) => p.map((i) => (i.nome === nome ? { ...i, ms_pct: ms === "" ? null : Number(ms) } : i)));
  async function salvar(nome: string, ms: number | null) {
    setSalvando(nome); setAviso(null);
    try { await salvarMateriaSeca({ nome, ms_pct: ms }); setAviso(`Matéria seca de ${nome} salva.`); }
    catch (e: any) { setAviso(e.message || "Erro ao salvar."); }
    finally { setSalvando(null); }
  }
  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        % de matéria seca (MS) de cada ingrediente padrão — usada para converter entre matéria natural e matéria seca nas dietas. Edite e salve.
      </p>
      <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden", maxWidth: "36rem" }}>
        {itens.map((i) => (
          <div key={i.nome} className="flex items-center gap-3" style={{ padding: "0.5rem 0.7rem", borderBottom: "1px solid var(--border)" }}>
            <span style={{ flex: 1, fontSize: "0.85rem" }}>{i.nome}</span>
            <input type="number" inputMode="decimal" step="0.01" style={{ ...input, width: "6rem" }} value={i.ms_pct ?? ""} onChange={(e) => patch(i.nome, e.target.value)} placeholder="% MS" />
            <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>%</span>
            <button className="btn-primary" style={{ fontSize: "0.75rem", padding: "0.3rem 0.7rem" }} disabled={salvando === i.nome} onClick={() => salvar(i.nome, i.ms_pct)}>
              {salvando === i.nome ? "…" : "Salvar"}
            </button>
          </div>
        ))}
        {!itens.length && <p style={{ padding: "0.8rem", color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando ingredientes…</p>}
      </div>
      {aviso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{aviso}</p>}
    </div>
  );
}

// ─────────────────────────── Análise bromatológica ───────────────────────────
// Laudo de laboratório de um lote/silo real da fazenda — não confundir com
// Tabela Nutricional (referência padrão) ou Matéria seca (só %MS genérico).
// Registro pontual (sem edição/exclusão), listado do mais recente ao mais antigo.
const CAMPOS_BROMATOLOGICA: [keyof AnaliseBromatologica, string][] = [
  ["ms_pct", "MS (%)"], ["pb_pct", "PB (%)"], ["fdn_pct", "FDN (%)"], ["fda_pct", "FDA (%)"],
  ["ndt_pct", "NDT (%)"], ["ee_pct", "EE (%)"], ["cinzas_pct", "Cinzas (%)"], ["ca_pct", "Ca (%)"], ["p_pct", "P (%)"],
];
function formBromatologicaVazio(): Record<string, string> {
  return { data: hoje(), alimento: "", observacao: "", ms_pct: "", pb_pct: "", fdn_pct: "", fda_pct: "", ndt_pct: "", ee_pct: "", cinzas_pct: "", ca_pct: "", p_pct: "" };
}
function AnaliseBromatologicaTab() {
  const [estoqueItens, setEstoqueItens] = useState<EstoqueItemPicker[]>([]);
  const [registros, setRegistros] = useState<AnaliseBromatologica[] | null>(null);
  const [form, setForm] = useState<Record<string, string>>(formBromatologicaVazio());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const carregar = () => fetchAnaliseBromatologica().then((d) => setRegistros(d.registros)).catch((e: any) => setErro(e.message));
  useEffect(() => {
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => {});
    carregar();
  }, []);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!form.data || !form.alimento) { setErro("Informe a data e o alimento/silo."); return; }
    setSalvando(true);
    try {
      const num = (v: string) => (v === "" ? undefined : Number(v));
      await criarAnaliseBromatologica({
        data: form.data, alimento: form.alimento, observacao: form.observacao || undefined,
        ms_pct: num(form.ms_pct), pb_pct: num(form.pb_pct), fdn_pct: num(form.fdn_pct), fda_pct: num(form.fda_pct),
        ndt_pct: num(form.ndt_pct), ee_pct: num(form.ee_pct), cinzas_pct: num(form.cinzas_pct), ca_pct: num(form.ca_pct), p_pct: num(form.p_pct),
      });
      setSucesso("Laudo de análise bromatológica salvo.");
      setForm(formBromatologicaVazio());
      await carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar análise bromatológica");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
        Laudo de laboratório de um lote/silo real da fazenda — diferente da Tabela Nutricional (referência padrão) e da Matéria seca (só o %MS).
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label style={lbl}>Data do laudo</label>
          <input type="date" style={input} value={form.data} onChange={(e) => setForm((f) => ({ ...f, data: e.target.value }))} />
        </div>
        <div style={{ gridColumn: "span 2" }}>
          <label style={lbl}>Alimento / silo</label>
          <EstoquePicker itens={estoqueItens} value={form.alimento} onChange={(v) => setForm((f) => ({ ...f, alimento: v }))}
            finalidades={["Ração/Alimento"]} placeholder="Selecionar silagem/alimento…" />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
        {CAMPOS_BROMATOLOGICA.map(([campo, label]) => (
          <div key={campo}>
            <label style={lbl}>{label}</label>
            <input type="number" inputMode="decimal" step="0.01" style={input} value={form[campo] || ""} onChange={(e) => setForm((f) => ({ ...f, [campo]: e.target.value }))} />
          </div>
        ))}
      </div>

      <div className="mb-3">
        <label style={lbl}>Observação</label>
        <input style={input} value={form.observacao} onChange={(e) => setForm((f) => ({ ...f, observacao: e.target.value }))} />
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{sucesso}</p>}
      <button className="btn-primary" style={{ fontSize: "0.8rem", marginBottom: "1.2rem" }} disabled={salvando} onClick={salvar}>
        {salvando ? "Salvando…" : "Salvar laudo"}
      </button>

      <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr>
            <th>Data</th><th>Alimento</th>
            {CAMPOS_BROMATOLOGICA.map(([campo, label]) => <th key={campo} style={{ textAlign: "right" }}>{label}</th>)}
            <th>Obs.</th>
          </tr></thead>
          <tbody>
            {(registros || []).map((r) => (
              <tr key={r.id}>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(r.data)}</td>
                <td style={{ fontWeight: 700 }}>{r.alimento}</td>
                {CAMPOS_BROMATOLOGICA.map(([campo]) => (
                  <td key={campo} style={{ textAlign: "right", fontSize: "0.78rem" }}>{r[campo] != null ? String(r[campo]) : "—"}</td>
                ))}
                <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{r.observacao || "—"}</td>
              </tr>
            ))}
            {registros && !registros.length && (
              <tr><td colSpan={CAMPOS_BROMATOLOGICA.length + 3} style={{ color: "var(--text-muted)", textAlign: "center", padding: "1rem" }}>Nenhum laudo lançado ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────── Cadastrar nova dieta ───────────────────────────
// Exportado para ser reaproveitado por Lançamentos > Alimentação > Cadastro de
// dieta — mesma tela do Configurações > Cadastro > Alimentação (`onSalvo`
// deixa quem incorpora este formulário atualizar sua própria lista de dietas
// lançadas depois de um salvamento, já que este componente só cuida da
// criação).
export function CadastrarNovaDieta({ onSalvo }: { onSalvo?: () => void } = {}) {
  const [lotes, setLotes] = useState<LoteRow[]>([]);
  const [estoqueItens, setEstoqueItens] = useState<EstoqueItemPicker[]>([]);
  const [msPorAlimento, setMsPorAlimento] = useState<Record<string, number | null>>({});
  const [contextos, setContextos] = useState<Record<number, ContextoDieta | null>>({});
  const [forms, setForms] = useState<Record<number, LoteForm>>({});
  const [aberto, setAberto] = useState<Set<number>>(new Set());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  useEffect(() => {
    fetchLotes().then((ls: LoteRow[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo)))).catch((e) => setErro(e.message));
    fetchMateriaSeca().then((itens) => setMsPorAlimento(Object.fromEntries(itens.map((i) => [i.nome, i.ms_pct])))).catch(() => {});
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => {});
  }, []);

  const loteNum = (l: LoteRow) => Number(l.codigo.slice(0, 2));

  function toggle(lote: number) {
    setAberto((prev) => {
      const n = new Set(prev);
      if (n.has(lote)) n.delete(lote);
      else {
        n.add(lote);
        if (!(lote in contextos)) {
          setContextos((c) => ({ ...c, [lote]: null }));
          fetchContextoDieta(lote).then((ctx) => setContextos((c) => ({ ...c, [lote]: ctx }))).catch(() => setContextos((c) => ({ ...c, [lote]: null })));
        }
        if (!(lote in forms)) setForms((f) => ({ ...f, [lote]: formVazio() }));
      }
      return n;
    });
  }

  const patchForm = (lote: number, patch: Partial<LoteForm>) => setForms((f) => ({ ...f, [lote]: { ...(f[lote] || formVazio()), ...patch } }));
  const patchItem = (lote: number, idx: number, patch: Partial<ItemForm>) => setForms((f) => {
    const cur = f[lote] || formVazio();
    const itens = cur.itens.map((it, i) => (i === idx ? { ...it, ...patch } : it));
    return { ...f, [lote]: { ...cur, itens } };
  });
  const addItem = (lote: number) => setForms((f) => { const cur = f[lote] || formVazio(); return { ...f, [lote]: { ...cur, itens: [...cur.itens, itemVazio()] } }; });
  const delItem = (lote: number, idx: number) => setForms((f) => { const cur = f[lote] || formVazio(); return { ...f, [lote]: { ...cur, itens: cur.itens.length > 1 ? cur.itens.filter((_, i) => i !== idx) : cur.itens } }; });

  // Lotes com ao menos um item válido (pronto para salvar).
  const lotesPreenchidos = useMemo(() => {
    return lotes.map(loteNum).filter((ln) => {
      const f = forms[ln];
      return f && f.itens.some((it) => it.alimento && Number(it.quantidade) > 0);
    });
  }, [lotes, forms]);

  async function salvarTudo() {
    setErro(null); setSucesso(null);
    if (!lotesPreenchidos.length) { setErro("Configure ao menos um lote com um produto e quantidade."); return; }
    setSalvando(true);
    const salvos: number[] = [];
    const falhas: string[] = [];
    try {
      for (const ln of lotesPreenchidos) {
        const f = forms[ln]!;
        const itensValidos = f.itens.filter((it) => it.alimento && Number(it.quantidade) > 0);
        if (!f.dataAbertura) { falhas.push(`Lote ${ln}: informe a data de início.`); continue; }
        // Se já há dieta ativa, pergunta se deseja encerrá-la na data de início.
        let encerrar = false;
        if (contextos[ln]?.ultima_dieta) {
          encerrar = window.confirm(`O lote ${ln} já tem uma dieta ativa. Deseja encerrar a dieta atual na data de início desta nova dieta (${formatDate(f.dataAbertura)})?`);
          if (!encerrar) { falhas.push(`Lote ${ln}: não salvo (dieta ativa mantida).`); continue; }
        }
        try {
          await criarDieta({
            lote: ln, responsavel: f.responsavel || undefined, data_abertura: f.dataAbertura, base_quantidade: f.baseQuantidade,
            leite_bezerros_kg_dia: f.leiteBezerros ? Number(f.leiteBezerros) : null,
            data_prevista_encerramento: f.dataPrevista || undefined,
            itens: itensValidos.map((it) => ({ alimento: it.alimento, quantidade: Number(it.quantidade), unidade: it.unidade, base: it.base, ms_pct: it.ms_pct })),
            encerrar_anterior: encerrar,
          });
          salvos.push(ln);
        } catch (e: any) {
          falhas.push(`Lote ${ln}: ${e.message || "erro ao salvar"}`);
        }
      }
      if (salvos.length) {
        setSucesso(`Dieta salva para ${salvos.length === 1 ? "o lote" : "os lotes"} ${salvos.join(", ")}.`);
        // Limpa os lotes salvos e recarrega seus contextos.
        setForms((f) => { const n = { ...f }; salvos.forEach((ln) => delete n[ln]); return n; });
        setAberto((prev) => { const n = new Set(prev); salvos.forEach((ln) => n.delete(ln)); return n; });
        salvos.forEach((ln) => fetchContextoDieta(ln).then((ctx) => setContextos((c) => ({ ...c, [ln]: ctx }))).catch(() => {}));
        onSalvo?.();
      }
      if (falhas.length) setErro(falhas.join(" · "));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
        Abra cada lote para ver o rebanho, a última dieta e o último controle leiteiro, e lançar a nova dieta.
        A <strong>quantidade</strong> de cada produto é o total do lote por dia — o sistema calcula sozinho por cabeça,
        por trato ({NUM_TRATOS} tratos/dia) e o total de kg no vagão. Ao final, um único botão salva todos os lotes.
      </p>

      <div className="space-y-2">
        {lotes.map((l) => {
          const ln = loteNum(l);
          const isOpen = aberto.has(ln);
          const ctx = contextos[ln];
          const f = forms[ln];
          const nAnimais = ctx?.qtd_animais ?? l.qtd_animais ?? 0;
          const vagaoKg = f ? f.itens.reduce((s, it) => (["kg", "g"].includes(it.unidade) ? s + quantidadeFisica(it) : s), 0) : 0;
          const preenchido = lotesPreenchidos.includes(ln);
          return (
            <div key={l.codigo} style={{ border: "1px solid " + (preenchido ? "var(--dourado)" : "var(--border)"), borderRadius: 10, overflow: "hidden" }}>
              <button onClick={() => toggle(ln)}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem",
                  padding: "0.7rem 0.9rem", background: "var(--surface-2)", border: "none", cursor: "pointer", color: "var(--text)", textAlign: "left" }}>
                <span className="flex items-center gap-2" style={{ fontWeight: 700 }}>
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  Lote {ln}{l.nome ? ` · ${l.nome}` : ""}
                </span>
                <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", flexShrink: 0 }}>
                  {nAnimais} {nAnimais === 1 ? "animal" : "animais"}{preenchido ? " · pronto p/ salvar" : ""}
                </span>
              </button>

              {isOpen && (
                <div style={{ padding: "0.9rem" }}>
                  {ctx === undefined || ctx === null ? (
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{ln in contextos ? "Carregando contexto do lote…" : ""}</p>
                  ) : (
                    <ContextoLoteBox ctx={ctx} />
                  )}

                  {/* ── Lançamento da nova dieta ── */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label style={lbl}>Responsável (nutricionista)</label>
                      <select style={input} value={f?.responsavel || ""} onChange={(e) => patchForm(ln, { responsavel: e.target.value })}>
                        <option value="">—</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
                      </select>
                    </div>
                    <div>
                      <label style={lbl}>Data de início</label>
                      <input type="date" style={input} value={f?.dataAbertura || ""} onChange={(e) => patchForm(ln, { dataAbertura: e.target.value })} />
                    </div>
                    <div>
                      <label style={lbl}>Provável data de fim</label>
                      <input type="date" style={input} value={f?.dataPrevista || ""} onChange={(e) => patchForm(ln, { dataPrevista: e.target.value })} />
                    </div>
                    <div>
                      <label style={lbl}>Quantidades informadas</label>
                      <select style={input} value={f?.baseQuantidade || "total"} onChange={(e) => patchForm(ln, { baseQuantidade: e.target.value })}>
                        <option value="total">Total do lote/dia</option>
                        <option value="animal">Por animal/dia</option>
                      </select>
                    </div>
                    <div>
                      <label style={lbl}>Leite por bezerro (L/dia)</label>
                      <input type="number" inputMode="decimal" min={0} style={input} value={f?.leitePorBezerroLDia || ""}
                        onChange={(e) => {
                          const porBezerro = e.target.value;
                          const total = porBezerro && nAnimais ? String(Math.round(Number(porBezerro) * nAnimais * 100) / 100) : f?.leiteBezerros || "";
                          patchForm(ln, { leitePorBezerroLDia: porBezerro, leiteBezerros: total });
                        }}
                        placeholder="ex.: 2 (bezerreiro 1) ou 3 (bezerreiro 2)" />
                      <span style={{ fontSize: "0.66rem", color: "var(--text-muted)" }}>
                        {nAnimais ? `Calcula o total do lote: ${nAnimais} animal(is) × valor informado.` : "Informe a quantidade por bezerro; o total do lote é calculado automaticamente."}
                      </span>
                    </div>
                    <div>
                      <label style={lbl}>Leite para bezerros (kg/dia) — total do lote</label>
                      <input type="number" inputMode="decimal" min={0} style={input} value={f?.leiteBezerros || ""} onChange={(e) => patchForm(ln, { leiteBezerros: e.target.value, leitePorBezerroLDia: "" })} placeholder="ex.: 120" />
                      <span style={{ fontSize: "0.66rem", color: "var(--text-muted)" }}>Total do lote/dia — alimenta o relatório Controle × Entregue. Editável direto se preferir não usar o campo por bezerro.</span>
                    </div>
                  </div>

                  <div className="space-y-2 mt-3">
                    {(f?.itens || []).map((it, idx) => {
                      const qLancado = Number(it.quantidade) || 0;
                      const qFisica = quantidadeFisica(it);
                      const porCab = nAnimais ? qFisica / nAnimais : null;
                      const porTrato = qFisica / NUM_TRATOS;
                      const msConhecido = it.alimento in msPorAlimento;
                      const semMsCadastrado = it.base === "MS" && msConhecido && !msPorAlimento[it.alimento];
                      return (
                        <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem", position: "relative" }}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                            <div>
                              <label style={lbl}>Produto {idx + 1}</label>
                              <EstoquePicker
                                itens={estoqueItens}
                                value={it.alimento}
                                onChange={(v) => patchItem(ln, idx, { alimento: v, ms_pct: msPorAlimento[v] ?? null })}
                                finalidades={["Ração/Alimento"]}
                                somenteVinculadosAlimento
                                placeholder="Selecionar silagem/alimento…"
                              />
                            </div>
                            <div>
                              <label style={lbl}>{f?.baseQuantidade === "animal" ? "Quantidade por animal/dia" : "Quantidade total/dia (lote)"}</label>
                              <input type="number" inputMode="decimal" style={input} value={it.quantidade} onChange={(e) => patchItem(ln, idx, { quantidade: e.target.value })} />
                            </div>
                            <div>
                              <label style={lbl}>Unidade</label>
                              <select style={input} value={it.unidade} onChange={(e) => patchItem(ln, idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                            </div>
                            <div>
                              <label style={lbl}>Base</label>
                              <select style={input} value={it.base} onChange={(e) => patchItem(ln, idx, { base: e.target.value })}>
                                <option value="MN">Matéria natural (MN)</option>
                                <option value="MS">Matéria seca (MS)</option>
                              </select>
                            </div>
                          </div>
                          {/* Cálculo automático enquanto edita — já convertido para o físico
                              (matéria natural) quando lançado em base MS. */}
                          <div className="flex items-center gap-4 mt-2" style={{ flexWrap: "wrap", fontSize: "0.76rem" }}>
                            <span style={{ color: "var(--green-light)", fontWeight: 700 }}>{num(porTrato)} {it.unidade}/trato</span>
                            <span style={{ color: "var(--amber)", fontWeight: 600 }}>{num(qFisica)} {it.unidade}/dia</span>
                            <span style={{ color: "var(--text-muted)" }}>{porCab != null ? `${num(porCab, 3)} ${it.unidade}/cab` : "—/cab"}</span>
                            {it.base === "MS" && it.ms_pct && qFisica !== qLancado && (
                              <span style={{ color: "var(--text-muted)" }}>({num(qLancado)} {it.unidade} MS a {num(it.ms_pct, 1)}% MS)</span>
                            )}
                          </div>
                          {semMsCadastrado && (
                            <p style={{ color: "var(--red)", fontSize: "0.72rem", marginTop: "0.3rem" }}>
                              Cadastre o % de matéria seca de "{it.alimento}" na aba Matéria seca antes de salvar em base MS.
                            </p>
                          )}
                          {(f?.itens.length || 0) > 1 && (
                            <button onClick={() => delItem(ln, idx)} title="Remover produto" aria-label="Remover produto" className="btn-ghost"
                              style={{ position: "absolute", top: "0.4rem", right: "0.4rem", color: "var(--red)" }}><Trash2 size={13} /></button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex items-center justify-between mt-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                    <button onClick={() => addItem(ln)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>
                    <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                      Vagão: <span style={{ color: "var(--dourado-light)" }}>{num(vagaoKg)} kg/dia</span>
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}> · {num(vagaoKg / NUM_TRATOS)} kg/trato</span>
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {!lotes.length && <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhum lote cadastrado.</p>}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{sucesso}</p>}

      <div className="mt-4" style={{ position: "sticky", bottom: 0, paddingTop: "0.5rem" }}>
        <button className="btn-primary" onClick={salvarTudo} disabled={salvando || !lotesPreenchidos.length}>
          {salvando ? "Salvando…" : `Salvar ${lotesPreenchidos.length || ""} ${lotesPreenchidos.length === 1 ? "dieta" : "dietas"}`.trim()}
        </button>
      </div>
    </div>
  );
}

function ContextoLoteBox({ ctx }: { ctx: ContextoDieta }) {
  const [verAnimais, setVerAnimais] = useState(false);
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: "0.75rem" }}>
      {/* Relatório simplificado */}
      <div className="grid grid-cols-3 gap-2" style={{ marginBottom: "0.6rem" }}>
        <Metrica titulo="DEL médio hoje" valor={ctx.del_medio != null ? `${ctx.del_medio} d` : "—"} />
        <Metrica titulo="Média no último CL" valor={ctx.media_cl != null ? `${num(ctx.media_cl, 1)} kg` : "—"} />
        <Metrica titulo="Data do último CL" valor={formatDate(ctx.data_ult_cl)} />
      </div>

      {/* Última dieta */}
      <div style={{ marginBottom: "0.5rem" }}>
        <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
          Última dieta{ctx.ultima_dieta ? ` (desde ${formatDate(ctx.ultima_dieta.data_abertura)})` : ""}
        </div>
        {ctx.ultima_dieta && ctx.ultima_dieta.itens.length ? (
          <div className="flex flex-wrap gap-2">
            {ctx.ultima_dieta.itens.map((it, i) => (
              <span key={i} style={{ fontSize: "0.74rem", padding: "0.15rem 0.5rem", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)" }}>
                <strong>{it.alimento}</strong>: {num(it.total_dia)} {it.unidade}/dia{it.por_cabeca != null ? ` · ${num(it.por_cabeca, 3)}/cab` : ""}
              </span>
            ))}
          </div>
        ) : <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Sem dieta ativa registrada.</span>}
      </div>

      {/* Último controle leiteiro de cada animal (expansível) */}
      <button onClick={() => setVerAnimais((v) => !v)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.76rem" }}>
        {verAnimais ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Último controle leiteiro por animal ({ctx.animais.length})
      </button>
      {verAnimais && (
        <div className="overflow-x-auto mt-1">
          <table className="fazenda-table" style={{ fontSize: "0.74rem", margin: 0 }}>
            <thead><tr><th>Animal</th><th style={{ textAlign: "right" }}>DEL</th><th style={{ textAlign: "right" }}>Último CL</th><th style={{ textAlign: "right" }}>Data</th></tr></thead>
            <tbody>
              {ctx.animais.map((a) => (
                <tr key={a.numero}>
                  <td style={{ fontWeight: 600 }}>{a.numero}</td>
                  <td style={{ textAlign: "right" }}>{a.del_dias != null ? `${a.del_dias} d` : "—"}</td>
                  <td style={{ textAlign: "right" }}>{a.ult_cl_kg != null ? `${num(a.ult_cl_kg, 1)} kg` : "—"}</td>
                  <td style={{ textAlign: "right" }}>{formatDate(a.data_ult_leite)}</td>
                </tr>
              ))}
              {!ctx.animais.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum animal no lote.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Metrica({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.45rem 0.55rem" }}>
      <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{titulo}</div>
      <div style={{ fontSize: "0.95rem", fontWeight: 800 }}>{valor}</div>
    </div>
  );
}

// ─────────────────────────── Visualizar dietas ───────────────────────────
type DietaRow = { id: number; lote: number; responsavel?: string | null; data_abertura: string; data_prevista_encerramento?: string | null; data_efetivo_encerramento?: string | null; ativa: boolean; usuario_nome?: string | null };

function VisualizarDietas() {
  const [dietas, setDietas] = useState<DietaRow[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberta, setAberta] = useState<number | null>(null);
  const [apres, setApres] = useState<Record<number, ApresentacaoDieta | null>>({});
  const admin = ehAdmin();

  useEffect(() => { fetchDietas().then(setDietas).catch((e) => setErro(e.message)); }, []);

  function toggle(id: number) {
    setAberta((cur) => (cur === id ? null : id));
    if (aberta !== id && !(id in apres)) {
      setApres((a) => ({ ...a, [id]: null }));
      fetchApresentacaoDieta(id).then((d) => setApres((a) => ({ ...a, [id]: d }))).catch(() => setApres((a) => ({ ...a, [id]: null })));
    }
  }

  if (erro) return <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>;
  if (!dietas) return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th></th><th>Lote</th><th>Responsável</th><th>Início</th><th>Provável fim</th><th>Situação</th>{admin && <th style={{ textAlign: "left" }}>Usuário</th>}</tr></thead>
        <tbody>
          {dietas.map((d) => (
            <Fragment key={d.id}>
              <tr onClick={() => toggle(d.id)} style={{ cursor: "pointer" }}>
                <td>{aberta === d.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
                <td style={{ fontWeight: 700 }}>{d.lote}</td>
                <td style={{ fontSize: "0.78rem" }}>{d.responsavel || "—"}</td>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_abertura)}</td>
                <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_prevista_encerramento)}</td>
                <td>
                  <span style={{ fontSize: "0.72rem", fontWeight: 700, color: d.ativa ? "var(--green-light)" : "var(--text-muted)" }}>
                    {d.ativa ? "Ativa" : `Encerrada em ${formatDate(d.data_efetivo_encerramento)}`}
                  </span>
                </td>
                {admin && <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{d.usuario_nome ?? "—"}</td>}
              </tr>
              {aberta === d.id && (
                <tr><td colSpan={admin ? 7 : 6} style={{ padding: 0 }}>
                  <div style={{ background: "var(--surface-2)", padding: "0.85rem" }}>
                    {apres[d.id] === null ? <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando apresentação…</p> : apres[d.id] && <ApresentacaoBox a={apres[d.id]!} />}
                  </div>
                </td></tr>
              )}
            </Fragment>
          ))}
          {!dietas.length && <tr><td colSpan={admin ? 7 : 6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma dieta lançada ainda.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function ApresentacaoBox({ a }: { a: ApresentacaoDieta }) {
  return (
    <div>
      <div style={{ fontSize: "0.8rem", marginBottom: "0.5rem" }}>
        <strong>Lote {a.lote}{a.nome ? ` · ${a.nome}` : ""}</strong> — {a.qtd_animais} {a.qtd_animais === 1 ? "animal" : "animais"} · {a.num_tratos} tratos/dia
      </div>
      <table className="fazenda-table" style={{ margin: 0 }}>
        <thead><tr>
          <th>Produto</th>
          <th style={{ textAlign: "right" }}>Por cabeça/dia</th>
          <th style={{ textAlign: "right" }}>Total/dia</th>
          <th style={{ textAlign: "right" }}>Total/trato</th>
        </tr></thead>
        <tbody>
          {a.itens.map((it, i) => (
            <tr key={i}>
              <td style={{ fontWeight: 700 }}>{it.alimento}</td>
              <td style={{ textAlign: "right" }}>{it.por_cabeca != null ? `${num(it.por_cabeca, 3)} ${it.unidade}` : "—"}</td>
              <td style={{ textAlign: "right", color: "var(--amber)", fontWeight: 600 }}>{num(it.total_dia)} {it.unidade}</td>
              <td style={{ textAlign: "right", color: "var(--green-light)", fontWeight: 700 }}>{num(it.total_trato)} {it.unidade}</td>
            </tr>
          ))}
          {!a.itens.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Sem produtos.</td></tr>}
        </tbody>
      </table>
      <div style={{ marginTop: "0.6rem", fontSize: "0.85rem", fontWeight: 700 }}>
        Somatório no vagão: <span style={{ color: "var(--dourado-light)" }}>{num(a.vagao_kg_dia)} kg/dia</span>
        <span style={{ color: "var(--text-muted)", fontWeight: 500 }}> · {num(a.vagao_kg_trato)} kg por trato</span>
      </div>
    </div>
  );
}
