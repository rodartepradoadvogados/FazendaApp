"use client";
import React, { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Plus } from "lucide-react";
import {
  fetchAgenda, fetchLotes, fetchMastiteContexto, fetchMastiteOpcoes, fetchMedicamentos, fetchProtocolosSanitarios,
  lancarProtocoloSanitario, previewCriteriosLote,
} from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
import { EstoquePicker } from "@/components/EstoquePicker";
import { Modal } from "@/components/Modal";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, nota, type EstoqueItem, codigoGrupo } from "@/components/lancamentos/comumForms";
import { CATEGORIAS_ANIMAIS, SelectAnimal, addDias } from "@/components/lancamentos/_shared";
const PainelLancarBst = dynamic(() => import("@/components/PainelLancarBst").then((m) => m.PainelLancarBst), { ssr: false });
const CadastroProtocolosSanitarios = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroProtocolosSanitarios), { ssr: false });

type ProtocoloEtapaLocal = { id?: number; dia: number; criterio_tipo?: string; produto: string; dosagem: number; unidade: string; via?: string | null };
type ProtocoloLocal = { id: number; nome: string; eh_mastite: boolean; ativo: boolean; etapas: ProtocoloEtapaLocal[] };
const TETOS = ["AE", "AD", "PD", "PE"] as const;
const CLASSIFICACOES_MASTITE = [["clinica", "Clínica"], ["subclinica", "Subclínica"], ["ambiental", "Ambiental"]] as const;
// ─────────────────────── BST — seleção nas tabelas (Aptas/Incluir no próximo BST/Inaptas) ───────────────────────
export function BstLancamentoView() {
  const [dados, setDados] = useState<any | null>(null);
  const carregar = () => fetchAgenda().then(setDados).catch(() => setDados(null));
  useEffect(() => { carregar(); }, []);
  return (
    <>
      <p style={nota}>BST (somatotropina bovina) — marque os animais direto nas tabelas e lance (aplicar, agendar ou marcar inapta).</p>
      <PainelLancarBst agenda={dados} onAtualizado={carregar} />
    </>
  );
}

export function FormProtocoloSanitario({ animais, estoque, onSalvo }: { animais: AnimalRow[]; estoque: EstoqueItem[]; onSalvo?: () => void }) {
  const [protocolos, setProtocolos] = useState<ProtocoloLocal[]>([]);
  const [protocoloId, setProtocoloId] = useState("");
  const [matriz, setMatriz] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [observacao, setObservacao] = useState("");
  const [classificacaoMastite, setClassificacaoMastite] = useState("");
  const [grauMastite, setGrauMastite] = useState("");
  const [agente, setAgente] = useState("");
  const [resultadoCmt, setResultadoCmt] = useState("");
  const [tetosSel, setTetosSel] = useState<Set<string>>(new Set());
  const [agentesMastite, setAgentesMastite] = useState<string[]>([]);
  const [ctxMastite, setCtxMastite] = useState<{ del_atual: number | null; ccs_ultima: number | null; cmt_ultimo: string | null } | null>(null);
  // Etapas cadastradas por princípio ativo/classificação: escolher o medicamento agora.
  const [escolhasMed, setEscolhasMed] = useState<Record<number, string>>({});
  const [medOpcoes, setMedOpcoes] = useState<Record<number, { nome: string; quantidade?: number | null; unidade?: string | null }[]>>({});
  // "Incluir itens sem estoque" — mesmo padrão da Inseminação/Sanidade avulsa.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const protocoloSel = protocolos.find((p) => String(p.id) === protocoloId);
  useEffect(() => { if (protocoloSel?.eh_mastite && !agentesMastite.length) fetchMastiteOpcoes().then((o) => setAgentesMastite(o.agentes)).catch(() => {}); }, [protocoloSel?.eh_mastite]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (protocoloSel?.eh_mastite && matriz) { fetchMastiteContexto(matriz).then(setCtxMastite).catch(() => setCtxMastite(null)); }
    else setCtxMastite(null);
  }, [protocoloSel?.eh_mastite, matriz]);

  // Lançamento em massa (protocolos que não são de mastite): animal(is), lote(s) ou categoria de animais.
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "categoria">("animal");
  const [animaisSelecionados, setAnimaisSelecionados] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<Set<string>>(new Set());
  const [lotesTodos, setLotesTodos] = useState<LoteRow[]>([]);
  const [pickerAberto, setPickerAberto] = useState<"lote" | null>(null);
  const abrirPickerLotes = () => {
    if (!lotesTodos.length) fetchLotes().then(setLotesTodos).catch(() => {});
    setPickerAberto("lote");
  };
  const toggleAnimalSelecionado = (numero: string) => setAnimaisSelecionados((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
  const toggleLoteSelecionado = (codigo: string) => setLotesSelecionados((p) => { const n = new Set(p); n.has(codigo) ? n.delete(codigo) : n.add(codigo); return n; });
  const toggleTodosLotes = () => setLotesSelecionados((p) => (p.size === lotesTodos.length ? new Set() : new Set(lotesTodos.map((l) => l.codigo))));
  const pickerColunasAnimais = [
    { header: "Grupo", render: (a: AnimalRow) => a.grupo_primario || "—" },
    { header: "Categoria", render: (a: AnimalRow) => a.categoria_abrev || a.categoria_completa || "—" },
  ];

  const [categoriaId, setCategoriaId] = useState("");
  const [animaisCategoria, setAnimaisCategoria] = useState<string[] | null>(null);
  const [carregandoCategoria, setCarregandoCategoria] = useState(false);
  useEffect(() => {
    if (!categoriaId) { setAnimaisCategoria(null); return; }
    const categoria = CATEGORIAS_ANIMAIS.find((c) => c.id === categoriaId);
    if (!categoria) return;
    setCarregandoCategoria(true);
    previewCriteriosLote({ codigo: "categoria", nome: categoria.label, ...categoria.criterios })
      .then((d) => setAnimaisCategoria(d.animais || []))
      .catch(() => setAnimaisCategoria([]))
      .finally(() => setCarregandoCategoria(false));
  }, [categoriaId]);

  const animaisDoLote = useMemo(
    () => animais.filter((a) => { const cod = codigoGrupo(a.grupo_primario); return cod && lotesSelecionados.has(cod); }).map((a) => a.numero),
    [animais, lotesSelecionados]
  );

  const numerosSelecionados = useMemo(() => {
    if (vinculo === "animal") return Array.from(animaisSelecionados);
    if (vinculo === "lote") return animaisDoLote;
    return animaisCategoria || [];
  }, [vinculo, animaisSelecionados, animaisDoLote, animaisCategoria]);

  const carregarProtocolos = () => fetchProtocolosSanitarios().then((d) => setProtocolos(d.filter((p: ProtocoloLocal) => p.ativo))).catch(() => {});
  useEffect(() => { carregarProtocolos(); }, []);
  const [abrirNovoProtocolo, setAbrirNovoProtocolo] = useState(false);

  const protocolo = protocolos.find((p) => p.id === Number(protocoloId));
  const toggleTeto = (t: string) => setTetosSel((p) => { const s = new Set(p); s.has(t) ? s.delete(t) : s.add(t); return s; });

  // Ao escolher o protocolo, carrega os medicamentos que cumprem o critério de
  // cada etapa cadastrada por princípio ativo/classificação.
  const etapasCriterio = useMemo(
    () => (protocolo?.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") !== "medicamento" && e.id != null),
    [protocolo]
  );
  // Etapas de produto FIXO (cadastrado direto no protocolo, não por critério)
  // — pode faltar o medicamento cadastrado; se estiver zerado/negativo/no
  // mínimo, oferece a opção de escolher um substituto na hora do lançamento.
  const etapasFixas = useMemo(
    () => (protocolo?.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") === "medicamento" && e.id != null),
    [protocolo]
  );
  const estoquePorNome = useMemo(() => new Map(estoque.map((e) => [e.nome, e])), [estoque]);
  const estoqueBaixo = (produto: string) => {
    const item = estoquePorNome.get(produto);
    if (!item) return false;
    const qtd = item.quantidade ?? 0;
    return qtd <= 0 || (item.estoque_minimo != null && qtd < item.estoque_minimo);
  };
  const [substitutosAtivos, setSubstitutosAtivos] = useState<Set<number>>(new Set());
  const [medOpcoesSubstituto, setMedOpcoesSubstituto] = useState<Record<number, { nome: string; quantidade?: number | null; unidade?: string | null }[]>>({});
  const toggleSubstituto = (etapaId: number, produtoOriginal: string) => {
    setSubstitutosAtivos((p) => {
      const n = new Set(p);
      if (n.has(etapaId)) {
        n.delete(etapaId);
        setEscolhasMed((s) => { const c = { ...s }; delete c[etapaId]; return c; });
      } else {
        n.add(etapaId);
        const item = estoquePorNome.get(produtoOriginal);
        const filtro = item?.classificacao_medicamento ? { classificacao: item.classificacao_medicamento }
          : item?.principio_ativo ? { principio_ativo: item.principio_ativo } : {};
        fetchMedicamentos({ ...filtro, incluir_sem_estoque: incluirSemEstoque })
          .then((m) => setMedOpcoesSubstituto((o) => ({ ...o, [etapaId]: m as any[] })))
          .catch(() => setMedOpcoesSubstituto((o) => ({ ...o, [etapaId]: [] })));
      }
      return n;
    });
  };
  useEffect(() => {
    setEscolhasMed({});
    setSubstitutosAtivos(new Set());
    setMedOpcoesSubstituto({});
    if (!protocolo) { setMedOpcoes({}); return; }
    const crit = (protocolo.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") !== "medicamento" && e.id != null);
    if (!crit.length) { setMedOpcoes({}); return; }
    Promise.all(crit.map((e) =>
      fetchMedicamentos({ ...(e.criterio_tipo === "principio_ativo" ? { principio_ativo: e.produto } : e.criterio_tipo === "doenca" ? { doenca: e.produto } : { classificacao: e.produto }), incluir_sem_estoque: incluirSemEstoque })
        .then((m) => [e.id as number, m] as const).catch(() => [e.id as number, [] as any[]] as const)
    )).then((pares) => setMedOpcoes(Object.fromEntries(pares)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [protocoloId, incluirSemEstoque]);

  const cronograma = useMemo(() => {
    if (!protocolo || !dataInicio) return [];
    return [...protocolo.etapas].sort((a, b) => a.dia - b.dia).map((e) => ({
      ...e, data: addDias(dataInicio, e.dia - 1),
    }));
  }, [protocolo, dataInicio]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!protocolo) { setErro("Selecione o protocolo."); return; }
    const numeros = protocolo.eh_mastite ? (matriz ? [matriz] : []) : numerosSelecionados;
    if (!numeros.length) { setErro("Selecione ao menos um animal, lote ou categoria."); return; }
    if (protocolo.eh_mastite && !classificacaoMastite) { setErro("Informe a classificação da mastite (clínica, subclínica ou ambiental)."); return; }
    const faltando = etapasCriterio.find((e) => !escolhasMed[e.id as number]);
    if (faltando) { setErro(`Escolha o medicamento da etapa D${faltando.dia} (${faltando.produto}).`); return; }

    setSalvando(true);
    try {
      const r = await lancarProtocoloSanitario({
        protocolo_id: protocolo.id, numeros_matriz: numeros, data_inicio: dataInicio,
        responsavel: responsavel || undefined, observacao: observacao || undefined,
        classificacao_mastite: classificacaoMastite || undefined,
        grau_mastite: grauMastite ? Number(grauMastite) : undefined, agente: agente || undefined,
        resultado_cmt: resultadoCmt || undefined,
        tetos_afetados: Array.from(tetosSel),
        escolhas_medicamento: Object.fromEntries([
          ...etapasCriterio.map((e) => [String(e.id), escolhasMed[e.id as number]]),
          ...etapasFixas.filter((e) => substitutosAtivos.has(e.id as number) && escolhasMed[e.id as number]).map((e) => [String(e.id), escolhasMed[e.id as number]]),
        ]),
      });
      // `pulados > 0` = o backend achou, animal a animal, um lançamento ativo
      // idêntico (mesmo protocolo/data/matriz) e pulou esse animal em vez de
      // duplicar — duplo clique ou retry da fila offline reenviando os mesmos
      // animais (o aviso do backend já entra em `r.avisos`, ver avisoTxt
      // abaixo). Quando TODOS foram pulados (`r.criados === 0`), a frase
      // principal não pode dizer "lançado para 0 animal(is)" — isso parece
      // defeito (mesmo padrão de FormInducaoLactacao); em vez disso, o aviso
      // já explica sozinho que nada foi duplicado.
      const avisoTxt = (r.avisos && r.avisos.length) ? " ⚠️ " + r.avisos.join(" ") : "";
      setSucesso(r.criados === 0
        ? (r.avisos?.[0] || "Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado.")
        : `Protocolo "${protocolo.nome}" lançado para ${r.criados} animal(is) — ${protocolo.etapas.length} evento(s) na Agenda por animal.${avisoTxt}`);
      setMatriz(""); setObservacao(""); setClassificacaoMastite(""); setGrauMastite(""); setAgente(""); setResultadoCmt(""); setTetosSel(new Set());
      setAnimaisSelecionados(new Set()); setLotesSelecionados(new Set()); setCategoriaId("");
      onSalvo?.();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar protocolo sanitário");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Protocolo">
          <div className="flex items-center gap-2">
            <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
              <option value="">Selecione…</option>
              {protocolos.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.eh_mastite ? " (mastite)" : ""}</option>)}
            </select>
            <button type="button" className="btn-ghost" title="Cadastrar novo protocolo sanitário" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoProtocolo(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
          {abrirNovoProtocolo && (
            <Modal title="Novo protocolo sanitário" onClose={() => { setAbrirNovoProtocolo(false); carregarProtocolos(); }} width="900px">
              <CadastroProtocolosSanitarios />
            </Modal>
          )}
        </Campo>
        <Campo label="Data de início (D1)"><input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></Campo>

        {protocolo?.eh_mastite ? (
          <Campo label="Matriz (nº)" full><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz…" /></Campo>
        ) : (
          <Campo label="Animal(is), lote(s) ou categoria" full>
            <TabBar<"animal" | "lote" | "categoria">
              abas={[
                { id: "animal", label: "Animal(is)", title: "Selecionar animais individualmente" },
                { id: "lote", label: "Lote(s)", title: "Aplicar a todos os animais de um ou mais lotes" },
                { id: "categoria", label: "Categoria de animais", title: "Aplicar a uma categoria pronta (ex.: vacas em lactação, secas)" },
              ]}
              ativa={vinculo}
              onChange={setVinculo}
            />
            {vinculo === "animal" && (
              <AnimalPickerModal animais={animais} selecionados={animaisSelecionados} onToggle={toggleAnimalSelecionado} colunas={pickerColunasAnimais} titulo="Selecionar animal(is)" />
            )}
            {vinculo === "lote" && (
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={abrirPickerLotes}>
                {lotesSelecionados.size ? `${lotesSelecionados.size} lote(s) selecionado(s) (${animaisDoLote.length} animal(is)) — alterar` : "Selecionar lotes…"}
              </button>
            )}
            {vinculo === "categoria" && (
              <div>
                <select style={inputStyle} value={categoriaId} onChange={(e) => setCategoriaId(e.target.value)}>
                  <option value="">Selecione…</option>
                  {CATEGORIAS_ANIMAIS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
                {categoriaId && (
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                    {carregandoCategoria ? "Calculando…" : `${(animaisCategoria || []).length} animal(is) atendem a este critério.`}
                  </p>
                )}
              </div>
            )}
          </Campo>
        )}
      </div>
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {etapasCriterio.length > 0 && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.5rem" }}>Escolha o medicamento de cada etapa (cadastrada por critério)</p>
          <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.75rem", color: "var(--text-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
            Incluir todos os medicamentos/hormônios (inclusive sem estoque)
          </label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {etapasCriterio.map((e) => (
              <div key={e.id}>
                <label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>D{e.dia} — {e.criterio_tipo === "principio_ativo" ? "Princípio ativo" : e.criterio_tipo === "doenca" ? "Doença" : "Classificação"}: <strong>{e.produto}</strong></label>
                <EstoquePicker
                  itens={medOpcoes[e.id as number] || []} value={escolhasMed[e.id as number] || ""}
                  onChange={(nome) => setEscolhasMed((s) => ({ ...s, [e.id as number]: nome }))}
                  placeholder="Selecione o medicamento…"
                />
                {!(medOpcoes[e.id as number] || []).length && <p style={{ fontSize: "0.7rem", color: "var(--amber)" }}>Nenhum medicamento cadastrado com esse critério.</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="" disabled>Selecione…</option>{nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      {protocolo?.eh_mastite && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.6rem" }}>Tratamento diferenciado de mastite</p>
          {ctxMastite && (
            <div className="flex items-center gap-4 mb-2" style={{ flexWrap: "wrap", fontSize: "0.78rem" }}>
              <span>DEL: <strong>{ctxMastite.del_atual != null ? `${ctxMastite.del_atual} dias` : "—"}</strong></span>
              <span>Última CCS: <strong>{ctxMastite.ccs_ultima != null ? `${ctxMastite.ccs_ultima} mil/mL` : "—"}</strong></span>
              <span>Último CMT: <strong>{ctxMastite.cmt_ultimo || "—"}</strong></span>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Campo label="Classificação">
              <select style={inputStyle} value={classificacaoMastite} onChange={(e) => setClassificacaoMastite(e.target.value)}>
                <option value="">Selecione…</option>
                {CLASSIFICACOES_MASTITE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Campo>
            <Campo label="Grau">
              <select style={inputStyle} value={grauMastite} onChange={(e) => setGrauMastite(e.target.value)}>
                <option value="">Selecione…</option>
                <option value="1">Grau 1</option><option value="2">Grau 2</option><option value="3">Grau 3</option>
              </select>
            </Campo>
            <Campo label="Agente (patógeno)">
              <input style={inputStyle} list="agentes-mastite" value={agente} onChange={(e) => setAgente(e.target.value)} placeholder="Selecione ou digite…" />
              <datalist id="agentes-mastite">{agentesMastite.map((a) => <option key={a} value={a} />)}</datalist>
            </Campo>
            <Campo label="Resultado do CMT">
              <select style={inputStyle} value={resultadoCmt} onChange={(e) => setResultadoCmt(e.target.value)}>
                <option value="">Selecione…</option>
                {["-", "+", "++", "+++"].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Campo>
            <Campo label="Teto(s) afetado(s)" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {TETOS.map((t) => (
                  <label key={t} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}>
                    <input type="checkbox" checked={tetosSel.has(t)} onChange={() => toggleTeto(t)} /> {t}
                  </label>
                ))}
              </div>
            </Campo>
          </div>
        </div>
      )}

      {cronograma.length > 0 && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.4rem" }}>Cronograma — vai para a Agenda</p>
          <table className="fazenda-table">
            <thead><tr><th>Dia</th><th>Data</th><th>Produto</th><th>Dosagem</th><th>Via</th></tr></thead>
            <tbody>
              {cronograma.map((e, i) => {
                const fixa = (e.criterio_tipo || "medicamento") === "medicamento" && e.id != null;
                const baixo = fixa && estoqueBaixo(e.produto);
                return (
                  <tr key={i}>
                    <td>D{e.dia}</td>
                    <td>{e.data}</td>
                    <td>
                      {e.produto}
                      {baixo && (
                        <div style={{ marginTop: "0.3rem" }}>
                          <p style={{ fontSize: "0.7rem", color: "var(--amber)", margin: 0 }}>⚠ Estoque zerado, negativo ou no mínimo.</p>
                          <label className="flex items-center gap-2" style={{ fontSize: "0.72rem", color: "var(--text-muted)", cursor: "pointer" }}>
                            <input type="checkbox" checked={substitutosAtivos.has(e.id as number)} onChange={() => toggleSubstituto(e.id as number, e.produto)} />
                            Selecionar medicamento substituto
                          </label>
                          {substitutosAtivos.has(e.id as number) && (
                            <div style={{ marginTop: "0.25rem" }}>
                              <EstoquePicker
                                itens={medOpcoesSubstituto[e.id as number] || []} value={escolhasMed[e.id as number] || ""}
                                onChange={(nome) => setEscolhasMed((s) => ({ ...s, [e.id as number]: nome }))}
                                placeholder="Selecione o substituto…"
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td>{e.dosagem} {e.unidade}</td>
                    <td>{e.via || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={nota}>Ao salvar, cria um evento na Agenda por dia — marcar "realizado" dá baixa automática do produto no Estoque.</p>
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar protocolo"}
        </button>
      </div>
      </div>
      </div>

      {pickerAberto === "lote" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 55, padding: "1rem" }}>
          <div className="card" style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="card-header mb-3">Selecionar lote(s)</div>
            <SelecaoLotesTabela lotes={lotesTodos} selecionados={lotesSelecionados} toggle={toggleLoteSelecionado} toggleTodos={toggleTodosLotes} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setPickerAberto(null)} className="btn-primary">OK</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

