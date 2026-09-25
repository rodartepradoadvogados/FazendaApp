"use client";
// Cotação de preços com os fornecedores da PRÓPRIA CowData — a equipe liga/
// escreve pra eles por fora do sistema (telefone, e-mail, WhatsApp) e
// registra aqui o que cada um respondeu. Sem disparo automático nem link
// público: diferente da Cotação de uma fazenda (fazenda.models.cotacao),
// aqui os fornecedores já são conhecidos e contatados diretamente.
import { useEffect, useMemo, useState } from "react";
import { Ban, ChevronLeft, Package, Plus, Send, Tag, Trash2, X } from "lucide-react";
import {
  fetchCotacoesCowData, criarCotacaoCowData, fetchCotacaoCowData, adicionarItemCotacaoCowData, removerItemCotacaoCowData,
  adicionarFornecedoresCotacaoCowData, removerFornecedorCotacaoCowData, registrarRespostaCotacaoCowData,
  fecharCotacaoCowData, cancelarCotacaoCowData, atribuirPrecoProdutoPadrao,
  fetchProdutosPadrao, fetchClassificacoesCowData, fetchFinalidadesCowData, fetchFornecedoresCowData,
  type CotacaoCowDataResumo, type CotacaoCowDataDetalhe, type CotacaoCowDataItem, type ProdutoPadrao,
  type ClassificacaoCowData, type FinalidadeCowData, type FornecedorCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}

const STATUS_LABEL: Record<string, string> = {
  rascunho: "Rascunho", em_andamento: "Em andamento", fechada: "Fechada", cancelada: "Cancelada",
};
const MODO_LABEL: Record<string, string> = {
  produto: "Produto", classificacao: "Classificação", finalidade: "Finalidade",
};
const STATUS_COR: Record<string, string> = {
  rascunho: "var(--text-muted)", em_andamento: "var(--amber)", fechada: "var(--green-light)", cancelada: "var(--red)",
};

function Badge({ status }: { status: string }) {
  return <span style={{ fontSize: "0.72rem", fontWeight: 700, color: STATUS_COR[status] || "var(--text-muted)" }}>● {STATUS_LABEL[status] || status}</span>;
}

export default function CotacoesCowDataCotacoes() {
  const [lista, setLista] = useState<CotacaoCowDataResumo[] | null>(null);
  const [detalheId, setDetalheId] = useState<number | null>(null);
  const { cor: COR, inputStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [novoTitulo, setNovoTitulo] = useState("");
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() { setLista(await fetchCotacoesCowData()); }
  useEffect(() => { carregar(); }, []);

  async function criar() {
    if (!novoTitulo.trim()) return;
    setCriando(true); setErro(null);
    try {
      const c = await criarCotacaoCowData(novoTitulo.trim());
      setNovoTitulo("");
      await carregar();
      setDetalheId(c.id);
    } catch (e) { setErro(msgErro(e)); } finally { setCriando(false); }
  }

  if (detalheId != null) {
    return <DetalheCotacao id={detalheId} onVoltar={() => { setDetalheId(null); carregar(); }} />;
  }

  if (!lista) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <input style={{ ...inputStyle, flex: 1, maxWidth: "360px" }} placeholder="Título da nova cotação (ex.: Concentrados energéticos — out/2026)"
          value={novoTitulo} onChange={(e) => setNovoTitulo(e.target.value)} onKeyDown={(e) => e.key === "Enter" && criar()} />
        <button style={btnPrimario} disabled={criando} onClick={criar}><Plus size={14} /> Nova cotação</button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.6rem" }}>{erro}</p>}
      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", overflow: "hidden" }}>
        <table className="fazenda-table" style={{ width: "100%" }}>
          <thead>
            <tr style={{ color: COR.mudo }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Título</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Status</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Criada em</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id} className="row-clickable" style={{ cursor: "pointer", borderTop: `1px solid ${COR.borda}` }} onClick={() => setDetalheId(c.id)}>
                <td style={{ padding: "0.6rem", color: COR.texto, fontWeight: 600, fontSize: "0.85rem" }}>{c.titulo}</td>
                <td style={{ padding: "0.6rem" }}><Badge status={c.status} /></td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{new Date(c.criado_em).toLocaleDateString("pt-BR")}</td>
              </tr>
            ))}
            {lista.length === 0 && (
              <tr><td colSpan={3} style={{ padding: "1.5rem", textAlign: "center", color: COR.mudo, fontSize: "0.82rem" }}>Nenhuma cotação ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DetalheCotacao({ id, onVoltar }: { id: number; onVoltar: () => void }) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [detalhe, setDetalhe] = useState<CotacaoCowDataDetalhe | null>(null);
  const [produtos, setProdutos] = useState<ProdutoPadrao[]>([]);
  const [classificacoes, setClassificacoes] = useState<ClassificacaoCowData[]>([]);
  const [finalidades, setFinalidades] = useState<FinalidadeCowData[]>([]);
  const [fornecedoresTodos, setFornecedoresTodos] = useState<FornecedorCowData[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [precoDeItem, setPrecoDeItem] = useState<CotacaoCowDataItem | null>(null);

  async function carregar() {
    const [d, p, c, f, forn] = await Promise.all([
      fetchCotacaoCowData(id), fetchProdutosPadrao(), fetchClassificacoesCowData(), fetchFinalidadesCowData(), fetchFornecedoresCowData(),
    ]);
    setDetalhe(d); setProdutos(p); setClassificacoes(c); setFinalidades(f); setFornecedoresTodos(forn);
  }
  useEffect(() => { carregar(); }, [id]);

  const aberta = detalhe && (detalhe.status === "rascunho" || detalhe.status === "em_andamento");

  // ---- adicionar item ----
  const [modo, setModo] = useState<"produto" | "classificacao" | "finalidade">("produto");
  const [alvoId, setAlvoId] = useState<number | "">("");
  const [descricaoLivre, setDescricaoLivre] = useState("");
  async function adicionarItem() {
    if (!alvoId) { setErro("Selecione o alvo do item"); return; }
    setErro(null);
    try {
      await adicionarItemCotacaoCowData(id, {
        modo,
        produto_padrao_id: modo === "produto" ? (alvoId as number) : null,
        classificacao_id: modo === "classificacao" ? (alvoId as number) : null,
        finalidade_id: modo === "finalidade" ? (alvoId as number) : null,
        descricao_livre: descricaoLivre || null,
      });
      setAlvoId(""); setDescricaoLivre("");
      await carregar();
    } catch (e) { setErro(msgErro(e)); }
  }

  // ---- fornecedores convidados ----
  const [fornecedorNovo, setFornecedorNovo] = useState<number | "">("");
  async function adicionarFornecedor() {
    if (!fornecedorNovo) return;
    await adicionarFornecedoresCotacaoCowData(id, [fornecedorNovo as number]);
    setFornecedorNovo("");
    await carregar();
  }

  if (!detalhe) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  const fornecedoresDisponiveis = fornecedoresTodos.filter((f) => !detalhe.fornecedores.some((x) => x.id === f.id));

  return (
    <div>
      <button style={{ ...btnGhost, marginBottom: "0.8rem" }} onClick={onVoltar}><ChevronLeft size={14} /> Voltar às cotações</button>

      <div className="flex items-center justify-between mb-4" style={{ flexWrap: "wrap", gap: "0.6rem" }}>
        <div>
          <h2 style={{ color: COR.texto, fontWeight: 700, fontSize: "1.15rem" }}>{detalhe.titulo}</h2>
          <Badge status={detalhe.status} />
        </div>
        {aberta && (
          <div className="flex gap-2">
            <button style={{ ...btnGhost, color: "var(--red)" }} onClick={async () => { await cancelarCotacaoCowData(id); await carregar(); }}><Ban size={14} /> Cancelar</button>
            <button style={btnPrimario} onClick={async () => { await fecharCotacaoCowData(id); await carregar(); }}><Send size={14} /> Fechar cotação</button>
          </div>
        )}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginBottom: "0.8rem" }}>{erro}</p>}

      {/* Fornecedores convidados */}
      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1rem", marginBottom: "1rem" }}>
        <p style={{ fontSize: "0.78rem", fontWeight: 700, color: COR.mudo, marginBottom: "0.6rem", textTransform: "uppercase" }}>Fornecedores convidados</p>
        <div className="flex gap-2 flex-wrap mb-2">
          {detalhe.fornecedores.map((f) => (
            <span key={f.id} style={{ fontSize: "0.8rem", padding: "0.3rem 0.6rem", borderRadius: "999px", border: `1px solid ${COR.borda}`, color: COR.texto, display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
              {f.nome}
              {aberta && <button onClick={async () => { await removerFornecedorCotacaoCowData(id, f.id); await carregar(); }} style={{ background: "none", border: "none", cursor: "pointer", color: COR.mudo }}><X size={12} /></button>}
            </span>
          ))}
          {detalhe.fornecedores.length === 0 && <span style={{ fontSize: "0.8rem", color: COR.mudo }}>Nenhum convidado ainda.</span>}
        </div>
        {aberta && (
          <div className="flex gap-2">
            <select style={inputStyle} value={fornecedorNovo} onChange={(e) => setFornecedorNovo(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Adicionar fornecedor…</option>
              {fornecedoresDisponiveis.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
            </select>
            <button style={btnGhost} onClick={adicionarFornecedor}><Plus size={13} /></button>
          </div>
        )}
      </div>

      {/* Adicionar item */}
      {aberta && (
        <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1rem", marginBottom: "1rem" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: COR.mudo, marginBottom: "0.6rem", textTransform: "uppercase" }}>Adicionar item</p>
          <div className="flex gap-2 mb-2" style={{ flexWrap: "wrap" }}>
            {(["produto", "classificacao", "finalidade"] as const).map((m) => (
              <button key={m} onClick={() => { setModo(m); setAlvoId(""); }}
                style={{
                  fontSize: "0.78rem", padding: "0.35rem 0.7rem", borderRadius: "var(--r-sm)", cursor: "pointer", fontWeight: 700,
                  border: `1px solid ${modo === m ? COR.dourado : COR.borda}`, background: modo === m ? COR.dourado : "transparent",
                  color: modo === m ? COR.bg : COR.mudo,
                }}>
                {m === "produto" ? "Por produto" : m === "classificacao" ? "Por classificação" : "Por finalidade"}
              </button>
            ))}
          </div>
          <div className="flex gap-2 mb-2" style={{ flexWrap: "wrap" }}>
            <select style={{ ...inputStyle, minWidth: "220px" }} value={alvoId} onChange={(e) => setAlvoId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecione…</option>
              {modo === "produto" && produtos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              {modo === "classificacao" && classificacoes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
              {modo === "finalidade" && finalidades.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
            </select>
          </div>
          <textarea style={{ ...inputStyle, width: "100%", minHeight: "50px", marginBottom: "0.6rem" }}
            placeholder="Elaboração livre (uso interno — ex.: milho moído, farelo de soja, casquinha de soja)"
            value={descricaoLivre} onChange={(e) => setDescricaoLivre(e.target.value)} />
          <button style={btnPrimario} onClick={adicionarItem}><Plus size={14} /> Adicionar item</button>
        </div>
      )}

      {/* Itens + respostas */}
      {detalhe.itens.map((item) => (
        <ItemCotacao key={item.id} item={item} cotacaoId={id} fechada={!aberta} fornecedores={detalhe.fornecedores}
          respostas={detalhe.respostas.filter((r) => r.cotacao_cowdata_item_id === item.id)}
          onMudou={carregar} onRemover={aberta ? async () => { await removerItemCotacaoCowData(id, item.id); await carregar(); } : undefined}
          onAtribuirPreco={item.modo === "produto" && !aberta ? () => setPrecoDeItem(item) : undefined} />
      ))}
      {detalhe.itens.length === 0 && <p style={{ fontSize: "0.82rem", color: COR.mudo }}>Nenhum item ainda.</p>}

      {precoDeItem && (
        <ModalAtribuirPrecoDeCotacao item={precoDeItem} respostas={detalhe.respostas.filter((r) => r.cotacao_cowdata_item_id === precoDeItem.id)}
          fornecedores={detalhe.fornecedores} onFechar={() => setPrecoDeItem(null)} onSalvo={async () => { setPrecoDeItem(null); await carregar(); }} />
      )}
    </div>
  );
}

function ItemCotacao({
  item, cotacaoId, fechada, fornecedores, respostas, onMudou, onRemover, onAtribuirPreco,
}: {
  item: CotacaoCowDataItem; cotacaoId: number; fechada: boolean;
  fornecedores: { id: number; nome: string }[]; respostas: any[];
  onMudou: () => Promise<void>; onRemover?: () => void; onAtribuirPreco?: () => void;
}) {
  const { cor: COR, inputStyle, btnGhost, btnPrimario } = usePainelCowDataEstilos();
  const respostaDe = (fornecedorId: number) => respostas.find((r: any) => r.fornecedor_cowdata_id === fornecedorId);

  return (
    <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1rem", marginBottom: "0.8rem" }}>
      <div className="flex items-center justify-between mb-2">
        <div>
          <span style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", color: COR.dourado }}>
            {item.modo === "produto" ? <Package size={11} style={{ display: "inline", marginRight: 4 }} /> : <Tag size={11} style={{ display: "inline", marginRight: 4 }} />}
            {MODO_LABEL[item.modo] || item.modo}
          </span>
          <p style={{ fontSize: "0.9rem", fontWeight: 700, color: COR.texto }}>{item.rotulo}</p>
          {item.descricao_livre && <p style={{ fontSize: "0.78rem", color: COR.mudo }}>{item.descricao_livre}</p>}
        </div>
        <div className="flex gap-2">
          {onAtribuirPreco && <button style={{ ...btnPrimario, fontSize: "0.75rem" }} onClick={onAtribuirPreco}><Tag size={13} /> Atribuir preço</button>}
          {onRemover && <button style={btnGhost} onClick={onRemover}><Trash2 size={13} /></button>}
        </div>
      </div>
      <table className="fazenda-table" style={{ width: "100%" }}>
        <thead>
          <tr style={{ color: COR.mudo, fontSize: "0.72rem" }}>
            <th style={{ textAlign: "left", padding: "0.3rem" }}>Fornecedor</th>
            <th style={{ textAlign: "right", padding: "0.3rem" }}>Valor</th>
            <th style={{ textAlign: "left", padding: "0.3rem" }}>Condição</th>
            <th style={{ textAlign: "left", padding: "0.3rem" }}>Prazo (dias)</th>
            <th style={{ textAlign: "left", padding: "0.3rem" }}>Recusou?</th>
          </tr>
        </thead>
        <tbody>
          {fornecedores.map((f) => (
            <LinhaResposta key={f.id} fornecedor={f} resposta={respostaDe(f.id)} cotacaoId={cotacaoId} itemId={item.id}
              editavel={!fechada} onSalvo={onMudou} />
          ))}
          {fornecedores.length === 0 && <tr><td colSpan={5} style={{ padding: "0.6rem", color: COR.mudo, fontSize: "0.78rem" }}>Convide fornecedores acima.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function LinhaResposta({
  fornecedor, resposta, cotacaoId, itemId, editavel, onSalvo,
}: { fornecedor: { id: number; nome: string }; resposta: any; cotacaoId: number; itemId: number; editavel: boolean; onSalvo: () => Promise<void> }) {
  const { cor: COR, inputStyle, btnGhost } = usePainelCowDataEstilos();
  const [valor, setValor] = useState(resposta?.valor != null ? String(resposta.valor) : "");
  const [condicao, setCondicao] = useState(resposta?.condicao_pagamento || "");
  const [prazo, setPrazo] = useState(resposta?.prazo_entrega_dias != null ? String(resposta.prazo_entrega_dias) : "");
  const [recusado, setRecusado] = useState(resposta?.recusado || false);
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true);
    try {
      await registrarRespostaCotacaoCowData(cotacaoId, itemId, fornecedor.id, {
        valor: valor ? Number(valor) : null, condicao_pagamento: condicao || null,
        prazo_entrega_dias: prazo ? Number(prazo) : null, recusado,
      });
      await onSalvo();
    } finally { setSalvando(false); }
  }

  if (!editavel) {
    return (
      <tr style={{ borderTop: `1px solid ${COR.borda}` }}>
        <td style={{ padding: "0.4rem", fontSize: "0.8rem", color: COR.texto }}>{fornecedor.nome}</td>
        <td style={{ padding: "0.4rem", fontSize: "0.8rem", textAlign: "right", color: COR.texto }}>{resposta?.recusado ? "—" : (resposta?.valor != null ? resposta.valor : "—")}</td>
        <td style={{ padding: "0.4rem", fontSize: "0.78rem", color: COR.mudo }}>{resposta?.condicao_pagamento || "—"}</td>
        <td style={{ padding: "0.4rem", fontSize: "0.78rem", color: COR.mudo }}>{resposta?.prazo_entrega_dias ?? "—"}</td>
        <td style={{ padding: "0.4rem", fontSize: "0.78rem", color: resposta?.recusado ? "var(--red)" : COR.mudo }}>{resposta?.recusado ? "Sim" : "Não"}</td>
      </tr>
    );
  }

  return (
    <tr style={{ borderTop: `1px solid ${COR.borda}` }}>
      <td style={{ padding: "0.3rem", fontSize: "0.8rem", color: COR.texto }}>{fornecedor.nome}</td>
      <td style={{ padding: "0.3rem" }}><input style={{ ...inputStyle, width: "90px", textAlign: "right" }} type="number" step="0.01" value={valor} onChange={(e) => setValor(e.target.value)} onBlur={salvar} /></td>
      <td style={{ padding: "0.3rem" }}><input style={{ ...inputStyle, width: "110px" }} value={condicao} onChange={(e) => setCondicao(e.target.value)} onBlur={salvar} /></td>
      <td style={{ padding: "0.3rem" }}><input style={{ ...inputStyle, width: "70px" }} type="number" value={prazo} onChange={(e) => setPrazo(e.target.value)} onBlur={salvar} /></td>
      <td style={{ padding: "0.3rem" }}><input type="checkbox" checked={recusado} onChange={(e) => { setRecusado(e.target.checked); setTimeout(salvar, 0); }} /></td>
    </tr>
  );
}

function ModalAtribuirPrecoDeCotacao({
  item, respostas, fornecedores, onFechar, onSalvo,
}: { item: CotacaoCowDataItem; respostas: any[]; fornecedores: { id: number; nome: string }[]; onFechar: () => void; onSalvo: () => void }) {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const validas = respostas.filter((r) => !r.recusado && r.valor != null);
  const [ehMedia, setEhMedia] = useState(false);
  const [vencedorId, setVencedorId] = useState<number | "">(validas[0]?.fornecedor_cowdata_id ?? "");
  const [participantesSelecionados, setParticipantesSelecionados] = useState<number[]>(validas.map((r) => r.fornecedor_cowdata_id));
  const [unidade, setUnidade] = useState("");
  const [regiao, setRegiao] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState<"publicar" | "rascunho" | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const nomeFornecedor = (id: number) => fornecedores.find((f) => f.id === id)?.nome || `#${id}`;
  const valorVencedor = validas.find((r) => r.fornecedor_cowdata_id === vencedorId)?.valor;
  const valorMedia = useMemo(() => {
    const selecionadas = validas.filter((r) => participantesSelecionados.includes(r.fornecedor_cowdata_id));
    if (!selecionadas.length) return null;
    return selecionadas.reduce((acc, r) => acc + r.valor, 0) / selecionadas.length;
  }, [participantesSelecionados, validas]);

  async function salvar(publicar: boolean) {
    const valor = ehMedia ? valorMedia : valorVencedor;
    if (valor == null) { setErro("Escolha ao menos uma resposta válida"); return; }
    if (ehMedia && participantesSelecionados.length < 2) { setErro("Média exige ao menos 2 fornecedores"); return; }
    setSalvando(publicar ? "publicar" : "rascunho"); setErro(null);
    try {
      await atribuirPrecoProdutoPadrao(item.produto_padrao_id as number, {
        valor, unidade: unidade || null, regiao: regiao || null, origem: "cotacao", cotacao_cowdata_item_id: item.id,
        fornecedor_escolhido_id: ehMedia ? null : (vencedorId || null), eh_media: ehMedia,
        participantes_media: ehMedia
          ? validas.filter((r) => participantesSelecionados.includes(r.fornecedor_cowdata_id))
              .map((r) => ({ fornecedor_cowdata_id: r.fornecedor_cowdata_id, valor_informado: r.valor }))
          : [],
        observacao: observacao || null, publicar,
      });
      onSalvo();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(null); }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 110 }} onClick={onFechar}>
      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1.4rem", width: "min(560px, 92vw)", maxHeight: "88vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 style={{ color: COR.texto, fontWeight: 700 }}>Atribuir preço — {item.rotulo}</h3>
          <button style={btnGhost} onClick={onFechar}><X size={14} /></button>
        </div>
        {validas.length === 0 ? (
          <p style={{ fontSize: "0.82rem", color: COR.mudo }}>Nenhuma resposta válida registrada para este item ainda.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto }}>
              <input type="checkbox" checked={ehMedia} onChange={(e) => setEhMedia(e.target.checked)} /> Usar a média entre fornecedores
            </label>
            {!ehMedia ? (
              <div>
                <label style={labelStyle}>Fornecedor vencedor</label>
                {validas.map((r) => (
                  <label key={r.fornecedor_cowdata_id} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto, marginBottom: "0.3rem" }}>
                    <input type="radio" checked={vencedorId === r.fornecedor_cowdata_id} onChange={() => setVencedorId(r.fornecedor_cowdata_id)} />
                    {nomeFornecedor(r.fornecedor_cowdata_id)} — {r.valor}
                  </label>
                ))}
              </div>
            ) : (
              <div>
                <label style={labelStyle}>Participantes da média</label>
                {validas.map((r) => (
                  <label key={r.fornecedor_cowdata_id} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto, marginBottom: "0.3rem" }}>
                    <input type="checkbox" checked={participantesSelecionados.includes(r.fornecedor_cowdata_id)}
                      onChange={(e) => setParticipantesSelecionados(e.target.checked
                        ? [...participantesSelecionados, r.fornecedor_cowdata_id]
                        : participantesSelecionados.filter((id) => id !== r.fornecedor_cowdata_id))} />
                    {nomeFornecedor(r.fornecedor_cowdata_id)} — {r.valor}
                  </label>
                ))}
                {valorMedia != null && <p style={{ fontSize: "0.8rem", color: COR.texto, fontWeight: 700 }}>Média calculada: {valorMedia.toFixed(2)}</p>}
              </div>
            )}
            <div className="flex gap-2">
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Unidade</label>
                <input style={{ ...inputStyle, width: "100%" }} value={unidade} onChange={(e) => setUnidade(e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Região (opcional)</label>
                <input style={{ ...inputStyle, width: "100%" }} value={regiao} onChange={(e) => setRegiao(e.target.value)} />
              </div>
            </div>
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
        )}
      </div>
    </div>
  );
}
