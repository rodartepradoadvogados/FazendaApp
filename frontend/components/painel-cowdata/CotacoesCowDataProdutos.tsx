"use client";
// Produtos-padrão do catálogo CowData — cada um pode receber um preço-base
// sugerido (com ou sem cotação formal por trás). Aviso ativo de possível
// duplicata ao nomear um produto novo (nunca uma trava — granularidade fora
// de medicamento não tem regra fixa imposta, decisão do usuário: fica a
// critério da curadoria da CowData).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Pencil, Plus, Tag, X } from "lucide-react";
import {
  fetchProdutosPadrao, criarProdutoPadrao, editarProdutoPadrao, checarDuplicataProdutoPadrao,
  fetchClassificacoesCowData, fetchFinalidadesCowData, fetchFornecedoresCowData,
  atribuirPrecoProdutoPadrao,
  type ProdutoPadrao, type ClassificacaoCowData, type FinalidadeCowData, type FornecedorCowData,
  type SugestaoDuplicataProduto,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import SeletorMultiploComBusca from "@/components/SeletorMultiploComBusca";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}
function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

const FORM_VAZIO = { nome: "", unidade: "", classificacao_id: null as number | null, finalidade_ids: [] as number[] };

export default function CotacoesCowDataProdutos() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [produtos, setProdutos] = useState<ProdutoPadrao[] | null>(null);
  const [classificacoes, setClassificacoes] = useState<ClassificacaoCowData[]>([]);
  const [finalidades, setFinalidades] = useState<FinalidadeCowData[]>([]);
  const [fornecedores, setFornecedores] = useState<FornecedorCowData[]>([]);
  const [filtroClassificacao, setFiltroClassificacao] = useState<number | "">("");
  const [busca, setBusca] = useState("");

  const [editando, setEditando] = useState<number | null>(null);
  const [form, setForm] = useState(FORM_VAZIO);
  const [aberto, setAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [duplicatas, setDuplicatas] = useState<SugestaoDuplicataProduto[]>([]);

  const [produtoPreco, setProdutoPreco] = useState<ProdutoPadrao | null>(null);

  async function carregar() {
    const [p, c, f, forn] = await Promise.all([
      fetchProdutosPadrao(filtroClassificacao ? { classificacao_id: filtroClassificacao as number } : undefined),
      fetchClassificacoesCowData(), fetchFinalidadesCowData(), fetchFornecedoresCowData(),
    ]);
    setProdutos(p); setClassificacoes(c); setFinalidades(f); setFornecedores(forn);
  }
  useEffect(() => { carregar(); }, [filtroClassificacao]);

  useEffect(() => {
    if (!aberto || !form.nome.trim() || form.nome.trim().length < 3) { setDuplicatas([]); return; }
    const t = setTimeout(() => {
      checarDuplicataProdutoPadrao(form.nome.trim(), form.classificacao_id).then(setDuplicatas).catch(() => setDuplicatas([]));
    }, 400);
    return () => clearTimeout(t);
  }, [form.nome, form.classificacao_id, aberto]);

  const produtosFiltrados = useMemo(() => {
    if (!produtos) return [];
    if (!busca.trim()) return produtos;
    const b = busca.trim().toLowerCase();
    return produtos.filter((p) => p.nome.toLowerCase().includes(b));
  }, [produtos, busca]);

  function abrirNovo() { setEditando(null); setForm(FORM_VAZIO); setAberto(true); setErro(null); setDuplicatas([]); }
  function abrirEdicao(p: ProdutoPadrao) {
    setEditando(p.id);
    setForm({ nome: p.nome, unidade: p.unidade || "", classificacao_id: p.classificacao_id, finalidade_ids: p.finalidades.map((f) => f.id) });
    setAberto(true); setErro(null); setDuplicatas([]);
  }

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório"); return; }
    setSalvando(true); setErro(null);
    try {
      if (editando) await editarProdutoPadrao(editando, form);
      else await criarProdutoPadrao(form);
      setAberto(false);
      await carregar();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  if (!produtos) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <button style={btnPrimario} onClick={abrirNovo}><Plus size={14} /> Novo produto-padrão</button>
        <input style={{ ...inputStyle, minWidth: "220px" }} placeholder="Buscar por nome…" value={busca} onChange={(e) => setBusca(e.target.value)} />
        <select style={inputStyle} value={filtroClassificacao} onChange={(e) => setFiltroClassificacao(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Todas as classificações</option>
          {classificacoes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </select>
      </div>

      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", overflow: "hidden" }}>
        <table className="fazenda-table" style={{ width: "100%" }}>
          <thead>
            <tr style={{ color: COR.mudo }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Produto</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Classificação</th>
              <th style={{ textAlign: "right", padding: "0.6rem" }}>Preço atual</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Atribuído em</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {produtosFiltrados.map((p) => (
              <tr key={p.id} style={{ borderTop: `1px solid ${COR.borda}` }}>
                <td style={{ padding: "0.6rem", color: COR.texto, fontWeight: 600, fontSize: "0.85rem" }}>{p.nome} {p.unidade && <span style={{ color: COR.mudo, fontWeight: 400 }}>({p.unidade})</span>}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{p.classificacao_nome || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.85rem", textAlign: "right", color: p.preco_atual ? "var(--green-light)" : COR.mudo }}>
                  {p.preco_atual ? formatBRL(p.preco_atual.valor) : "sem preço publicado"}
                </td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>
                  {p.preco_atual ? new Date(p.preco_atual.atribuido_em).toLocaleDateString("pt-BR") : "—"}
                </td>
                <td style={{ padding: "0.6rem", display: "flex", gap: "0.4rem" }}>
                  <button style={btnGhost} onClick={() => abrirEdicao(p)}><Pencil size={13} /></button>
                  <button style={{ ...btnGhost, fontWeight: 700 }} onClick={() => setProdutoPreco(p)}><Tag size={13} /> Atribuir preço</button>
                </td>
              </tr>
            ))}
            {produtosFiltrados.length === 0 && (
              <tr><td colSpan={5} style={{ padding: "1.5rem", textAlign: "center", color: COR.mudo, fontSize: "0.82rem" }}>Nenhum produto-padrão ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
          onClick={() => setAberto(false)}>
          <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1.4rem", width: "min(520px, 92vw)", maxHeight: "88vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 style={{ color: COR.texto, fontWeight: 700 }}>{editando ? "Editar produto-padrão" : "Novo produto-padrão"}</h3>
              <button style={btnGhost} onClick={() => setAberto(false)}><X size={14} /></button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
              <div>
                <label style={labelStyle}>Nome</label>
                <input style={{ ...inputStyle, width: "100%" }} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
              </div>
              {duplicatas.length > 0 && (
                <div style={{ background: "color-mix(in srgb, var(--amber) 12%, transparent)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem" }}>
                  <p style={{ fontSize: "0.78rem", color: "var(--amber)", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.3rem", marginBottom: "0.3rem" }}>
                    <AlertTriangle size={13} /> Já existe algo parecido — confira antes de criar outro:
                  </p>
                  <ul style={{ fontSize: "0.78rem", color: COR.texto, paddingLeft: "1.1rem" }}>
                    {duplicatas.map((d) => <li key={d.id}>{d.nome}</li>)}
                  </ul>
                </div>
              )}
              <div className="flex gap-2">
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Unidade</label>
                  <input style={{ ...inputStyle, width: "100%" }} placeholder="ex.: saca 50kg" value={form.unidade} onChange={(e) => setForm({ ...form, unidade: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Classificação</label>
                  <select style={{ ...inputStyle, width: "100%" }} value={form.classificacao_id ?? ""} onChange={(e) => setForm({ ...form, classificacao_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">—</option>
                    {classificacoes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
                  </select>
                </div>
              </div>
              <SeletorMultiploComBusca label="Finalidades (uma ou mais)" opcoes={finalidades.map((f) => ({ id: f.id, nome: f.nome }))}
                selecionados={form.finalidade_ids} onChange={(ids) => setForm({ ...form, finalidade_ids: ids })}
                cor={{ bg: COR.bg, borda: COR.borda, texto: COR.texto, mudo: COR.mudo, dourado: COR.dourado, painelAlt: COR.painelAlt }} />
              {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erro}</p>}
              <button style={btnPrimario} disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
            </div>
          </div>
        </div>
      )}

      {produtoPreco && (
        <ModalAtribuirPreco produto={produtoPreco} fornecedores={fornecedores} onFechar={() => setProdutoPreco(null)}
          onSalvo={async () => { setProdutoPreco(null); await carregar(); }} />
      )}
    </div>
  );
}

function ModalAtribuirPreco({
  produto, fornecedores, onFechar, onSalvo,
}: { produto: ProdutoPadrao; fornecedores: FornecedorCowData[]; onFechar: () => void; onSalvo: () => void }) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [valor, setValor] = useState(produto.preco_atual ? String(produto.preco_atual.valor) : "");
  const [unidade, setUnidade] = useState(produto.unidade || "");
  const [regiao, setRegiao] = useState("");
  const [ehMedia, setEhMedia] = useState(false);
  const [fornecedorId, setFornecedorId] = useState<number | "">("");
  const [participantes, setParticipantes] = useState<{ fornecedor_cowdata_id: number | ""; valor_informado: string }[]>([{ fornecedor_cowdata_id: "", valor_informado: "" }]);
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState<"publicar" | "rascunho" | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function addParticipante() { setParticipantes([...participantes, { fornecedor_cowdata_id: "", valor_informado: "" }]); }
  function removerParticipante(i: number) { setParticipantes(participantes.filter((_, idx) => idx !== i)); }

  async function salvar(publicar: boolean) {
    if (!valor || Number.isNaN(Number(valor))) { setErro("Informe o valor"); return; }
    if (ehMedia && participantes.filter((p) => p.fornecedor_cowdata_id).length < 2) {
      setErro("Média exige ao menos 2 fornecedores participantes"); return;
    }
    setSalvando(publicar ? "publicar" : "rascunho"); setErro(null);
    try {
      await atribuirPrecoProdutoPadrao(produto.id, {
        valor: Number(valor), unidade: unidade || null, regiao: regiao || null, origem: "manual",
        fornecedor_escolhido_id: ehMedia ? null : (fornecedorId || null),
        eh_media: ehMedia,
        participantes_media: ehMedia
          ? participantes.filter((p) => p.fornecedor_cowdata_id).map((p) => ({
              fornecedor_cowdata_id: p.fornecedor_cowdata_id as number,
              valor_informado: p.valor_informado ? Number(p.valor_informado) : null,
            }))
          : [],
        observacao: observacao || null,
        publicar,
      });
      onSalvo();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(null); }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 110 }}
      onClick={onFechar}>
      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1.4rem", width: "min(560px, 92vw)", maxHeight: "88vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 style={{ color: COR.texto, fontWeight: 700 }}>Atribuir preço — {produto.nome}</h3>
          <button style={btnGhost} onClick={onFechar}><X size={14} /></button>
        </div>
        <p style={{ fontSize: "0.78rem", color: COR.mudo, marginBottom: "0.8rem" }}>
          Pode vir de pesquisa simples (sem cotação formal) ou de uma cotação já fechada — para atribuir a partir de uma
          cotação, use o botão "Atribuir preço" dentro da própria cotação, na aba Cotações.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <div className="flex gap-2">
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Valor</label>
              <input style={{ ...inputStyle, width: "100%" }} type="number" step="0.01" value={valor} onChange={(e) => setValor(e.target.value)} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Unidade</label>
              <input style={{ ...inputStyle, width: "100%" }} value={unidade} onChange={(e) => setUnidade(e.target.value)} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Região (opcional)</label>
              <input style={{ ...inputStyle, width: "100%" }} value={regiao} onChange={(e) => setRegiao(e.target.value)} />
            </div>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto }}>
            <input type="checkbox" checked={ehMedia} onChange={(e) => setEhMedia(e.target.checked)} /> Veio de mais de um fornecedor (média)?
          </label>

          {!ehMedia ? (
            <div>
              <label style={labelStyle}>Fornecedor (opcional — nunca aparece para as fazendas)</label>
              <select style={{ ...inputStyle, width: "100%" }} value={fornecedorId} onChange={(e) => setFornecedorId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Não informar</option>
                {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
              </select>
            </div>
          ) : (
            <div>
              <label style={labelStyle}>Fornecedores que entraram na média</label>
              {participantes.map((p, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <select style={{ ...inputStyle, flex: 2 }} value={p.fornecedor_cowdata_id}
                    onChange={(e) => setParticipantes(participantes.map((x, idx) => idx === i ? { ...x, fornecedor_cowdata_id: e.target.value ? Number(e.target.value) : "" } : x))}>
                    <option value="">Selecione…</option>
                    {fornecedores.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
                  </select>
                  <input style={{ ...inputStyle, flex: 1 }} type="number" step="0.01" placeholder="Valor dele" value={p.valor_informado}
                    onChange={(e) => setParticipantes(participantes.map((x, idx) => idx === i ? { ...x, valor_informado: e.target.value } : x))} />
                  <button style={btnGhost} onClick={() => removerParticipante(i)}><X size={13} /></button>
                </div>
              ))}
              <button style={btnGhost} onClick={addParticipante}><Plus size={12} /> Outro fornecedor</button>
            </div>
          )}

          <div>
            <label style={labelStyle}>Observação interna</label>
            <textarea style={{ ...inputStyle, width: "100%", minHeight: "50px" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} />
          </div>

          {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erro}</p>}

          <p style={{ fontSize: "0.8rem", color: COR.texto, fontWeight: 600 }}>Publicar este preço para as fazendas agora, ou manter oculto por enquanto?</p>
          <div className="flex gap-2">
            <button style={{ ...btnGhost, flex: 1, fontWeight: 700 }} disabled={!!salvando} onClick={() => salvar(false)}>
              {salvando === "rascunho" ? "Salvando…" : "Manter oculto"}
            </button>
            <button style={{ ...btnPrimario, flex: 1, justifyContent: "center" }} disabled={!!salvando} onClick={() => salvar(true)}>
              {salvando === "publicar" ? "Publicando…" : "Publicar para as fazendas"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
