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
import { Plus, Trash2, ClipboardList, ChevronDown, ChevronRight, Percent, Table2, FlaskConical, Tag, Wheat, Pencil, Check, X, AlertTriangle, Import, SearchCheck, CheckCircle2, GitMerge } from "lucide-react";
import {
  fetchLotes, fetchContextoDieta, fetchDietas, fetchApresentacaoDieta, fetchEstoque,
  criarDieta, fetchMateriaSeca, salvarMateriaSeca, ehAdmin, moduloFormulacaoDietasAtivo,
  fetchAnaliseBromatologica, criarAnaliseBromatologica, type AnaliseBromatologica,
  type ContextoDieta, type ApresentacaoDieta,
  fetchCategoriasAlimento, criarCategoriaAlimento, atualizarCategoriaAlimento, excluirCategoriaAlimento, type CategoriaAlimento,
  fetchAlimentos, criarAlimento, atualizarAlimento, excluirAlimento, type Alimento,
  fetchRelatorioMigracaoAlimentacao, atualizarEstoquePreferidoAlimento, atualizarCategoriaAlimentoEstoque, type RelatorioMigracao,
} from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { casaBusca } from "@/lib/busca";
import { TabelaNutricionalBotao, TabelaNutricionalCadastroInline } from "./TabelaNutricional";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";
import {
  pedirCadastroDeEstoque, onPedidoCadastroDeAlimento, consumirCadastroDeAlimentoPendente,
  onPedidoReaberturaDeAlimento, consumirReaberturaDeAlimentoPendente, type PrefillNovoAlimento,
} from "@/lib/alimentoEstoqueBridge";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { Modal } from "@/components/Modal";
import { SecaoRecolhivel } from "@/components/ui";
import { listarSimulacoes, obterSimulacao, type SimulacaoResumo } from "@/lib/dietas";

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

// Dado o id gravado em `Alimento.categoria_alimento_id` (FK única — decisão
// de modelagem da spec), devolve os dois valores que os selects encadeados
// do formulário precisam: se o id aponta para uma subcategoria, a raiz vai
// para o select de Categoria e o próprio id para o de Subcategoria; se aponta
// para uma raiz, só o select de Categoria é preenchido.
function idsCategoriaSubcategoria(id: number | null, categorias: CategoriaAlimento[]): { categoriaId: string; subcategoriaId: string } {
  const cat = id != null ? categorias.find((c) => c.id === id) : undefined;
  if (!cat) return { categoriaId: "", subcategoriaId: "" };
  if (cat.categoria_pai_id != null) return { categoriaId: String(cat.categoria_pai_id), subcategoriaId: String(cat.id) };
  return { categoriaId: String(cat.id), subcategoriaId: "" };
}

const input: React.CSSProperties = {
  width: "100%", padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem", display: "block" };

export default function CadastroAlimentacao() {
  const [aba, setAba] = useState<"ver" | "ms" | "tabela-nutricional" | "bromatologica" | "categorias" | "alimentos" | "conferencia">("ver");
  const [prefillAlimento, setPrefillAlimento] = useState<PrefillNovoAlimento | null>(null);
  const [alimentoIdParaReabrir, setAlimentoIdParaReabrir] = useState<number | null>(null);

  // As duas pontes (vira-Alimento e reabre-Alimento) guardam o dado em
  // sessionStorage, não só no evento — esta tela pode montar DEPOIS do
  // disparo (troca de aba em Cadastro.tsx desmonta/remonta), então lê o
  // pendente uma vez no próprio mount, além de continuar ouvindo o evento
  // pro caso raro de já estar montada.
  useEffect(() => {
    const pendenteAlimento = consumirCadastroDeAlimentoPendente();
    if (pendenteAlimento) { setPrefillAlimento(pendenteAlimento); setAba("alimentos"); }
    const pendenteReabrir = consumirReaberturaDeAlimentoPendente();
    if (pendenteReabrir != null) { setAlimentoIdParaReabrir(pendenteReabrir); setAba("alimentos"); }
    const off1 = onPedidoCadastroDeAlimento((dados) => { setPrefillAlimento(dados); setAba("alimentos"); });
    const off2 = onPedidoReaberturaDeAlimento((id) => { setAlimentoIdParaReabrir(id); setAba("alimentos"); });
    return () => { off1(); off2(); };
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-3" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
          {([["ver", "Visualizar dietas", ClipboardList], ["ms", "% Matéria seca", Percent], ["tabela-nutricional", "Cadastro de tabela nutricional", Table2], ["bromatologica", "Análise bromatológica", FlaskConical], ["categorias", "Categorias", Tag], ["alimentos", "Alimentos", Wheat], ["conferencia", "Conferência", SearchCheck]] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setAba(id)}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.35rem 0.85rem", borderRadius: 999, cursor: "pointer",
                // Tokens de pílula ativa (globals.css) em vez de literal fixo: no
                // claro/misto o fundo vira vinho SÓLIDO (não o vinho translúcido do
                // escuro), senão o texto dourado fica ilegível sobre fundo branco.
                border: "1px solid " + (aba === id ? "var(--pill-active-border)" : "var(--border)"),
                background: aba === id ? "var(--pill-active-bg)" : "transparent",
                color: aba === id ? "var(--pill-active-fg)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
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
          abrirEdicaoId={alimentoIdParaReabrir}
          onAbrirEdicaoConsumido={() => setAlimentoIdParaReabrir(null)}
        />
      )}
      {aba === "conferencia" && <ConferenciaMigracaoTab />}
    </div>
  );
}

// ─────────────────────────── Categorias de alimento ───────────────────────────
// Dois níveis (raiz e subcategoria — B1): o mesmo formulário de nome serve
// para os dois, só muda o `paiId` alvo quando é criação. Guardamos a
// categoria inteira (não só o id) ao entrar em edição porque o PUT precisa
// reenviar o `categoria_pai_id` atual — omitir o campo arriscaria o backend
// entender "virou raiz" e mover a subcategoria sem o usuário ter pedido isso.
type ModoEdicaoCategoria = { tipo: "novo"; paiId: number | null } | { tipo: "editar"; cat: CategoriaAlimento };

function CategoriasAlimentoTab() {
  const [itens, setItens] = useState<CategoriaAlimento[] | null>(null);
  const [modo, setModo] = useState<ModoEdicaoCategoria | null>(null);
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchCategoriasAlimento().then(setItens).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const abrirNovo = (paiId: number | null) => { setNome(""); setModo({ tipo: "novo", paiId }); setErro(null); };
  const abrirEdicao = (c: CategoriaAlimento) => { setNome(c.nome); setModo({ tipo: "editar", cat: c }); setErro(null); };
  const cancelar = () => setModo(null);

  const salvar = async () => {
    if (!modo) return;
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      if (modo.tipo === "novo") await criarCategoriaAlimento({ nome: nome.trim(), categoria_pai_id: modo.paiId });
      else await atualizarCategoriaAlimento(modo.cat.id, { nome: nome.trim(), categoria_pai_id: modo.cat.categoria_pai_id });
      setModo(null);
      await carregar();
    } catch (e: any) {
      // Mensagem do backend direto na tela (terceiro nível, nome duplicado
      // sob o mesmo pai, exclusão com filhas — B4): nada de traduzir/engolir.
      setErro(e.message);
    }
    finally { setSalvando(false); }
  };

  const excluir = async (c: CategoriaAlimento) => {
    if (!window.confirm(`Excluir a categoria "${c.nome}"?`)) return;
    try { await excluirCategoriaAlimento(c.id); await carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  // Raízes por nome e, sob cada uma, as filhas por nome — mesmo agrupamento
  // que o backend já devolve (A6), recalculado aqui só por segurança.
  const raizes = useMemo(() => (itens ?? []).filter((c) => c.categoria_pai_id == null).sort((a, b) => a.nome.localeCompare(b.nome)), [itens]);
  const filhasDe = (paiId: number) => (itens ?? []).filter((c) => c.categoria_pai_id === paiId).sort((a, b) => a.nome.localeCompare(b.nome));

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center justify-between">
        <span className="flex items-center gap-2"><Tag size={16} /> Categorias de alimento</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => abrirNovo(null)}>
          <Plus size={14} /> Nova categoria
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Agrupa os alimentos cadastrados na aba "Alimentos" em dois níveis — ex.: "Concentrado" com as subcategorias
        "Proteico" e "Energético" — tudo livremente editável.
      </p>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}

      {modo?.tipo === "novo" && modo.paiId === null && (
        <div className="flex items-center gap-2 mb-3">
          <input autoFocus style={input} placeholder="Nome da categoria" value={nome} onChange={(e) => setNome(e.target.value)} />
          <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={salvar} disabled={salvando}><Check size={14} /></button>
          <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={cancelar}><X size={14} /></button>
        </div>
      )}

      {!itens && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {itens && (
        <div className="space-y-2">
          {raizes.map((raiz) => (
            <Fragment key={raiz.id}>
              <LinhaCategoriaAlimento
                c={raiz} subordinada={false}
                emEdicao={modo?.tipo === "editar" && modo.cat.id === raiz.id}
                nome={nome} setNome={setNome} salvando={salvando}
                onEditar={() => abrirEdicao(raiz)} onSalvar={salvar} onCancelar={cancelar}
                onExcluir={() => excluir(raiz)} onNovaSub={() => abrirNovo(raiz.id)}
              />
              {modo?.tipo === "novo" && modo.paiId === raiz.id && (
                <div className="flex items-center gap-2" style={{ marginLeft: "1.8rem" }}>
                  <input autoFocus style={input} placeholder="Nome da subcategoria" value={nome} onChange={(e) => setNome(e.target.value)} />
                  <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={salvar} disabled={salvando}><Check size={14} /></button>
                  <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={cancelar}><X size={14} /></button>
                </div>
              )}
              {filhasDe(raiz.id).map((filha) => (
                <LinhaCategoriaAlimento
                  key={filha.id} c={filha} subordinada
                  emEdicao={modo?.tipo === "editar" && modo.cat.id === filha.id}
                  nome={nome} setNome={setNome} salvando={salvando}
                  onEditar={() => abrirEdicao(filha)} onSalvar={salvar} onCancelar={cancelar}
                  onExcluir={() => excluir(filha)}
                />
              ))}
            </Fragment>
          ))}
          {!raizes.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma categoria cadastrada ainda.</p>}
        </div>
      )}
    </div>
  );
}

// Uma linha da árvore (raiz ou subcategoria — indentada e com borda à
// esquerda em vez de fundo próprio, para não competir com os tokens de
// destaque `--pill-active-*` das abas). "Nova subcategoria" só existe na
// raiz: dois níveis é o máximo que o backend aceita (A3) — B2/B3.
function LinhaCategoriaAlimento({ c, subordinada, emEdicao, nome, setNome, salvando, onEditar, onSalvar, onCancelar, onExcluir, onNovaSub }: {
  c: CategoriaAlimento; subordinada: boolean; emEdicao: boolean;
  nome: string; setNome: (v: string) => void; salvando: boolean;
  onEditar: () => void; onSalvar: () => void; onCancelar: () => void; onExcluir: () => void; onNovaSub?: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2" style={{
      padding: "0.5rem 0.7rem", borderRadius: 8, background: "var(--surface-2)",
      border: "1px solid var(--border)", marginLeft: subordinada ? "1.8rem" : 0,
      borderLeft: subordinada ? "3px solid var(--border)" : "1px solid var(--border)",
    }}>
      {emEdicao ? (
        <>
          <input autoFocus style={{ ...input, flex: 1 }} value={nome} onChange={(e) => setNome(e.target.value)} />
          <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={onSalvar} disabled={salvando}><Check size={13} /></button>
          <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={onCancelar}><X size={13} /></button>
        </>
      ) : (
        <>
          <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{c.nome}</span>
          <div className="flex items-center gap-1">
            {onNovaSub && (
              <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.25rem" }} onClick={onNovaSub}>
                <Plus size={13} /> Nova subcategoria
              </button>
            )}
            <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={onEditar}><Pencil size={13} /></button>
            <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={onExcluir}><Trash2 size={13} /></button>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────── Alimentos (cadastro) ───────────────────────────
function AlimentosTab({ prefill, onPrefillConsumido, onIrParaTabelaNutricional, onIrParaBromatologica, abrirEdicaoId, onAbrirEdicaoConsumido }: {
  prefill: PrefillNovoAlimento | null; onPrefillConsumido: () => void;
  onIrParaTabelaNutricional: () => void; onIrParaBromatologica: () => void;
  abrirEdicaoId: number | null; onAbrirEdicaoConsumido: () => void;
}) {
  const [itens, setItens] = useState<Alimento[] | null>(null);
  const [categorias, setCategorias] = useState<CategoriaAlimento[]>([]);
  const [estoqueItens, setEstoqueItens] = useState<(EstoqueItemPicker & { id: number; alimento_id?: number | null })[]>([]);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [nome, setNome] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  // Categoria (raiz) e subcategoria são dois selects encadeados no formulário
  // (B8) mesmo a FK sendo uma só (`categoria_alimento_id`) — subcategoriaId
  // vazio é estado legítimo, grava a raiz.
  const [subcategoriaId, setSubcategoriaId] = useState("");
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
    setNome(prefill?.nome || ""); setCategoriaId(""); setSubcategoriaId(""); setObservacao("");
    setEstoqueIds(prefill?.estoqueId ? [prefill.estoqueId] : []);
    setEditando("novo"); setErro(null);
  };
  useEffect(() => { if (prefill) abrirNovo(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [prefill]);

  const abrirEdicao = (a: Alimento) => {
    setNome(a.nome);
    const { categoriaId: cId, subcategoriaId: sId } = idsCategoriaSubcategoria(a.categoria_alimento_id, categorias);
    setCategoriaId(cId); setSubcategoriaId(sId);
    setObservacao(a.observacao || ""); setEstoqueIds((a.estoque_vinculado || []).map((e: any) => e.id));
    setEditando(a.id); setErro(null);
  };
  const cancelar = () => { setEditando(null); onPrefillConsumido(); };

  // Volta de "Cadastrar novo item de estoque vinculado" (ver alimentoEstoqueBridge)
  // — reabre este alimento em edição já com o vínculo novo visível.
  useEffect(() => {
    if (abrirEdicaoId == null || !itens) return;
    const alvo = itens.find((a) => a.id === abrirEdicaoId);
    if (alvo) abrirEdicao(alvo);
    onAbrirEdicaoConsumido();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abrirEdicaoId, itens]);

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      // A FK grava a subcategoria quando escolhida, senão a raiz — a subcategoria
      // vazia é estado legítimo (B8), nunca bloqueia o salvamento.
      const dados = {
        nome: nome.trim(), categoria_alimento_id: subcategoriaId ? Number(subcategoriaId) : (categoriaId ? Number(categoriaId) : null),
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

  // Categoria e Subcategoria são derivadas da mesma FK única, pela regra da
  // decisão de modelagem da spec: se o alimento aponta para uma subcategoria,
  // Categoria mostra o PAI e Subcategoria mostra ela mesma; se aponta para
  // uma raiz, Categoria mostra ela mesma e Subcategoria fica vazia (não é
  // erro/pendência, então nunca cai no "—" alarmante) — B6.
  const categoriaEfetiva = (id: number | null): { categoria: string; subcategoria: string } => {
    const cat = id != null ? categorias.find((c) => c.id === id) : undefined;
    if (!cat) return { categoria: "—", subcategoria: "" };
    if (cat.categoria_pai_id != null) {
      const pai = categorias.find((c) => c.id === cat.categoria_pai_id);
      return { categoria: pai?.nome ?? "—", subcategoria: cat.nome };
    }
    return { categoria: cat.nome, subcategoria: "" };
  };
  // Só categorias raiz entram no primeiro select do formulário; o segundo é
  // preenchido com as filhas da raiz escolhida (B8).
  const categoriasRaiz = categorias.filter((c) => c.categoria_pai_id == null);
  const subcategoriasDaCategoria = categoriaId ? categorias.filter((c) => c.categoria_pai_id === Number(categoriaId)) : [];

  // Só alimentos de verdade (rações, silagens...) — nunca medicamento,
  // equipamento ou material.
  //
  // Antes isto era uma LISTA DE PERMISSÃO por texto fixo (`finalidade` vazia ou
  // exatamente "Ração/Alimento"), e isso escondia item legítimo: a finalidade é
  // cadastro livre e extensível (Configurações > Cadastro > Estoque >
  // Finalidade — ver SEED_FINALIDADES_ESTOQUE no backend), então quem cadastrou
  // um alimento com finalidade própria (o caso real: "Nutrição") via o produto
  // sumir da busca mesmo existindo e batendo o nome. O `EstoquePicker` já tinha
  // topado com o mesmo bug e resolveu com um escape (`todasFinalidades`, ver o
  // comentário lá).
  //
  // Vira LISTA DE EXCLUSÃO: passa qualquer finalidade — inclusive as
  // personalizadas da fazenda e a vazia (legado, ou item salvo sem escolher
  // nada) — menos as que comprovadamente não são alimento. Preferir deixar
  // passar um item a mais do que esconder um que o usuário precisa vincular.
  const FINALIDADES_NAO_ALIMENTO = ["Medicamento", "Equipamento", "Material/Insumo"];
  const estoqueFiltrado = estoqueItens.filter((e) =>
    !FINALIDADES_NAO_ALIMENTO.includes(e.finalidade || "") && casaBusca(e.nome, buscaEstoque)
  );

  // Colunas derivadas (categoria/subcategoria/estoque vinculado) só para
  // permitir ordenar por clique no cabeçalho — mesmo padrão de
  // CadastroPessoas.tsx, agora cobrindo as duas colunas derivadas (B7).
  const linhasOrdenaveis = useMemo(() => (itens ?? []).map((a) => {
    const { categoria, subcategoria } = categoriaEfetiva(a.categoria_alimento_id);
    return {
      ...a, categoriaOrdenacao: categoria, subcategoriaOrdenacao: subcategoria,
      estoqueOrdenacao: a.estoque_vinculado?.length ? a.estoque_vinculado.map((e: any) => e.nome).join(", ") : "",
    };
  }), [itens, categorias]);
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
              <select style={input} value={categoriaId} onChange={(e) => { setCategoriaId(e.target.value); setSubcategoriaId(""); }}>
                <option value="">—</option>
                {categoriasRaiz.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
              </select>
            </div>
            <div><label style={lbl}>Subcategoria</label>
              {/* Encadeado com Categoria: só lista as filhas da raiz escolhida
                  e fica vazio/desabilitado quando ela não tem filhas — trocar
                  a categoria já limpa a subcategoria acima, para nunca gravar
                  filha de outro pai (B8/B9). */}
              <select style={input} value={subcategoriaId} onChange={(e) => setSubcategoriaId(e.target.value)} disabled={!subcategoriasDaCategoria.length}>
                <option value="">—</option>
                {subcategoriasDaCategoria.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
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
          <button className="btn-ghost" style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.2rem" }}
            disabled={typeof editando !== "number"}
            title={typeof editando !== "number" ? "Salve o alimento primeiro — sem isso o item de estoque nasceria sem vínculo nenhum" : undefined}
            onClick={() => pedirCadastroDeEstoque({ nome: nome.trim(), finalidade: "Ração/Alimento", alimentoId: editando as number })}>
            <Plus size={13} /> Cadastrar novo item de estoque vinculado
          </button>
          {typeof editando !== "number" && (
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
              Salve o alimento primeiro para poder cadastrar um item de estoque já vinculado a ele.
            </p>
          )}

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
                <ThOrdenavel label="Produto do estoque" campo="estoqueOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Categoria" campo="categoriaOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Subcategoria" campo="subcategoriaOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Alimento" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhasOrdenadas.map((a) => (
                <tr key={a.id}>
                  <td style={{ fontSize: "0.78rem" }}>
                    {a.estoque_vinculado?.length
                      ? a.estoque_vinculado.map((e: any) => e.nome).join(", ")
                      : <span style={{ color: "var(--amber)", display: "flex", alignItems: "center", gap: "0.3rem" }}><AlertTriangle size={12} /> Sem produto de estoque vinculado</span>}
                  </td>
                  {/* Categoria/Subcategoria derivadas da FK única — B6: alimento
                      ligado direto à raiz mostra Subcategoria vazia (sem "—"
                      alarmante, sem aviso de pendência: é estado legítimo). */}
                  <td style={{ fontSize: "0.78rem" }}>{categoriaEfetiva(a.categoria_alimento_id).categoria}</td>
                  <td style={{ fontSize: "0.78rem" }}>{categoriaEfetiva(a.categoria_alimento_id).subcategoria}</td>
                  <td style={{ fontWeight: 700 }}>{a.nome}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", marginRight: "0.3rem" }} onClick={() => abrirEdicao(a)}><Pencil size={13} /> Editar</button>
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(a)}><Trash2 size={13} /></button>
                  </td>
                </tr>
              ))}
              {!itens.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum alimento cadastrado ainda.</td></tr>}
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

// ─────────────────────── Conferência (Fase P0-B, só leitura) ───────────────────────
// Retrato dos dados de Alimento/Estoque antes do refactor que vai eliminar a
// camada `Alimento` da interface — GET /alimentacao/migracao/relatorio NÃO
// escreve nada; esta aba só lê e mostra. Nenhum botão de ação aqui de
// propósito (mesclar/manter/excluir vem numa fase futura, com o próprio
// endpoint de escrita) — um botão desabilitado sugeriria uma função que
// ainda não existe.
function VazioPositivo({ texto }: { texto: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--green-light)", fontSize: "0.82rem", padding: "0.5rem 0.1rem" }}>
      <CheckCircle2 size={15} /> {texto}
    </div>
  );
}

function ChipContagem({ n }: { n: number }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: "1.4rem", padding: "0.05rem 0.4rem",
      borderRadius: 999, fontSize: "0.72rem", fontWeight: 700,
      background: n > 0 ? "var(--pill-active-bg)" : "var(--surface-2)",
      color: n > 0 ? "var(--pill-active-fg)" : "var(--text-muted)",
      border: "1px solid " + (n > 0 ? "var(--pill-active-border)" : "var(--border)"),
    }}>
      {n}
    </span>
  );
}

function ListaCandidatos({ candidatos }: { candidatos: { id: number; nome: string }[] }) {
  if (!candidatos.length) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return <span style={{ fontSize: "0.78rem" }}>{candidatos.map((c) => c.nome).join(", ")}</span>;
}

function TabelaItensFantasma({ itens }: { itens: RelatorioMigracao["fantasmas_importacao"] }) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr>
          <th>Nome</th><th style={{ textAlign: "right" }}>Qtd.</th><th>Unid.</th><th>Finalidade</th>
          <th>Fontes (dieta / curva ABC / lançamento / sanidade)</th><th>Movimentos</th><th>Candidatos a mesclagem</th>
        </tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.id}>
              <td style={{ fontWeight: 700 }}>{it.nome}</td>
              <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{num(it.quantidade)}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.unidade || "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.finalidade || "—"}</td>
              <td>
                <div style={{ display: "flex", gap: "0.3rem" }}>
                  <ChipContagem n={it.fontes.dieta} /><ChipContagem n={it.fontes.curva_abc} />
                  <ChipContagem n={it.fontes.lancamento_item} /><ChipContagem n={it.fontes.sanidade} />
                </div>
              </td>
              <td style={{ fontSize: "0.78rem" }}>
                {it.quantidade_movimentos === 0
                  ? <span style={{ color: "var(--text-muted)" }}>nenhum</span>
                  : <>{it.quantidade_movimentos} · {formatDate(it.primeiro_movimento)} – {formatDate(it.ultimo_movimento)}</>}
              </td>
              <td><ListaCandidatos candidatos={it.candidatos_mesclagem} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Mesmo agrupamento raiz→filhas de `CategoriasAlimentoTab`/`AlimentosTab`
// (categoria_pai_id), aqui achatado num só <select> por linha da tabela — a
// subcategoria some indentada (↳) logo abaixo da raiz, em vez dos dois
// selects encadeados do formulário de Alimento (que não cabem numa célula).
function opcoesCategoriaHierarquicas(categorias: CategoriaAlimento[]) {
  const raizes = categorias.filter((c) => c.categoria_pai_id == null).sort((a, b) => a.nome.localeCompare(b.nome));
  const filhasDe = (paiId: number) => categorias.filter((c) => c.categoria_pai_id === paiId).sort((a, b) => a.nome.localeCompare(b.nome));
  const opcoes: React.ReactNode[] = [];
  raizes.forEach((raiz) => {
    opcoes.push(<option key={raiz.id} value={raiz.id}>{raiz.nome}</option>);
    filhasDe(raiz.id).forEach((filha) => {
      opcoes.push(<option key={filha.id} value={filha.id}>{"  ↳ " + filha.nome}</option>);
    });
  });
  return opcoes;
}

// Fase P1 — ação nova desta linha: liga o item de Estoque direto a uma
// CategoriaAlimento (PUT /alimentacao/estoque/{id}/categoria), sem precisar
// cadastrar/editar um Alimento no meio. Ao salvar com sucesso a linha some da
// lista (avisa `onCategorizado`) — o motivo "sem categoria" deixou de valer,
// então mantê-la aqui com o picker preenchido ficaria contradizendo a própria
// coluna "Motivo".
function CategoriaEstoquePicker({ item, categorias, onCategorizado }: {
  item: RelatorioMigracao["produtos_sem_categoria"][number];
  categorias: CategoriaAlimento[];
  onCategorizado: (estoqueId: number, estoqueNome: string, categoriaNome: string) => void;
}) {
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const escolher = async (valor: string) => {
    if (!valor) return;
    const categoriaId = Number(valor);
    setSalvando(true); setErro(null);
    try {
      await atualizarCategoriaAlimentoEstoque(item.id, categoriaId);
      const nomeCategoria = categorias.find((c) => c.id === categoriaId)?.nome || "";
      onCategorizado(item.id, item.nome, nomeCategoria);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a categoria");
      setSalvando(false);
    }
  };

  return (
    <div>
      <select style={{ ...input, maxWidth: "17rem" }} value="" disabled={salvando} onChange={(e) => escolher(e.target.value)}>
        <option value="">{salvando ? "Salvando…" : "Selecionar categoria…"}</option>
        {opcoesCategoriaHierarquicas(categorias)}
      </select>
      {erro && <p style={{ fontSize: "0.72rem", color: "var(--red)", marginTop: "0.2rem" }}>{erro}</p>}
    </div>
  );
}

function TabelaProdutosSemCategoria({ itens, categorias, onCategorizado }: {
  itens: RelatorioMigracao["produtos_sem_categoria"];
  categorias: CategoriaAlimento[];
  onCategorizado: (estoqueId: number, estoqueNome: string, categoriaNome: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th>Nome</th><th style={{ textAlign: "right" }}>Qtd.</th><th>Unid.</th><th>Finalidade</th><th>Motivo</th><th>Categorizar agora</th></tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.id}>
              <td style={{ fontWeight: 700 }}>{it.nome}</td>
              <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{num(it.quantidade)}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.unidade || "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.finalidade || "—"}</td>
              <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{it.motivo}</td>
              <td><CategoriaEstoquePicker item={it} categorias={categorias} onCategorizado={onCategorizado} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Fase P1 — ação nova desta linha: escolhe qual `produtos[]` recebe a baixa
// automática/consumo manual (PUT /alimentacao/alimentos/{id}/estoque-preferido).
// Hoje, sem escolha, o backend usa o primeiro item vinculado, numa ordem
// arbitrária que pode mudar sozinha conforme o vínculo é reordenado — este
// picker troca essa arbitrariedade por uma decisão explícita da fazenda, que
// só muda quando alguém mudar aqui de novo.
function ItemPreferidoPicker({ item, onAtualizado }: {
  item: RelatorioMigracao["desmembramentos"][number];
  onAtualizado: (alimentoId: number, estoquePreferidoId: number | null) => void;
}) {
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const escolher = async (valor: string) => {
    const novoId = valor === "" ? null : Number(valor);
    setSalvando(true); setErro(null);
    try {
      await atualizarEstoquePreferidoAlimento(item.alimento_id, novoId);
      onAtualizado(item.alimento_id, novoId);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar o item preferido");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div>
      <label style={{ ...lbl, marginBottom: "0.15rem" }}>Item preferido para a baixa automática</label>
      <select style={{ ...input, maxWidth: "20rem" }} value={item.estoque_preferido_id ?? ""} disabled={salvando} onChange={(e) => escolher(e.target.value)}>
        <option value="">nenhum escolhido — usa a ordem arbitrária de hoje</option>
        {item.produtos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
      </select>
      <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
        Sem uma escolha aqui, o sistema usa o primeiro item vinculado — uma ordem que pode mudar sozinha. Escolher fixa
        deliberadamente qual item recebe a baixa/consumo, até você trocar de novo.
      </p>
      {salvando && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>Salvando…</p>}
      {!salvando && erro && <p style={{ fontSize: "0.72rem", color: "var(--red)", marginTop: "0.2rem" }}>{erro}</p>}
      {!salvando && !erro && item.estoque_preferido_id != null && (
        <p style={{ fontSize: "0.72rem", color: "var(--green-light)", marginTop: "0.2rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
          <CheckCircle2 size={12} /> Escolha salva.
        </p>
      )}
      {item.tem_alimento_nutricional && (
        <p style={{ fontSize: "0.7rem", color: "var(--amber, #c99a2e)", marginTop: "0.3rem" }}>
          Este alimento tem composição nutricional cadastrada (AlimentoNutricional) — no desmembramento futuro, só um
          produto poderá herdá-la; escolher o preferido aqui já deixa claro qual.
        </p>
      )}
    </div>
  );
}

function TabelaDesmembramentos({ itens, onAtualizado }: {
  itens: RelatorioMigracao["desmembramentos"];
  onAtualizado: (alimentoId: number, estoquePreferidoId: number | null) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th>Alimento</th><th>Produtos de Estoque vinculados</th><th>Baixa automática</th></tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.alimento_id}>
              <td style={{ fontWeight: 700 }}>{it.alimento_nome || `#${it.alimento_id}`}</td>
              <td style={{ fontSize: "0.78rem" }}>
                {it.produtos.map((p) => `${p.nome} (${num(p.quantidade)} ${p.unidade || ""})`).join(" · ")}
              </td>
              <td style={{ minWidth: "18rem" }}>
                <ItemPreferidoPicker item={it} onAtualizado={onAtualizado} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Só informativo (sem picker/ação) — a divergência de nome em si não tem
// mecanismo de resolução nesta fase; as duas contagens só deixam claro o
// risco de um futuro rename: "pelo nome" é o quanto quebraria HOJE (vínculo
// por igualdade exata de string), "por id" é o quanto já está imune a isso
// (vínculo direto, sobrevive a renomear o Alimento).
function TabelaDivergenciaNome({ itens }: { itens: RelatorioMigracao["divergencia_nome"] }) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr>
          <th>Nome do Alimento (atual)</th><th>Nome no item de Estoque</th>
          <th style={{ textAlign: "right" }}>Laudos presos ao nome atual</th>
          <th style={{ textAlign: "right" }}>Laudos já seguros (vínculo por id)</th>
        </tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={`${it.alimento_id}-${it.estoque_id}`}>
              <td style={{ fontWeight: 700 }}>{it.alimento_nome}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.estoque_nome}</td>
              <td style={{ textAlign: "right", fontSize: "0.78rem" }}>
                {it.quantidade_laudos_pelo_nome_atual > 0
                  ? <span style={{ color: "var(--amber, #c99a2e)", fontWeight: 700 }}>{it.quantidade_laudos_pelo_nome_atual}</span>
                  : 0}
              </td>
              <td style={{ textAlign: "right", fontSize: "0.78rem" }}>
                {it.quantidade_laudos_pelo_id > 0
                  ? <span style={{ color: "var(--green-light)", fontWeight: 700 }}>{it.quantidade_laudos_pelo_id}</span>
                  : 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabelaIngredientesNaoResolviveis({ itens }: { itens: RelatorioMigracao["ingredientes_nao_resolviveis"] }) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th>Ingrediente da dieta</th><th>Classificação</th><th>Motivo</th><th>Candidatos encontrados</th></tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.ingrediente}>
              <td style={{ fontWeight: 700 }}>{it.ingrediente}</td>
              <td>
                <span style={{
                  fontSize: "0.72rem", fontWeight: 700, padding: "0.1rem 0.5rem", borderRadius: 999,
                  background: it.classificacao === "ambiguo" ? "color-mix(in srgb, var(--amber, #c99a2e) 20%, transparent)" : "var(--surface-2)",
                  color: it.classificacao === "ambiguo" ? "var(--amber, #c99a2e)" : "var(--text-muted)",
                  border: "1px solid " + (it.classificacao === "ambiguo" ? "var(--amber, #c99a2e)" : "var(--border)"),
                }}>
                  {it.classificacao === "ambiguo" ? "Ambíguo" : "Não resolve"}
                </span>
              </td>
              <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{it.motivo}</td>
              <td><ListaCandidatos candidatos={it.candidatos} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabelaRmca({ itens }: { itens: RelatorioMigracao["rmca"]["so_pela_conta"] }) {
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead><tr><th>Nome</th><th>Conta gerencial de despesa</th><th>Finalidade</th></tr></thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.id}>
              <td style={{ fontWeight: 700 }}>{it.nome}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.conta_gerencial_despesa_padrao || "—"}</td>
              <td style={{ fontSize: "0.78rem" }}>{it.finalidade || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConferenciaMigracaoTab() {
  const [dados, setDados] = useState<RelatorioMigracao | null>(null);
  const [categorias, setCategorias] = useState<CategoriaAlimento[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [ultimaCategorizacao, setUltimaCategorizacao] = useState<string | null>(null);

  useEffect(() => {
    setCarregando(true);
    fetchRelatorioMigracaoAlimentacao()
      .then(setDados)
      .catch((e: any) => setErro(e.message || "Erro ao carregar o relatório"))
      .finally(() => setCarregando(false));
    fetchCategoriasAlimento().then(setCategorias).catch(() => {});
  }, []);

  // Atualiza o estado local após cada ação de Fase P1 — nunca refaz o
  // fetch inteiro do relatório, só reflete o que acabou de ser salvo.
  const atualizarPreferido = (alimentoId: number, estoquePreferidoId: number | null) => {
    setDados((d) => d && {
      ...d,
      desmembramentos: d.desmembramentos.map((it) => it.alimento_id === alimentoId ? { ...it, estoque_preferido_id: estoquePreferidoId } : it),
    });
  };
  const marcarCategorizado = (estoqueId: number, estoqueNome: string, categoriaNome: string) => {
    setUltimaCategorizacao(`"${estoqueNome}" foi categorizado como "${categoriaNome}" e saiu desta lista.`);
    setDados((d) => d && { ...d, produtos_sem_categoria: d.produtos_sem_categoria.filter((p) => p.id !== estoqueId) });
  };

  return (
    <div>
      <div style={{
        display: "flex", alignItems: "flex-start", gap: "0.6rem", padding: "0.7rem 0.9rem", borderRadius: 8,
        background: "var(--surface-2)", border: "1px solid var(--border)", marginBottom: "1rem", fontSize: "0.82rem",
      }}>
        <SearchCheck size={16} style={{ flexShrink: 0, marginTop: "0.1rem", color: "var(--accent-icon)" }} />
        <div>
          <strong>Este relatório é, na maior parte, um retrato dos dados para conferência — quase nada aqui altera algo.</strong>
          <div style={{ color: "var(--text-muted)", marginTop: "0.15rem" }}>
            Nenhum item é mesclado, renomeado ou excluído aqui. Duas seções abaixo ("Alimentos com mais de um produto" e
            "Produtos de alimento sem categoria") deixam você escolher um item preferido ou uma categoria diretamente — o
            resto continua somente leitura, com as demais ações vindo numa fase futura.
          </div>
        </div>
      </div>

      {carregando && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}

      {dados && (
        <>
          <SecaoRecolhivel
            titulo="Fantasmas da importação" icon={GitMerge} defaultAberta={dados.fantasmas_importacao.length > 0}
            badge={String(dados.fantasmas_importacao.length)}
            descricao='Itens de Estoque criados pela importação antiga a partir de nomes de ingrediente/produto (sem finalidade, sem Alimento vinculado, quantidade 0) — ficaram só com o nome.'
          >
            {dados.fantasmas_importacao.length
              ? <TabelaItensFantasma itens={dados.fantasmas_importacao} />
              : <VazioPositivo texto="Nenhuma ocorrência — nenhum item fantasma da importação encontrado." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Fantasmas ponte (Ração/Alimento sem movimento)" icon={GitMerge}
            defaultAberta={dados.fantasmas_ponte.length > 0} badge={String(dados.fantasmas_ponte.length)}
            descricao="Itens com finalidade Ração/Alimento e Alimento vinculado, mas ZERO movimentos de estoque — nunca chegaram a ser usados."
          >
            {dados.fantasmas_ponte.length
              ? <TabelaItensFantasma itens={dados.fantasmas_ponte} />
              : <VazioPositivo texto="Nenhuma ocorrência — toda ponte Alimento → Estoque tem pelo menos um movimento." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Produtos de alimento sem categoria" icon={Tag}
            defaultAberta={dados.produtos_sem_categoria.length > 0} badge={String(dados.produtos_sem_categoria.length)}
            descricao='Itens que são alimento (por vínculo ou pela finalidade), mas sem classificação completa hoje — escolha a categoria direto na coluna "Categorizar agora", sem precisar passar pelo cadastro de Alimento.'
          >
            {ultimaCategorizacao && (
              <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.7rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <CheckCircle2 size={14} /> {ultimaCategorizacao}
              </p>
            )}
            {dados.produtos_sem_categoria.length
              ? <TabelaProdutosSemCategoria itens={dados.produtos_sem_categoria} categorias={categorias} onCategorizado={marcarCategorizado} />
              : <VazioPositivo texto="Nenhuma ocorrência — todo produto de alimento está classificado." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Alimentos com mais de um produto (desmembramento futuro)" icon={GitMerge}
            defaultAberta={dados.desmembramentos.length > 0} badge={String(dados.desmembramentos.length)}
            descricao='Um Alimento com 2+ itens de Estoque vinculados — hoje o sistema escolhe sozinho, em ordem arbitrária, qual deles recebe a baixa automática/consumo; a coluna "Baixa automática" deixa você tornar essa escolha deliberada. Quando a camada Alimento sair da interface, cada produto também vira uma linha independente.'
          >
            {dados.desmembramentos.length
              ? <TabelaDesmembramentos itens={dados.desmembramentos} onAtualizado={atualizarPreferido} />
              : <VazioPositivo texto="Nenhuma ocorrência — nenhum Alimento tem mais de um produto vinculado." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Nome do Alimento diverge do produto de Estoque" icon={FlaskConical}
            defaultAberta={dados.divergencia_nome.length > 0} badge={String(dados.divergencia_nome.length)}
            descricao='Análises bromatológicas podem se ligar ao alimento por igualdade EXATA de string com o nome (quebra ao renomear) ou por vínculo direto de id (sobrevive a um rename). Quanto maior "presos ao nome atual", mais arriscado renomear; quanto maior "já seguros por id", mais seguro.'
          >
            {dados.divergencia_nome.length
              ? <TabelaDivergenciaNome itens={dados.divergencia_nome} />
              : <VazioPositivo texto="Nenhuma ocorrência — nome do Alimento e do produto de Estoque coincidem em todos os vínculos." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="Ingredientes de dieta que não resolvem" icon={AlertTriangle}
            defaultAberta={dados.ingredientes_nao_resolviveis.length > 0} badge={String(dados.ingredientes_nao_resolviveis.length)}
            descricao="Ingrediente de Dieta que a resolução de hoje (nome exato de Estoque, depois via Alimento) não casa com exatamente um item."
          >
            {dados.ingredientes_nao_resolviveis.length
              ? <TabelaIngredientesNaoResolviveis itens={dados.ingredientes_nao_resolviveis} />
              : <VazioPositivo texto="Nenhuma ocorrência — todo ingrediente de dieta resolve para exatamente um item de Estoque." />}
          </SecaoRecolhivel>

          <SecaoRecolhivel
            titulo="RMCA: regra atual × regra futura" icon={Percent}
            defaultAberta={
              dados.rmca.so_pela_conta.length + dados.rmca.so_pela_finalidade.length + dados.rmca.por_ambas.length > 0
            }
            badge={String(dados.rmca.so_pela_conta.length + dados.rmca.so_pela_finalidade.length + dados.rmca.por_ambas.length)}
            descricao='Hoje o custo físico do RMCA entra só pela conta gerencial de despesa ("3.01.01..."). A regra futura é finalidade OU conta — a conta fica como rede de segurança justamente para que NENHUM item saia do indicador: só podem entrar itens novos, listados aqui antes de qualquer mudança.'
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
              <div>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.3rem" }}>
                  Só pela conta gerencial (continua entrando — é a rede de segurança) <ChipContagem n={dados.rmca.so_pela_conta.length} />
                </div>
                {dados.rmca.so_pela_conta.length ? <TabelaRmca itens={dados.rmca.so_pela_conta} /> : <VazioPositivo texto="Nenhuma ocorrência." />}
              </div>
              <div>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.3rem" }}>
                  Só pela finalidade (passa a entrar no RMCA — são os itens que a regra nova acrescenta) <ChipContagem n={dados.rmca.so_pela_finalidade.length} />
                </div>
                {dados.rmca.so_pela_finalidade.length ? <TabelaRmca itens={dados.rmca.so_pela_finalidade} /> : <VazioPositivo texto="Nenhuma ocorrência." />}
              </div>
              <div>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.3rem" }}>
                  Por ambas as regras (sem mudança) <ChipContagem n={dados.rmca.por_ambas.length} />
                </div>
                {dados.rmca.por_ambas.length ? <TabelaRmca itens={dados.rmca.por_ambas} /> : <VazioPositivo texto="Nenhuma ocorrência." />}
              </div>
            </div>
          </SecaoRecolhivel>
        </>
      )}
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
  // Por padrão só oferece produto de estoque com saldo positivo — evita
  // lançar dieta com um item que já zerou. Marcar liga a exceção.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  // Popup "importar dieta formulada" (Formulação de Dietas) — qual lote está
  // com o popup aberto, ou null se nenhum.
  const [importarAberto, setImportarAberto] = useState<number | null>(null);

  useEffect(() => {
    fetchLotes().then((ls: LoteRow[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo)))).catch((e) => setErro(e.message));
    fetchMateriaSeca().then((itens) => setMsPorAlimento(Object.fromEntries(itens.map((i) => [i.nome, i.ms_pct])))).catch(() => {});
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => {});
  }, []);

  // Produtos de estoque elegíveis para dieta: finalidade de alimentação/
  // nutrição (não só o valor literal "Ração/Alimento" — cobre variações como
  // "Nutrição" cadastradas pela própria fazenda, mesmo critério de
  // `_finalidade_indica_alimento` no backend) e, por padrão, saldo positivo.
  const itensDietaPicker = useMemo(() => {
    const termosNutricao = ["aliment", "nutri", "racao"];
    return estoqueItens.filter((it) => {
      const finalidadeOk = it.finalidade == null || termosNutricao.some((t) => casaBusca(it.finalidade, t));
      if (!finalidadeOk) return false;
      return incluirSemEstoque || Number(it.quantidade ?? 0) > 0;
    });
  }, [estoqueItens, incluirSemEstoque]);

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

      <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem", cursor: "pointer" }}>
        <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
        Incluir produtos sem estoque na lista de seleção
      </label>

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
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3" style={{ padding: "0.9rem" }}>
                  {/* Coluna esquerda — visualização da dieta atual e dados
                      básicos, rolagem própria, nunca editável aqui. */}
                  <div style={{ maxHeight: "640px", overflowY: "auto", paddingRight: "0.3rem" }}>
                    {ctx === undefined || ctx === null ? (
                      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{ln in contextos ? "Carregando contexto do lote…" : ""}</p>
                    ) : (
                      <ContextoLoteBox ctx={ctx} />
                    )}
                  </div>

                  {/* Coluna direita — lançar a dieta nova: formulação
                      (produto/quantidade/unidade/base/vagão), com rolagem
                      própria, independente da coluna esquerda. */}
                  <div style={{ maxHeight: "640px", overflowY: "auto", paddingRight: "0.3rem" }}>
                    {moduloFormulacaoDietasAtivo() && (
                      <div style={{ background: "rgba(94,26,46,0.12)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.6rem 0.75rem", marginBottom: "0.75rem" }}>
                        <div className="flex items-center justify-between gap-2" style={{ flexWrap: "wrap" }}>
                          <span style={{ fontSize: "0.8rem" }}>Deseja importar uma dieta formulada para este lote?</span>
                          <button type="button" className="btn-primary" style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                            onClick={() => setImportarAberto(ln)}>
                            <Import size={13} /> Importar dieta formulada
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label style={lbl}>Responsável (nutricionista)</label>
                        <select style={input} value={f?.responsavel || ""} onChange={(e) => patchForm(ln, { responsavel: e.target.value })}>
                          <option value="">—</option>{nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}
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
                            <div className="grid grid-cols-2 gap-2">
                              <div style={{ gridColumn: "1 / -1" }}>
                                <label style={lbl}>Produto {idx + 1}</label>
                                <EstoquePicker
                                  itens={itensDietaPicker}
                                  value={it.alimento}
                                  onChange={(v) => patchItem(ln, idx, { alimento: v, ms_pct: msPorAlimento[v] ?? null })}
                                  todasFinalidades
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
                              <div style={{ gridColumn: "1 / -1" }}>
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
                </div>
              )}
            </div>
          );
        })}
        {!lotes.length && <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhum lote cadastrado.</p>}
      </div>

      {importarAberto !== null && (
        <ImportarDietaFormuladaModal
          lote={importarAberto}
          nAnimais={contextos[importarAberto]?.qtd_animais ?? lotes.find((l) => loteNum(l) === importarAberto)?.qtd_animais ?? 0}
          onFechar={() => setImportarAberto(null)}
          onImportar={(itens) => { patchForm(importarAberto, { itens }); setImportarAberto(null); }}
        />
      )}

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

const ROTULO_BASE_QUANTIDADE: Record<string, string> = { total: "Total do lote/dia", animal: "Por animal/dia" };

// Coluna ESQUERDA do card do lote — só visualização (dados básicos + a
// dieta atualmente ativa), nunca editável aqui; a coluna direita
// (formulário) é quem lança a dieta nova.
function ContextoLoteBox({ ctx }: { ctx: ContextoDieta }) {
  const [verAnimais, setVerAnimais] = useState(false);
  const ud = ctx.ultima_dieta;
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 8, padding: "0.75rem" }}>
      {/* Relatório simplificado */}
      <div className="grid grid-cols-3 gap-2" style={{ marginBottom: "0.6rem" }}>
        <Metrica titulo="DEL médio hoje" valor={ctx.del_medio != null ? `${ctx.del_medio} d` : "—"} />
        <Metrica titulo="Média no último CL" valor={ctx.media_cl != null ? `${num(ctx.media_cl, 1)} kg` : "—"} />
        <Metrica titulo="Data do último CL" valor={formatDate(ctx.data_ult_cl)} />
      </div>

      {/* Última dieta — dados básicos do lançamento ativo, só visualização */}
      <div style={{ marginBottom: "0.5rem" }}>
        <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
          Última dieta{ud ? ` (desde ${formatDate(ud.data_abertura)})` : ""}
        </div>
        {ud ? (
          <>
            <div className="grid grid-cols-2 gap-2" style={{ marginBottom: "0.5rem" }}>
              <Metrica titulo="Responsável" valor={ud.responsavel || "—"} />
              <Metrica titulo="Data de início" valor={formatDate(ud.data_abertura)} />
              <Metrica titulo="Provável data de fim" valor={formatDate(ud.data_prevista_encerramento)} />
              <Metrica titulo="Quantidades informadas" valor={ud.base_quantidade ? (ROTULO_BASE_QUANTIDADE[ud.base_quantidade] || ud.base_quantidade) : "—"} />
              <Metrica titulo="Leite por bezerro" valor={ud.leite_por_bezerro_kg_dia != null ? `${num(ud.leite_por_bezerro_kg_dia, 2)} kg/dia` : "—"} />
              <Metrica titulo="Leite para bezerros" valor={ud.leite_bezerros_kg_dia != null ? `${num(ud.leite_bezerros_kg_dia, 1)} kg/dia` : "—"} />
            </div>
            {ud.itens.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {ud.itens.map((it, i) => (
                  <span key={i} style={{ fontSize: "0.74rem", padding: "0.15rem 0.5rem", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)" }}>
                    <strong>{it.alimento}</strong>: {num(it.total_dia)} {it.unidade}/dia{it.por_cabeca != null ? ` · ${num(it.por_cabeca, 3)}/cab` : ""}
                  </span>
                ))}
              </div>
            ) : <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Sem produtos lançados.</span>}
          </>
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

// Popup de "dietas formuladas" salvas em Formulação de Dietas — só
// visualização dos números (nunca edição/nova simulação aqui). Selecionar
// uma importa os produtos calculados dela na formulação do lote (coluna da
// direita) — o usuário ainda confirma/edita antes de salvar o lançamento.
function ImportarDietaFormuladaModal({ lote, nAnimais, onFechar, onImportar }: {
  lote: number; nAnimais: number; onFechar: () => void; onImportar: (itens: ItemForm[]) => void;
}) {
  const [incluirTodas, setIncluirTodas] = useState(false);
  const [simulacoes, setSimulacoes] = useState<SimulacaoResumo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [importando, setImportando] = useState<number | null>(null);

  useEffect(() => {
    setSimulacoes(null);
    listarSimulacoes(incluirTodas ? {} : { lote })
      .then(setSimulacoes)
      .catch((e) => setErro(e.message || "Erro ao listar dietas formuladas"));
  }, [lote, incluirTodas]);

  async function usar(s: SimulacaoResumo) {
    setImportando(s.id); setErro(null);
    try {
      const detalhe = await obterSimulacao(s.id);
      if (!detalhe.resultado) { setErro(`"${s.nome}" ainda não foi calculada — abra em Formulação de Dietas antes de importar.`); return; }
      const itens: ItemForm[] = detalhe.resultado.ingredientes.map((ing) => ({
        alimento: ing.nome, unidade: "kg", base: "MN",
        // kg_materia_natural_dia do motor é POR ANIMAL — a formulação do
        // lote aqui trabalha em total do lote/dia, mesma conversão que
        // "por cabeça" já faz no resto da tela (ver quantidadeFisica/porCab).
        quantidade: nAnimais ? String(Math.round(ing.kg_materia_natural_dia * nAnimais * 100) / 100) : String(ing.kg_materia_natural_dia),
        ms_pct: null,
      }));
      if (!itens.length) { setErro(`"${s.nome}" não tem ingredientes calculados.`); return; }
      onImportar(itens);
    } catch (e: any) {
      setErro(e.message || "Erro ao importar a dieta formulada");
    } finally {
      setImportando(null);
    }
  }

  return (
    <Modal title={`Dietas formuladas — Lote ${lote}`} onClose={onFechar} width="640px">
      <label className="flex items-center gap-2 mb-3" style={{ fontSize: "0.8rem" }}>
        <input type="checkbox" checked={incluirTodas} onChange={(e) => setIncluirTodas(e.target.checked)} />
        Incluir todas as dietas salvas (não só as deste lote)
      </label>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {simulacoes === null && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>}
      {simulacoes && !simulacoes.length && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
          {incluirTodas ? "Nenhuma dieta formulada salva ainda." : "Nenhuma dieta formulada salva para este lote — marque \"incluir todas\" para ver de outros lotes."}
        </p>
      )}
      <div className="space-y-2" style={{ maxHeight: "420px", overflowY: "auto" }}>
        {(simulacoes || []).map((s) => (
          <div key={s.id} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.6rem 0.75rem" }}>
            <div className="flex items-center justify-between" style={{ marginBottom: "0.35rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{s.nome}</span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                Lote {s.lote ?? "—"} · {s.status}
              </span>
            </div>
            <div className="grid grid-cols-4 gap-2" style={{ marginBottom: "0.5rem" }}>
              <Metrica titulo="CMS" valor={s.cms_kg_dia != null ? `${num(s.cms_kg_dia, 1)} kg` : "—"} />
              <Metrica titulo="Balanço ELl" valor={s.balanco_ell_mcal != null ? `${num(s.balanco_ell_mcal, 1)}` : "—"} />
              <Metrica titulo="Balanço PM" valor={s.balanco_pm_g != null ? `${num(s.balanco_pm_g, 0)} g` : "—"} />
              <Metrica titulo="Custo/dia" valor={s.custo_dia != null ? `R$ ${num(s.custo_dia, 2)}` : "—"} />
            </div>
            <button type="button" className="btn-primary" style={{ fontSize: "0.76rem" }}
              disabled={s.cms_kg_dia == null || importando === s.id} onClick={() => usar(s)}>
              {importando === s.id ? "Importando…" : "Usar esta dieta"}
            </button>
            {s.cms_kg_dia == null && <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.5rem" }}>ainda não calculada</span>}
          </div>
        ))}
      </div>
    </Modal>
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
