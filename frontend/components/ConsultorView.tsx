"use client";
import { useEffect, useState } from "react";
import {
  Briefcase, Building2, Plus, Trash2, Upload, Calculator, ShieldCheck, AlertTriangle, Check, ChevronDown, ChevronRight,
} from "lucide-react";
import {
  fetchPlanosConsultorCatalogo, solicitarPlanoConsultor, fetchMeuContratoConsultor,
  fetchFazendasGerenciadas, criarFazendaGerenciada, excluirFazendaGerenciada,
  importarPlanilhaGerenciada, fetchIndicadoresGerenciados, excluirRegistroImportado,
  calcularSimulacaoConsultor,
  type PlanoConsultorNome, type PlanoConsultorCatalogo, type ContratoConsultor,
  type FazendaGerenciada, type CategoriaImportacao, type RegistroImportado, type SimulacaoIn, type SimulacaoOut,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";

const inp: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem" };
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

const NOME_CATEGORIA: Record<CategoriaImportacao, string> = {
  rebanho: "Rebanho", reprodutivo: "Reprodutivo", produtivo: "Produtivo", sanitario: "Sanitário",
  financeiro: "Financeiro", estoque: "Estoque", alimentacao: "Alimentação", agricultura: "Agricultura/Plantio",
};
const CATEGORIAS = Object.keys(NOME_CATEGORIA) as CategoriaImportacao[];

function StatusBadge({ status }: { status: ContratoConsultor["status"] }) {
  const cfg = {
    ativo: { cor: "var(--green-light)", label: "Ativo" },
    aguardando_aprovacao: { cor: "var(--dourado)", label: "Aguardando aprovação" },
    suspenso: { cor: "var(--red)", label: "Suspenso" },
  }[status || "aguardando_aprovacao"] || { cor: "var(--text-muted)", label: "Sem assinatura" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", fontWeight: 700, color: cfg.cor, border: `1px solid ${cfg.cor}`, borderRadius: "999px", padding: "0.2rem 0.7rem" }}>
      {cfg.label}
    </span>
  );
}

// Rascunho do modo Simulação — guardado só na sessão do navegador (nunca
// enviado para persistência real): fecha a aba/navegador e some, exatamente
// como pedido ("fica salva durante a sessão").
const CHAVE_SESSAO_SIMULACAO = "consultor_simulacao_rascunho";

function ContratoConsultorPainel({ contrato, catalogo, onSolicitado }: {
  contrato: ContratoConsultor; catalogo: Record<PlanoConsultorNome, PlanoConsultorCatalogo> | null; onSolicitado: () => void;
}) {
  const [solicitando, setSolicitando] = useState<PlanoConsultorNome | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function solicitar(plano: PlanoConsultorNome) {
    setSolicitando(plano); setErro(null);
    try { await solicitarPlanoConsultor(plano); onSolicitado(); }
    catch (e: any) { setErro(e.message); } finally { setSolicitando(null); }
  }

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center justify-between">
        <span>Assinatura de consultor</span>
        <StatusBadge status={contrato.status} />
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "1rem" }}>
        {contrato.status === "aguardando_aprovacao"
          ? "Plano solicitado — aguardando aprovação do proprietário para liberar fazendas gerenciadas e importação."
          : contrato.status === "suspenso"
          ? "Sua assinatura foi suspensa. Solicite novamente ou fale com o proprietário."
          : "Escolha um plano para começar a acompanhar fazendas por importação de planilha e usar o modo Simulação."}
      </p>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
        {catalogo && (Object.entries(catalogo) as [PlanoConsultorNome, PlanoConsultorCatalogo][]).map(([chave, p]) => (
          <div key={chave} style={{ border: "1px solid " + (contrato.plano === chave ? "var(--dourado)" : "var(--border)"), borderRadius: "8px", padding: "0.8rem 1rem", flex: "1 1 180px", minWidth: "180px" }}>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{p.nome}</div>
            <div style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.6rem" }}>R$ {p.preco.toFixed(2)}/mês</div>
            <button onClick={() => solicitar(chave)} disabled={solicitando === chave || contrato.plano === chave && contrato.status !== "suspenso"}
              className="btn-primary" style={{ fontSize: "0.76rem", padding: "0.35rem 0.7rem" }}>
              {solicitando === chave ? "Solicitando…" : contrato.plano === chave && contrato.status === "aguardando_aprovacao" ? "Solicitado" : "Solicitar"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function FazendasGerenciadasPainel() {
  const [fazendas, setFazendas] = useState<FazendaGerenciada[] | null>(null);
  const [selecionada, setSelecionada] = useState<number | null>(null);
  const [registros, setRegistros] = useState<RegistroImportado[] | null>(null);
  const [filtroCategoria, setFiltroCategoria] = useState<CategoriaImportacao | "">("");
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [abrirNova, setAbrirNova] = useState(false);
  const [nome, setNome] = useState("");
  const [produtor, setProdutor] = useState("");
  const [cidade, setCidade] = useState("");
  const [uf, setUf] = useState("");
  const [criando, setCriando] = useState(false);

  const [categoriaImportar, setCategoriaImportar] = useState<CategoriaImportacao>("rebanho");
  const [importando, setImportando] = useState(false);
  const [expandidos, setExpandidos] = useState<Record<number, boolean>>({});

  function carregarFazendas() {
    fetchFazendasGerenciadas().then(setFazendas).catch((e) => setErro(e.message));
  }
  useEffect(carregarFazendas, []);

  function carregarRegistros(fazendaId: number, categoria?: CategoriaImportacao) {
    fetchIndicadoresGerenciados(fazendaId, categoria || undefined).then(setRegistros).catch((e) => setErro(e.message));
  }

  function selecionar(id: number) {
    setSelecionada(id); setErro(null); setMsg(null); setFiltroCategoria("");
    carregarRegistros(id);
  }

  async function criar() {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setCriando(true); setErro(null);
    try {
      const f = await criarFazendaGerenciada({
        nome: nome.trim(), produtor: produtor.trim() || undefined, cidade: cidade.trim() || undefined, uf: uf.trim() || undefined,
      });
      setAbrirNova(false); setNome(""); setProdutor(""); setCidade(""); setUf("");
      carregarFazendas();
      selecionar(f.id);
    } catch (e: any) { setErro(e.message); } finally { setCriando(false); }
  }

  async function excluir(id: number) {
    setErro(null);
    try {
      await excluirFazendaGerenciada(id);
      if (selecionada === id) { setSelecionada(null); setRegistros(null); }
      carregarFazendas();
    } catch (e: any) { setErro(e.message); }
  }

  async function importar(file: File) {
    if (selecionada == null) return;
    setImportando(true); setErro(null); setMsg(null);
    try {
      const r = await importarPlanilhaGerenciada(selecionada, categoriaImportar, file);
      setMsg(`${r.criados} registro(s) importado(s) em ${NOME_CATEGORIA[categoriaImportar]}.`);
      carregarRegistros(selecionada, filtroCategoria || undefined);
    } catch (e: any) { setErro(e.message); } finally { setImportando(false); }
  }

  async function excluirRegistro(registroId: number) {
    if (selecionada == null) return;
    try {
      await excluirRegistroImportado(selecionada, registroId);
      carregarRegistros(selecionada, filtroCategoria || undefined);
    } catch (e: any) { setErro(e.message); }
  }

  return (
    <div className="animate-in">
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {msg && (
        <div className="mb-3 flex items-center gap-2" style={{ background: "rgba(45,138,86,0.15)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 1rem", color: "var(--green-light)", fontSize: "0.82rem" }}>
          <Check size={15} /><span>{msg}</span>
        </div>
      )}
      <div className="flex gap-4" style={{ flexWrap: "wrap", alignItems: "flex-start" }}>
        <div className="card" style={{ minWidth: "220px", flex: "0 0 260px" }}>
          <div className="card-header mb-2 flex items-center justify-between">
            <span>Fazendas gerenciadas</span>
            <button onClick={() => setAbrirNova((v) => !v)} title="Cadastrar fazenda gerenciada" style={{ background: "transparent", border: "none", color: "var(--dourado-light)", cursor: "pointer" }}>
              <Plus size={16} />
            </button>
          </div>
          {abrirNova && (
            <div className="mb-3" style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <input placeholder="Nome da fazenda" style={inp} value={nome} onChange={(e) => setNome(e.target.value)} />
              <input placeholder="Produtor (opcional)" style={inp} value={produtor} onChange={(e) => setProdutor(e.target.value)} />
              <input placeholder="Cidade (opcional)" style={inp} value={cidade} onChange={(e) => setCidade(e.target.value)} />
              <input placeholder="UF (opcional)" style={inp} value={uf} onChange={(e) => setUf(e.target.value)} />
              <button onClick={criar} disabled={criando} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.35rem 0.7rem" }}>
                {criando ? "Cadastrando…" : "Cadastrar"}
              </button>
            </div>
          )}
          {!fazendas ? <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p> : fazendas.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhuma fazenda cadastrada ainda.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {fazendas.map((f) => (
                <div key={f.id} style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
                  <button onClick={() => selecionar(f.id)}
                    style={{ flex: 1, textAlign: "left", padding: "0.5rem 0.7rem", borderRadius: "6px", cursor: "pointer",
                      border: "1px solid " + (selecionada === f.id ? "var(--dourado)" : "var(--border)"),
                      background: selecionada === f.id ? "rgba(212,160,23,0.12)" : "transparent", color: "var(--text)", fontSize: "0.83rem" }}>
                    <div style={{ fontWeight: 600 }}>{f.nome}</div>
                    {(f.produtor || f.cidade || f.uf) && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                        {[f.produtor, [f.cidade, f.uf].filter(Boolean).join("/")].filter(Boolean).join(" — ")}
                      </div>
                    )}
                  </button>
                  <button onClick={() => excluir(f.id)} title="Excluir" style={{ background: "transparent", border: "none", color: "var(--red)", cursor: "pointer" }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {selecionada != null && (
          <div className="card" style={{ flex: "1 1 420px", minWidth: "360px" }}>
            <div className="card-header mb-3">Importar planilha</div>
            <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
              <select style={{ ...inp, width: "auto" }} value={categoriaImportar} onChange={(e) => setCategoriaImportar(e.target.value as CategoriaImportacao)}>
                {CATEGORIAS.map((c) => <option key={c} value={c}>{NOME_CATEGORIA[c]}</option>)}
              </select>
              <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: "1px solid var(--border)", cursor: "pointer", color: "var(--text-muted)" }}>
                <Upload size={13} /> {importando ? "Importando…" : "Escolher planilha (.xlsx/.csv)"}
                <input type="file" accept=".xlsx,.xlsm,.csv" style={{ display: "none" }} disabled={importando}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) importar(f); e.target.value = ""; }} />
              </label>
            </div>

            <div className="card-header mb-2 flex items-center justify-between">
              <span>Indicadores importados</span>
              <select style={{ ...inp, width: "auto" }} value={filtroCategoria}
                onChange={(e) => { const v = e.target.value as CategoriaImportacao | ""; setFiltroCategoria(v); carregarRegistros(selecionada, v || undefined); }}>
                <option value="">Todas as categorias</option>
                {CATEGORIAS.map((c) => <option key={c} value={c}>{NOME_CATEGORIA[c]}</option>)}
              </select>
            </div>
            {!registros ? <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p> : registros.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Nenhum registro importado ainda.</p>
            ) : (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                {registros.map((r) => {
                  const aberto = !!expandidos[r.id];
                  return (
                    <li key={r.id} style={{ border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem" }}>
                      <div className="flex items-center justify-between gap-2">
                        <button onClick={() => setExpandidos((s) => ({ ...s, [r.id]: !aberto }))}
                          style={{ background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem" }}>
                          {aberto ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          <strong>{NOME_CATEGORIA[r.categoria]}</strong>
                          {r.data_referencia && <span style={{ color: "var(--text-muted)" }}>— {r.data_referencia}</span>}
                          <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>({r.arquivo_origem})</span>
                        </button>
                        <button onClick={() => excluirRegistro(r.id)} title="Excluir registro" style={{ background: "transparent", border: "none", color: "var(--red)", cursor: "pointer" }}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                      {aberto && (
                        <div style={{ marginTop: "0.4rem", fontSize: "0.78rem", color: "var(--text-muted)", display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.15rem 0.6rem" }}>
                          {Object.entries(r.dados).map(([k, v]) => (
                            <div key={k} style={{ display: "contents" }}>
                              <span style={{ fontWeight: 600 }}>{k}</span><span>{v}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SimulacaoPainel() {
  const [form, setForm] = useState<SimulacaoIn>(() => {
    if (typeof window === "undefined") return { vacas_lactacao: 0, producao_media_litro_vaca_dia: 0, preco_litro: 0, custo_alimentar_vaca_dia: 0, outros_custos_mensais: 0 };
    try {
      const salvo = sessionStorage.getItem(CHAVE_SESSAO_SIMULACAO);
      if (salvo) return JSON.parse(salvo);
    } catch { /* ignore */ }
    return { vacas_lactacao: 0, producao_media_litro_vaca_dia: 0, preco_litro: 0, custo_alimentar_vaca_dia: 0, outros_custos_mensais: 0 };
  });
  const [resultado, setResultado] = useState<SimulacaoOut | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    try { sessionStorage.setItem(CHAVE_SESSAO_SIMULACAO, JSON.stringify(form)); } catch { /* ignore */ }
  }, [form]);

  function set<K extends keyof SimulacaoIn>(campo: K, valor: string) {
    setForm((s) => ({ ...s, [campo]: valor === "" ? (campo === "taxa_prenhez_pct" ? null : 0) : Number(valor) }));
  }

  async function calcular() {
    setCalculando(true); setErro(null);
    try { setResultado(await calcularSimulacaoConsultor(form)); }
    catch (e: any) { setErro(e.message); } finally { setCalculando(false); }
  }

  function limpar() {
    setForm({ vacas_lactacao: 0, producao_media_litro_vaca_dia: 0, preco_litro: 0, custo_alimentar_vaca_dia: 0, outros_custos_mensais: 0 });
    setResultado(null);
    try { sessionStorage.removeItem(CHAVE_SESSAO_SIMULACAO); } catch { /* ignore */ }
  }

  const CAMPOS: { campo: keyof SimulacaoIn; label: string; sufixo?: string; moeda?: boolean }[] = [
    { campo: "vacas_lactacao", label: "Vacas em lactação" },
    { campo: "producao_media_litro_vaca_dia", label: "Produção média (L/vaca/dia)" },
    { campo: "preco_litro", label: "Preço do litro (R$)", moeda: true },
    { campo: "custo_alimentar_vaca_dia", label: "Custo alimentar (R$/vaca/dia)", moeda: true },
    { campo: "outros_custos_mensais", label: "Outros custos mensais (R$)", moeda: true },
    { campo: "taxa_prenhez_pct", label: "Taxa de prenhez (%, opcional)" },
  ];

  return (
    <div className="animate-in">
      <div className="card" style={{ maxWidth: "640px" }}>
        <div className="card-header mb-2 flex items-center gap-2"><Calculator size={16} style={{ color: "var(--dourado)" }} /> Simulação</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "1rem" }}>
          Projeto fictício para aulas, estudos e projeção de resultados — nada aqui é salvo no sistema. Os valores
          ficam só nesta aba, durante a sessão do navegador.
        </p>
        {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
        <div className="mb-4" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {CAMPOS.map(({ campo, label, moeda }) => (
            <label key={campo}>
              <span style={lbl}>{label}</span>
              {moeda ? (
                <CampoMoeda style={inp} value={typeof form[campo] === "number" ? (form[campo] as number) : 0}
                  onChange={(v) => setForm((s) => ({ ...s, [campo]: v }))} />
              ) : (
                <input type="number" min={0} step="0.01" style={inp}
                  value={form[campo] ?? ""} onChange={(e) => set(campo, e.target.value)} />
              )}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 mb-4">
          <button onClick={calcular} disabled={calculando} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
            {calculando ? "Calculando…" : "Calcular"}
          </button>
          <button onClick={limpar} style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
            Limpar
          </button>
        </div>

        {resultado && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem 1rem", fontSize: "0.85rem" }}>
            <span style={{ color: "var(--text-muted)" }}>Produção total/dia</span><span style={{ fontWeight: 700 }}>{resultado.producao_total_litro_dia.toLocaleString("pt-BR")} L</span>
            <span style={{ color: "var(--text-muted)" }}>Produção total/mês</span><span style={{ fontWeight: 700 }}>{resultado.producao_total_litro_mes.toLocaleString("pt-BR")} L</span>
            <span style={{ color: "var(--text-muted)" }}>Receita/mês</span><span style={{ fontWeight: 700, color: "var(--green-light)" }}>R$ {resultado.receita_mes.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
            <span style={{ color: "var(--text-muted)" }}>Custo alimentar/mês</span><span>R$ {resultado.custo_alimentar_mes.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
            <span style={{ color: "var(--text-muted)" }}>Custo total/mês</span><span>R$ {resultado.custo_total_mes.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
            <span style={{ color: "var(--text-muted)" }}>Margem/mês</span>
            <span style={{ fontWeight: 700, color: resultado.margem_mes >= 0 ? "var(--green-light)" : "var(--red)" }}>
              R$ {resultado.margem_mes.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
            </span>
            {resultado.custo_por_litro != null && (
              <><span style={{ color: "var(--text-muted)" }}>Custo por litro</span><span>R$ {resultado.custo_por_litro.toFixed(4)}</span></>
            )}
            {resultado.margem_por_litro != null && (
              <><span style={{ color: "var(--text-muted)" }}>Margem por litro</span><span>R$ {resultado.margem_por_litro.toFixed(4)}</span></>
            )}
            {resultado.taxa_prenhez_pct != null && (
              <><span style={{ color: "var(--text-muted)" }}>Taxa de prenhez informada</span><span>{resultado.taxa_prenhez_pct}%</span></>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ConsultorView() {
  const [contrato, setContrato] = useState<ContratoConsultor | null>(null);
  const [catalogo, setCatalogo] = useState<Record<PlanoConsultorNome, PlanoConsultorCatalogo> | null>(null);
  const [aba, setAba] = useState<"fazendas" | "simulacao">("fazendas");

  function carregar() {
    fetchMeuContratoConsultor().then(setContrato);
    fetchPlanosConsultorCatalogo().then(setCatalogo);
  }
  useEffect(carregar, []);

  if (!contrato || !catalogo) return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>;

  if (contrato.status !== "ativo") {
    return <ContratoConsultorPainel contrato={contrato} catalogo={catalogo} onSolicitado={carregar} />;
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setAba("fazendas")}
          className={aba === "fazendas" ? "btn-primary" : ""}
          style={aba !== "fazendas" ? { fontSize: "0.82rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: "1px solid var(--border)", background: "transparent", color: "var(--text)", cursor: "pointer" } : { fontSize: "0.82rem", padding: "0.4rem 0.9rem" }}>
          <Building2 size={14} style={{ marginRight: "0.35rem", display: "inline" }} /> Fazendas gerenciadas
        </button>
        <button onClick={() => setAba("simulacao")}
          className={aba === "simulacao" ? "btn-primary" : ""}
          style={aba !== "simulacao" ? { fontSize: "0.82rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: "1px solid var(--border)", background: "transparent", color: "var(--text)", cursor: "pointer" } : { fontSize: "0.82rem", padding: "0.4rem 0.9rem" }}>
          <Calculator size={14} style={{ marginRight: "0.35rem", display: "inline" }} /> Simulação
        </button>
        <span style={{ marginLeft: "auto" }}><StatusBadge status={contrato.status} /></span>
      </div>
      {aba === "fazendas" ? <FazendasGerenciadasPainel /> : <SimulacaoPainel />}
    </div>
  );
}
