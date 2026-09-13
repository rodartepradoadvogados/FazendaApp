"use client";
// Cadastros globais do Painel CowData — versão mobile-nativa: grade de
// categorias → lista da categoria escolhida (mesma mecânica "aplicar em
// todas as fazendas ativas OU só nas selecionadas" do desktop, ver
// app/painel-cowdata/cadastros/page.tsx, fonte da verdade de toda a
// funcionalidade aqui reproduzida). Navegação categoria↔lista é estado local
// (não é rota do Next.js) — só o cabeçalho compartilhado volta pra
// /painel-cowdata via <Link>. Sem window.confirm() (ruim em app touch-first):
// "Desativar" vira um "Confirmar desativação" num segundo toque, com
// "Cancelar" como saída.
import { useEffect, useState } from "react";
import { CheckCircle2, ChevronRight, Pencil, Plus, Tag, XCircle } from "lucide-react";
import {
  fetchCategoriasCadastroCowData, fetchFazendasCadastroCowData, fetchItensCadastroCowData, aplicarItemCadastroCowData,
  renomearItemCadastroCowData, desativarItemCadastroCowData, fetchMetodosCadastroCowData, aplicarMetodoCadastroCowData,
  type CategoriaCadastroCowData, type FazendaCadastroCowData, type ItemCadastroCowData, type ItemMetodoCadastroCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import {
  CabecalhoMobilePainelCowData, CorpoMobilePainelCowData, SeletorAlvoFazendas, CampoMobile, BotaoMobile, inputEstilo,
} from "./ComumMobile";

type Categoria = { chave: string; label: string };
type ItemLinha = ItemCadastroCowData | ItemMetodoCadastroCowData;

function ehItemMetodo(item: ItemLinha, ehMetodo: boolean): item is ItemMetodoCadastroCowData {
  return ehMetodo;
}

export default function CadastrosMobile() {
  const estilos = usePainelCowDataEstilos();
  const { cor: COR } = estilos;

  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [fazendas, setFazendas] = useState<FazendaCadastroCowData[]>([]);
  const [categoriaAtiva, setCategoriaAtiva] = useState<string | null>(null); // null = grade de categorias
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
  const [renomeando, setRenomeando] = useState<string | null>(null); // chave do item em edição
  const [novoNome, setNovoNome] = useState("");
  const [confirmDesativar, setConfirmDesativar] = useState<string | null>(null); // chave do item aguardando 2º toque

  const ehMetodo = categoriaAtiva === "metodo_servico";
  const ehGrauSangue = categoriaAtiva === "grau_sangue";
  const categoriaLabel = categorias.find((c) => c.chave === categoriaAtiva)?.label ?? "";

  useEffect(() => {
    fetchCategoriasCadastroCowData().then(setCategorias).catch((e) => setErro(e.message));
    fetchFazendasCadastroCowData().then(setFazendas).catch((e) => setErro(e.message));
  }, []);

  function carregar() {
    if (!categoriaAtiva) return;
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

  function chaveItem(item: ItemLinha): string {
    return ehItemMetodo(item, ehMetodo) ? `${item.tipo_nome}::${item.nome}` : item.nome;
  }

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

  function abrirCategoria(chave: string) {
    setErro(null); setAviso(null);
    setNome(""); setFracaoHolandes(""); setTipoServicoNome("");
    setRenomeando(null); setNovoNome(""); setConfirmDesativar(null);
    setCategoriaAtiva(chave);
  }
  function voltarParaGrade() {
    setErro(null); setAviso(null);
    setRenomeando(null); setNovoNome(""); setConfirmDesativar(null);
    setCategoriaAtiva(null);
  }

  async function aplicar() {
    if (!categoriaAtiva) return;
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
    setErro(null); setAviso(null);
    try {
      const r = await desativarItemCadastroCowData(categoriaAtiva as CategoriaCadastroCowData, { nome: nomeItem, fazenda_ids: fazendaIdsAlvo() });
      setAviso(`${r.desativados} desativado(s).`);
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  const linhas: ItemLinha[] = ehMetodo ? metodos : itens;

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <CabecalhoMobilePainelCowData
        titulo={categoriaAtiva ? categoriaLabel : "Cadastros globais"}
        subtitulo={categoriaAtiva
          ? "Aplique em todas as fazendas de uma vez, ou só nas selecionadas."
          : "Motivos, raças, grau de sangue, unidades de estoque e tipos/métodos de serviço reprodutivo."}
        cor={COR}
      />
      <CorpoMobilePainelCowData>
        {!categoriaAtiva && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.7rem" }}>
            {categorias.length === 0 && !erro && <p style={{ color: COR.mudo, fontSize: "0.82rem" }}>Carregando…</p>}
            {categorias.map((c) => (
              <button key={c.chave} type="button" onClick={() => abrirCategoria(c.chave)} style={{
                display: "flex", flexDirection: "column", alignItems: "flex-start", justifyContent: "space-between", gap: "0.9rem",
                background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)",
                padding: "0.9rem", color: COR.texto, cursor: "pointer", textAlign: "left", minHeight: "5.2rem",
              }}>
                <Tag size={16} style={{ color: COR.doradoClaro, flexShrink: 0 }} />
                <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", width: "100%" }}>
                  <span style={{ flex: 1, fontSize: "0.8rem", fontWeight: 700, lineHeight: 1.25 }}>{c.label}</span>
                  <ChevronRight size={15} style={{ color: COR.mudo, flexShrink: 0 }} />
                </span>
              </button>
            ))}
          </div>
        )}

        {categoriaAtiva && (
          <>
            <button type="button" onClick={voltarParaGrade} style={{
              display: "flex", alignItems: "center", gap: "0.35rem", background: "none", border: "none",
              color: COR.mudo, fontSize: "0.78rem", cursor: "pointer", padding: 0, alignSelf: "flex-start",
            }}>
              <ChevronRight size={13} style={{ transform: "rotate(180deg)" }} /> Cadastros globais
            </button>

            {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem", margin: 0 }}>{erro}</p>}
            {aviso && <p style={{ color: COR.verde, fontSize: "0.82rem", margin: 0 }}>{aviso}</p>}

            <SeletorAlvoFazendas
              fazendas={fazendas}
              alvoTodas={alvoTodas}
              setAlvoTodas={(v) => { setAlvoTodas(v); setMostrarSeletor(!v); }}
              selecionadas={selecionadas}
              toggleSelecionada={toggleSelecionada}
              mostrarSeletor={mostrarSeletor}
              setMostrarSeletor={setMostrarSeletor}
              cor={COR}
            />

            <div style={{ background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.9rem" }}>
              <p style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: COR.mudo, margin: "0 0 0.7rem" }}>
                Adicionar / garantir nas fazendas-alvo
              </p>
              {ehMetodo && (
                <CampoMobile label="Tipo de serviço" estilos={estilos}>
                  <select value={tipoServicoNome} onChange={(e) => setTipoServicoNome(e.target.value)} style={inputEstilo(estilos)}>
                    <option value="">Selecione…</option>
                    {[...new Set(tiposDisponiveis.map((t) => t.nome))].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </CampoMobile>
              )}
              <CampoMobile label="Nome" estilos={estilos}>
                <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Morte, Girolando, IATF…" style={inputEstilo(estilos)} />
              </CampoMobile>
              {ehGrauSangue && (
                <CampoMobile label="Fração Holandês (0 a 1, opcional)" estilos={estilos}>
                  <input value={fracaoHolandes} onChange={(e) => setFracaoHolandes(e.target.value)} placeholder="ex.: 0.5" style={inputEstilo(estilos)} />
                </CampoMobile>
              )}
              <BotaoMobile estilos={estilos} onClick={aplicar} style={{ marginTop: "0.2rem" }}>
                <Plus size={14} /> Aplicar
              </BotaoMobile>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {carregando && <p style={{ color: COR.mudo, fontSize: "0.82rem" }}>Carregando…</p>}
              {!carregando && linhas.length === 0 && <p style={{ color: COR.mudo, fontSize: "0.82rem" }}>Nada cadastrado ainda nesta categoria.</p>}
              {linhas.map((item) => {
                const key = chaveItem(item);
                const completo = item.total_fazendas > 0 && item.em_fazendas.length === item.total_fazendas;
                const estaRenomeando = renomeando === key;
                const estaConfirmandoDesativar = confirmDesativar === key;
                const fracao = !ehMetodo ? (item as ItemCadastroCowData).fracao_holandes : null;
                return (
                  <div key={key} style={{ background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.8rem 0.9rem" }}>
                    {ehItemMetodo(item, ehMetodo) && (
                      <div style={{ fontSize: "0.68rem", color: COR.mudo, marginBottom: "0.2rem" }}>{item.tipo_nome}</div>
                    )}
                    {estaRenomeando ? (
                      <input autoFocus value={novoNome} onChange={(e) => setNovoNome(e.target.value)}
                        style={inputEstilo(estilos, { marginBottom: "0.5rem" })} />
                    ) : (
                      <div style={{ fontSize: "0.9rem", fontWeight: 700, color: COR.texto, marginBottom: "0.35rem" }}>{item.nome}</div>
                    )}
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "0.3rem", fontSize: "0.74rem", color: completo ? COR.verde : COR.mudo }}>
                      {completo ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                      {item.em_fazendas.length} de {item.total_fazendas} fazendas
                      {ehGrauSangue && fracao != null && <span style={{ color: COR.mudo }}>· fração {fracao}</span>}
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.65rem", flexWrap: "wrap" }}>
                      {estaRenomeando ? (
                        <>
                          <button type="button" onClick={() => confirmarRenomear(item.nome, ehItemMetodo(item, ehMetodo) ? item.tipo_nome : undefined)}
                            style={{ ...estilos.btnGhost, color: COR.verde }}>Salvar</button>
                          <button type="button" onClick={() => { setRenomeando(null); setNovoNome(""); }} style={estilos.btnGhost}>Cancelar</button>
                        </>
                      ) : estaConfirmandoDesativar ? (
                        <>
                          <button type="button" onClick={() => { desativar(item.nome); setConfirmDesativar(null); }}
                            style={{ ...estilos.btnGhost, color: "#fff", background: COR.vermelho, border: `1px solid ${COR.vermelho}` }}>
                            Confirmar desativação
                          </button>
                          <button type="button" onClick={() => setConfirmDesativar(null)} style={estilos.btnGhost}>Cancelar</button>
                        </>
                      ) : (
                        <>
                          <button type="button" onClick={() => { setRenomeando(key); setNovoNome(item.nome); setConfirmDesativar(null); }}
                            title="Renomear" style={{ ...estilos.btnGhost, display: "flex", alignItems: "center", gap: "0.3rem" }}>
                            <Pencil size={13} /> Renomear
                          </button>
                          <button type="button" onClick={() => { setConfirmDesativar(key); setRenomeando(null); }}
                            title="Desativar nas fazendas-alvo" style={{ ...estilos.btnGhost, color: COR.vermelho }}>
                            Desativar
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CorpoMobilePainelCowData>
    </div>
  );
}
