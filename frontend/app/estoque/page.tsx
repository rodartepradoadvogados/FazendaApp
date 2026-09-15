"use client";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Pencil, Trash2, ArrowDownToLine, ArrowUpFromLine, Repeat, Boxes, X, Plus } from "lucide-react";
import {
  fetchEstoque, fetchAgenda, formatBRL, fetchMovimentosEstoque, atualizarMovimentoEstoque, confirmarExclusao,
  ehAdmin, formatDate, type MovimentoEstoqueRow,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import NovoItemEstoque, { type ItemEstoqueEditando } from "@/components/NovoItemEstoque";
import { EstoquePicker } from "@/components/EstoquePicker";
import { Indicador, TelaSkeleton, ErroCarregamento } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { casaBusca } from "@/lib/busca";

const COLUNAS_ESTOQUE = [
  { header: "Produto", key: "nome" }, { header: "Categoria", key: "categoria" },
  { header: "Qtd", key: "quantidade" }, { header: "Unidade", key: "unidade" },
  { header: "Mínimo", key: "estoque_minimo" }, { header: "Valor unit.", key: "valor_unitario" },
  { header: "Valor total", key: "valor_total" }, { header: "Status", key: "status" },
];

const COLUNAS_MOVIMENTOS = [
  { header: "Data", key: "data_movimento" }, { header: "Item", key: "nome_item" },
  { header: "Movimento", key: "movimento" }, { header: "Quantidade", key: "quantidade" },
  { header: "Unidade", key: "unidade" }, { header: "Embalagem", key: "embalagem" },
  { header: "Observação", key: "observacao" },
];

const COLUNAS_POR_PRODUTO = [
  { header: "Produto", key: "produto" }, { header: "Unidade", key: "unidade" },
  { header: "Total entradas", key: "totalEntradas" }, { header: "Total saídas", key: "totalSaidas" },
  { header: "Saldo movimentado", key: "saldo" },
];

// G1 — `GET /estoque/movimentos` já devolve `origem_tipo`/`pedido_item_id`
// (é um `model_dump()` do `MovimentoEstoque` inteiro), só que o tipo
// `MovimentoEstoqueRow` de `lib/api.ts` não os declara — estendido aqui em
// vez de tocar em `api.ts` (fora da fronteira deste agente).
type MovimentoRow = MovimentoEstoqueRow & { origem_tipo?: string | null; pedido_item_id?: number | null };

// Mesma classificação entrada/saída do backend (backend/fazenda/api/routers/estoque.py) —
// usada para separar o mesmo histórico de movimentos nos mapas de entrada/saída
// e no resumo por produto, sem precisar de um endpoint novo.
// "Entrada de compra" faltava aqui — compra de produto/sêmen (Financeiro ou
// Comprar sêmen) já gerava esse movimento no backend, mas sumia dos 3 mapas
// abaixo porque nenhum deles reconhecia o tipo como entrada. "Saldo inicial"
// é o mesmo caso: o cadastro de um item de Estoque com saldo > 0 gera esse
// movimento (ver criar_item_estoque em fazenda/api/routers/estoque.py).
const MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia", "Entrada de compra", "Saldo inicial"];
const MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"];

type Item = {
  id: number; categoria: string | null; nome: string; quantidade: number | null;
  estoque_minimo: number | null; unidade: string | null;
  valor_unitario: number | null; valor_total: number | null; abaixo_minimo: boolean | null;
  principio_ativo: string | null; finalidade: string | null;
} & Record<string, any>;

const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;
const CORES = ["var(--vinho-light, #416180)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)"];

const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

function EstoqueInventario() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [horm, setHorm] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [busca, setBusca] = useState("");
  const [soAbaixo, setSoAbaixo] = useState(false);
  const [modalAbaixo, setModalAbaixo] = useState(false);
  const [modalCategorias, setModalCategorias] = useState(false);
  const [editando, setEditando] = useState<ItemEstoqueEditando | null>(null);
  const [criandoNovo, setCriandoNovo] = useState(false);

  const carregar = () => { setError(null); fetchEstoque().then((d) => setItens(d.itens)).catch((e) => setError(e.message)); };

  useEffect(() => {
    carregar();
    fetchAgenda().then((a) => setHorm(a.hormonios_check || [])).catch(() => {});
  }, []);

  const categorias = useMemo(() => {
    const s = new Set<string>(); (itens ?? []).forEach((i) => { if (i.categoria) s.add(i.categoria); });
    return Array.from(s).sort();
  }, [itens]);

  const filtrados = useMemo(() => {
    if (!itens) return [];
    return itens.filter((i) =>
      (!fCat || i.categoria === fCat) &&
      casaBusca(i.nome, busca) &&
      (!soAbaixo || i.abaixo_minimo === true)
    );
  }, [itens, fCat, busca, soAbaixo]);

  const ordItens = useOrdenacao(filtrados);
  const pagItens = usePaginacao(ordItens.linhasOrdenadas);

  const valorTotal = filtrados.reduce((a, i) => a + (i.valor_total || 0), 0);
  const itensAbaixo = useMemo(() => filtrados.filter((i) => i.abaixo_minimo === true), [filtrados]);
  const abaixo = itensAbaixo.length;

  const categoriasComContagem = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((i) => { const c = i.categoria || "(sem categoria)"; by.set(c, (by.get(c) ?? 0) + 1); });
    return Array.from(by.entries()).map(([categoria, n]) => ({ categoria, n })).sort((a, b) => a.categoria.localeCompare(b.categoria));
  }, [filtrados]);

  const porCategoria = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((i) => { const c = i.categoria || "(sem categoria)"; by.set(c, (by.get(c) ?? 0) + (i.valor_total || 0)); });
    return Array.from(by.entries()).map(([cat, valor]) => ({ cat, valor })).sort((a, b) => b.valor - a.valor).slice(0, 8);
  }, [filtrados]);

  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Boxes size={22} style={{ color: "var(--dourado)" }} /> Inventário / Saldo de estoque</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Saldo atual de cada item — filtre por categoria, busque ou veja só o que está abaixo do mínimo.</p>
        </div>
        <button type="button" className="btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setCriandoNovo(true)}>
          <Plus size={15} /> Novo item
        </button>
      </div>

      {error && <ErroCarregamento mensagem={`Não foi possível carregar o estoque: ${error}.`} onRetry={carregar} linkHref="/configuracoes?aba=importar" linkLabel="Importar itens de estoque" />}
      {!itens && !error && <TelaSkeleton kpis={0} />}

      {/* Hormônios IATF (necessidade vs estoque) */}
      {horm.length > 0 && (
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><AlertTriangle size={14} /> Hormônios IATF — Necessidade vs. Estoque</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {horm.map((h: any, i: number) => (
              <div key={i} className="p-3 rounded-lg" style={{ background: h.suficiente ? "rgba(46,125,82,0.1)" : "rgba(192,57,43,0.15)", border: `1px solid ${h.suficiente ? "var(--green)" : "var(--red)"}` }}>
                <div className="flex items-center justify-between mb-1">
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{h.nome}</span>
                  <span style={{ color: h.suficiente ? "var(--green-light)" : "var(--red)", fontWeight: 800, fontSize: "0.8rem" }}>{h.suficiente ? "OK" : `FALTA ${Math.ceil(h.falta)} ${h.unidade}`}</span>
                </div>
                <div style={{ display: "flex", gap: "1.5rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  <span>Estoque: <strong style={{ color: "var(--text)" }}>{h.estoque_atual?.toFixed(2)} {h.unidade}</strong></span>
                  <span>Necessário: <strong style={{ color: "var(--text)" }}>{h.necessidade?.toFixed(1)} {h.unidade}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {itens && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
                <select title="Filtrar itens por categoria" style={selStyle} value={fCat} onChange={(e) => setFCat(e.target.value)}><option value="">Todas</option>{categorias.map((c) => <option key={c}>{c}</option>)}</select></div>
              {/* Janela suspensa em vez de texto livre: a lista completa já
                  está carregada aqui (fetchEstoque), e digitar o nome à mão
                  errava acento/abreviação sem dizer por que nada aparecia.
                  `todasFinalidades` é obrigatório — o default do picker é só
                  "Medicamento" e esconderia quase todo o inventário. */}
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar produto</label>
                <div className="flex items-center gap-1">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <EstoquePicker itens={itens ?? []} value={busca} onChange={setBusca}
                      placeholder="Todos os produtos" todasFinalidades incluirNaoEstocaveis />
                  </div>
                  {busca && (
                    <button type="button" onClick={() => setBusca("")} className="btn-ghost" title="Limpar filtro de produto" aria-label="Limpar filtro de produto">
                      <X size={14} />
                    </button>
                  )}
                </div></div>
              <label title="Mostrar apenas itens com quantidade abaixo do estoque mínimo" style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", cursor: "pointer", paddingBottom: "0.35rem" }}>
                <input type="checkbox" checked={soAbaixo} onChange={(e) => setSoAbaixo(e.target.checked)} /> Só abaixo do mínimo
              </label>
            </div>
          </div>

          {/* Valor em estoque já era o único KPI marcado em dourado — vira a
              métrica-âncora. Abaixo do mínimo e Categorias continuam clicáveis
              (mesmos modais de antes), só em tamanho de apoio. Mesmos 4 números. */}
          <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
            <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Valor em estoque</div>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--dourado-light)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
              {formatBRL(valorTotal)}
            </div>
            <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{filtrados.length}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Itens (filtro)</div>
              </div>
              <div onClick={() => setModalAbaixo(true)} title="Ver quais produtos estão abaixo do mínimo" style={{ cursor: "pointer" }}>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, color: abaixo ? "var(--red)" : "var(--green-light)", fontVariantNumeric: "tabular-nums" }}>{abaixo}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Abaixo do mínimo</div>
              </div>
              <div onClick={() => setModalCategorias(true)} title="Ver as categorias e quantos itens cada uma tem" style={{ cursor: "pointer" }}>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{categorias.length}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Categorias</div>
              </div>
            </div>
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3">Valor em Estoque por Categoria</div>
            <ResponsiveContainer width="100%" height={Math.max(180, porCategoria.length * 36)}>
              <BarChart data={porCategoria} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis type="category" dataKey="cat" tick={{ fill: "var(--text-muted)", fontSize: 9 }} width={180} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="valor" name="Valor" radius={[0, 3, 3, 0]}>
                  {porCategoria.map((_, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Itens</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length} no filtro</span>
                <ExportarBotoes titulo="Estoque" nomeArquivoBase="estoque" colunas={COLUNAS_ESTOQUE}
                  linhas={filtrados.map((i) => ({ ...i, status: i.abaixo_minimo ? "ABAIXO DO MÍNIMO" : "OK" }))} />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Produto" campo="nome" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} />
                  <ThOrdenavel label="Categoria" campo="categoria" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} />
                  <ThOrdenavel label="Qtd" campo="quantidade" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} alinhar="right" />
                  <ThOrdenavel label="Mín." campo="estoque_minimo" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} alinhar="right" />
                  <ThOrdenavel label="Valor" campo="valor_total" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} alinhar="right" />
                  <ThOrdenavel label="Status" campo="abaixo_minimo" coluna={ordItens.coluna} dir={ordItens.dir} ordenar={ordItens.ordenar} />
                  <th></th>
                </tr></thead>
                <tbody>
                  {pagItens.linhasPagina.map((i, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{i.nome}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{i.categoria || "—"}</td>
                      <td style={{ textAlign: "right" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                      <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{i.estoque_minimo ?? "—"}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                      <td>{i.abaixo_minimo === true ? <span style={{ color: "var(--red)", fontWeight: 700, fontSize: "0.75rem" }}>ABAIXO</span> : <span style={{ color: "var(--green-light)", fontSize: "0.75rem" }}>OK</span>}</td>
                      <td style={{ textAlign: "right" }}>
                        <button onClick={() => setEditando(i)} title="Editar cadastro do produto"
                          style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                          <Pencil size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Paginacao pagina={pagItens.pagina} totalPaginas={pagItens.totalPaginas} totalLinhas={pagItens.totalLinhas}
                tamanhoPagina={pagItens.tamanhoPagina} onMudarPagina={pagItens.setPagina} onMudarTamanho={pagItens.setTamanhoPagina} />
            </div>
          </div>
        </>
      )}

      {modalAbaixo && (
        <Modal title="Produtos abaixo do mínimo" onClose={() => setModalAbaixo(false)} width="720px">
          {itensAbaixo.length ? (
            <div className="overflow-x-auto" style={{ maxHeight: "60vh" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Produto</th><th>Princípio ativo</th><th>Uso principal (finalidade)</th><th style={{ textAlign: "right" }}>Saldo</th></tr></thead>
                <tbody>
                  {itensAbaixo.map((i, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{i.nome}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{i.principio_ativo || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{i.finalidade || "—"}</td>
                      <td style={{ textAlign: "right", color: "var(--red)", fontWeight: 700 }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum produto abaixo do mínimo no filtro atual.</p>
          )}
        </Modal>
      )}

      {modalCategorias && (
        <Modal title="Categorias de estoque" onClose={() => setModalCategorias(false)} width="480px">
          <div className="overflow-x-auto" style={{ maxHeight: "60vh" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Categoria</th><th style={{ textAlign: "right" }}>Itens</th></tr></thead>
              <tbody>
                {categoriasComContagem.map((c) => (
                  <tr key={c.categoria}>
                    <td style={{ fontSize: "0.82rem" }}>{c.categoria}</td>
                    <td style={{ textAlign: "right", fontWeight: 600 }}>{c.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}

      {editando && (
        <Modal title={`Editar item — ${editando.nome}`} onClose={() => setEditando(null)} width="960px">
          <NovoItemEstoque
            editando={editando}
            onCriado={() => { setEditando(null); carregar(); }}
            onCancelar={() => setEditando(null)}
          />
        </Modal>
      )}

      {criandoNovo && (
        <Modal title="Novo item de estoque" onClose={() => setCriandoNovo(false)} width="960px">
          <NovoItemEstoque
            onCriado={() => { setCriandoNovo(false); carregar(); }}
            onCancelar={() => setCriandoNovo(false)}
          />
        </Modal>
      )}
    </div>
  );
}

// Mapa de entradas / Mapa de saídas: mesmo histórico de movimentos manuais do
// estoque (ver /estoque/movimentos), só filtrado por tipo de movimento —
// entrada ou saída — com filtro de período e busca por produto.
function MapaMovimentos({ titulo, descricao, tiposIncluidos, icon: Icon, corIcone, corQtd, nomeArquivoBase }: {
  titulo: string; descricao: string; tiposIncluidos: string[]; icon: any; corIcone: string; corQtd: string; nomeArquivoBase: string;
}) {
  const [movimentos, setMovimentos] = useState<MovimentoRow[] | null>(null);
  const [itens, setItens] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [busca, setBusca] = useState("");
  const admin = ehAdmin();

  // G1 — edição/exclusão do movimento manual (`origem_tipo` nulo). Igual ao
  // padrão de app/sanidade/page.tsx:960-982: admin exclui na hora, operador
  // só solicita (fica pendente até um admin aprovar) — passa pelo mesmo
  // motor central e auditado de exclusão (POST /exclusoes/confirmar) em vez
  // de um DELETE direto.
  const [editando, setEditando] = useState<MovimentoRow | null>(null);
  const [editQtd, setEditQtd] = useState("");
  const [editUnidade, setEditUnidade] = useState("");
  const [editData, setEditData] = useState("");
  const [editObs, setEditObs] = useState("");
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);

  const carregar = () => { setError(null); fetchMovimentosEstoque().then((d) => setMovimentos(d.movimentos as MovimentoRow[])).catch((e) => setError(e.message)); };

  useEffect(() => {
    carregar();
    fetchEstoque().then((d) => setItens(d.itens)).catch(() => {});
  }, []);

  const abrirEdicao = (m: MovimentoRow) => {
    setEditando(m);
    setEditQtd(String(m.quantidade));
    setEditUnidade(m.unidade || "");
    setEditData(m.data_movimento);
    setEditObs(m.observacao || "");
  };

  const salvarEdicao = async () => {
    if (!editando) return;
    setOcupado(editando.id); setError(null);
    try {
      await atualizarMovimentoEstoque(editando.id, {
        quantidade: Number(editQtd), unidade: editUnidade || null, data_movimento: editData, observacao: editObs || null,
      });
      setEditando(null);
      await carregar();
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  const excluir = async (m: MovimentoRow) => {
    const msg = admin
      ? `Excluir o movimento "${m.movimento}" de ${m.quantidade} ${m.unidade || ""} de ${m.nome_item}? Isso não pode ser desfeito.`
      : `Solicitar a exclusão do movimento "${m.movimento}" de ${m.nome_item}? Um administrador precisa aprovar antes de ser excluído de fato.`;
    if (!window.confirm(msg)) return;
    setOcupado(m.id); setError(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("movimento_estoque", String(m.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) { setError(e.message); }
    finally { setOcupado(null); }
  };

  const filtrados = useMemo(() => {
    if (!movimentos) return [];
    return movimentos.filter((m) =>
      tiposIncluidos.includes(m.movimento) &&
      (!de || (m.data_movimento || "") >= de) &&
      (!ate || (m.data_movimento || "") <= ate) &&
      casaBusca(m.nome_item, busca)
    );
  }, [movimentos, tiposIncluidos, de, ate, busca]);

  const ord = useOrdenacao(filtrados);
  const pag = usePaginacao(ord.linhasOrdenadas);
  const totalQtd = filtrados.reduce((a, m) => a + (m.quantidade || 0), 0);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Icon size={22} style={{ color: corIcone }} /> {titulo}</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>{descricao}</p>
      </div>

      {error && <ErroCarregamento mensagem={`Não foi possível carregar: ${error}.`} onRetry={carregar} />}
      {avisoExclusao && <div className="alert-aviso mb-4"><AlertTriangle size={18} /><span>{avisoExclusao}</span></div>}
      {!movimentos && !error && <TelaSkeleton kpis={0} />}

      {movimentos && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
                <input type="date" style={selStyle} value={de} onChange={(e) => setDe(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
                <input type="date" style={selStyle} value={ate} onChange={(e) => setAte(e.target.value)} /></div>
              {/* Janela suspensa em vez de texto livre — mesmo padrão do
                  Inventário (linha ~161): lista já carregada, sem depender do
                  usuário acertar acento/abreviação do nome do produto. */}
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar produto</label>
                <div className="flex items-center gap-1">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <EstoquePicker itens={itens} value={busca} onChange={setBusca}
                      placeholder="Todos os produtos" todasFinalidades incluirNaoEstocaveis />
                  </div>
                  {busca && (
                    <button type="button" onClick={() => setBusca("")} className="btn-ghost" title="Limpar filtro de produto" aria-label="Limpar filtro de produto">
                      <X size={14} />
                    </button>
                  )}
                </div></div>
            </div>
          </div>

          {/* Quantidade total já era o único KPI com cor (verde nas entradas,
              vermelho nas saídas) — vira métrica-âncora. Mesmos 2 números de antes. */}
          <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
            <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Quantidade total</div>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: corQtd, marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
              {totalQtd.toLocaleString("pt-BR")}
            </div>
            <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{filtrados.length}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Movimentos (filtro)</div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>{titulo}</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length} no filtro</span>
                <ExportarBotoes titulo={titulo} nomeArquivoBase={nomeArquivoBase} colunas={COLUNAS_MOVIMENTOS} linhas={filtrados} />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Data" campo="data_movimento" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Item" campo="nome_item" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Movimento" campo="movimento" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Qtd" campo="quantidade" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <th>Embalagem</th>
                  <th>Observação</th>
                  {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
                  <th style={{ textAlign: "right" }}>Ações</th>
                </tr></thead>
                <tbody>
                  {pag.linhasPagina.map((m) => {
                    // Movimento gerado por outro lançamento (Sanidade, Protocolo,
                    // Secagem…) não pode ser editado/excluído por aqui — o
                    // backend bloqueia com 400, então nem mostramos os botões.
                    const editavel = !m.origem_tipo;
                    return (
                    <tr key={m.id}>
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{formatDate(m.data_movimento)}</td>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{m.nome_item}</td>
                      <td style={{ fontSize: "0.78rem" }}>{m.movimento}</td>
                      <td style={{ textAlign: "right" }}>{m.quantidade} {m.unidade || ""}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.embalagem || "—"}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.observacao || "—"}</td>
                      {admin && <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{m.usuario_nome ?? "—"}</td>}
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {editavel ? (
                          <>
                            <button onClick={() => abrirEdicao(m)} disabled={ocupado === m.id} title="Editar movimento"
                              style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", marginRight: "0.5rem" }}>
                              <Pencil size={14} />
                            </button>
                            <button onClick={() => excluir(m)} disabled={ocupado === m.id} title="Excluir movimento"
                              style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--red)" }}>
                              <Trash2 size={14} />
                            </button>
                          </>
                        ) : (
                          <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }} title={`Gerado por ${m.origem_tipo} — desfaça pelo lançamento de origem`}>
                            gerado por {m.origem_tipo}
                          </span>
                        )}
                      </td>
                    </tr>
                    );
                  })}
                  {!filtrados.length && <tr><td colSpan={admin ? 7 : 6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum movimento no filtro.</td></tr>}
                </tbody>
              </table>
              <Paginacao pagina={pag.pagina} totalPaginas={pag.totalPaginas} totalLinhas={pag.totalLinhas}
                tamanhoPagina={pag.tamanhoPagina} onMudarPagina={pag.setPagina} onMudarTamanho={pag.setTamanhoPagina} />
            </div>
          </div>
        </>
      )}

      {editando && (
        <Modal title={`Editar movimento — ${editando.nome_item}`} onClose={() => setEditando(null)} width="480px">
          <div style={{ display: "grid", gap: "0.75rem" }}>
            <div>
              <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Quantidade</label>
              <input type="number" step="any" style={selStyle} value={editQtd} onChange={(e) => setEditQtd(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Unidade</label>
              <input style={selStyle} value={editUnidade} onChange={(e) => setEditUnidade(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data</label>
              <input type="date" style={selStyle} value={editData} onChange={(e) => setEditData(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Observação</label>
              <input style={selStyle} value={editObs} onChange={(e) => setEditObs(e.target.value)} />
            </div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              Não é possível trocar o item ou o tipo (entrada/saída) por aqui — exclua este movimento e lance um novo.
            </p>
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setEditando(null)}>Cancelar</button>
              <button className="btn-primary" onClick={salvarEdicao} disabled={ocupado === editando.id}>Salvar</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

type LinhaPorProduto = { produto: string; unidade: string; totalEntradas: number; totalSaidas: number; saldo: number };

// Some as entradas e saídas de cada produto no período — mesmo histórico dos
// mapas acima, só agrupado por item em vez de listado movimento a movimento.
function EstoquePorProduto() {
  const [movimentos, setMovimentos] = useState<MovimentoEstoqueRow[] | null>(null);
  const [itens, setItens] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [busca, setBusca] = useState("");

  const carregar = () => {
    setError(null);
    fetchMovimentosEstoque().then((d) => setMovimentos(d.movimentos)).catch((e) => setError(e.message));
    fetchEstoque().then((d) => setItens(d.itens)).catch(() => {});
  };
  useEffect(carregar, []);

  const noPeriodo = useMemo(() => {
    if (!movimentos) return [];
    return movimentos.filter((m) => (!de || (m.data_movimento || "") >= de) && (!ate || (m.data_movimento || "") <= ate));
  }, [movimentos, de, ate]);

  const porProduto = useMemo(() => {
    const by = new Map<string, LinhaPorProduto>();
    noPeriodo.forEach((m) => {
      const atual = by.get(m.nome_item) || { produto: m.nome_item, unidade: m.unidade || "", totalEntradas: 0, totalSaidas: 0, saldo: 0 };
      if (MOVIMENTOS_ENTRADA.includes(m.movimento)) atual.totalEntradas += m.quantidade || 0;
      else if (MOVIMENTOS_SAIDA.includes(m.movimento)) atual.totalSaidas += m.quantidade || 0;
      atual.saldo = atual.totalEntradas - atual.totalSaidas;
      by.set(m.nome_item, atual);
    });
    return Array.from(by.values()).filter((l) => casaBusca(l.produto, busca));
  }, [noPeriodo, busca]);

  const ord = useOrdenacao(porProduto);
  const pag = usePaginacao(ord.linhasOrdenadas);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Repeat size={22} style={{ color: "var(--dourado)" }} /> Entradas/saídas por produto</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Total de entradas e saídas de cada produto no período — o saldo movimentado é a diferença entre as duas.</p>
      </div>

      {error && <ErroCarregamento mensagem={`Não foi possível carregar: ${error}.`} onRetry={carregar} />}
      {!movimentos && !error && <TelaSkeleton kpis={0} />}

      {movimentos && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
                <input type="date" style={selStyle} value={de} onChange={(e) => setDe(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
                <input type="date" style={selStyle} value={ate} onChange={(e) => setAte(e.target.value)} /></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar produto</label>
                <div className="flex items-center gap-1">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <EstoquePicker itens={itens} value={busca} onChange={setBusca}
                      placeholder="Todos os produtos" todasFinalidades incluirNaoEstocaveis />
                  </div>
                  {busca && (
                    <button type="button" onClick={() => setBusca("")} className="btn-ghost" title="Limpar filtro de produto" aria-label="Limpar filtro de produto">
                      <X size={14} />
                    </button>
                  )}
                </div></div>
            </div>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Entradas/saídas por produto</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{porProduto.length} produto(s)</span>
                <ExportarBotoes titulo="Entradas e saídas por produto" nomeArquivoBase="estoque_por_produto" colunas={COLUNAS_POR_PRODUTO} linhas={porProduto} />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Produto" campo="produto" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Total entradas" campo="totalEntradas" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Total saídas" campo="totalSaidas" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Saldo movimentado" campo="saldo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {pag.linhasPagina.map((l) => (
                    <tr key={l.produto}>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{l.produto}</td>
                      <td style={{ textAlign: "right", color: "var(--green-light)" }}>{l.totalEntradas} {l.unidade}</td>
                      <td style={{ textAlign: "right", color: "var(--red)" }}>{l.totalSaidas} {l.unidade}</td>
                      <td style={{ textAlign: "right", fontWeight: 700 }}>{l.saldo > 0 ? "+" : ""}{l.saldo} {l.unidade}</td>
                    </tr>
                  ))}
                  {!porProduto.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum movimento no filtro.</td></tr>}
                </tbody>
              </table>
              <Paginacao pagina={pag.pagina} totalPaginas={pag.totalPaginas} totalLinhas={pag.totalLinhas}
                tamanhoPagina={pag.tamanhoPagina} onMudarPagina={pag.setPagina} onMudarTamanho={pag.setTamanhoPagina} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

type Aba = "mapaEntradas" | "mapaSaidas" | "porProduto" | "inventario";

const ABAS_ESTOQUE = [
  { id: "mapaEntradas", label: "Mapa de entradas", icon: ArrowDownToLine, title: "Histórico de entradas no estoque" },
  { id: "mapaSaidas", label: "Mapa de saídas", icon: ArrowUpFromLine, title: "Histórico de saídas do estoque" },
  { id: "porProduto", label: "Entradas/saídas por produto", icon: Repeat, title: "Totais de entradas e saídas agrupados por produto" },
  { id: "inventario", label: "Inventário / Saldo de estoque", icon: Boxes, title: "Saldo atual de cada item do estoque" },
] as const satisfies readonly { id: Aba; label: string; icon: any; title: string }[];

export default function EstoquePage() {
  const [aba, setAba] = useState<Aba>("mapaEntradas");
  const subNavTree: SubNavNode[] = useMemo(() => ABAS_ESTOQUE.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: setAba as (id: string) => void }), [subNavTree, aba]));

  return (
    <div className="px-6 pt-6">
      <div style={{ margin: "0 -1.5rem" }}>
        {aba === "mapaEntradas" && (
          <MapaMovimentos titulo="Mapa de entradas" descricao="Histórico de entradas manuais no estoque."
            tiposIncluidos={MOVIMENTOS_ENTRADA} icon={ArrowDownToLine} corIcone="var(--green-light)" corQtd="var(--green-light)"
            nomeArquivoBase="mapa_entradas_estoque" />
        )}
        {aba === "mapaSaidas" && (
          <MapaMovimentos titulo="Mapa de saídas" descricao="Histórico de saídas manuais do estoque."
            tiposIncluidos={MOVIMENTOS_SAIDA} icon={ArrowUpFromLine} corIcone="var(--red)" corQtd="var(--red)"
            nomeArquivoBase="mapa_saidas_estoque" />
        )}
        {aba === "porProduto" && <EstoquePorProduto />}
        {aba === "inventario" && <EstoqueInventario />}
      </div>
    </div>
  );
}
