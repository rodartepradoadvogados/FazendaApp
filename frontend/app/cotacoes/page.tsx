"use client";
import { useEffect, useMemo, useState } from "react";
import {
  FileSearch, Plus, Send, X, ChevronLeft, Trophy, PackageCheck, Ban, AlertTriangle, Mail, MessageCircle, Clock,
} from "lucide-react";
import {
  fetchCotacoes, fetchCotacao, criarCotacao, dispararCotacao, marcarVencedoresCotacao, gerarPedidosCotacao,
  cancelarCotacao, fetchFornecedoresSugeridos, fetchFornecedores, fetchEstoque, formatBRL,
  type CotacaoResumo, type CotacaoDetalhe, type CotacaoItemPayload, type CotacaoFornecedorPayload,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import NovoFornecedorRapido from "@/components/NovoFornecedorRapido";

// Mesma lista de fazenda.rules.categorias.CATEGORIAS_FORNECEDOR no backend
// (já duplicada em components/CadastroFornecedores.tsx — mesma convenção).
const CATEGORIAS_FORNECEDOR = [
  "Ração e insumos alimentares", "Sêmen e genética", "Medicamentos e produtos veterinários",
  "Equipamentos e manutenção", "Combustível e transporte", "Serviços veterinários/técnicos",
  "Energia e utilidades", "Embalagens e materiais", "Outros",
];

const STATUS_INFO: Record<string, { label: string; cor: string }> = {
  rascunho: { label: "Rascunho", cor: "var(--text-muted)" },
  enviada: { label: "Enviada", cor: "var(--amber)" },
  parcialmente_respondida: { label: "Parcialmente respondida", cor: "var(--amber)" },
  respondida: { label: "Respondida", cor: "var(--dourado-light)" },
  comparada: { label: "Comparada", cor: "var(--dourado-light)" },
  pedidos_gerados: { label: "Pedidos gerados", cor: "var(--green-light)" },
  expirada: { label: "Expirada", cor: "var(--red)" },
  cancelada: { label: "Cancelada", cor: "var(--text-muted)" },
};

const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };

function Badge({ status }: { status: string }) {
  const info = STATUS_INFO[status] || { label: status, cor: "var(--text-muted)" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 600,
      color: info.cor, border: `1px solid ${info.cor}`, borderRadius: "999px", padding: "0.15rem 0.55rem",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: info.cor }} />
      {info.label}
    </span>
  );
}

export default function CotacoesPage() {
  const [cotacoes, setCotacoes] = useState<CotacaoResumo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [abrindoNova, setAbrindoNova] = useState(false);
  const [detalheId, setDetalheId] = useState<number | null>(null);

  const recarregarLista = () => fetchCotacoes().then(setCotacoes).catch((e) => setErro(e.message));
  useEffect(() => { recarregarLista(); }, []);

  if (detalheId != null) {
    return <DetalheCotacao id={detalheId} onVoltar={() => { setDetalheId(null); recarregarLista(); }} />;
  }

  return (
    <div className="p-6 animate-in">
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><FileSearch size={22} style={{ color: "var(--dourado)" }} /> Cotações</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Peça preço a vários fornecedores de uma categoria, compare as respostas e gere os Pedidos com os vencedores.
            Compra avulsa/urgente e venda continuam em <a href="/pedidos" style={{ color: "var(--dourado-light)" }}>Pedido direto</a>, sem passar por cotação.
          </p>
        </div>
        <button className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={() => setAbrindoNova(true)}>
          <Plus size={14} /> Nova cotação
        </button>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      <div className="card">
        <div className="card-header mb-3">Cotações</div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Nº cotação</th><th>Categoria</th><th>Status</th>
                <th style={{ textAlign: "right" }}>Fornecedores</th><th style={{ textAlign: "right" }}>Respondidos</th>
                <th>Prazo</th><th>Criada em</th>
              </tr>
            </thead>
            <tbody>
              {(cotacoes ?? []).map((c) => (
                <tr key={c.id} className="row-clickable" style={{ cursor: "pointer" }} onClick={() => setDetalheId(c.id)}>
                  <td style={{ fontSize: "0.82rem", fontWeight: 600 }}>{c.numero_cotacao}</td>
                  <td style={{ fontSize: "0.8rem" }}>{c.categoria}</td>
                  <td><Badge status={c.status} /></td>
                  <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{c.total_fornecedores}</td>
                  <td style={{ textAlign: "right", fontSize: "0.8rem" }}>{c.total_respondidos}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{new Date(c.prazo_resposta).toLocaleString("pt-BR")}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{new Date(c.criado_em).toLocaleDateString("pt-BR")}</td>
                </tr>
              ))}
              {cotacoes && !cotacoes.length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhuma cotação ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {abrindoNova && (
        <Modal onClose={() => setAbrindoNova(false)} title="Nova cotação" width="900px">
          <FormNovaCotacao onSalvo={(id) => { setAbrindoNova(false); recarregarLista(); setDetalheId(id); }} onCancelar={() => setAbrindoNova(false)} />
        </Modal>
      )}
    </div>
  );
}

function FormNovaCotacao({ onSalvo, onCancelar }: { onSalvo: (id: number) => void; onCancelar: () => void }) {
  const [categoria, setCategoria] = useState(CATEGORIAS_FORNECEDOR[0]);
  const [modo, setModo] = useState<"completo" | "expresso">("completo");
  const amanha = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000);
  const [prazo, setPrazo] = useState(amanha.toISOString().slice(0, 16));
  const [observacao, setObservacao] = useState("");
  const [itens, setItens] = useState<CotacaoItemPayload[]>([{ produto: "", quantidade: 1, unidade: "" }]);
  const [produtosEstoque, setProdutosEstoque] = useState<EstoqueItemPicker[]>([]);
  const [fornecedoresCadastro, setFornecedoresCadastro] = useState<any[]>([]);
  const [sugeridosIds, setSugeridosIds] = useState<Set<number>>(new Set());
  const [selecionados, setSelecionados] = useState<Record<number, CotacaoFornecedorPayload>>({});
  const [abrirNovoFornecedor, setAbrirNovoFornecedor] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchEstoque().then((d: any) => setProdutosEstoque((d.itens || []).map((i: any) => ({
      nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
      estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
    })))).catch(() => {});
    fetchFornecedores().then((d: any[]) => setFornecedoresCadastro((d || []).filter((f) => f.tipo === "fornecedor" || f.tipo === "fabricante"))).catch(() => {});
  }, []);

  useEffect(() => {
    fetchFornecedoresSugeridos(categoria).then((sugeridos) => {
      const ids = new Set<number>(sugeridos.map((f: any) => f.id));
      setSugeridosIds(ids);
      setSelecionados((prev) => {
        const novo: Record<number, CotacaoFornecedorPayload> = {};
        ids.forEach((id) => { novo[id] = prev[id] || { fornecedor_id: id, canal: "email" }; });
        return novo;
      });
    }).catch(() => {});
  }, [categoria]);

  function alternarFornecedor(id: number) {
    setSelecionados((prev) => {
      const novo = { ...prev };
      if (novo[id]) delete novo[id]; else novo[id] = { fornecedor_id: id, canal: "email" };
      return novo;
    });
  }
  function mudarCanal(id: number, canal: CotacaoFornecedorPayload["canal"]) {
    setSelecionados((prev) => ({ ...prev, [id]: { ...prev[id], canal } }));
  }

  function atualizarItem(idx: number, patch: Partial<CotacaoItemPayload>) {
    setItens((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }
  function adicionarItem() { setItens((prev) => [...prev, { produto: "", quantidade: 1, unidade: "" }]); }
  function removerItem(idx: number) { setItens((prev) => prev.filter((_, i) => i !== idx)); }

  async function salvar() {
    const itensValidos = itens.filter((i) => i.produto.trim() && i.quantidade > 0);
    if (!itensValidos.length) { setErro("Informe ao menos um item com quantidade."); return; }
    const fornecedores = Object.values(selecionados);
    if (!fornecedores.length) { setErro("Selecione ao menos um fornecedor."); return; }
    setSalvando(true); setErro(null);
    try {
      const criado = await criarCotacao({
        categoria, modo, prazo_resposta: new Date(prazo).toISOString(), observacao: observacao || null,
        itens: itensValidos.map((i) => ({
          ...i,
          estoque_id: produtosEstoque.find((p) => p.nome === i.produto) ? undefined : i.estoque_id,
        })),
        fornecedores,
      });
      onSalvo(criado.id);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  }

  const todosFornecedoresPorId = useMemo(() => Object.fromEntries(fornecedoresCadastro.map((f) => [f.id, f])), [fornecedoresCadastro]);
  const idsExibidos = useMemo(() => {
    const s = new Set<number>(sugeridosIds);
    Object.keys(selecionados).forEach((id) => s.add(Number(id)));
    return Array.from(s);
  }, [sugeridosIds, selecionados]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div className="flex flex-wrap gap-3">
        <div><label style={labelStyle}>Categoria</label>
          <select style={inputStyle} value={categoria} onChange={(e) => setCategoria(e.target.value)}>
            {CATEGORIAS_FORNECEDOR.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></div>
        <div><label style={labelStyle}>Modo</label>
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}>
            <option value="completo">Completo — comparar vários fornecedores</option>
            <option value="expresso">Expresso — decisão rápida</option>
          </select></div>
        <div><label style={labelStyle}>Prazo para resposta</label>
          <input type="datetime-local" style={inputStyle} value={prazo} onChange={(e) => setPrazo(e.target.value)} /></div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label style={{ ...labelStyle, margin: 0 }}>Itens desta cotação</label>
          <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem" }} onClick={adicionarItem}><Plus size={12} /> Item</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {itens.map((item, idx) => (
            <div key={idx} className="flex flex-wrap gap-2 items-end">
              <div style={{ flex: 1, minWidth: "12rem" }}>
                <label style={labelStyle}>Produto</label>
                <EstoquePicker itens={produtosEstoque} value={item.produto} todasFinalidades incluirNaoEstocaveis
                  placeholder="Selecionar produto do Estoque, ou digitar um novo…"
                  onChange={(nome) => atualizarItem(idx, { produto: nome })} />
              </div>
              <div><label style={labelStyle}>Quantidade</label>
                <input type="number" step="0.01" style={{ ...inputStyle, width: "6rem" }} value={item.quantidade}
                  onChange={(e) => atualizarItem(idx, { quantidade: Number(e.target.value) })} /></div>
              <div><label style={labelStyle}>Unidade</label>
                <input style={{ ...inputStyle, width: "8rem" }} value={item.unidade || ""} placeholder="ex.: saca 50kg"
                  onChange={(e) => atualizarItem(idx, { unidade: e.target.value })} /></div>
              <button title="Remover" onClick={() => removerItem(idx)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)" }}><X size={15} /></button>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label style={{ ...labelStyle, margin: 0 }}>
            Fornecedores sugeridos pela categoria "{categoria}"
          </label>
          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setAbrirNovoFornecedor(true)}>+ Novo fornecedor</button>
        </div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th></th><th>Fornecedor</th><th>Canal</th><th>Motivo</th></tr></thead>
            <tbody>
              {idsExibidos.map((id) => {
                const f = todosFornecedoresPorId[id];
                const marcado = !!selecionados[id];
                return (
                  <tr key={id}>
                    <td><input type="checkbox" checked={marcado} onChange={() => alternarFornecedor(id)} /></td>
                    <td style={{ fontSize: "0.82rem" }}>{f?.nome ?? `#${id}`}</td>
                    <td>
                      <select style={inputStyle} disabled={!marcado} value={selecionados[id]?.canal || "email"}
                        onChange={(e) => mudarCanal(id, e.target.value as any)}>
                        <option value="email">E-mail</option><option value="whatsapp">WhatsApp</option><option value="ambos">Ambos</option>
                      </select>
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sugeridosIds.has(id) ? "Categoria vinculada" : "Adicionado manualmente"}
                    </td>
                  </tr>
                );
              })}
              {!idsExibidos.length && (
                <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem", fontSize: "0.8rem" }}>
                  Nenhum fornecedor vinculado a esta categoria ainda — cadastre em Configurações &gt; Cadastro &gt; Estoque &gt; Fornecedores, ou adicione um novo acima.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div><label style={labelStyle}>Observação (opcional)</label>
        <input style={{ ...inputStyle, width: "100%" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>

      {erro && <div className="alert-critico"><span>{erro}</span></div>}
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancelar}>Cancelar</button>
        <button className="btn-primary" disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar rascunho"}</button>
      </div>

      {abrirNovoFornecedor && (
        <Modal title="Novo fornecedor" onClose={() => setAbrirNovoFornecedor(false)} width="480px" zIndex={95}>
          <NovoFornecedorRapido tipoSugerido="despesa"
            onCriado={(f: any) => {
              fetchFornecedores().then((d: any[]) => setFornecedoresCadastro((d || []).filter((x) => x.tipo === "fornecedor" || x.tipo === "fabricante")));
              if (f?.id) setSelecionados((prev) => ({ ...prev, [f.id]: { fornecedor_id: f.id, canal: "email" } }));
              setAbrirNovoFornecedor(false);
            }}
            onCancelar={() => setAbrirNovoFornecedor(false)} />
        </Modal>
      )}
    </div>
  );
}

const STATUS_ENVIO_LABEL: Record<string, string> = {
  pendente: "Pendente", enviado: "Enviado", falha_envio: "Falha no envio",
  visualizado: "Visualizado", respondido: "Respondido", recusado: "Recusou",
};

function DetalheCotacao({ id, onVoltar }: { id: number; onVoltar: () => void }) {
  const [detalhe, setDetalhe] = useState<CotacaoDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [disparando, setDisparando] = useState(false);
  const [vencedores, setVencedores] = useState<Record<number, number>>({});
  const [salvandoVencedores, setSalvandoVencedores] = useState(false);
  const [gerando, setGerando] = useState(false);
  const [pedidosGerados, setPedidosGerados] = useState<{ id: number; numero_pedido: string }[] | null>(null);

  const carregar = () => fetchCotacao(id).then((d) => {
    setDetalhe(d);
    const iniciais: Record<number, number> = {};
    d.respostas.filter((r) => r.vencedor).forEach((r) => { iniciais[r.cotacao_item_id] = r.cotacao_fornecedor_id; });
    setVencedores(iniciais);
  }).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!detalhe) return <div className="p-6 animate-in">{erro ? <div className="alert-critico"><span>{erro}</span></div> : "Carregando…"}</div>;

  async function disparar() {
    setDisparando(true); setErro(null);
    try {
      const r = await dispararCotacao(id);
      if (r.erros.length) setErro(`Enviado, mas com falhas: ${r.erros.join(" · ")}`);
      await carregar();
    } catch (e: any) { setErro(e.message); } finally { setDisparando(false); }
  }

  async function salvarVencedores() {
    const escolhas = Object.entries(vencedores).map(([itemId, fornId]) => ({ cotacao_item_id: Number(itemId), cotacao_fornecedor_id: fornId }));
    if (!escolhas.length) { setErro("Escolha ao menos um vencedor."); return; }
    setSalvandoVencedores(true); setErro(null);
    try {
      await marcarVencedoresCotacao(id, escolhas);
      await carregar();
    } catch (e: any) { setErro(e.message); } finally { setSalvandoVencedores(false); }
  }

  async function gerarPedidos() {
    setGerando(true); setErro(null);
    try {
      const r = await gerarPedidosCotacao(id);
      setPedidosGerados(r.pedidos);
      await carregar();
    } catch (e: any) { setErro(e.message); } finally { setGerando(false); }
  }

  async function cancelar() {
    if (!confirm(`Cancelar a cotação ${detalhe!.numero_cotacao}?`)) return;
    try { await cancelarCotacao(id); await carregar(); } catch (e: any) { setErro(e.message); }
  }

  // Vencedores únicos entre os itens exibidos — mesmo atalho "tudo com um
  // fornecedor só" do protótipo, sem forçar: item a item continua possível.
  const fornecedoresComResposta = detalhe.fornecedores.filter((f) => f.status_envio === "respondido" || f.status_envio === "recusado");
  function aplicarFornecedorATodos(fornecedorId: number) {
    const novo: Record<number, number> = {};
    detalhe!.itens.forEach((item) => {
      const temResposta = detalhe!.respostas.some((r) => r.cotacao_item_id === item.id && r.cotacao_fornecedor_id === fornecedorId && !r.recusado);
      if (temResposta) novo[item.id] = fornecedorId;
    });
    setVencedores((prev) => ({ ...prev, ...novo }));
  }

  return (
    <div className="p-6 animate-in">
      <button className="btn-ghost mb-3" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem" }} onClick={onVoltar}>
        <ChevronLeft size={14} /> Voltar às cotações
      </button>

      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold">{detalhe.numero_cotacao} — {detalhe.categoria}</h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Badge status={detalhe.status} /> <Clock size={13} /> prazo {new Date(detalhe.prazo_resposta).toLocaleString("pt-BR")}
          </p>
        </div>
        <div className="flex gap-2">
          {(detalhe.status === "rascunho" || detalhe.status === "enviada") && (
            <button className="btn-primary" disabled={disparando} style={{ display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={disparar}>
              <Send size={14} /> {disparando ? "Disparando…" : "Disparar cotação"}
            </button>
          )}
          {detalhe.status !== "cancelada" && detalhe.status !== "pedidos_gerados" && (
            <button className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: "var(--red)" }} onClick={cancelar}>
              <Ban size={14} /> Cancelar
            </button>
          )}
        </div>
      </div>

      {erro && <div className="alert-critico mb-4"><span>{erro}</span></div>}

      <div className="card mb-4">
        <div className="card-header mb-3">Itens</div>
        <table className="fazenda-table">
          <thead><tr><th>Produto</th><th style={{ textAlign: "right" }}>Quantidade</th><th>Unidade</th></tr></thead>
          <tbody>
            {detalhe.itens.map((i) => (
              <tr key={i.id}><td style={{ fontSize: "0.82rem" }}>{i.produto}</td><td style={{ textAlign: "right", fontSize: "0.82rem" }}>{i.quantidade}</td><td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{i.unidade || "—"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3">Status por fornecedor</div>
        <table className="fazenda-table">
          <thead><tr><th>Fornecedor</th><th>Canal</th><th>Status</th><th>Última atualização</th></tr></thead>
          <tbody>
            {detalhe.fornecedores.map((f) => (
              <tr key={f.id}>
                <td style={{ fontSize: "0.82rem" }}>{f.fornecedor_nome ?? `#${f.fornecedor_id}`}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                  {(f.canal === "email" || f.canal === "ambos") && <Mail size={12} />}
                  {(f.canal === "whatsapp" || f.canal === "ambos") && <MessageCircle size={12} />}
                </td>
                <td style={{ fontSize: "0.8rem" }}>{STATUS_ENVIO_LABEL[f.status_envio] || f.status_envio}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  {f.respondido_em ? new Date(f.respondido_em).toLocaleString("pt-BR")
                    : f.visualizado_em ? new Date(f.visualizado_em).toLocaleString("pt-BR")
                    : f.enviado_em ? new Date(f.enviado_em).toLocaleString("pt-BR") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detalhe.respostas.length > 0 && detalhe.status !== "pedidos_gerados" && (
        <div className="card mb-4">
          <div className="card-header mb-3">Comparação — escolha o vencedor de cada item</div>
          {fornecedoresComResposta.length > 1 && (
            <div style={{ marginBottom: "0.9rem", display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Atalho:</span>
              {fornecedoresComResposta.map((f) => (
                <button key={f.id} className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => aplicarFornecedorATodos(f.fornecedor_id)}>
                  Tudo com {f.fornecedor_nome}
                </button>
              ))}
            </div>
          )}
          {detalhe.itens.map((item) => {
            const respostasDoItem = detalhe.respostas.filter((r) => r.cotacao_item_id === item.id);
            const melhorPreco = Math.min(...respostasDoItem.filter((r) => !r.recusado && r.preco_unitario != null).map((r) => r.preco_unitario as number));
            return (
              <div key={item.id} style={{ marginBottom: "1.1rem" }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.4rem" }}>{item.produto} <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.78rem" }}>{item.quantidade} {item.unidade}</span></div>
                <table className="fazenda-table">
                  <thead><tr><th></th><th>Fornecedor</th><th style={{ textAlign: "right" }}>Preço/un.</th><th>Frete</th><th>Prazo</th><th>Condição</th></tr></thead>
                  <tbody>
                    {respostasDoItem.map((r) => {
                      const cf = detalhe.fornecedores.find((f) => f.id === r.cotacao_fornecedor_id);
                      if (r.recusado) {
                        return (
                          <tr key={r.id} style={{ opacity: 0.55 }}>
                            <td></td><td style={{ fontSize: "0.8rem" }}>{cf?.fornecedor_nome}</td>
                            <td colSpan={4} style={{ fontSize: "0.78rem", color: "var(--red)" }}>Recusou este item</td>
                          </tr>
                        );
                      }
                      const escolhido = vencedores[item.id] === r.cotacao_fornecedor_id;
                      const melhor = r.preco_unitario === melhorPreco;
                      return (
                        <tr key={r.id} className="row-clickable" style={{ cursor: "pointer" }} onClick={() => setVencedores((prev) => ({ ...prev, [item.id]: r.cotacao_fornecedor_id }))}>
                          <td><input type="radio" checked={escolhido} readOnly /></td>
                          <td style={{ fontSize: "0.82rem", fontWeight: escolhido ? 700 : 400 }}>{cf?.fornecedor_nome}</td>
                          <td style={{ textAlign: "right", fontSize: "0.82rem", color: melhor ? "var(--green-light)" : undefined, fontWeight: melhor ? 700 : 400 }}>
                            {r.preco_unitario != null ? formatBRL(r.preco_unitario) : "—"}
                          </td>
                          <td style={{ fontSize: "0.78rem" }}>{r.frete_incluso ? "Incluso" : (r.valor_frete ? `+ ${formatBRL(r.valor_frete)}` : "—")}</td>
                          <td style={{ fontSize: "0.78rem" }}>{r.prazo_entrega_dias != null ? `${r.prazo_entrega_dias} dias` : "—"}</td>
                          <td style={{ fontSize: "0.78rem" }}>{r.condicao_pagamento || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })}
          <div className="flex gap-2 justify-end" style={{ marginTop: "0.8rem" }}>
            {detalhe.status !== "comparada" && (
              <button className="btn-secondary" disabled={salvandoVencedores} onClick={salvarVencedores}>
                {salvandoVencedores ? "Salvando…" : "Marcar vencedores"}
              </button>
            )}
            {detalhe.status === "comparada" && (
              <button className="btn-primary" disabled={gerando} style={{ display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={gerarPedidos}>
                <Trophy size={14} /> {gerando ? "Gerando…" : "Gerar pedidos com os vencedores"}
              </button>
            )}
          </div>
        </div>
      )}

      {(pedidosGerados || detalhe.status === "pedidos_gerados") && (
        <div className="card" style={{ background: "var(--surface-2)" }}>
          <div className="card-header mb-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <PackageCheck size={16} style={{ color: "var(--green-light)" }} /> Pedidos gerados
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
            A partir daqui, cada pedido segue o ciclo normal — confirmação do fornecedor, entrega física, lançamento em Financeiro. Acompanhe em{" "}
            <a href="/pedidos" style={{ color: "var(--dourado-light)" }}>Pedidos</a>.
          </p>
        </div>
      )}
    </div>
  );
}
