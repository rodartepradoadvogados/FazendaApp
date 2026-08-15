"use client";
// Painel CowData > Cadastros globais — motivos, raças, grau de sangue,
// unidades/categorias de estoque e tipos/métodos de serviço reprodutivo
// aplicáveis a TODAS as fazendas-cliente de uma vez, ou só às selecionadas,
// sem precisar entrar em cada uma via modo suporte (ver backend/fazenda/
// api/routers/painel_cowdata_cadastros.py). Escrita é só aditiva — "remover"
// aqui desativa (nunca apaga de várias fazendas de uma vez); apagar de
// verdade continua sendo uma ação de uma fazenda por vez, na tela de
// Cadastro dela mesma.
import { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, Layers, Pencil, Plus, XCircle } from "lucide-react";
import {
  fetchCategoriasCadastroCowData, fetchFazendasCadastroCowData, fetchItensCadastroCowData, aplicarItemCadastroCowData,
  renomearItemCadastroCowData, desativarItemCadastroCowData, fetchMetodosCadastroCowData, aplicarMetodoCadastroCowData,
  type CategoriaCadastroCowData, type FazendaCadastroCowData, type ItemCadastroCowData, type ItemMetodoCadastroCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

type Categoria = { chave: string; label: string };

export default function CadastrosGlobaisCowData() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [categoriaAtiva, setCategoriaAtiva] = useState<string>("motivo_baixa");
  const [itens, setItens] = useState<ItemCadastroCowData[]>([]);
  const [metodos, setMetodos] = useState<ItemMetodoCadastroCowData[]>([]);
  const [tiposDisponiveis, setTiposDisponiveis] = useState<ItemCadastroCowData[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // Alvo: todas as fazendas ativas (padrão) ou uma seleção específica.
  const [alvoTodas, setAlvoTodas] = useState(true);
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [mostrarSeletor, setMostrarSeletor] = useState(false);

  // Formulário de novo/renomeado item.
  const [nome, setNome] = useState("");
  const [fracaoHolandes, setFracaoHolandes] = useState("");
  const [tipoServicoNome, setTipoServicoNome] = useState("");
  const [renomeando, setRenomeando] = useState<string | null>(null); // nome_atual em edição
  const [novoNome, setNovoNome] = useState("");

  const ehMetodo = categoriaAtiva === "metodo_servico";
  const ehGrauSangue = categoriaAtiva === "grau_sangue";

  useEffect(() => {
    fetchCategoriasCadastroCowData().then(setCategorias).catch((e) => setErro(e.message));
    fetchFazendasCadastroCowData().then(setFazendas).catch((e) => setErro(e.message));
  }, []);

  function carregar() {
    setCarregando(true);
    setErro(null);
    if (ehMetodo) {
      Promise.all([fetchMetodosCadastroCowData(), fetchItensCadastroCowData("tipo_servico")])
        .then(([m, t]) => { setMetodos(m.itens); setTiposDisponiveis(t.itens); })
        .catch((e) => setErro(e.message))
        .finally(() => setCarregando(false));
      return;
    }
    fetchItensCadastroCowData(categoriaAtiva as CategoriaCadastroCowData)
      .then((r) => setItens(r.itens))
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }
  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [categoriaAtiva]);

  function fazendaIdsAlvo(): number[] | null {
    if (alvoTodas) return null;
    return [...selecionadas];
  }
  function toggleSelecionada(id: number) {
    setSelecionadas((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function resumoResultado(r: { criados: number; atualizados: number; ja_existiam: number; total_fazendas: number; sem_tipo_correspondente?: number }): string {
    const partes: string[] = [];
    if (r.criados) partes.push(`${r.criados} criado(s)`);
    if (r.atualizados) partes.push(`${r.atualizados} atualizado(s)`);
    if (r.ja_existiam) partes.push(`${r.ja_existiam} já existia(m)`);
    if (r.sem_tipo_correspondente) partes.push(`${r.sem_tipo_correspondente} pulado(s) — tipo inexistente na fazenda`);
    return partes.length ? partes.join(" · ") : "Nada mudou.";
  }

  async function aplicar() {
    const nomeLimpo = nome.trim();
    if (!nomeLimpo) { setErro("Informe o nome."); return; }
    if (ehMetodo && !tipoServicoNome) { setErro("Escolha o tipo de serviço (ex.: IA, Cobertura)."); return; }
    setErro(null); setAviso(null);
    try {
      const fazenda_ids = fazendaIdsAlvo();
      const r = ehMetodo
        ? await aplicarMetodoCadastroCowData({ tipo_nome: tipoServicoNome, nome: nomeLimpo, fazenda_ids })
        : await aplicarItemCadastroCowData(categoriaAtiva as CategoriaCadastroCowData, {
            nome: nomeLimpo, fracao_holandes: ehGrauSangue && fracaoHolandes ? Number(fracaoHolandes) : null, fazenda_ids,
          });
      setAviso(resumoResultado(r));
      setNome(""); setFracaoHolandes("");
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  async function confirmarRenomear(nomeAtual: string, tipoDoItem?: string) {
    const alvo = novoNome.trim();
    if (!alvo) return;
    setErro(null); setAviso(null);
    try {
      const fazenda_ids = fazendaIdsAlvo();
      if (ehMetodo) {
        // Métodos não têm rota de renomear dedicada — recria com o novo nome
        // (mesma mecânica de "aplicar": upsert por nome no tipo informado).
        const r = await aplicarMetodoCadastroCowData({ tipo_nome: tipoDoItem || "", nome: alvo, fazenda_ids });
        setAviso(resumoResultado(r));
      } else {
        const r = await renomearItemCadastroCowData(categoriaAtiva as CategoriaCadastroCowData, { nome_atual: nomeAtual, novo_nome: alvo, fazenda_ids });
        setAviso(`${r.renomeados} renomeado(s)${r.nao_encontrados ? ` · ${r.nao_encontrados} não encontrado(s)` : ""}${r.pulados_por_conflito ? ` · ${r.pulados_por_conflito} pulado(s) por conflito` : ""}`);
      }
      setRenomeando(null); setNovoNome("");
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  async function desativar(nomeItem: string) {
    if (!confirm(`Desativar "${nomeItem}" nas fazendas selecionadas? Isso não apaga histórico já lançado, só tira da lista de escolha.`)) return;
    setErro(null); setAviso(null);
    try {
      const r = await desativarItemCadastroCowData(categoriaAtiva as CategoriaCadastroCowData, { nome: nomeItem, fazenda_ids: fazendaIdsAlvo() });
      setAviso(`${r.desativados} desativado(s).`);
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  const linhas = ehMetodo ? metodos : itens;

  return (
    <div style={{ padding: "1.4rem", maxWidth: "72rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.3rem" }}>
        <Layers size={20} color={COR.dourado} />
        <h1 style={{ fontSize: "1.15rem", fontWeight: 700, color: COR.texto, margin: 0 }}>Cadastros globais</h1>
      </div>
      <p style={{ color: COR.mudo, fontSize: "0.82rem", marginBottom: "1.1rem" }}>
        Motivos, raças, grau de sangue, unidades de estoque e tipos/métodos de serviço reprodutivo — aplique em todas as fazendas de uma vez, ou só nas selecionadas.
      </p>

      {/* Abas de categoria */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "1.1rem" }}>
        {categorias.map((c) => (
          <button key={c.chave} type="button" onClick={() => setCategoriaAtiva(c.chave)}
            style={{
              padding: "0.4rem 0.75rem", borderRadius: "999px", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer",
              border: `1px solid ${categoriaAtiva === c.chave ? COR.dourado : COR.borda}`,
              background: categoriaAtiva === c.chave ? "rgba(107,127,153,0.18)" : "transparent",
              color: categoriaAtiva === c.chave ? COR.texto : COR.mudo,
            }}>
            {c.label}
          </button>
        ))}
      </div>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", marginBottom: "0.8rem" }}>{erro}</p>}
      {aviso && <p style={{ color: COR.verde, fontSize: "0.82rem", marginBottom: "0.8rem" }}>{aviso}</p>}

      {/* Alvo (fazendas) */}
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-md)", padding: "0.9rem 1rem", marginBottom: "1rem" }}>
        <p style={{ ...labelStyle, marginBottom: "0.5rem" }}>Aplicar em</p>
        <div style={{ display: "flex", alignItems: "center", gap: "1.2rem", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto, cursor: "pointer" }}>
            <input type="radio" checked={alvoTodas} onChange={() => { setAlvoTodas(true); setMostrarSeletor(false); }} />
            Todas as fazendas ativas ({fazendas.length})
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", color: COR.texto, cursor: "pointer" }}>
            <input type="radio" checked={!alvoTodas} onChange={() => { setAlvoTodas(false); setMostrarSeletor(true); }} />
            Selecionar fazendas específicas {!alvoTodas && `(${selecionadas.size})`}
          </label>
          {!alvoTodas && (
            <button type="button" onClick={() => setMostrarSeletor((v) => !v)} style={{ ...btnGhost, display: "flex", alignItems: "center", gap: "0.25rem" }}>
              {mostrarSeletor ? "Esconder lista" : "Escolher fazendas"} <ChevronDown size={13} style={{ transform: mostrarSeletor ? "rotate(180deg)" : "none" }} />
            </button>
          )}
        </div>
        {!alvoTodas && mostrarSeletor && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.7rem", maxHeight: "9rem", overflowY: "auto" }}>
            {fazendas.map((f) => (
              <label key={f.id} style={{
                display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", padding: "0.3rem 0.55rem",
                borderRadius: "var(--r-sm)", border: `1px solid ${COR.borda}`, cursor: "pointer",
                background: selecionadas.has(f.id) ? "rgba(143,170,123,0.15)" : "transparent", color: COR.texto,
              }}>
                <input type="checkbox" checked={selecionadas.has(f.id)} onChange={() => toggleSelecionada(f.id)} />
                {f.nome}
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Novo item */}
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-md)", padding: "0.9rem 1rem", marginBottom: "1.1rem" }}>
        <p style={{ ...labelStyle, marginBottom: "0.6rem" }}>Adicionar / garantir nas fazendas-alvo</p>
        <div style={{ display: "flex", alignItems: "flex-end", gap: "0.6rem", flexWrap: "wrap" }}>
          {ehMetodo && (
            <div>
              <label style={labelStyle}>Tipo de serviço</label>
              <select value={tipoServicoNome} onChange={(e) => setTipoServicoNome(e.target.value)} style={{ ...inputStyle, minWidth: "10rem" }}>
                <option value="">Selecione…</option>
                {[...new Set(tiposDisponiveis.map((t) => t.nome))].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          )}
          <div style={{ flex: 1, minWidth: "12rem" }}>
            <label style={labelStyle}>Nome</label>
            <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Morte, Girolando, IATF…" style={{ ...inputStyle, width: "100%" }} />
          </div>
          {ehGrauSangue && (
            <div>
              <label style={labelStyle}>Fração Holandês (0 a 1, opcional)</label>
              <input value={fracaoHolandes} onChange={(e) => setFracaoHolandes(e.target.value)} placeholder="ex.: 0.5" style={{ ...inputStyle, width: "8rem" }} />
            </div>
          )}
          <button type="button" onClick={aplicar} style={btnPrimario}><Plus size={14} /> Aplicar</button>
        </div>
      </div>

      {/* Lista agregada */}
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ background: COR.bg }}>
              {ehMetodo && <th style={{ textAlign: "left", padding: "0.55rem 0.8rem", color: COR.mudo, fontWeight: 600 }}>Tipo</th>}
              <th style={{ textAlign: "left", padding: "0.55rem 0.8rem", color: COR.mudo, fontWeight: 600 }}>Nome</th>
              <th style={{ textAlign: "left", padding: "0.55rem 0.8rem", color: COR.mudo, fontWeight: 600 }}>Em quantas fazendas</th>
              <th style={{ textAlign: "right", padding: "0.55rem 0.8rem", color: COR.mudo, fontWeight: 600 }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {carregando && <tr><td colSpan={4} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
            {!carregando && linhas.length === 0 && <tr><td colSpan={4} style={{ padding: "1rem", color: COR.mudo }}>Nada cadastrado ainda nesta categoria.</td></tr>}
            {linhas.map((item) => {
              const completo = item.total_fazendas > 0 && item.em_fazendas.length === item.total_fazendas;
              return (
                <tr key={ehMetodo ? `${(item as ItemMetodoCadastroCowData).tipo_nome}::${item.nome}` : item.nome} style={{ borderTop: `1px solid ${COR.borda}` }}>
                  {ehMetodo && <td style={{ padding: "0.55rem 0.8rem", color: COR.mudo }}>{(item as ItemMetodoCadastroCowData).tipo_nome}</td>}
                  <td style={{ padding: "0.55rem 0.8rem", color: COR.texto, fontWeight: 600 }}>
                    {renomeando === item.nome ? (
                      <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                        <input autoFocus value={novoNome} onChange={(e) => setNovoNome(e.target.value)} style={{ ...inputStyle, width: "12rem" }} />
                        <button type="button" onClick={() => confirmarRenomear(item.nome, ehMetodo ? (item as ItemMetodoCadastroCowData).tipo_nome : undefined)} style={{ ...btnGhost, color: COR.verde }}>Salvar</button>
                        <button type="button" onClick={() => { setRenomeando(null); setNovoNome(""); }} style={btnGhost}>Cancelar</button>
                      </div>
                    ) : item.nome}
                  </td>
                  <td style={{ padding: "0.55rem 0.8rem" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: completo ? COR.verde : COR.mudo }}>
                      {completo ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                      {item.em_fazendas.length} de {item.total_fazendas}
                    </span>
                    {ehGrauSangue && (item as ItemCadastroCowData).fracao_holandes != null && (
                      <span style={{ marginLeft: "0.6rem", color: COR.mudo }}>· fração {(item as ItemCadastroCowData).fracao_holandes}</span>
                    )}
                  </td>
                  <td style={{ padding: "0.55rem 0.8rem", textAlign: "right" }}>
                    {renomeando !== item.nome && (
                      <>
                        <button type="button" onClick={() => { setRenomeando(item.nome); setNovoNome(item.nome); }} title="Renomear" style={{ ...btnGhost, marginRight: "0.4rem" }}>
                          <Pencil size={13} />
                        </button>
                        <button type="button" onClick={() => desativar(item.nome)} title="Desativar nas fazendas-alvo" style={{ ...btnGhost, color: COR.vermelho }}>
                          Desativar
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
